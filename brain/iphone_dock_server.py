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
        self._sintetizando = False
        self._falas = OrderedDict()      # id -> {"audio": bytes, "texto": str, "ts": float}
        self._pendentes = []             # ids publicados e ainda não confirmados pelo HUD
        self._seq = 0
        self._subs = []

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
            self._sintetizando = True
        self.notificar()

    def fim_da_resposta(self):
        with self._lock:
            self._sintetizando = False
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
            self._sintetizando = False
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
                    "speaking": bool(self._pendentes) or self._sintetizando,
                    "pending_audio": list(self._pendentes), "audio_seq": self._seq,
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



HTML_STARK_HUD = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="J.A.R.V.I.S.">
<title>J.A.R.V.I.S. — Stark Dock</title>
<style>
  :root {
    --theme: #00f0ff;
    --theme-glow: rgba(0, 240, 255, 0.35);
    --theme-dim: rgba(0, 240, 255, 0.16);
    --ok: #00ff9d;
    --bg: #030811;
    --panel: rgba(7, 18, 34, 0.85);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; user-select: none; margin: 0; padding: 0; }
  body {
    background: radial-gradient(circle at 72% 50%, rgba(0, 120, 180, 0.14) 0%, #02050a 80%);
    color: var(--theme);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
    padding: env(safe-area-inset-top, 10px) env(safe-area-inset-right, 14px) env(safe-area-inset-bottom, 10px) env(safe-area-inset-left, 14px);
    display: flex;
    flex-direction: column;
    transition: color 0.35s ease;
  }

  /* LAYOUT PRINCIPAL: ESQUERDA (IoT + Braço) | DIREITA (Reator Arc + Avatar Persona) */
  .dock-workspace {
    display: grid;
    grid-template-columns: 0.92fr 1.08fr;
    gap: 14px;
    flex: 1;
    height: 100%;
    align-items: stretch;
  }
  /* Reator Arc à ESQUERDA, controles à DIREITA (operação mais fácil com a mão direita) */
  .dock-workspace > .right-panel { order: 1; }
  .dock-workspace > .left-panel { order: 2; }
  @media (max-width: 560px) {
    .dock-workspace {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
    }
  }

  /* PAINEL ESQUERDO: DUAS COLUNAS (COL 1: IoT | COL 2: BRAÇO ROBÓTICO) */
  .left-panel {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    height: 100%;
  }

  .column-card {
    background: var(--panel);
    border: 1px solid var(--theme-dim);
    border-radius: 18px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 8px;
    box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.45);
  }

  .col-header {
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 1.6px;
    text-transform: uppercase;
    opacity: 0.85;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--theme-dim);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .btn-stack {
    display: flex;
    flex-direction: column;
    gap: 9px;
    flex: 1;
    justify-content: center;
  }

  .ctrl-btn {
    flex: 1;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--theme-dim);
    border-radius: 14px;
    color: #eafaff;
    padding: 10px 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    transition: all 0.18s ease;
    text-align: left;
  }
  .ctrl-btn:active {
    transform: scale(0.96);
    background: var(--theme-dim);
  }
  .ctrl-btn.on {
    background: rgba(0, 255, 157, 0.16);
    border-color: var(--ok);
    color: #ffffff;
    box-shadow: 0 0 16px rgba(0, 255, 157, 0.22);
  }
  .ctrl-icon {
    font-size: 1.35rem;
    width: 30px;
    text-align: center;
    flex-shrink: 0;
  }
  .ctrl-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .ctrl-name {
    font-size: 0.84rem;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ctrl-state {
    font-size: 0.68rem;
    opacity: 0.72;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }

  /* PAINEL DIREITO: SOMENTE O REATOR ARC + AVATAR DA PERSONALIDADE ATIVA */
  .right-panel {
    background: var(--panel);
    border: 1px solid var(--theme-dim);
    border-radius: 18px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    position: relative;
    overflow: hidden;
    box-shadow: 0 0 30px rgba(0, 0, 0, 0.6);
  }

  .right-top {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
  }
  .persona-pill {
    padding: 4px 10px;
    border-radius: 20px;
    border: 1px solid var(--theme);
    background: var(--theme-dim);
    font-weight: 700;
    letter-spacing: 1.2px;
    font-size: 0.7rem;
    cursor: pointer;
  }
  .mini-bar {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .icon-btn {
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--theme-dim);
    color: #fff;
    border-radius: 10px;
    padding: 5px 9px;
    font-size: 0.74rem;
    cursor: pointer;
  }
  .icon-btn.active {
    border-color: var(--ok);
    color: var(--ok);
    background: rgba(0, 255, 157, 0.14);
  }

  /* REATOR ARC CENTRAL GRANDE COM AVATAR SVG DA PERSONALIDADE */
  .reactor-stage {
    position: relative;
    width: 190px;
    height: 190px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    margin: 4px 0;
  }
  .ring-outer {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 2px dashed var(--theme);
    box-shadow: 0 0 30px var(--theme-glow), inset 0 0 22px var(--theme-glow);
    animation: spinSlow 18s linear infinite;
  }
  .ring-mid {
    position: absolute;
    inset: 15px;
    border-radius: 50%;
    border: 1.5px solid var(--theme);
    opacity: 0.55;
    border-top-color: transparent;
    border-bottom-color: transparent;
    animation: spinRev 9s linear infinite;
  }
  .arc-core {
    width: 126px;
    height: 126px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(255,255,255,0.22) 0%, var(--theme-dim) 62%, rgba(0,0,0,0.88) 100%);
    border: 2px solid var(--theme);
    box-shadow: 0 0 28px var(--theme-glow);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
    z-index: 2;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
  }
  .speaking .arc-core {
    animation: speakPulse 0.3s ease-in-out infinite alternate;
    box-shadow: 0 0 55px var(--theme), 0 0 90px var(--theme);
  }
  .listening .arc-core {
    box-shadow: 0 0 55px #ffaa00, inset 0 0 25px #ffaa00;
    border-color: #ffaa00;
  }

  .avatar-svg-wrap {
    width: 66px;
    height: 66px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .avatar-svg-wrap svg {
    width: 100%;
    height: 100%;
    filter: drop-shadow(0 0 8px var(--theme));
  }

  @keyframes spinSlow { 100% { transform: rotate(360deg); } }
  @keyframes spinRev { 100% { transform: rotate(-360deg); } }
  @keyframes speakPulse { 0% { transform: scale(0.94); } 100% { transform: scale(1.12); } }

  /* IDENTIDADE E LEGENDA SUTIL DA VOZ */
  .persona-footer {
    text-align: center;
    width: 100%;
  }
  .persona-name {
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: 2px;
    color: #ffffff;
    text-shadow: 0 0 10px var(--theme);
  }
  .persona-sub {
    font-size: 0.74rem;
    opacity: 0.85;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* SELETOR DE AVATAR / PERSONALIDADE (POPUP SUTIL) */
  .persona-bar {
    display: flex;
    gap: 5px;
    margin-top: 6px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .p-chip {
    font-size: 0.64rem;
    padding: 3px 7px;
    border-radius: 8px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    color: #cceeff;
    cursor: pointer;
  }
  .p-chip.active {
    border-color: var(--theme);
    background: var(--theme-dim);
    color: #fff;
    font-weight: 700;
  }
</style>
</head>
<body>

  <div class="dock-workspace">

    <!-- PAINEL ESQUERDO: 2 COLUNAS (COLUNA 1: IoT | COLUNA 2: BRAÇO ROBÓTICO) -->
    <div class="left-panel">

      <!-- COLUNA 1: CONTROLE IoT (Seus 3 Dispositivos) -->
      <div class="column-card">
        <div class="col-header">
          <span>⚡ AUTOMAÇÃO IoT</span>
          <span id="clockTxt">--:--</span>
        </div>

        <div class="btn-stack" id="iotStack">
          <button class="ctrl-btn" id="btn_tomada_impressora" onclick="alternarIoT('tomada_impressora')">
            <div class="ctrl-icon">🖨️</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Impressora 3D</div>
              <div class="ctrl-state" id="st_tomada_impressora">DESLIGADO</div>
            </div>
          </button>

          <button class="ctrl-btn" id="btn_dimmer_quarto" onclick="alternarIoT('dimmer_quarto')">
            <div class="ctrl-icon">🌙</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Dimmer Quarto</div>
              <div class="ctrl-state" id="st_dimmer_quarto">DESLIGADO</div>
            </div>
          </button>

          <button class="ctrl-btn" id="btn_luz_estudo" onclick="alternarIoT('luz_estudo')">
            <div class="ctrl-icon">💡</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Luz de Estudo</div>
              <div class="ctrl-state" id="st_luz_estudo">DESLIGADO</div>
            </div>
          </button>
        </div>
      </div>

      <!-- COLUNA 2: BRAÇO ROBÓTICO 4-DOF -->
      <div class="column-card">
        <div class="col-header">
          <span>🦾 BRAÇO ROBÓTICO</span>
          <span id="oledFaceTxt">OLED: NEUTRO</span>
        </div>

        <div class="btn-stack">
          <button class="ctrl-btn" onclick="moverBraco('acenar')">
            <div class="ctrl-icon">👋</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Acenar</div>
              <div class="ctrl-state">Saudação</div>
            </div>
          </button>

          <button class="ctrl-btn" onclick="moverBraco('apontar')">
            <div class="ctrl-icon">👉</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Apontar</div>
              <div class="ctrl-state">Foco / Direção</div>
            </div>
          </button>

          <button class="ctrl-btn" onclick="moverBraco('pronto')">
            <div class="ctrl-icon">⚡</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Prontidão</div>
              <div class="ctrl-state">Posição Alerta</div>
            </div>
          </button>

          <button class="ctrl-btn" onclick="moverBraco('repouso')">
            <div class="ctrl-icon">💤</div>
            <div class="ctrl-info">
              <div class="ctrl-name">Repouso</div>
              <div class="ctrl-state">Recolher Servos</div>
            </div>
          </button>
        </div>
      </div>

    </div>

    <!-- PAINEL DIREITO: REATOR ARC & AVATAR DA PERSONALIDADE ATIVA -->
    <div class="right-panel" id="reactorPanel">

      <div class="right-top">
        <span class="persona-pill" id="personaBadge">🎩 J.A.R.V.I.S.</span>
        <div class="mini-bar">
          <button class="icon-btn" id="btnCamToggle" onclick="alternarCamera3D()" title="Ativar/Desativar Webcam Impressora 3D em segundo plano">📷 Cam 3D</button>
          <button class="icon-btn" id="btnAudioUnlock" onclick="ativarAudio()">🔊 Som</button>
        </div>
      </div>

      <!-- REATOR ARC COM AVATAR DINÂMICO -->
      <div class="reactor-stage" onclick="alternarEscutaVoz()" title="Toque no Reator para falar com o assistente">
        <div class="ring-outer"></div>
        <div class="ring-mid"></div>
        <div class="arc-core">
          <div class="avatar-svg-wrap" id="avatarContainer"></div>
        </div>
      </div>

      <!-- NOME DA PERSONA + RESPOSTA CURTA + TROCA RÁPIDA DE PERSONA -->
      <div class="persona-footer">
        <div class="persona-name" id="personaName">J.A.R.V.I.S.</div>
        <div class="persona-sub" id="personaSubtitle">Toque no Reator para falar</div>

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
  // Temas de cores e Avatares SVG exclusivos para cada Personalidade!
  const PERSONA_THEMES = {
    JARVIS: {
      color: "#00f0ff",
      glow: "rgba(0, 240, 255, 0.4)",
      dim: "rgba(0, 240, 255, 0.16)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#00f0ff" stroke-width="4">
              <circle cx="50" cy="50" r="38" stroke-dasharray="12 6"/>
              <polygon points="50,22 76,68 24,68" stroke-width="3.5" fill="rgba(0,240,255,0.18)"/>
              <circle cx="50" cy="52" r="10" fill="#ffffff"/>
            </svg>`
    },
    FRIDAY: {
      color: "#ff7b00",
      glow: "rgba(255, 123, 0, 0.42)",
      dim: "rgba(255, 123, 0, 0.18)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#ff7b00" stroke-width="4">
              <polygon points="50,10 88,30 88,70 50,90 12,70 12,30" fill="rgba(255,123,0,0.15)"/>
              <path d="M28 45 L45 52 L28 58 M72 45 L55 52 L72 58" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
              <circle cx="50" cy="52" r="7" fill="#ff7b00"/>
            </svg>`
    },
    GIDEON: {
      color: "#ffd000",
      glow: "rgba(255, 208, 0, 0.42)",
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
      glow: "rgba(0, 255, 136, 0.38)",
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
      glow: "rgba(255, 30, 56, 0.55)",
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
      glow: "rgba(255, 204, 0, 0.45)",
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
      glow: "rgba(43, 124, 255, 0.45)",
      dim: "rgba(43, 124, 255, 0.2)",
      svg: `<svg viewBox="0 0 100 100" fill="none" stroke="#2b7cff" stroke-width="3.5">
              <path d="M20 58 A30 30 0 0 1 80 58 Z" fill="rgba(43,124,255,0.22)"/>
              <rect x="20" y="58" width="60" height="22" rx="3" fill="rgba(255,255,255,0.1)"/>
              <circle cx="50" cy="40" r="9" fill="#0d1b33" stroke="#fff" stroke-width="3"/>
              <circle cx="64" cy="48" r="4" fill="#ff2a55" stroke="none"/>
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
    fetch('/api/audio/played', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id})}).catch(() => {});
    tocarProximo();
  }
  audioPlayer.addEventListener('ended', concluirAudio);
  audioPlayer.addEventListener('error', () => { console.warn('Falha ao reproduzir áudio.'); concluirAudio(); });
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

      document.getElementById('clockTxt').innerText = data.time || '--:--';
      document.getElementById('oledFaceTxt').innerText = 'OLED: ' + (data.hud.face || 'NEUTRO');

      // Atualiza Avatar e Cores da Personalidade Ativa
      if (data.persona) {
        aplicarTemaPersona(data.persona);
      }

      // Subtítulo dinâmico
      const subEl = document.getElementById('personaSubtitle');
      if (!escutando) {
        subEl.innerText = data.hud.last_response || data.persona.titulo || 'Pronto';
      }

      const rPanel = document.getElementById('reactorPanel');
      if (data.hud.speaking) {
        rPanel.classList.add('speaking');
      } else {
        rPanel.classList.remove('speaking');
      }

      (data.hud.pending_audio || []).forEach(enfileirarAudio);

      // Atualiza os 3 botões IoT
      const iot = data.iot || {};
      ['tomada_impressora', 'dimmer_quarto', 'luz_estudo'].forEach(chave => {
        const d = iot[chave];
        const btn = document.getElementById('btn_' + chave);
        const st = document.getElementById('st_' + chave);
        if (d && btn && st) {
          const ligado = (d.status === 'ligado');
          btn.classList.toggle('on', ligado);
          st.innerText = ligado ? 'LIGADO' : 'DESLIGADO';
        }
      });
    } catch (e) {}
  }

  async function alternarIoT(chave) {
    ativarAudio();
    await fetch('/api/iot', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dispositivo: chave, acao: 'alternar'})
    });
    carregarEstado();
  }

  async function moverBraco(acao) {
    ativarAudio();
    await fetch('/api/arm', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({acao})
    });
    carregarEstado();
  }

  async function mudarPersona(idPersona) {
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

  function setSub(txt) { document.getElementById('personaSubtitle').innerText = txt; }

  function pararGravacao(enviar) {
    if (!gravacao) return;
    const g = gravacao;
    gravacao = null;
    escutando = false;
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
    if (gravacao) { pararGravacao(true); return; }

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

  // ---- AUTO-ATIVAÇÃO DE SOM E CÂMERA POR PADRÃO ----
  function autoAtivarTudo() {
    if (!audioLiberado) ativarAudio();
    if (!camStream) ligarCamera3D();
  }

  // Tenta ativar assim que carregar o script e a página
  setTimeout(autoAtivarTudo, 300);
  window.addEventListener('DOMContentLoaded', autoAtivarTudo);
  window.addEventListener('load', autoAtivarTudo);

  // Destrave universal garantido no primeiro toque em qualquer lugar da tela (exigência do Safari)
  ['touchstart', 'touchend', 'pointerdown', 'click'].forEach(evt => {
    window.addEventListener(evt, autoAtivarTudo, { passive: true });
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
_RE_AUDIO = re.compile(r"^/api/audio/(\d+)\.mp3$")


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
        tok = self.headers.get("X-Jarvis-Token", "")
        auth = self.headers.get("Authorization", "")
        if not tok and auth.startswith("Bearer "):
            tok = auth[7:].strip()
        if tok and _igual(tok, DOCK_TOKEN):
            return True
        ck = self._cookie(_COOKIE_NOME)
        if ck and _igual(ck, _COOKIE_VALOR):
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
        self._responder(status, dados[inicio:fim + 1], "audio/mpeg", extra)

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
                    flags = "Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000" + ("; Secure" if self._https else "")
                    self._responder(302, b"", None, [("Location", "/"), ("Set-Cookie", f"{_COOKIE_NOME}={_COOKIE_VALOR}; {flags}")])
                    return
                _registrar_falha(self.client_address[0])
            if self._credencial_valida():
                self._responder(200, HTML_STARK_HUD.encode("utf-8"), "text/html; charset=utf-8")
            else:
                pagina = ("<meta name=viewport content='width=device-width'><body style='background:#000;color:#0cf;"
                          "font-family:sans-serif;padding:2em'><h2>J.A.R.V.I.S.</h2><p>Acesso restrito. "
                          "Abra o endereço com <code>?token=SEU_TOKEN</code> uma vez.</p>")
                self._responder(401, pagina.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path.startswith("/camera/"):
            # OctoPrint local consome via loopback sem token; acessos remotos exigem token (?token= ou cookie)
            if self.client_address[0] not in LOOPBACK_IPS and not self._exigir_auth(permitir_query=True):
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
    cert = os.getenv("DOCK_CERT") or os.path.join(BASE_DIR, "stark_dock_cert.pem")
    key = os.getenv("DOCK_KEY") or os.path.join(BASE_DIR, "stark_dock_key.pem")

    sans_ip = ["127.0.0.1", ip_local] + ([ip_ts] if ip_ts else []) + [x for x in os.getenv("DOCK_EXTRA_IPS", "").split(",") if x.strip()]
    sans_dns = [socket.gethostname(), "localhost"] + [x for x in os.getenv("DOCK_EXTRA_DNS", "").split(",") if x.strip()]

    if os.getenv("DOCK_ENABLE_HTTP", "0") == "1":
        try:
            srv = _ServidorBase((bind, http_port), StarkDockHTTPHandler)
            threading.Thread(target=srv.serve_forever, daemon=True, name="StarkDockHTTP").start()
            print(f"⚠️ [STARK DOCK] HTTP ativo em {http_port} (token em texto puro na rede; use só em LAN confiável).")
        except OSError as e:
            print(f"⚠️ [STARK DOCK] Porta HTTP {http_port} indisponível: {e}")

    https_ativo = False
    if gerar_certificado_https_local(cert, key, sans_ip, sans_dns):
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
        for ip in [ip_local] + ([ip_ts] if ip_ts else []):
            print(f"   👉 https://{ip}:{https_port}")
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
