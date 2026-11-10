"""
iphone_dock_server.py — Servidor do HUD (Stark WebApp) para o iPhone 11 no dock.

Resumo das mudanças desta versão:
  * Fila de áudio por fala (/api/audio/<id>.mp3) em vez de um único buffer "latest" que era
    sobrescrito; o HUD toca em ordem, confirma cada id e o servidor mantém só um histórico curto.
  * SSE (/api/events): o HUD recebe estado/falas por push; o polling de 900 ms (um handshake TLS
    por requisição) virou fallback lento.
  * Autenticação por token pré-compartilhado (header, Bearer ou cookie HttpOnly+SameSite=Strict
    definido ao abrir /?token=...), comparação em tempo constante, limite de tentativas por IP,
    checagem de Origin em POST, limite de tamanho de corpo e timeouts de socket.
  * HTTPS: o handshake TLS acontece na thread da conexão (antes, no accept() do servidor, um
    cliente que conectasse e não completasse o handshake congelava TODO o servidor HTTPS).
  * HTTP simples é opt-in (DOCK_ENABLE_HTTP=1): o iOS só libera microfone/câmera em HTTPS, e o
    token trafegaria em texto puro.
  * /api/voice e /api/command respondem sem segurar a requisição durante a chamada ao Gemini.
  * Ações lentas (IoT, braço) têm prazo e erro amigável.
"""

import os
import io
import re
import ssl
import sys
import json
import time
import hmac
import socket
import hashlib
import secrets
import datetime
import threading
import subprocess
from collections import OrderedDict
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv

from env_utils import ENV_PATH, atualizar_env

load_dotenv(ENV_PATH)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_JSON = 64 * 1024
MAX_FRAME = 3 * 1024 * 1024
MAX_WAV = 4 * 1024 * 1024


def obter_ip_local() -> str:
    """IP da interface de saída (sem enviar tráfego: UDP connect só escolhe a rota)."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if s:
            s.close()


def obter_ip_tailscale() -> str:
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2)
        return r.stdout.split()[0] if r.returncode == 0 and r.stdout.strip() else ""
    except Exception:
        return ""


# ----------------------------------------------------------------------------- autenticação
def _carregar_token() -> tuple:
    """Retorna (token, recem_gerado). Se não houver JARVIS_DOCK_TOKEN no .env, gera um e persiste."""
    token = os.getenv("JARVIS_DOCK_TOKEN", "").strip()
    if token:
        return token, False
    token = secrets.token_urlsafe(24)
    atualizar_env("JARVIS_DOCK_TOKEN", token)
    return token, True


DOCK_TOKEN, _TOKEN_NOVO = _carregar_token()
_COOKIE_VALOR = hmac.new(DOCK_TOKEN.encode(), b"jarvis-dock-cookie", hashlib.sha256).hexdigest()
_COOKIE_NOME = "jarvis_auth"
_falhas = {}                      # ip -> [timestamps]
_falhas_lock = threading.Lock()


def _gerar_cookie_sessao(duracao_segundos: int = 7 * 86400) -> str:
    """Gera um token de sessão assinado com timestamp de expiração (Pendência 4 / Ephemeral Key)."""
    exp = int(time.time() + duracao_segundos)
    assinatura = hmac.new(DOCK_TOKEN.encode(), f"dock-session:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{assinatura}"


def _validar_cookie_sessao(valor: str) -> bool:
    """Valida se o cookie de sessão é autêntico e ainda não expirou."""
    if not valor:
        return False
    if _igual(valor, _COOKIE_VALOR):  # compatibilidade com cookie legado
        return True
    if "." not in valor:
        return False
    partes = valor.split(".", 1)
    if len(partes) != 2:
        return False
    try:
        exp = int(partes[0])
    except ValueError:
        return False
    if time.time() > exp:
        return False  # expirado
    esperado = hmac.new(DOCK_TOKEN.encode(), f"dock-session:{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(partes[1], esperado)


def _bloqueado(ip: str) -> bool:
    agora = time.time()
    with _falhas_lock:
        recentes = [t for t in _falhas.get(ip, []) if agora - t < 60]
        _falhas[ip] = recentes
        return len(recentes) >= 10


def _registrar_falha(ip: str):
    with _falhas_lock:
        _falhas.setdefault(ip, []).append(time.time())
        if len(_falhas) > 256:  # evita crescimento ilimitado
            for k in list(_falhas)[:128]:
                _falhas.pop(k, None)


def _igual(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8", "ignore"), b.encode("utf-8", "ignore"))


def _eh_ip_privado_ou_local(ip: str) -> bool:
    """Retorna True se o IP for loopback, rede local privada (RFC 1918) ou CGNAT/Tailscale (100.64.0.0/10)."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return True
    try:
        import ipaddress
        addr = ipaddress.ip_address(ip)
        if addr.is_loopback or addr.is_private or addr.is_link_local:
            return True
        tailscale_net = ipaddress.ip_network("100.64.0.0/10")
        if addr in tailscale_net:
            return True
    except Exception:
        pass
    return False


# ----------------------------------------------------------------------------- estado
class _Assinante:
    def __init__(self):
        self.evento = threading.Event()
        self.sujo = True
        self.parar = False


class DockState:
    """Estado sincronizado entre o cérebro do J.A.R.V.I.S. e o iPhone (thread-safe)."""
    MAX_FALAS = 12
    MAX_BYTES = 6 * 1024 * 1024
    EXPIRA_PENDENTE = 90.0

    def __init__(self):
        self._lock = threading.Lock()
        self.hud_title = "J.A.R.V.I.S."
        self.hud_subtitle = "Mordomo & Engenheiro Stark"
        self.hud_icon = "🎩"
        self.face_expression = "NEUTRO"
        self.last_response = "Sistemas prontos no Dock, senhor. Toque no Reator para falar."
        self.camera_streaming = False
        self._ultimo_frame_ts = 0.0
        self._sintetizando = 0
        self._falas = OrderedDict()      # id -> {"audio": bytes, "texto": str, "ts": float}
        self._pendentes = []             # ids publicados e ainda não confirmados pelo HUD
        self._seq = 0
        self._subs = []
        # Telemetria e Proteção Inteligente de Bateria (Ciclo 20%-80%)
        self.battery_level = None
        self.battery_charging = None
        self.battery_last_check = 0.0
        self._ultimo_chaveamento_bateria = 0.0

    # ---- assinantes SSE
    def inscrever(self):
        s = _Assinante()
        with self._lock:
            self._subs.append(s)
        return s

    def desinscrever(self, s):
        with self._lock:
            if s in self._subs:
                self._subs.remove(s)

    def n_assinantes(self) -> int:
        with self._lock:
            return len(self._subs)

    def notificar(self):
        with self._lock:
            subs = list(self._subs)
        for s in subs:
            s.sujo = True
            s.evento.set()

    # ---- HUD / OLED
    def atualizar_hud(self, titulo: str, subtitulo: str, icone: str = "🤖"):
        with self._lock:
            self.hud_title, self.hud_subtitle, self.hud_icon = titulo, subtitulo, icone
        self.notificar()

    def atualizar_face(self, expressao: str):
        with self._lock:
            self.face_expression = expressao.upper().strip()
        self.notificar()

    def registrar_frame_camera(self):
        agora = time.monotonic()
        mudou = False
        with self._lock:
            self._ultimo_frame_ts = agora
            if not self.camera_streaming:
                self.camera_streaming = True
                mudou = True
        if mudou:
            self.notificar()

    # ---- fala / áudio
    def definir_resposta(self, texto: str):
        with self._lock:
            self.last_response = texto
            self._sintetizando += 1
        self.notificar()

    def fim_da_resposta(self):
        with self._lock:
            self._sintetizando = max(0, self._sintetizando - 1)
        self.notificar()

    def publicar_audio(self, audio_bytes: bytes, texto: str = "") -> int:
        with self._lock:
            self._seq += 1
            fid = self._seq
            self._falas[fid] = {"audio": audio_bytes, "texto": texto, "ts": time.time()}
            self._pendentes.append(fid)
            total = sum(len(f["audio"]) for f in self._falas.values())
            while len(self._falas) > self.MAX_FALAS or total > self.MAX_BYTES:
                antigo, f = self._falas.popitem(last=False)
                total -= len(f["audio"])
                if antigo in self._pendentes:
                    self._pendentes.remove(antigo)
        self.notificar()
        return fid

    def publicar_fala(self, texto: str, audio_bytes: bytes = b""):  # compatibilidade
        self.definir_resposta(texto)
        if audio_bytes:
            self.publicar_audio(audio_bytes, texto)
        self.fim_da_resposta()

    def marcar_tocada(self, fid):
        with self._lock:
            if fid in self._pendentes:
                self._pendentes.remove(fid)
        self.notificar()

    def limpar_audio(self):
        """Barge-in: descarta fila e manda o HUD parar."""
        with self._lock:
            self._pendentes.clear()
            self._sintetizando = 0
            subs = list(self._subs)
        for s in subs:
            s.parar = True
            s.evento.set()
        self.notificar()

    def obter_audio(self, fid):
        with self._lock:
            f = self._falas.get(fid)
            return f["audio"] if f else None

    def ultimo_audio(self):
        with self._lock:
            return next(reversed(self._falas.values()))["audio"] if self._falas else None

    # ---- snapshot
    def obter_snapshot(self) -> dict:
        try:
            from iot_service import iot_service
            dispositivos = dict(iot_service.dispositivos)   # cópia: o dict é mutado por outras threads
        except Exception:
            dispositivos = {}
        try:
            from persona_manager import persona_manager
            persona = persona_manager.obter_persona()
        except Exception:
            persona = {"id": "JARVIS", "nome": "J.A.R.V.I.S.", "titulo": "Mordomo & Engenheiro Stark", "icone": "🎩"}
        agora = time.time()
        with self._lock:
            # pendentes que o HUD nunca confirmou (aba fechada) expiram e não prendem "speaking"
            self._pendentes = [i for i in self._pendentes if i in self._falas and agora - self._falas[i]["ts"] < self.EXPIRA_PENDENTE]
            # Timeout de presença da câmera: se passar mais de 10 s sem frame novo, volta a False (F16)
            if self.camera_streaming and (time.monotonic() - getattr(self, "_ultimo_frame_ts", 0) > 10.0):
                self.camera_streaming = False

            return {
                "hud": {
                    "title": self.hud_title, "subtitle": self.hud_subtitle, "icon": self.hud_icon,
                    "face": self.face_expression, "last_response": self.last_response,
                    "speaking": bool(self._pendentes) or (self._sintetizando > 0),
                    "pending_audio": list(self._pendentes), "audio_seq": self._seq,
                    "battery": {
                        "level": self.battery_level,
                        "charging": self.battery_charging,
                    },
                },
                "persona": {
                    "id": persona.get("id", "JARVIS"), "nome": persona.get("nome", "J.A.R.V.I.S."),
                    "titulo": persona.get("titulo", "Mordomo & Engenheiro Stark"), "icone": persona.get("icone", "🎩"),
                },
                "iot": dispositivos,
                "camera": self.camera_streaming,
                "time": datetime.datetime.now().strftime("%H:%M"),
            }


