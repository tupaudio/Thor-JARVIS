"""
system_service.py — Telemetria e identificação real de hardware (Debian/Linux) do J.A.R.V.I.S.

Substitui o antigo windows_service.py. Lê diretamente do kernel (/sys, /proc, /run/udev)
e do psutil; não chama PowerShell/WMIC/cmd e não tem nenhuma dependência de Windows.

Pontos importantes:
  * /sys/block/<disco>/device/model é TRUNCADO em 16 caracteres para discos SATA
    (o campo T10 do SCSI INQUIRY), então "LITEON CV8-8E256-11" aparece como
    "LITEON CV8-8E256". O nome completo vem do banco do udev (/run/udev/data/b<maj>:<min>,
    chave ID_MODEL_ENC), com lsblk (JSON) e sysfs como degraus de fallback.
  * Nada aqui devolve texto "fixo" quando a detecção falha: se não souber, diz que não conseguiu ler.
  * Todas as chamadas externas têm timeout curto e há cache TTL para não repetir I/O a cada poll.
"""

import os
import re
import json
import glob
import time
import socket
import platform
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import psutil

_PREFIXOS_IGNORADOS = ("loop", "ram", "sr", "dm-", "md", "zram", "nbd", "fd")


def _ler(caminho: str, padrao: str = "") -> str:
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return padrao


def _gb_decimal(n_bytes: int) -> str:
    """Tamanho comercial (256 GB, 1 TB), que é o que o usuário espera ouvir."""
    gb = n_bytes / 1e9
    if gb >= 1000:
        tb = gb / 1000
        return f"{tb:.0f}TB" if abs(tb - round(tb)) < 0.05 else f"{tb:.1f}TB"
    return f"{round(gb):d}GB"


def _gib(n_bytes: int, casas: int = 1) -> float:
    return round(n_bytes / (1024 ** 3), casas)