dock_state = DockState()


# ----------------------------------------------------------------------------- TLS
def gerar_certificado_https_local(cert_path: str, key_path: str, sans_ip: list, sans_dns: list) -> bool:
    """Gera certificado autoassinado (se não existir). Prefira `tailscale cert` (confiável no Safari sem perfil)."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return True
    try:
        import ipaddress
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "J.A.R.V.I.S. Dock"),
                          x509.NameAttribute(NameOID.COMMON_NAME, sans_dns[0] if sans_dns else "jarvis-dock")])
        san = [x509.DNSName(d) for d in dict.fromkeys(sans_dns)]
        for ip in dict.fromkeys(sans_ip):
            try:
                san.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except ValueError:
                pass
        agora = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(agora - datetime.timedelta(days=1))
                .not_valid_after(agora + datetime.timedelta(days=825))   # limite aceito pelo iOS para certificados locais
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(key, hashes.SHA256()))
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # chave privada só para o dono
        with os.fdopen(fd, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        return True
    except Exception as e:
        print(f"⚠️ [STARK DOCK] Não foi possível gerar o certificado HTTPS ({e}). Instale 'cryptography' ou use DOCK_CERT/DOCK_KEY.")
        return False


def localizar_certificados_tailscale() -> tuple:
    """
    Procura automaticamente certificados emitidos pelo Tailscale (*.ts.net.crt e *.ts.net.key).
    Retorna (cert_path, key_path, fqdn) se encontrar, ou (None, None, None).
    """
    locais_busca = [
        BASE_DIR,
        os.path.abspath(os.path.join(BASE_DIR, "..")),
        "/var/lib/tailscale/certs",
        "/etc/ssl/tailscale",
        "/etc/tailscale"
    ]
    for pasta in locais_busca:
        if not os.path.isdir(pasta):
            continue
        try:
            arquivos = os.listdir(pasta)
            crts = [f for f in arquivos if f.endswith(".crt") and (".ts.net" in f or "tailscale" in f or "barros-server" in f)]
            for crt in crts:
                base_nome = crt[:-4]
                key_candidatas = [f"{base_nome}.key", f"{base_nome}.pem"]
                for kc in key_candidatas:
                    key_path = os.path.join(pasta, kc)
                    cert_path = os.path.join(pasta, crt)
                    if os.path.exists(key_path):
                        fqdn = base_nome if ".ts.net" in base_nome else ""
                        return cert_path, key_path, fqdn
        except Exception:
            continue
    return None, None, None



HTML_STARK_HUD = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="J.A.R.V.I.S.">
<title>J.A.R.V.I.S. — Stark Dock OS</title>
<style>
  :root {
    --theme: #00f0ff;
    --theme-glow: rgba(0, 240, 255, 0.45);
    --theme-dim: rgba(0, 240, 255, 0.16);
    --ok: #00ff9d;
    --ok-glow: rgba(0, 255, 157, 0.4);
    --warn: #ffaa00;
    --bg-base: #030712;
    --panel-bg: rgba(7, 16, 32, 0.78);
    --panel-border: rgba(0, 240, 255, 0.22);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; user-select: none; margin: 0; padding: 0; }
  
  body {
    background-color: var(--bg-base);
    background-image: 
      radial-gradient(circle at 75% 50%, var(--theme-dim) 0%, transparent 65%),
      radial-gradient(circle at 20% 80%, rgba(0, 50, 100, 0.18) 0%, transparent 50%),
      radial-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px);
    background-size: 100% 100%, 100% 100%, 20px 20px;
    color: #eafaff;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
    padding: env(safe-area-inset-top, 8px) env(safe-area-inset-right, 14px) env(safe-area-inset-bottom, 8px) env(safe-area-inset-left, 14px);
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: background 0.4s ease;
  }

  /* BARRA SUPERIOR DE TELEMETRIA HUD */
  .hud-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 14px;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 14px;
    backdrop-filter: blur(20px) saturate(190%);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.55);
    flex-shrink: 0;
  }
  .hud-brand {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .brand-radar {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--ok);
    box-shadow: 0 0 10px var(--ok), 0 0 18px var(--ok);
    animation: radarBlink 1.8s ease-in-out infinite alternate;
  }
  @keyframes radarBlink {
    0% { opacity: 0.35; transform: scale(0.85); }
    100% { opacity: 1; transform: scale(1.15); }
  }
  .brand-name {
    font-size: 0.76rem;
    font-weight: 800;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    color: #ffffff;
    text-shadow: 0 0 10px var(--theme-glow);
  }
  .brand-sub {
    font-size: 0.65rem;
    opacity: 0.65;
    letter-spacing: 1.2px;
    font-weight: 600;
    color: var(--theme);
  }
  .hud-telemetry {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .status-pill {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #a8d5e5;
    border-radius: 9px;
    padding: 4px 8px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .status-pill:active {
    transform: scale(0.95);
  }
  .status-pill.active {
    border-color: var(--ok);
    color: #ffffff;
    background: rgba(0, 255, 157, 0.16);
    box-shadow: 0 0 12px var(--ok-glow);
  }
  .icon-btn {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #fff;
    border-radius: 9px;
    padding: 4px 9px;
    font-size: 0.70rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .icon-btn:active {
    transform: scale(0.95);
  }
  .icon-btn.active {
    border-color: var(--ok);
    color: var(--ok);
    background: rgba(0, 255, 157, 0.14);
    box-shadow: 0 0 10px var(--ok-glow);
  }

  /* WORKSPACE PRINCIPAL (GRID 2 COLUNAS DE CONTROLES | 1 COLUNA DE REATOR ARC) */
  .dock-workspace {
    display: grid;
    grid-template-columns: 1.05fr 0.95fr;
    gap: 12px;
    flex: 1;
    height: 100%;
    min-height: 0;
    align-items: stretch;
  }
  .dock-workspace > .right-panel { order: 1; }
  .dock-workspace > .left-panel { order: 2; }

  @media (max-width: 580px) {
    .dock-workspace {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
    }
  }

  /* PAINEL ESQUERDO: 2 COLUNAS SIMÉTRICAS DE 4 BOTÕES CADA */
  .left-panel {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    height: 100%;
    min-height: 0;
  }
  .column-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    padding: 10px 10px 8px 10px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 7px;
    backdrop-filter: blur(20px) saturate(190%);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    position: relative;
    overflow: hidden;
  }
  .col-header {
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    color: var(--theme);
    padding-bottom: 5px;
    border-bottom: 1px solid var(--theme-dim);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .btn-stack {
    display: flex;
    flex-direction: column;
    gap: 7px;
    flex: 1;
    justify-content: space-between;
    min-height: 0;
  }

  /* BOTÕES GLASSMORFICOS HIGH-TECH */
  .ctrl-btn {
    flex: 1;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    color: #eafaff;
    padding: 6px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: pointer;
    transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
    position: relative;
    overflow: hidden;
    backdrop-filter: blur(12px);
    text-align: left;
  }
  .ctrl-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 100%);
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  .ctrl-btn:active {
    transform: scale(0.965);
    border-color: var(--theme);
  }
  .ctrl-btn:active::before {
    opacity: 1;
  }
  .ctrl-btn.on {
    background: rgba(0, 255, 157, 0.14);
    border-color: var(--ok);
    color: #ffffff;
    box-shadow: 0 0 16px rgba(0, 255, 157, 0.22), inset 0 0 10px rgba(0, 255, 157, 0.10);
  }
  .ctrl-left {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .ctrl-icon {
    font-size: 1.25rem;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
    transition: all 0.2s ease;
  }
  .ctrl-btn.on .ctrl-icon {
    background: rgba(0, 255, 157, 0.2);
    border-color: var(--ok);
  }
  .ctrl-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .ctrl-name {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ctrl-state {
    font-size: 0.62rem;
    opacity: 0.68;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    font-weight: 600;
  }
  .status-led {
    width: 6.5px;
    height: 6.5px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.2);
    flex-shrink: 0;
    transition: all 0.25s ease;
  }
  .ctrl-btn.on .status-led {
    background: var(--ok);
    box-shadow: 0 0 10px var(--ok), 0 0 16px var(--ok);
  }

  /* PAINEL DIREITO: REATOR ARC MARK 85 COM SOUNDWAVE EQUALIZER */
  .right-panel {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
    backdrop-filter: blur(20px) saturate(190%);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  }
  .right-top {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .persona-badge {
    padding: 3px 10px;
    border-radius: 16px;
    border: 1px solid var(--theme);
    background: var(--theme-dim);
    font-weight: 800;
    letter-spacing: 1.2px;
    font-size: 0.68rem;
    color: #fff;
    box-shadow: 0 0 12px var(--theme-glow);
  }
  .clock-badge {
    font-family: "SF Mono", Menlo, monospace;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--theme);
  }

  /* REATOR ARC CENTRAL COM ANÉIS TELEMÉTRICOS CONCÊNTRICOS */
  .reactor-stage {
    position: relative;
    width: 172px;
    height: 172px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    margin: 2px 0;
  }
  .ring-ticks {
    position: absolute;
    inset: -6px;
    border-radius: 50%;
    border: 1px dashed var(--theme);
    opacity: 0.35;
    animation: spinClockwise 32s linear infinite;
  }
  .ring-outer {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 2px dashed var(--theme);
    box-shadow: 0 0 25px var(--theme-glow), inset 0 0 18px var(--theme-glow);
    animation: spinClockwise 16s linear infinite;
  }
  .ring-mid {
    position: absolute;
    inset: 12px;
    border-radius: 50%;
    border: 1.5px solid var(--theme);
    opacity: 0.6;
    border-top-color: transparent;
    border-bottom-color: transparent;
    animation: spinCounter 8s linear infinite;
  }
  .arc-core {
    width: 114px;
    height: 114px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255,255,255,0.25) 0%, var(--theme-dim) 58%, rgba(0,0,0,0.92) 100%);
    border: 2px solid var(--theme);
    box-shadow: 0 0 26px var(--theme-glow);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 2;
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
  }
  .speaking .arc-core {
    animation: speakPulse 0.32s ease-in-out infinite alternate;
    box-shadow: 0 0 50px var(--theme), 0 0 90px var(--theme);
  }
  .listening .arc-core {
    box-shadow: 0 0 50px var(--warn), inset 0 0 25px var(--warn);
    border-color: var(--warn);
  }
  .avatar-svg-wrap {
    width: 60px;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .avatar-svg-wrap svg {
    width: 100%;
    height: 100%;
    filter: drop-shadow(0 0 8px var(--theme));
  }

  @keyframes spinClockwise { 100% { transform: rotate(360deg); } }
  @keyframes spinCounter { 100% { transform: rotate(-360deg); } }
  @keyframes speakPulse { 0% { transform: scale(0.95); } 100% { transform: scale(1.10); } }

  /* SOUNDWAVE EQUALIZER HOLOGRÁFICO */
  .soundwave-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3.5px;
    height: 18px;
    margin: 1px 0 3px 0;
  }
  .sw-bar {
    width: 3px;
    height: 4px;
    border-radius: 2px;
    background: var(--theme);
    box-shadow: 0 0 6px var(--theme-glow);
    transition: height 0.15s ease, background-color 0.3s ease;
    opacity: 0.35;
  }
  .speaking .sw-bar {
    opacity: 1;
    animation: wavePulse 0.45s ease-in-out infinite alternate;
  }
  .listening .sw-bar {
    opacity: 1;
    background: var(--warn);
    box-shadow: 0 0 8px var(--warn);
    animation: wavePulse 0.32s ease-in-out infinite alternate;
  }
  .sw-bar:nth-child(2n) { animation-delay: 0.08s; }
  .sw-bar:nth-child(3n) { animation-delay: 0.18s; }
  .sw-bar:nth-child(4n) { animation-delay: 0.28s; }
  .sw-bar:nth-child(5n) { animation-delay: 0.12s; }

  @keyframes wavePulse {
    0% { height: 4px; }
    50% { height: 18px; }
    100% { height: 7px; }
  }

  /* CONSOLE HOLOGRÁFICO DE DIÁLOGO E RESPOSTA */
  .persona-footer {
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .persona-name {
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: 2px;
    color: #ffffff;
    text-shadow: 0 0 10px var(--theme-glow);
  }
  .dialogue-console {
    background: rgba(0, 0, 0, 0.45);
    border: 1px solid var(--theme-dim);
    border-radius: 10px;
    padding: 5px 10px;
    min-height: 40px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    box-shadow: inset 0 0 12px rgba(0, 0, 0, 0.6);
  }
  .dialogue-tag {
    font-size: 0.58rem;
    font-weight: 800;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--theme);
    opacity: 0.75;
  }
  .dialogue-text {
    font-size: 0.72rem;
    line-height: 1.25;
    color: #e6f7ff;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  /* SELETOR RÁPIDO DE PERSONALIDADE (CHIPS HOLOGRÁFICOS) */
  .persona-bar {
    display: flex;
    gap: 4px;
    justify-content: center;
    flex-wrap: wrap;
    margin-top: 2px;
  }
  .p-chip {
    font-size: 0.62rem;
    padding: 3px 6px;
    border-radius: 7px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    color: #b0d8ea;
    cursor: pointer;
    transition: all 0.18s ease;
  }
  .p-chip:active {
    transform: scale(0.95);
  }
  .p-chip.active {
    border-color: var(--theme);
    background: var(--theme-dim);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 0 8px var(--theme-glow);
  }
</style>
</head>
<body>

  <!-- BARRA SUPERIOR DE TELEMETRIA HUD -->
  <header class="hud-header">
    <div class="hud-brand">
      <span class="brand-radar"></span>
      <span class="brand-name">STARK HUD <span class="brand-sub">// OS 4.2</span></span>
    </div>
    <div class="hud-telemetry">
      <button class="status-pill" id="wakeLockPill" onclick="solicitarWakeLock()" title="Manter tela do iPhone 11 sempre ativa no Dock">☀️ WAKE</button>
      <button class="status-pill" id="batteryPill" title="Monitoramento e Proteção Inteligente da Bateria">🔋 --%</button>
      <button class="icon-btn" id="btnCamToggle" onclick="alternarCamera3D()" title="Ativar/Desativar Webcam Impressora 3D">📷 Cam 3D</button>
      <button class="icon-btn" id="btnAudioUnlock" onclick="ativarAudio()">🔊 Som</button>
    </div>
  </header>

  <div class="dock-workspace">

    <!-- PAINEL ESQUERDO: 2 COLUNAS (COLUNA 1: IoT | COLUNA 2: BRAÇO ROBÓTICO) -->
    <div class="left-panel">

      <!-- COLUNA 1: CONTROLE IoT (4 Dispositivos com Carregador Dock) -->
      <div class="column-card">
        <div class="col-header">
          <span>⚡ AUTOMAÇÃO IoT</span>
          <span id="clockTxt">--:--</span>
        </div>

        <div class="btn-stack" id="iotStack">
          <button class="ctrl-btn" id="btn_tomada_impressora" onclick="alternarIoT('tomada_impressora')">
            <div class="ctrl-left">
              <div class="ctrl-icon">🖨️</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Impressora 3D</div>
                <div class="ctrl-state" id="st_tomada_impressora">DESLIGADO</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" id="btn_dimmer_quarto" onclick="alternarIoT('dimmer_quarto')">
            <div class="ctrl-left">
              <div class="ctrl-icon">🌙</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Dimmer Quarto</div>
                <div class="ctrl-state" id="st_dimmer_quarto">DESLIGADO</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" id="btn_luz_estudo" onclick="alternarIoT('luz_estudo')">
            <div class="ctrl-left">
              <div class="ctrl-icon">💡</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Luz de Estudo</div>
                <div class="ctrl-state" id="st_luz_estudo">DESLIGADO</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" id="btn_tomada_dock" onclick="alternarIoT('tomada_dock')">
            <div class="ctrl-left">
              <div class="ctrl-icon">⚡</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Carregador Dock</div>
                <div class="ctrl-state" id="st_tomada_dock">LIGADO</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>
        </div>
      </div>

      <!-- COLUNA 2: BRAÇO ROBÓTICO 4-DOF (4 GESTOS) -->
      <div class="column-card">
        <div class="col-header">
          <span>🦾 BRAÇO ROBÓTICO</span>
          <span id="oledFaceTxt">OLED: NEUTRO</span>
        </div>

        <div class="btn-stack">
          <button class="ctrl-btn" onclick="moverBraco('acenar')">
            <div class="ctrl-left">
              <div class="ctrl-icon">👋</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Acenar</div>
                <div class="ctrl-state">Saudação</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" onclick="moverBraco('apontar')">
            <div class="ctrl-left">
              <div class="ctrl-icon">👉</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Apontar</div>
                <div class="ctrl-state">Foco / Alvo</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" id="btn_garra" onclick="alternarGarra()">
            <div class="ctrl-left">
              <div class="ctrl-icon" id="ic_garra">✊</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Garra</div>
                <div class="ctrl-state" id="st_garra">Alternar Abertura</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>

          <button class="ctrl-btn" onclick="moverBraco('repouso')">
            <div class="ctrl-left">
              <div class="ctrl-icon">💤</div>
              <div class="ctrl-info">
                <div class="ctrl-name">Repouso</div>
                <div class="ctrl-state">Recolher Servos</div>
              </div>
            </div>
            <div class="status-led"></div>
          </button>
        </div>
      </div>

    </div>

    <!-- PAINEL DIREITO: REATOR ARC MARK 85 COM EQUALIZER & DIÁLOGO HOLOGRÁFICO -->
    <div class="right-panel" id="reactorPanel">

      <div class="right-top">
        <span class="persona-badge" id="personaBadge">🎩 J.A.R.V.I.S.</span>
        <span class="clock-badge" id="clockSecTxt">ONLINE</span>
      </div>

      <!-- REATOR ARC CENTRAL COM AVATAR DINÂMICO -->
      <div class="reactor-stage" onclick="alternarEscutaVoz()" title="Toque no Reator para falar com o assistente">
        <div class="ring-ticks"></div>
        <div class="ring-outer"></div>
        <div class="ring-mid"></div>
        <div class="arc-core">
          <div class="avatar-svg-wrap" id="avatarContainer"></div>
        </div>
      </div>

      <!-- EQUALIZER SOUNDWAVE HOLOGRÁFICO -->
      <div class="soundwave-wrap" id="soundwaveWrap">
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
        <span class="sw-bar"></span>
      </div>

      <!-- NOME DA PERSONA + CONSOLE HOLOGRÁFICO + SELETOR DE PERSONA -->
      <div class="persona-footer">
        <div class="persona-name" id="personaName">J.A.R.V.I.S.</div>
        
        <div class="dialogue-console">
          <div class="dialogue-tag" id="dialogueTag">// COMANDO_DE_VOZ: PRONTO</div>
          <div class="dialogue-text" id="personaSubtitle">Toque no Reator Arc para falar</div>
        </div>

        <div class="persona-bar">
          <span class="p-chip active" id="chip_JARVIS" onclick="mudarPersona('JARVIS')">JARVIS</span>
          <span class="p-chip" id="chip_FRIDAY" onclick="mudarPersona('FRIDAY')">FRIDAY</span>
          <span class="p-chip" id="chip_GIDEON" onclick="mudarPersona('GIDEON')">GIDEON</span>
          <span class="p-chip" id="chip_TARS" onclick="mudarPersona('TARS')">TARS</span>
          <span class="p-chip" id="chip_HAL9000" onclick="mudarPersona('HAL9000')">HAL 9000</span>
          <span class="p-chip" id="chip_C3PO" onclick="mudarPersona('C3PO')">C-3PO</span>
          <span class="p-chip" id="chip_R2D2" onclick="mudarPersona('R2D2')">R2-D2</span>
        </div>
      </div>

    </div>

  </div>

  <!-- Elementos invisíveis para streaming silencioso da câmera 3D caso ativada -->
  <video id="hiddenVideo" playsinline autoplay muted style="display:none;"></video>
  <canvas id="hiddenCanvas" width="640" height="360" style="display:none;"></canvas>

<script>
  // Injeção de credencial pré-compartilhada para autenticação fluida de chamadas REST
  const DOCK_TOKEN = "__STARK_DOCK_TOKEN__";
  const _origFetch = window.fetch;
  window.fetch = function(url, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (DOCK_TOKEN && !DOCK_TOKEN.startsWith('__')) {
      if (opts.headers instanceof Headers) {
        if (!opts.headers.has('X-Jarvis-Token')) opts.headers.set('X-Jarvis-Token', DOCK_TOKEN);
      } else {
        if (!opts.headers['X-Jarvis-Token']) opts.headers['X-Jarvis-Token'] = DOCK_TOKEN;
      }
    }
    opts.credentials = opts.credentials || 'same-origin';
    return _origFetch.call(this, url, opts);
  };

  // Temas de cores e Avatares SVG de Alta Definição para cada Personalidade!
  const PERSONA_THEMES = {
    JARVIS: {
      color: "#00f0ff",
      glow: "rgba(0, 240, 255, 0.45)",
      dim: "rgba(0, 240, 255, 0.16)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#00f0ff" stroke-width="3.5">
              <circle cx="50" cy="50" r="40" stroke-dasharray="14 6" opacity="0.8"/>
              <circle cx="50" cy="50" r="32" stroke-dasharray="6 4" opacity="0.5"/>
              <polygon points="50,20 76,66 24,66" stroke-width="3" fill="rgba(0,240,255,0.18)"/>
              <circle cx="50" cy="51" r="10" fill="#ffffff" filter="drop-shadow(0 0 6px #00f0ff)"/>
              <line x1="50" y1="8" x2="50" y2="16" stroke="#00f0ff" stroke-width="3"/>
              <line x1="50" y1="84" x2="50" y2="92" stroke="#00f0ff" stroke-width="3"/>
            </svg>`
    },
    FRIDAY: {
      color: "#ff7b00",
      glow: "rgba(255, 123, 0, 0.45)",
      dim: "rgba(255, 123, 0, 0.18)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#ff7b00" stroke-width="4">
              <polygon points="50,10 88,30 88,70 50,90 12,70 12,30" fill="rgba(255,123,0,0.15)"/>
              <path d="M28 45 L45 52 L28 58 M72 45 L55 52 L72 58" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
              <circle cx="50" cy="52" r="7" fill="#ff7b00"/>
            </svg>`
    },
    GIDEON: {
      color: "#ffd000",
      glow: "rgba(255, 208, 0, 0.45)",
      dim: "rgba(255, 208, 0, 0.18)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#ffd000" stroke-width="3.5">
              <ellipse cx="50" cy="30" rx="26" ry="8"/>
              <path d="M24 30 L50 54 L76 30" fill="rgba(255,208,0,0.2)"/>
              <path d="M32 72 L50 54 L68 72" fill="rgba(255,208,0,0.35)"/>
              <ellipse cx="50" cy="72" rx="22" ry="6"/>
              <circle cx="50" cy="50" r="5" fill="#fff"/>
            </svg>`
    },
    TARS: {
      color: "#00ff88",
      glow: "rgba(0, 255, 136, 0.40)",
      dim: "rgba(0, 255, 136, 0.16)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#00ff88" stroke-width="3.5">
              <rect x="20" y="14" width="13" height="72" rx="2" fill="rgba(0,255,136,0.15)"/>
              <rect x="36" y="14" width="13" height="72" rx="2" fill="rgba(0,255,136,0.25)"/>
              <rect x="52" y="14" width="13" height="72" rx="2" fill="rgba(0,255,136,0.25)"/>
              <rect x="68" y="14" width="13" height="72" rx="2" fill="rgba(0,255,136,0.15)"/>
              <rect x="39" y="32" width="23" height="10" fill="#fff"/>
            </svg>`
    },
    HAL9000: {
      color: "#ff1e38",
      glow: "rgba(255, 30, 56, 0.58)",
      dim: "rgba(255, 30, 56, 0.2)",
      svg: `<svg viewBox="0 0 100 100" fill="none">
              <circle cx="50" cy="50" r="40" stroke="#888" stroke-width="4" fill="#1a0004"/>
              <circle cx="50" cy="50" r="24" fill="#ff0022"/>
              <circle cx="50" cy="50" r="10" fill="#ffcc00"/>
              <circle cx="43" cy="42" r="4" fill="#ffffff"/>
            </svg>`
    },
    C3PO: {
      color: "#ffcc00",
      glow: "rgba(255, 204, 0, 0.48)",
      dim: "rgba(255, 204, 0, 0.18)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#ffcc00" stroke-width="3.5">
              <path d="M26 46 C26 22, 74 22, 74 46 L70 74 C70 84, 30 84, 30 74 Z" fill="rgba(255,204,0,0.18)"/>
              <circle cx="38" cy="48" r="8" fill="#fff"/>
              <circle cx="62" cy="48" r="8" fill="#fff"/>
              <rect x="44" y="68" width="12" height="5" rx="2" fill="#ffcc00"/>
            </svg>`
    },
    R2D2: {
      color: "#2b7cff",
      glow: "rgba(43, 124, 255, 0.52)",
      dim: "rgba(43, 124, 255, 0.20)",
      svg: `<svg viewBox="0 0 100 100" fill="none">
              <!-- Cúpula de Astromech R2-D2 -->
              <path d="M22 62 C22 28, 78 28, 78 62 Z" fill="rgba(43,124,255,0.25)" stroke="#2b7cff" stroke-width="3.5"/>
              <path d="M34 32 C42 27, 58 27, 66 32 L66 42 L34 42 Z" fill="#2b7cff" opacity="0.9"/>
              <rect x="22" y="62" width="56" height="24" rx="3" fill="rgba(255,255,255,0.08)" stroke="#2b7cff" stroke-width="3"/>
              <line x1="50" y1="28" x2="50" y2="42" stroke="#fff" stroke-width="2"/>
              <line x1="36" y1="62" x2="36" y2="86" stroke="#2b7cff" stroke-width="2"/>
              <line x1="64" y1="62" x2="64" y2="86" stroke="#2b7cff" stroke-width="2"/>
              <circle cx="50" cy="52" r="8" fill="#081022" stroke="#fff" stroke-width="2.5"/>
              <circle cx="50" cy="52" r="5" fill="#00e5ff"/>
              <circle cx="65" cy="50" r="3.5" fill="#ff2244"/>
              <circle cx="35" cy="50" r="3" fill="#2b7cff"/>
            </svg>`
    }
  };

  let personaAtualId = "";
  let audioLiberado = false;
  let tocando = false;
  let filaAudio = [];
  const idsVistos = new Set();
  let audioPlayer = new Audio();
  audioPlayer.preload = 'auto';
  audioPlayer.playsInline = true;

  function enfileirarAudio(id) {
    if (idsVistos.has(id)) return;
    idsVistos.add(id);
    filaAudio.push(id);
    tocarProximo();
  }
  function tocarProximo() {
    if (!audioLiberado || tocando || filaAudio.length === 0) return;
    const id = filaAudio.shift();
    tocando = true;
    audioPlayer.dataset.id = id;
    audioPlayer.src = '/api/audio/' + id + '.mp3';
    const p = audioPlayer.play();
    if (p && p.catch) p.catch(err => {
      console.warn('Playback iOS bloqueado:', err);
      tocando = false;
      filaAudio.unshift(id);   // tenta de novo após o próximo toque (ativarAudio)
    });
  }
  function concluirAudio() {
    if (!tocando) return;
    const id = Number(audioPlayer.dataset.id);
    tocando = false;
    vibrar([20, 40, 20]);
    fetch('/api/audio/played', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id})}).catch(() => {});
    tocarProximo();
  }
  audioPlayer.addEventListener('ended', concluirAudio);
  audioPlayer.addEventListener('error', () => { console.warn('Falha ao reproduzir áudio.'); concluirAudio(); });

  // ---- FEEDBACK HÁPTICO / VIBRAÇÃO (TAPTIC ENGINE NO IPHONE 11) ----
  function vibrar(padrao = 25) {
    if (navigator.vibrate) {
      try { navigator.vibrate(padrao); } catch (e) {}
    }
    // Efeito háptico acústico via Web Audio API (ressonância nos transdutores estéreo do iPhone)
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        if (!window._audioCtx) window._audioCtx = new AC();
        if (window._audioCtx.state === 'running') {
          const dur = typeof padrao === 'number' ? (padrao / 1000) : 0.04;
          const osc = window._audioCtx.createOscillator();
          const gain = window._audioCtx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(52, window._audioCtx.currentTime);
          gain.gain.setValueAtTime(0.14, window._audioCtx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, window._audioCtx.currentTime + Math.min(dur, 0.05));
          osc.connect(gain);
          gain.connect(window._audioCtx.destination);
          osc.start();
          osc.stop(window._audioCtx.currentTime + Math.min(dur, 0.05));
        }
      }
    } catch (e) {}
  }

  // ---- SCREEN WAKE LOCK API (TELA DO IPHONE SEMPRE ATIVA NO DOCK) ----
  let wakeLock = null;
  let fallbackVideo = null;

  async function solicitarWakeLock() {
    vibrar(20);
    if ('wakeLock' in navigator) {
      try {
        wakeLock = await navigator.wakeLock.request('screen');
        atualizarIndicadorWake(true);
        wakeLock.addEventListener('release', () => {
          atualizarIndicadorWake(false);
          wakeLock = null;
        });
        console.log('☀️ [STARK DOCK] Screen Wake Lock ativo.');
        return;
      } catch (err) {
        console.warn('⚠️ [STARK DOCK] Wake Lock falhou:', err);
        atualizarIndicadorWake(false);
      }
    }
    iniciarFallbackWakeLock();
  }

  function atualizarIndicadorWake(ativo) {
    const el = document.getElementById('wakeLockPill');
    if (!el) return;
    el.classList.toggle('active', ativo);
    el.innerHTML = ativo ? '☀️ WAKE ON' : '💤 WAKE';
  }

  function iniciarFallbackWakeLock() {
    if (fallbackVideo) return;
    try {
      const v = document.createElement('video');
      v.setAttribute('playsinline', '');
      v.setAttribute('autoplay', '');
      v.setAttribute('loop', '');
      v.setAttribute('muted', '');
      v.muted = true;
      v.style.position = 'fixed';
      v.style.left = '-9999px';
      v.style.width = '1px';
      v.style.height = '1px';
      v.src = 'data:video/mp4;base64,AAAAHGZ0eXBpc29tAAAAAGlzb21tcDQxAAAACHZpZGVvAAAAAG1vb3YAAABsbXZoZAAAAADa4y5o2uMuaAAACXgAAAEAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
      document.body.appendChild(v);
      v.play().then(() => {
        fallbackVideo = v;
        atualizarIndicadorWake(true);
      }).catch(() => {});
    } catch (e) {}
  }

  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
      await solicitarWakeLock();
    }
  });

  // ---- MONITORAMENTO E PROTEÇÃO DE BATERIA (SMART CHARGING 20%-80%) ----
  let monitorBateriaIniciado = false;
  let bateriaNivel = null;
  let bateriaCarregando = null;

  async function iniciarMonitoramentoBateria() {
    if (monitorBateriaIniciado) return;
    monitorBateriaIniciado = true;
    if ('getBattery' in navigator) {
      try {
        const b = await navigator.getBattery();
        const reportar = () => {
          bateriaNivel = Math.round(b.level * 100);
          bateriaCarregando = b.charging;
          atualizarUIBateria(bateriaNivel, bateriaCarregando);
          fetch('/api/dock_battery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ nivel: bateriaNivel, carregando: bateriaCarregando })
          }).catch(() => {});
        };
        b.addEventListener('levelchange', reportar);
        b.addEventListener('chargingchange', reportar);
        reportar();
        setInterval(reportar, 60000);
      } catch (e) {
        console.log('Battery API restrita pelo navegador:', e);
      }
    }
  }

  function atualizarUIBateria(nivel, carregando) {
    const el = document.getElementById('batteryPill');
    if (!el) return;
    if (nivel !== null && nivel !== undefined) {
      const icone = carregando ? '⚡' : '🔋';
      el.innerHTML = `${icone} ${nivel}%`;
      el.classList.toggle('active', !!carregando);
      if (nivel <= 20) {
        el.style.borderColor = '#ff4444';
        el.style.color = '#ff6666';
      } else if (nivel >= 80 && carregando) {
        el.style.borderColor = '#00ff9d';
        el.style.color = '#00ff9d';
      } else {
        el.style.borderColor = '';
        el.style.color = '';
      }
    }
  }

  let recognition = null;
  let escutando = false;
  let camStream = null;
  let camTimer = null;
  let enviandoFrame = false;

  function aplicarTemaPersona(persona) {
    const id = persona.id || "JARVIS";
    if (id === personaAtualId) return;
    personaAtualId = id;

    const cfg = PERSONA_THEMES[id] || PERSONA_THEMES.JARVIS;
    document.documentElement.style.setProperty('--theme', cfg.color);
    document.documentElement.style.setProperty('--theme-glow', cfg.glow);
    document.documentElement.style.setProperty('--theme-dim', cfg.dim);
    document.documentElement.style.setProperty('--panel-border', cfg.dim);

    document.getElementById('avatarContainer').innerHTML = cfg.svg;
    document.getElementById('personaBadge').innerText = `${persona.icone || '🎩'} ${persona.nome}`;
    document.getElementById('personaName').innerText = persona.nome;

    document.querySelectorAll('.p-chip').forEach(el => el.classList.remove('active'));
    const chip = document.getElementById('chip_' + id);
    if (chip) chip.classList.add('active');
  }

  function ativarAudio() {
    audioLiberado = true;
    const btn = document.getElementById('btnAudioUnlock');
    if (btn) {
      btn.classList.add('active');
      btn.innerText = "🔊 ON";
    }
    // Cria ou inicializa contexto de áudio web (padrão oficial aceito pelo iOS)
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        if (!window._audioCtx) window._audioCtx = new AC();
        if (window._audioCtx.state === 'suspended') window._audioCtx.resume();
      }
    } catch (e) {}

    // Desbloqueia o elemento de áudio html5
    try {
      audioPlayer.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
      audioPlayer.play().catch(() => {});
    } catch (e) {}
    setTimeout(() => { tocando = false; tocarProximo(); carregarEstado(); }, 300);
  }

  async function carregarEstado() {
    try {
      const res = await fetch('/api/status');
      if (res.status === 401) { setSub('Acesso negado: abra o HUD com ?token=SEU_TOKEN uma vez.'); return; }
      if (!res.ok) return;
      aplicarEstado(await res.json());
    } catch (e) {}
  }

  function aplicarEstado(data) {
    try {
      if (data.time) {
        const clk = document.getElementById('clockTxt');
        if (clk) clk.innerText = data.time;
        const clkSec = document.getElementById('clockSecTxt');
        if (clkSec) clkSec.innerText = data.time;
      }
      const oled = document.getElementById('oledFaceTxt');
      if (oled) oled.innerText = 'OLED: ' + (data.hud.face || 'NEUTRO');

      // Atualiza Avatar e Cores da Personalidade Ativa
      if (data.persona) {
        aplicarTemaPersona(data.persona);
      }

      // Subtítulo dinâmico
      const subEl = document.getElementById('personaSubtitle');
      const tagEl = document.getElementById('dialogueTag');
      if (!escutando && subEl) {
        subEl.innerText = data.hud.last_response || (data.persona && data.persona.titulo) || 'Pronto';
        if (tagEl) {
          if (data.persona && data.persona.id === 'R2D2') {
            tagEl.innerText = '// TRANSMISSÃO_ASTROMECH';
          } else {
            tagEl.innerText = '// RESPOSTA_DO_NÚCLEO';
          }
        }
      }

      const rPanel = document.getElementById('reactorPanel');
      if (data.hud.speaking) {
        rPanel.classList.add('speaking');
      } else {
        rPanel.classList.remove('speaking');
      }

      (data.hud.pending_audio || []).forEach(enfileirarAudio);

      // Atualiza os botões IoT
      const iot = data.iot || {};
      ['tomada_impressora', 'dimmer_quarto', 'luz_estudo', 'tomada_dock'].forEach(chave => {
        const d = iot[chave];
        const btn = document.getElementById('btn_' + chave);
        const st = document.getElementById('st_' + chave);
        if (d && btn && st) {
          const ligado = (d.status === 'ligado');
          btn.classList.toggle('on', ligado);
          st.innerText = ligado ? 'LIGADO' : 'DESLIGADO';
        }
      });

      // Atualiza telemetria de bateria sincronizada se vier do backend
      if (data.hud && data.hud.battery && data.hud.battery.level !== null && data.hud.battery.level !== undefined) {
        atualizarUIBateria(data.hud.battery.level, data.hud.battery.charging);
      }
    } catch (e) {}
  }

  async function alternarIoT(chave) {
    vibrar(25);
    ativarAudio();
    await fetch('/api/iot', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dispositivo: chave, acao: 'alternar'})
    });
    carregarEstado();
  }

  async function moverBraco(acao) {
    vibrar(30);
    ativarAudio();
    await fetch('/api/arm', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({acao})
    });
    carregarEstado();
  }

  let garraAberta = false;
  async function alternarGarra() {
    garraAberta = !garraAberta;
    const acao = garraAberta ? 'abrir garra' : 'fechar garra';
    const stEl = document.getElementById('st_garra');
    const icEl = document.getElementById('ic_garra');
    if (stEl) stEl.innerText = garraAberta ? 'Aberta (60°)' : 'Fechada (100°)';
    if (icEl) icEl.innerText = garraAberta ? '👐' : '✊';
    await moverBraco(acao);
  }

  async function mudarPersona(idPersona) {
    vibrar(35);
    ativarAudio();
    await fetch('/api/persona', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({persona: idPersona})
    });
    carregarEstado();
  }

  // ---- GRAVAÇÃO DE VOZ NO IPHONE (janela de escuta generosa + envio ao servidor) ----
  const VOZ_ESPERA_INICIO_MS = 10000;   // aguarda até 10 s você começar a falar
  const VOZ_SILENCIO_FIM_MS = 2200;     // encerra após 2,2 s de silêncio depois da fala
  const VOZ_MAX_MS = 30000;             // limite total de gravação
  const VOZ_LIMIAR = 0.012;             // sensibilidade (RMS 0..1)
  let gravacao = null;

  function setSub(txt) {
    const sub = document.getElementById('personaSubtitle');
    if (sub) sub.innerText = txt;
    const tag = document.getElementById('dialogueTag');
    if (tag) tag.innerText = '// ENTRADA_DE_VOZ';
  }

  function pararGravacao(enviar) {
    if (!gravacao) return;
    const g = gravacao;
    gravacao = null;
    escutando = false;
    vibrar(40);
    try { g.proc.disconnect(); g.src.disconnect(); } catch (e) {}
    try { g.stream.getTracks().forEach(t => t.stop()); } catch (e) {}
    try { g.ctx.close(); } catch (e) {}
    document.getElementById('reactorPanel').classList.remove('listening');
    clearTimeout(g.timerMax);
    clearInterval(g.timerCheck);
    if (!enviar || !g.falou) { setSub(g.falou ? 'Cancelado.' : 'Não ouvi nada, senhor. Toque e fale.'); return; }
    enviarVoz(g);
  }

  function codificarWav(chunks, taxaOrigem) {
    let total = 0; chunks.forEach(c => total += c.length);
    const dados = new Float32Array(total);
    let off = 0; chunks.forEach(c => { dados.set(c, off); off += c.length; });
    const taxaAlvo = 16000;
    const razao = taxaOrigem / taxaAlvo;
    const n = Math.floor(dados.length / razao);
    const buf = new ArrayBuffer(44 + n * 2);
    const v = new DataView(buf);
    const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, taxaAlvo, true); v.setUint32(28, taxaAlvo * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) {
      const ini = Math.floor(i * razao), fim = Math.min(Math.floor((i + 1) * razao), dados.length);
      let soma = 0, c = 0;
      for (let j = ini; j < fim; j++) { soma += dados[j]; c++; }
      const s = Math.max(-1, Math.min(1, c ? soma / c : 0));
      v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return new Blob([buf], {type: 'audio/wav'});
  }

  async function enviarVoz(g) {
    setSub('⏳ Interpretando sua fala...');
    try {
      const wav = codificarWav(g.chunks, g.ctx.sampleRate);
      const res = await fetch('/api/voice', {method: 'POST', headers: {'Content-Type': 'audio/wav'}, body: wav});
      const data = await res.json();
      if (data.ok) setSub('🗣️ ' + (data.text || '') + ' …');
      else setSub(data.error || 'Não entendi, senhor. Tente novamente.');
    } catch (e) {
      setSub('Falha ao enviar a voz ao servidor.');
    }
    carregarEstado();
  }

  async function alternarEscutaVoz() {
    ativarAudio();

    // Segundo toque enquanto grava = encerra e envia imediatamente
    if (gravacao) { vibrar(40); pararGravacao(true); return; }

    // Sem HTTPS o iOS bloqueia o microfone: usa o microfone do servidor como alternativa
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      fetch('/api/listen_server', {method: 'POST'});
      setSub('Ouvindo pelo microfone do servidor... (use https para falar pelo iPhone)');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC();
      if (ctx.state === 'suspended') await ctx.resume();
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      const g = {stream, ctx, src, proc, chunks: [], falou: false, inicio: Date.now(), ultimaVoz: Date.now()};
      proc.onaudioprocess = (e) => {
        const d = new Float32Array(e.inputBuffer.getChannelData(0));
        g.chunks.push(d);
        let s = 0; for (let i = 0; i < d.length; i++) s += d[i] * d[i];
        if (Math.sqrt(s / d.length) > VOZ_LIMIAR) { g.falou = true; g.ultimaVoz = Date.now(); }
      };
      src.connect(proc); proc.connect(ctx.destination);
      gravacao = g;
      escutando = true;
      vibrar([40, 60, 40]);
      document.getElementById('reactorPanel').classList.add('listening');
      setSub('🎙️ Ouvindo... fale à vontade (toque de novo para enviar)');

      g.timerCheck = setInterval(() => {
        const agora = Date.now();
        if (!g.falou && agora - g.inicio > VOZ_ESPERA_INICIO_MS) pararGravacao(true);
        else if (g.falou && agora - g.ultimaVoz > VOZ_SILENCIO_FIM_MS) pararGravacao(true);
      }, 200);
      g.timerMax = setTimeout(() => pararGravacao(true), VOZ_MAX_MS);
    } catch (err) {
      setSub('Microfone bloqueado. Permita o acesso em Ajustes > Safari e use https://' + location.hostname + ':8443');
    }
  }

  // Webcam em segundo plano (para a Impressora 3D continuar alimentando o JARVIS sem poluir a tela!)
  async function ligarCamera3D() {
    if (camStream) return;
    const btn = document.getElementById('btnCamToggle');
    try {
      camStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });
      document.getElementById('hiddenVideo').srcObject = camStream;
      if (btn) {
        btn.classList.add('active');
        btn.innerText = '📷 3D ON';
      }
      if (!camTimer) {
        camTimer = setInterval(enviarFrameSilencioso, 450);
      }
    } catch (err) {
      console.warn("Câmera 3D aguardando permissão ou toque na tela:", err);
    }
  }

  async function alternarCamera3D() {
    vibrar(25);
    const btn = document.getElementById('btnCamToggle');
    if (camStream) {
      if (camTimer) { clearInterval(camTimer); camTimer = null; }
      camStream.getTracks().forEach(t => t.stop());
      camStream = null;
      if (btn) {
        btn.classList.remove('active');
        btn.innerText = '📷 Cam 3D';
      }
      return;
    }
    await ligarCamera3D();
  }

  function enviarFrameSilencioso() {
    if (!camStream || enviandoFrame) return;
    const video = document.getElementById('hiddenVideo');
    if (video.readyState < 2) return;
    enviandoFrame = true;
    const canvas = document.getElementById('hiddenCanvas');
    let w = video.videoWidth || 640;
    let h = video.videoHeight || 360;
    const maxDim = 800;
    if (w > maxDim) {
      h = Math.round(h * (maxDim / w));
      w = maxDim;
    }
    canvas.width = w;
    canvas.height = h;
    canvas.getContext('2d').drawImage(video, 0, 0, w, h);
    canvas.toBlob(async (blob) => {
      if (blob) {
        try { await fetch('/api/camera/frame', { method: 'POST', headers: {'Content-Type': 'image/jpeg'}, body: blob }); } catch (e) {}
      }
      enviandoFrame = false;
    }, 'image/jpeg', 0.68);
  }

  aplicarTemaPersona({id: 'JARVIS', nome: 'J.A.R.V.I.S.', icone: '🎩'});
  let pollTimer = null;
  function iniciarEventos() {
    if (!window.EventSource) { pollTimer = setInterval(carregarEstado, 1500); carregarEstado(); return; }
    const es = new EventSource('/api/events');
    es.addEventListener('state', ev => { try { aplicarEstado(JSON.parse(ev.data)); } catch (e) {} });
    es.addEventListener('parar', () => { filaAudio = []; tocando = false; try { audioPlayer.pause(); } catch (e) {} });
    es.onopen = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } carregarEstado(); };
    es.onerror = () => { if (!pollTimer) pollTimer = setInterval(carregarEstado, 3000); };  // EventSource reconecta sozinho
  }
  iniciarEventos();

  // ---- AUTO-ATIVAÇÃO DE SOM, CÂMERA, WAKE LOCK E BATERIA POR PADRÃO ----
  function autoAtivarTudo() {
    if (!audioLiberado) ativarAudio();
    if (!camStream) ligarCamera3D();
    if (!wakeLock) solicitarWakeLock();
    if (!monitorBateriaIniciado) iniciarMonitoramentoBateria();
  }

  // Tenta ativar assim que carregar o script e a página
  setTimeout(autoAtivarTudo, 300);
  window.addEventListener('DOMContentLoaded', autoAtivarTudo);
  window.addEventListener('load', autoAtivarTudo);

  // Destrave universal garantido no primeiro toque em qualquer lugar da tela (exigência do Safari)
  ['touchstart', 'touchend', 'pointerdown', 'click'].forEach(evt => {
    window.addEventListener(evt, () => {
      autoAtivarTudo();
      if (!wakeLock) solicitarWakeLock();
    }, { passive: true });
  });
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------------- HTTP
_sse_sem = threading.BoundedSemaphore(4)
_mjpeg_sem = threading.BoundedSemaphore(8)
_recognizer = None
_recognizer_lock = threading.Lock()
_RE_AUDIO = re.compile(r"^/api/audio/(\d+)(\.[a-zA-Z0-9]+)?$")


def _get_recognizer():
    global _recognizer
    with _recognizer_lock:
        if _recognizer is None:
            import speech_recognition as sr
            _recognizer = sr.Recognizer()
            _recognizer.operation_timeout = 10   # sem isto recognize_google pode ficar pendurado indefinidamente
        return _recognizer


class StarkDockHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"     # keep-alive: evita um handshake TLS por requisição
    timeout = 20                      # corta clientes lentos/ociosos (slowloris) e escritas travadas
    server_version = "StarkDock"
    sys_version = ""

    def setup(self):
        if isinstance(self.request, ssl.SSLSocket):
            self.request.settimeout(10)
            self.request.do_handshake()          # handshake aqui, na thread da conexão (não no accept)
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        super().setup()

    def log_message(self, format, *args):
        pass

    # ---- utilidades
    @property
    def _https(self) -> bool:
        return isinstance(self.request, ssl.SSLSocket)

    def _responder(self, status: int, corpo: bytes = b"", ctype: str = None, extra=None):
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if corpo:
            self.wfile.write(corpo)

    def _json(self, data: dict, status: int = 200):
        self._responder(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _ler_corpo(self, limite: int):
        """Lê o corpo com limite. Retorna bytes, ou None (já respondeu 400/411/413)."""
        bruto = self.headers.get("Content-Length")
        if bruto is None:
            self._json({"ok": False, "error": "Content-Length obrigatório"}, 411)
            return None
        try:
            n = int(bruto)
        except ValueError:
            self._json({"ok": False, "error": "Content-Length inválido"}, 400)
            return None
        if n < 0 or n > limite:
            self.close_connection = True
            self._json({"ok": False, "error": "Corpo grande demais"}, 413)
            return None
        return self.rfile.read(n) if n else b""

    def _cookie(self, nome: str) -> str:
        from http.cookies import SimpleCookie
        try:
            c = SimpleCookie(self.headers.get("Cookie", ""))
            return c[nome].value if nome in c else ""
        except Exception:
            return ""

    def _credencial_valida(self, permitir_query: bool = False) -> bool:
        ip = self.client_address[0]
        if _eh_ip_privado_ou_local(ip):
            return True
        tok = self.headers.get("X-Jarvis-Token", "")
        auth = self.headers.get("Authorization", "")
        if not tok and auth.startswith("Bearer "):
            tok = auth[7:].strip()
        if tok and _igual(tok, DOCK_TOKEN):
            return True
        ck = self._cookie(_COOKIE_NOME)
        if ck and _validar_cookie_sessao(ck):
            return True
        if permitir_query:
            q = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if q and _igual(q, DOCK_TOKEN):
                return True
        return False

    def _exigir_auth(self, permitir_query: bool = False) -> bool:
        ip = self.client_address[0]
        if _bloqueado(ip):
            self._json({"ok": False, "error": "Muitas tentativas. Aguarde 1 minuto."}, 429)
            return False
        if self._credencial_valida(permitir_query):
            return True
        _registrar_falha(ip)
        self._json({"ok": False, "error": "Não autorizado"}, 401)
        return False

    def _origem_ok(self) -> bool:
        ip = self.client_address[0]
        if _eh_ip_privado_ou_local(ip):
            return True
        origem = self.headers.get("Origin")
        if not origem:
            return True
        return urlparse(origem).netloc == self.headers.get("Host", "")

    # ---- áudio com HTTP Range (exigido pelo Safari/iOS)
    def _servir_audio(self, dados: bytes):
        total = len(dados)
        rng = self.headers.get("Range", "")
        inicio, fim, status = 0, total - 1, 200
        if rng.startswith("bytes="):
            try:
                a, b = rng[6:].split(",")[0].split("-", 1)
                if not a:
                    suf = int(b)
                    if suf <= 0:
                        raise ValueError
                    inicio, fim = max(0, total - suf), total - 1
                else:
                    inicio = int(a)
                    fim = min(int(b), total - 1) if b else total - 1
                if inicio < 0 or inicio >= total or inicio > fim:
                    self._responder(416, b"", None, [("Content-Range", f"bytes */{total}"), ("Accept-Ranges", "bytes")])
                    return
                status = 206
            except (ValueError, TypeError):
                inicio, fim, status = 0, total - 1, 200
        extra = [("Accept-Ranges", "bytes")]
        if status == 206:
            extra.append(("Content-Range", f"bytes {inicio}-{fim}/{total}"))
        ctype = "audio/wav" if dados.startswith(b"RIFF") else "audio/mpeg"
        self._responder(status, dados[inicio:fim + 1], ctype, extra)

    # ---- SSE
    def _sse_escrever(self, evento: str, dados: str):
        self.wfile.write(f"event: {evento}\ndata: {dados}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _servir_eventos(self):
        if not _sse_sem.acquire(blocking=False):
            self._json({"ok": False, "error": "Limite de conexões de eventos atingido"}, 503)
            return
        sub = dock_state.inscrever()
        try:
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                sub.evento.wait(10)             # 10 s sem mudanças = heartbeat com o estado atual (relógio incluso)
                sub.evento.clear()
                if sub.parar:
                    sub.parar = False
                    self._sse_escrever("parar", "{}")
                sub.sujo = False
                self._sse_escrever("state", json.dumps(dock_state.obter_snapshot(), ensure_ascii=False))
        except (OSError, ssl.SSLError):
            pass
        finally:
            dock_state.desinscrever(sub)
            _sse_sem.release()

    def _servir_mjpeg(self):
        from camera_manager import camera_manager
        if not _mjpeg_sem.acquire(blocking=False):
            self._json({"ok": False, "error": "Limite de clientes de vídeo atingido"}, 503)
            return
        try:
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            seq, ocioso, ultimo_envio = -1, 0.0, 0.0
            while ocioso < 60:
                espera = 0.12 - (time.monotonic() - ultimo_envio)   # teto de ~8 fps por cliente
                if espera > 0:
                    time.sleep(espera)
                seq, jpg = camera_manager.aguardar_frame_novo(seq, timeout=5.0)
                if jpg is None:
                    ocioso += 5.0
                    continue
                ocioso = 0.0
                ultimo_envio = time.monotonic()
                buf = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
                self.wfile.write(buf)
                self.wfile.flush()
        except (OSError, ssl.SSLError):
            pass
        finally:
            _mjpeg_sem.release()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Api-Key, Range")
        self.end_headers()

    # ---- GET
    def do_GET(self):
        path = urlparse(self.path).path
        LOOPBACK_IPS = ("127.0.0.1", "::1", "localhost")

        if path in ("/go", "/pair", "/entrar"):
            # Apenas acessível a partir do terminal/loopback local do servidor
            if self.client_address[0] not in LOOPBACK_IPS:
                self._responder(404)
                return
            ip_local = obter_ip_local()
            https_port = int(os.getenv("DOCK_HTTPS_PORT", "8443"))
            dest = f"https://{ip_local}:{https_port}/?token={DOCK_TOKEN}"
            self._responder(302, b"", None, [("Location", dest)])
            return

        if path in ("/", "/index.html", "/hud"):
            q = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if q:
                if _bloqueado(self.client_address[0]):
                    self._json({"ok": False, "error": "Muitas tentativas."}, 429)
                    return
                if _igual(q, DOCK_TOKEN):
                    flags = "Path=/; HttpOnly; SameSite=Strict; Max-Age=604800" + ("; Secure" if self._https else "")
                    sessao_cookie = _gerar_cookie_sessao()
                    self._responder(302, b"", None, [("Location", "/"), ("Set-Cookie", f"{_COOKIE_NOME}={sessao_cookie}; {flags}")])
                    return
                _registrar_falha(self.client_address[0])
            if self._credencial_valida():
                html = HTML_STARK_HUD.replace("__STARK_DOCK_TOKEN__", DOCK_TOKEN)
                self._responder(200, html.encode("utf-8"), "text/html; charset=utf-8")
            else:
                pagina = ("<meta name=viewport content='width=device-width'><body style='background:#000;color:#0cf;"
                          "font-family:sans-serif;padding:2em'><h2>J.A.R.V.I.S.</h2><p>Acesso restrito. "
                          "Abra o endereço com <code>?token=SEU_TOKEN</code> uma vez.</p>")
                self._responder(401, pagina.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path.startswith("/camera/"):
            # Acesso liberado sem token para loopback, LAN interna e Tailscale; externos exigem token
            if not _eh_ip_privado_ou_local(self.client_address[0]) and not self._exigir_auth(permitir_query=True):
                return

            if path == "/camera/snapshot.jpg":
                from camera_manager import camera_manager
                jpg = camera_manager.obter_ultimo_jpeg_remoto()
                if not jpg:
                    try:
                        p = camera_manager.default_photo_path
                        if os.path.exists(p) and (time.time() - os.path.getmtime(p) < 60):
                            with open(p, "rb") as f:
                                jpg = f.read()
                    except Exception:
                        pass
                if jpg:
                    self._responder(200, jpg, "image/jpeg")
                else:
                    self._responder(503)
                return
            if path == "/camera/stream.mjpg":
                self._servir_mjpeg()
                return
            self._responder(404)
            return

        if not path.startswith("/api/"):
            self._responder(404)
            return
        if not self._exigir_auth():
            return

        if path == "/api/status":
            self._json(dock_state.obter_snapshot())
            return
        if path == "/api/events":
            self._servir_eventos()
            return
        if path == "/api/health":
            from gemini_session import gemini_session
            from ai_router import ai_router
            self._json({"ok": True, "gemini": gemini_session.status(), "ollama": ai_router.status_ollama()["online"],
                        "sse": dock_state.n_assinantes(), "threads": threading.active_count()})
            return
        if path == "/api/audio/latest":
            dados = dock_state.ultimo_audio()
            self._servir_audio(dados) if dados else self._responder(204)
            return
        m = _RE_AUDIO.match(path)
        if m:
            dados = dock_state.obter_audio(int(m.group(1)))
            self._servir_audio(dados) if dados else self._responder(404)
            return
        self._responder(404)

    # ---- POST
    def do_POST(self):
        path = urlparse(self.path).path
        if not self._exigir_auth():
            self.close_connection = True     # corpo não lido: não reaproveita a conexão
            return
        if not self._origem_ok():
            self.close_connection = True
            self._json({"ok": False, "error": "Origem não permitida"}, 403)
            return

        limite = MAX_FRAME if path == "/api/camera/frame" else MAX_WAV if path == "/api/voice" else MAX_JSON
        raw = self._ler_corpo(limite)
        if raw is None:
            return

        from brain_core import com_prazo, processar_async, processar_comando, _pool

        if path == "/api/camera/frame":
            from camera_manager import camera_manager
            ok = camera_manager.atualizar_frame_remoto(raw)
            if ok:
                dock_state.registrar_frame_camera()
            self._json({"ok": ok})
            return

        try:
            payload = json.loads(raw.decode("utf-8")) if raw and path != "/api/voice" else {}
        except Exception:
            payload = {}

        if path == "/api/audio/played":
            try:
                dock_state.marcar_tocada(int(payload.get("id")))
            except (TypeError, ValueError):
                pass
            self._json({"ok": True})
            return

        if path == "/api/dock_battery":
            try:
                nivel = int(payload.get("nivel", 0))
                carregando = bool(payload.get("carregando", False))
                dock_state.battery_level = nivel
                dock_state.battery_charging = carregando
                dock_state.battery_last_check = time.time()

                # Automação de Proteção de Bateria (Ciclo Inteligente 20% - 80%)
                from iot_service import iot_service
                disp_dock = None
                for k in ["tomada_dock", "carregador_dock", "carregador", "dock"]:
                    if k in iot_service.dispositivos:
                        disp_dock = k
                        break

                agora = time.time()
                # Intervalo mínimo de 120s entre comutações de proteção para evitar oscilações
                if disp_dock and (agora - getattr(dock_state, "_ultimo_chaveamento_bateria", 0) > 120):
                    disp_info = iot_service.dispositivos[disp_dock]
                    status_atual = disp_info.get("status", "desligado")

                    if nivel >= 80 and carregando and status_atual == "ligado":
                        print(f"\n🔋 [SMART CHARGING]: Bateria do iPhone atingiu {nivel}%. Desligando {disp_dock} para preservar a vida útil.")
                        dock_state._ultimo_chaveamento_bateria = agora
                        iot_service.controlar(disp_dock, "desligar")
                        dock_state.atualizar_hud("PROTEÇÃO DE BATERIA", f"Carga em {nivel}%. Carregador desligado.", "🔋")
                    elif nivel <= 20 and not carregando and status_atual != "ligado":
                        print(f"\n⚡ [SMART CHARGING]: Bateria do iPhone baixa ({nivel}%). Ligando {disp_dock} para recarga.")
                        dock_state._ultimo_chaveamento_bateria = agora
                        iot_service.controlar(disp_dock, "ligar")
                        dock_state.atualizar_hud("RECARGA DOCK", f"Carga em {nivel}%. Carregador ligado.", "⚡")

                self._json({"ok": True, "level": nivel, "charging": carregando})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/api/stop":                       # barge-in
            from voice_engine import voice_engine
            voice_engine.parar()
            self._json({"ok": True})
            return

        if path == "/api/iot":
            from iot_service import iot_service
            from voice_engine import voice_engine
            disp, acao, valor = payload.get("dispositivo", "tudo"), payload.get("acao", "alternar"), str(payload.get("valor", ""))
            print(f"\n💡 [HUD IoT]: Dispositivo='{disp}' | Ação='{acao}' | Valor='{valor}'")
            res = com_prazo(lambda: iot_service.controlar(disp, acao, valor), 7, "Os dispositivos não responderam a tempo, senhor.")
            dock_state.atualizar_hud("AUTOMAÇÃO IoT", res, "💡")
            voice_engine.speak(res)
            self._json({"ok": True, "response": res})
            return

        if path == "/api/arm":
            from hardware_simulator import hardware
            acao = str(payload.get("acao", "acenar"))[:20]
            print(f"\n🦾 [HUD BRAÇO]: Acionando gesto '{acao}'")
            res = com_prazo(lambda: hardware.mover_braco(acao, detalhes="Acionado via Stark Dock iPhone 11"), 5,
                            "O braço não confirmou o movimento a tempo, senhor.")
            self._json({"ok": True, "response": res})
            return

        if path == "/api/persona":
            from persona_manager import persona_manager
            from voice_engine import voice_engine
            saudacao = persona_manager.definir_persona(str(payload.get("persona", "JARVIS"))[:20])
            p = persona_manager.obter_persona()
            print(f"\n🎭 [HUD PERSONA]: Mudando para {p['nome']}")
            voice_engine.voice_name = p["voz"]
            voice_engine.speak(saudacao)
            dock_state.notificar()
            self._json({"ok": True, "persona": p, "response": saudacao})
            return

        if path == "/api/command":
            texto = str(payload.get("text", "")).strip()[:2000]
            if not texto:
                self._json({"ok": False, "error": "Comando vazio"}, 400)
                return
            print(f"\n📱 [HUD COMANDO]: \"{texto}\"")
            from voice_engine import voice_engine
            if payload.get("async"):
                processar_async(texto, "voz", voice_engine.speak)
                self._json({"ok": True, "pending": True})
                return
            resposta = processar_comando(texto, origem="voz", timeout=60)
            voice_engine.speak(resposta)
            self._json({"ok": True, "response": resposta})
            return

        if path == "/api/voice":          # WAV 16 kHz mono gravado no iPhone
            import speech_recognition as sr
            from voice_engine import voice_engine
            from hardware_simulator import hardware
            try:
                rec = _get_recognizer()
                with sr.AudioFile(io.BytesIO(raw)) as fonte:
                    audio = rec.record(fonte)
                texto = rec.recognize_google(audio, language="pt-BR").strip()
            except sr.UnknownValueError:
                self._json({"ok": False, "error": "Não entendi a fala, senhor."})
                return
            except sr.RequestError:
                self._json({"ok": False, "error": "O serviço de reconhecimento de voz está indisponível, senhor."})
                return
            except Exception as e:
                self._json({"ok": False, "error": f"Falha na transcrição: {e}"})
                return

            print(f"\n📱 [HUD IPHONE VOZ]: \"{texto}\"")
            _pool.submit(hardware.desenhar_rosto_oled, "OUVINDO")

            def _responder_voz(resposta: str):
                _pool.submit(hardware.desenhar_rosto_oled, "FELIZ")
                voice_engine.speak(resposta)

            processar_async(texto, "voz", _responder_voz)       # não segura o HTTP durante o Gemini
            self._json({"ok": True, "text": texto, "pending": True})
            return

        if path == "/api/listen_server":  # fallback: microfone do SERVIDOR (normalmente inexistente)
            def _escutar():
                from voice_engine import voice_engine
                falado = voice_engine.listen()
                if falado:
                    voice_engine.speak(processar_comando(falado, origem="voz"))
            threading.Thread(target=_escutar, daemon=True).start()
            self._json({"ok": True})
            return

        self._json({"ok": False, "error": "Rota não encontrada"}, 404)


class _ServidorBase(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (OSError, ssl.SSLError)):   # resets, timeouts e handshakes abortados: ruído normal
            return
        super().handle_error(request, client_address)


class _ServidorHTTPS(_ServidorBase):
    def __init__(self, endereco, handler, contexto):
        self._ctx = contexto
        super().__init__(endereco, handler)

    def get_request(self):
        sock, addr = super().get_request()
        return self._ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr


def iniciar_dock_server(http_port: int = None, https_port: int = None):
    http_port = http_port or int(os.getenv("DOCK_HTTP_PORT", "8080"))
    https_port = https_port or int(os.getenv("DOCK_HTTPS_PORT", "8443"))
    bind = os.getenv("DOCK_BIND", "0.0.0.0")
    ip_local, ip_ts = obter_ip_local(), obter_ip_tailscale()

    # Auto-detecção de certificados Tailscale oficiais (*.ts.net.crt e *.ts.net.key)
    ts_cert, ts_key, ts_fqdn = localizar_certificados_tailscale()
    cert_tailscale_ativo = False

    if os.getenv("DOCK_CERT") and os.getenv("DOCK_KEY"):
        cert = os.getenv("DOCK_CERT")
        key = os.getenv("DOCK_KEY")
    elif ts_cert and ts_key:
        cert = ts_cert
        key = ts_key
        cert_tailscale_ativo = True
    else:
        cert = os.path.join(BASE_DIR, "stark_dock_cert.pem")
        key = os.path.join(BASE_DIR, "stark_dock_key.pem")

    sans_ip = ["127.0.0.1", ip_local] + ([ip_ts] if ip_ts else []) + [x for x in os.getenv("DOCK_EXTRA_IPS", "").split(",") if x.strip()]
    sans_dns = [socket.gethostname(), "localhost"] + [x for x in os.getenv("DOCK_EXTRA_DNS", "").split(",") if x.strip()]
    if ts_fqdn and ts_fqdn not in sans_dns:
        sans_dns.append(ts_fqdn)

    if os.getenv("DOCK_ENABLE_HTTP", "0") == "1":
        try:
            srv = _ServidorBase((bind, http_port), StarkDockHTTPHandler)
            threading.Thread(target=srv.serve_forever, daemon=True, name="StarkDockHTTP").start()
            print(f"⚠️ [STARK DOCK] HTTP ativo em {http_port} (token em texto puro na rede; use só em LAN confiável).")
        except OSError as e:
            print(f"⚠️ [STARK DOCK] Porta HTTP {http_port} indisponível: {e}")

    https_ativo = False
    if cert_tailscale_ativo or gerar_certificado_https_local(cert, key, sans_ip, sans_dns):
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(certfile=cert, keyfile=key)
            srv = _ServidorHTTPS((bind, https_port), StarkDockHTTPHandler, ctx)
            threading.Thread(target=srv.serve_forever, daemon=True, name="StarkDockHTTPS").start()
            https_ativo = True
        except (OSError, ssl.SSLError) as e:
            print(f"⚠️ [STARK DOCK] Porta HTTPS {https_port} indisponível: {e}")

    print("\n" + "═" * 64)
    print("📱 [STARK DOCK HUD] SERVIDOR ONLINE")
    if https_ativo:
        if cert_tailscale_ativo:
            print(f"   🔒 TLS Oficial Tailscale ativo ({os.path.basename(cert)}) - 100% Confiável no Safari!")
            if ts_fqdn:
                print(f"   👉 https://{ts_fqdn}:{https_port}")
        for ip in [ip_local] + ([ip_ts] if ip_ts else []):
            print(f"   👉 https://{ip}:{https_port}")
        if not cert_tailscale_ativo:
            print("   💡 Dica Tailscale: Se quiser HTTPS oficial grátis aceito direto no Safari, rode:")
            print("      sudo tailscale cert <seu-host>.ts.net")
        if _TOKEN_NOVO:
            print(f"   🔑 Token gerado e salvo no .env. Abra UMA vez: https://{ip_local}:{https_port}/?token={DOCK_TOKEN}")
        else:
            print("   🔑 Token em JARVIS_DOCK_TOKEN (.env). Abra https://<ip>:<porta>/?token=... uma vez por aparelho.")
    else:
        print("   ❌ HTTPS indisponível: sem ele o iPhone não libera microfone nem câmera.")
    print("═" * 64 + "\n")


if __name__ == "__main__":
    iniciar_dock_server()
    print("Servidor Stark Dock em modo standalone. Ctrl+C para sair.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