class _Cache:
    """Cache TTL minúsculo e thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._dados = {}

    def obter(self, chave: str, ttl: float, produtor):
        agora = time.monotonic()
        with self._lock:
            item = self._dados.get(chave)
            if item and agora - item[0] < ttl:
                return item[1]
        valor = produtor()  # fora do lock: nunca segura lock durante I/O
        with self._lock:
            self._dados[chave] = (agora, valor)
        return valor


class SystemService:
    def __init__(self):
        base = Path(__file__).resolve().parent
        self.webcam_path = str(base / "webcam_jarvis.jpg")
        self._cache = _Cache()
        psutil.cpu_percent(interval=None)  # prepara a linha de base do contador de CPU

    # ------------------------------------------------------------------ discos
    @staticmethod
    def _udev_model(nome_bloco: str) -> str:
        """Nome completo do modelo, como o udev/lsblk enxergam (sem truncar em 16 chars)."""
        majmin = _ler(f"/sys/block/{nome_bloco}/dev")
        if not majmin:
            return ""
        dados = _ler(f"/run/udev/data/b{majmin}")
        enc = plain = ""
        for linha in dados.splitlines():
            if linha.startswith("E:ID_MODEL_ENC="):
                enc = linha.split("=", 1)[1]
            elif linha.startswith("E:ID_MODEL="):
                plain = linha.split("=", 1)[1]
        if enc:
            return re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), enc).strip()
        return plain.replace("_", " ").strip()

    @staticmethod
    def _lsblk_modelos() -> dict:
        try:
            r = subprocess.run(
                ["lsblk", "-J", "-d", "-n", "-o", "NAME,MODEL"],
                capture_output=True, text=True, timeout=2,
            )
            if r.returncode == 0:
                return {d["name"]: (d.get("model") or "").strip()
                        for d in json.loads(r.stdout).get("blockdevices", [])}
        except Exception:
            pass
        return {}

    @staticmethod
    def _transporte(nome: str, caminho_real: str) -> str:
        if nome.startswith("nvme"):
            return "NVMe"
        if nome.startswith("mmcblk"):
            return "eMMC/SD"
        if re.search(r"/usb\d+/", caminho_real):
            return "USB"
        if re.search(r"/ata\d+/", caminho_real):
            return "SATA"
        if "virtio" in caminho_real:
            return "VirtIO"
        return ""

    @staticmethod
    def _bloco_do_root() -> str:
        """Nome do disco físico que contém a partição montada em '/', ou '' se não der para saber."""
        try:
            dev = next((p.device for p in psutil.disk_partitions(all=False) if p.mountpoint == "/"), "")
            nome = os.path.basename(os.path.realpath(dev)) if dev else ""
            if not nome:
                return ""
            real = os.path.realpath(f"/sys/class/block/{nome}")  # .../block/sda/sda1  ou  .../block/sda
            pai = os.path.basename(os.path.dirname(real))
            return nome if pai == "block" else pai
        except Exception:
            return ""

    def listar_discos(self) -> list:
        def _produzir():
            lsblk = None
            raiz = self._bloco_do_root()
            discos = []
            for caminho in sorted(glob.glob("/sys/block/*")):
                nome = os.path.basename(caminho)
                if nome.startswith(_PREFIXOS_IGNORADOS):
                    continue
                setores = _ler(f"{caminho}/size", "0")
                try:
                    tamanho = int(setores) * 512
                except ValueError:
                    tamanho = 0
                if tamanho < 100 * 1000 ** 2:   # ignora dispositivos minúsculos/virtuais (<100 MB)
                    continue

                modelo = self._udev_model(nome)
                if not modelo:
                    if lsblk is None:
                        lsblk = self._lsblk_modelos()
                    modelo = lsblk.get(nome, "")
                if not modelo:
                    modelo = _ler(f"{caminho}/device/model")  # truncado em 16 chars: último recurso
                    vendor = _ler(f"{caminho}/device/vendor")
                    if vendor and vendor.upper() != "ATA" and not vendor.startswith("0x"):
                        modelo = f"{vendor} {modelo}".strip()

                real = os.path.realpath(caminho)
                transporte = self._transporte(nome, real)
                rotacional = _ler(f"{caminho}/queue/rotational", "")
                if nome.startswith("nvme") or rotacional == "0":
                    tipo = "SSD"
                elif rotacional == "1":
                    tipo = "HDD"
                else:
                    tipo = "Disco"
                discos.append({
                    "dev": f"/dev/{nome}", "nome": nome, "modelo": modelo or "modelo não informado",
                    "transporte": transporte, "tipo": tipo, "bytes": tamanho,
                    "tamanho": _gb_decimal(tamanho), "raiz": nome == raiz,
                })
            return discos

        return self._cache.obter("discos", 60.0, _produzir)

    def obter_modelo_disco(self) -> str:
        """Ex.: 'LITEON CV8-8E256-11 SATA SSD 256GB'. Vários discos são separados por '; '."""
        discos = self.listar_discos()
        if not discos:
            return "não consegui ler os discos físicos em /sys/block"
        # Disco do sistema primeiro; se houver só um, devolve exatamente o formato esperado.
        discos = sorted(discos, key=lambda d: not d["raiz"])
        partes = []
        for d in discos:
            texto = " ".join(x for x in (d["modelo"], d["transporte"], d["tipo"], d["tamanho"]) if x)
            if len(discos) > 1 and d["raiz"]:
                texto += " (sistema)"
            partes.append(texto)
        return "; ".join(partes)

    # --------------------------------------------------------- máquina e CPU
    def obter_modelo_maquina(self) -> str:
        """Ex.: 'Dell Inc. OptiPlex 3060'."""
        vendor = _ler("/sys/class/dmi/id/sys_vendor")
        produto = _ler("/sys/class/dmi/id/product_name")
        texto = f"{vendor} {produto}".strip()
        return texto or "máquina não identificada (DMI indisponível)"

    def obter_modelo_processador(self) -> str:
        for linha in _ler("/proc/cpuinfo").splitlines():
            if linha.lower().startswith("model name"):
                nome = linha.split(":", 1)[1].strip()
                return re.sub(r"\s+", " ", nome.replace("(R)", "").replace("(TM)", "")).strip()
        return platform.processor() or platform.machine()

    def obter_temperatura_cpu(self):
        try:
            sensores = psutil.sensors_temperatures()
            for chave in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                leituras = sensores.get(chave) or []
                if leituras:
                    return round(max(l.current for l in leituras), 0)
        except Exception:
            pass
        valores = []
        for zona in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                valores.append(int(_ler(zona)) / 1000)
            except ValueError:
                pass
        return round(max(valores), 0) if valores else None

    @staticmethod
    def _so_pretty() -> str:
        for linha in _ler("/etc/os-release").splitlines():
            if linha.startswith("PRETTY_NAME="):
                return linha.split("=", 1)[1].strip().strip('"')
        return f"{platform.system()} {platform.release()}"

    # ------------------------------------------------------------------ Ollama
    def obter_status_ollama(self) -> dict:
        from ai_router import ai_router  # import tardio: evita ciclo de importação
        return ai_router.status_ollama()

    # ------------------------------------------------------------- relatórios
    @staticmethod
    def _uptime() -> str:
        delta = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        h, resto = divmod(delta.seconds, 3600)
        m = resto // 60
        return f"{delta.days}d {h}h {m}m" if delta.days else f"{h}h {m}m"

    def obter_telemetria(self) -> str:
        """Resposta curta e falável sobre o estado do servidor."""
        try:
            cpu = psutil.cpu_percent(interval=0.25)
            ram = psutil.virtual_memory()
            disco = psutil.disk_usage("/")
            temp = self.obter_temperatura_cpu()
            ol = self.obter_status_ollama()
            carga = os.getloadavg()[0]
            linhas = [
                f"Servidor {socket.gethostname()}, {self._so_pretty()}, senhor:",
                f"• Processador: {cpu:.0f}% de uso, carga {carga:.2f}"
                + (f", {temp:.0f} graus" if temp is not None else ""),
                f"• Memória: {ram.percent:.0f}% ({_gib(ram.used)} de {_gib(ram.total)} GB)",
                f"• Armazenamento: {self.obter_modelo_disco()}",
                f"• Partição raiz: {_gib(disco.free)} GB livres de {_gib(disco.total)} GB ({disco.percent:.0f}% ocupado)",
                f"• Ollama: {ol['resumo']}",
                f"• Ligado há {self._uptime()}",
            ]
            return "\n".join(linhas)
        except Exception as e:
            return f"Não consegui coletar a telemetria do servidor: {e}"

    def obter_detalhes_hardware(self) -> str:
        """Relatório de componentes (modelo da máquina, CPU, RAM, discos, Ollama)."""
        try:
            ram = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disco = psutil.disk_usage("/")
            freq = psutil.cpu_freq()
            fisicos = psutil.cpu_count(logical=False) or "?"
            logicos = psutil.cpu_count(logical=True) or "?"
            ol = self.obter_status_ollama()
            linhas = [
                "Especificações do servidor, senhor:",
                f"• Equipamento: {self.obter_modelo_maquina()}",
                f"• Sistema: {self._so_pretty()}, kernel {platform.release()}",
                f"• Processador: {self.obter_modelo_processador()}"
                + (f" a {freq.current:.0f} MHz" if freq and freq.current else "")
                + f" ({fisicos} núcleos, {logicos} threads)",
                f"• Memória: {_gib(ram.total)} GB, mais {_gib(swap.total)} GB de swap",
                f"• Armazenamento físico: {self.obter_modelo_disco()}",
                f"• Partição raiz (/): {_gib(disco.free)} GB livres de {_gib(disco.total)} GB",
                f"• Ollama: {ol['resumo']}",
            ]
            return "\n".join(linhas)
        except Exception as e:
            return f"Não consegui ler as especificações de hardware: {e}"

    def obter_armazenamento(self) -> str:
        """Resposta direta para 'qual o modelo do HD/SSD?'."""
        discos = self.listar_discos()
        if not discos:
            return "Não consegui ler os discos físicos do servidor, senhor."
        raiz = next((d for d in discos if d["raiz"]), discos[0])
        uso = psutil.disk_usage("/")
        frase = (f"O armazenamento do sistema é um {raiz['modelo']}, {raiz['transporte']} {raiz['tipo']} "
                 f"de {raiz['tamanho']}, senhor. A partição raiz está {uso.percent:.0f}% ocupada, "
                 f"com {_gib(uso.free)} GB livres.")
        outros = [d for d in discos if d is not raiz]
        if outros:
            frase += " Também há: " + "; ".join(f"{d['modelo']} {d['tipo']} {d['tamanho']}" for d in outros) + "."
        return re.sub(r"\s{2,}", " ", frase)

    def obter_status_ollama_texto(self) -> str:
        ol = self.obter_status_ollama()
        return f"Ollama: {ol['resumo']}, senhor."

    # ----------------------------------------------------------------- câmera
    def tirar_foto_camera(self) -> str:
        """Foto da câmera do iPhone (dock) ou, se houver, de uma webcam V4L2 local. Retorna o caminho ou ''."""
        try:
            from camera_manager import camera_manager
            caminho = camera_manager.capturar_foto(self.webcam_path)
            if caminho and os.path.exists(caminho):
                return caminho
        except Exception as e:
            print(f"⚠️ [CAMERA] {e}")
        return ""

    def tirar_foto_e_enviar_telegram(self, legenda: str = "") -> str:
        caminho = self.tirar_foto_camera()
        if not caminho:
            return "A câmera do iPhone precisa estar com o feed ativo ('Cam 3D'), senhor."
        from telegram_service import telegram_service
        legenda = legenda or f"📸 Captura do dock em {datetime.now():%d/%m/%Y às %H:%M}."
        ok = telegram_service.enviar_foto(caminho_arquivo=caminho, legenda=legenda)
        return "Foto enviada ao seu Telegram, senhor." if ok else "Capturei a imagem, mas o envio ao Telegram falhou."

    def analisar_ambiente_camera(self, pergunta: str = "") -> str:
        caminho = self.tirar_foto_camera()
        if not caminho:
            return "A câmera do iPhone precisa estar com o feed ativo para a análise visual, senhor."
        try:
            from PIL import Image
            from gemini_session import gemini_session
            with Image.open(caminho) as img:
                img.load()
                prompt = pergunta or "Descreva o que a câmera do dock está vendo. Seja conciso."
                return gemini_session.gerar_com_imagem(prompt, img) or "Visão processada, senhor."
        except Exception as e:
            return f"Não consegui analisar a imagem: {e}"


system_service = SystemService()


if __name__ == "__main__":
    print(system_service.obter_modelo_maquina())
    print(system_service.obter_modelo_processador())
    print(system_service.obter_modelo_disco())
    print(system_service.obter_armazenamento())
    print(system_service.obter_telemetria())
    print(system_service.obter_detalhes_hardware())
