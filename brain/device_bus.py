"""
J.A.R.V.I.S. - Device Bus & Auto-Discovery Manager
Gerencia a descoberta dinâmica e o inventário de hardware Plug-and-Play no servidor.
Sonda portas USB seriais (/dev/ttyUSB*, /dev/ttyACM*, /dev/serial/by-id/*)
utilizando o protocolo de auto-apresentação (CMD:WHO_ARE_YOU e M115).
"""

import os
import glob
import time
import threading
from typing import Dict, Optional, Any

class DeviceBus:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DeviceBus, cls).__new__(cls)
                cls._instance._inicializado = False
            return cls._instance

    def __init__(self):
        if self._inicializado:
            return
        self._inicializado = True
        self._dispositivos: Dict[str, Dict[str, Any]] = {}
        self._portas_ocupadas = set()
        self._bus_lock = threading.Lock()
        self._thread_monitor = None
        self._rodando = False

    def iniciar(self, intervalo_s: float = 12.0):
        """Inicia o monitor de auto-descoberta em segundo plano."""
        if self._rodando:
            return
        self._rodando = True
        self.escanear_tudo()
        self._thread_monitor = threading.Thread(
            target=self._loop_monitor,
            args=(intervalo_s,),
            name="JarvisDeviceBusMonitor",
            daemon=True
        )
        self._thread_monitor.start()

    def parar(self):
        self._rodando = False

    def _loop_monitor(self, intervalo: float):
        while self._rodando:
            time.sleep(intervalo)
            try:
                self.escanear_tudo()
            except Exception as e:
                # Log silencioso para resiliência contínua
                pass

    def listar_dispositivos(self) -> Dict[str, Dict[str, Any]]:
        with self._bus_lock:
            return dict(self._dispositivos)

    def obter_dispositivo(self, tipo: str) -> Optional[Dict[str, Any]]:
        with self._bus_lock:
            return self._dispositivos.get(tipo)

    def obter_porta(self, tipo: str) -> Optional[str]:
        dev = self.obter_dispositivo(tipo)
        return dev["porta"] if dev else None

    def registrar_porta_externa(self, tipo: str, porta: str):
        """Permite registrar uma porta gerenciada externamente (ex: OctoPrint)."""
        with self._bus_lock:
            real = os.path.realpath(porta)
            self._portas_ocupadas.add(real)
            self._dispositivos[tipo] = {
                "tipo": tipo,
                "porta": porta,
                "caminho_real": real,
                "origem": "externo",
                "atualizado_em": time.time()
            }

    def escanear_tudo(self) -> Dict[str, Dict[str, Any]]:
        """Varre todas as portas USB do sistema e identifica quem é quem."""
        import serial
        import serial.tools.list_ports

        todas_portas = [p.device for p in serial.tools.list_ports.comports()]
        candidatas_acm = sorted(glob.glob("/dev/ttyACM*"))
        candidatas_usb = sorted(glob.glob("/dev/ttyUSB*"))
        candidatas_by_id = sorted(glob.glob("/dev/serial/by-id/*"))

        # Junta todas sem duplicar caminhos reais
        portas_verificar = []
        vistos = set()
        for p in candidatas_by_id + candidatas_usb + candidatas_acm + todas_portas:
            real = os.path.realpath(p)
            if real not in vistos and os.path.exists(real):
                vistos.add(real)
                portas_verificar.append(p)

        # Adiciona proteção para a porta configurada no OctoPrint
        porta_octo = os.getenv("OCTOPRINT_SERIAL_PORT", "").strip()
        if porta_octo and porta_octo.lower() not in ("none", "", "disabled"):
            real_octo = os.path.realpath(porta_octo)
            if "printer" not in self._dispositivos:
                self.registrar_porta_externa("printer", porta_octo)

        for porta in portas_verificar:
            real = os.path.realpath(porta)
            
            # Se a porta já foi identificada e continua ativa, pula
            ja_conhecida = False
            with self._bus_lock:
                for k, v in self._dispositivos.items():
                    if v.get("caminho_real") == real:
                        ja_conhecida = True
                        break
            if ja_conhecida:
                continue

            # Se for o ESP32-S3 Dock, identifica diretamente pelo nome/ID sem abrir a serial (não interrompe o dock_manager)
            info_porta = (porta + " " + real).lower()
            if "espressif" in info_porta or "esp32" in info_porta or "jtag" in info_porta or "ttyacm" in info_porta:
                with self._bus_lock:
                    self._dispositivos["dock"] = {
                        "tipo": "dock",
                        "id": "ESP32_S3_DOCK",
                        "porta": porta,
                        "caminho_real": real,
                        "baud": 115200,
                        "detalhes": "ESP32-S3 Dock Touch 4.0\"",
                        "atualizado_em": time.time()
                    }
                    self._portas_ocupadas.add(real)
                    print(f"🤖 [DEVICE BUS] Dock ESP32-S3 identificado e preservado: {porta}", flush=True)
                continue

            # Tenta identificar o dispositivo
            info = self._sondar_dispositivo(porta)
            if info:
                with self._bus_lock:
                    tipo = info["tipo"]
                    self._dispositivos[tipo] = info
                    self._portas_ocupadas.add(real)
                    print(f"🤖 [DEVICE BUS] Novo dispositivo conectado e identificado: {tipo.upper()} na porta {porta} ({info.get('detalhes', '')})")

        return self.listar_dispositivos()

    def _sondar_dispositivo(self, porta: str) -> Optional[Dict[str, Any]]:
        """Abre a porta de forma não intrusiva para descobrir a identidade do hardware."""
        import serial

        real = os.path.realpath(porta)
        baudrates = [115200, 250000]

        for baud in baudrates:
            s = None
            try:
                s = serial.Serial(porta, baud, timeout=0.8, write_timeout=0.8)
                
                # 1. Escuta se a placa enviou algo no reset do DTR
                t_fim = time.time() + 2.2
                buffer = ""
                while time.time() < t_fim:
                    if s.in_waiting > 0:
                        l = s.readline().decode("utf-8", errors="ignore").strip()
                        buffer += " " + l
                        if "JARVIS_ARM" in l or "JARVIS_ONLINE_READY" in l:
                            s.close()
                            return {
                                "tipo": "arm",
                                "id": "JARVIS_ARM",
                                "porta": porta,
                                "caminho_real": real,
                                "baud": baud,
                                "detalhes": "Braço Robótico e Face OLED V3",
                                "atualizado_em": time.time()
                            }
                        if "FIRMWARE_NAME" in l or "Marlin" in l:
                            s.close()
                            return {
                                "tipo": "printer",
                                "id": "CREALITY_ENDER3",
                                "porta": porta,
                                "caminho_real": real,
                                "baud": baud,
                                "detalhes": "Impressora 3D Marlin",
                                "atualizado_em": time.time()
                            }
                    time.sleep(0.04)

                # 2. Pergunta ao ecossistema J.A.R.V.I.S.: CMD:WHO_ARE_YOU
                s.write(b"CMD:WHO_ARE_YOU\n")
                s.flush()
                time.sleep(0.15)
                resp = s.read(s.in_waiting or 128).decode("utf-8", errors="ignore")
                
                if "DEVICE:JARVIS_ARM" in resp or "ACK:JARVIS_ARM_PONG" in resp:
                    s.close()
                    return {
                        "tipo": "arm",
                        "id": "JARVIS_ARM",
                        "porta": porta,
                        "caminho_real": real,
                        "baud": baud,
                        "detalhes": "Braço Robótico e Face OLED V3",
                        "atualizado_em": time.time()
                    }
                elif "DEVICE:JARVIS_DOCK" in resp:
                    s.close()
                    return {
                        "tipo": "dock",
                        "id": "JARVIS_DOCK",
                        "porta": porta,
                        "caminho_real": real,
                        "baud": baud,
                        "detalhes": "Dock de Bancada & HUD Controller",
                        "atualizado_em": time.time()
                    }
                elif "DEVICE:" in resp:
                    # Qualquer novo dispositivo futuro que use o protocolo J.A.R.V.I.S.!
                    partes = resp.strip().split(":")
                    subtipo = partes[1].lower() if len(partes) > 1 else "generico"
                    s.close()
                    return {
                        "tipo": subtipo,
                        "id": resp.strip(),
                        "porta": porta,
                        "caminho_real": real,
                        "baud": baud,
                        "detalhes": f"Módulo JARVIS ({subtipo})",
                        "atualizado_em": time.time()
                    }

                # 3. Pergunta à impressora 3D se é Marlin: M115
                s.write(b"M115\n")
                s.flush()
                time.sleep(0.2)
                resp_m = s.read(s.in_waiting or 128).decode("utf-8", errors="ignore")
                if "FIRMWARE_NAME" in resp_m or "Marlin" in resp_m or "MACHINE_TYPE" in resp_m:
                    s.close()
                    return {
                        "tipo": "printer",
                        "id": "CREALITY_ENDER3",
                        "porta": porta,
                        "caminho_real": real,
                        "baud": baud,
                        "detalhes": "Impressora 3D Marlin",
                        "atualizado_em": time.time()
                    }

                s.close()
            except Exception:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

        return None

device_bus = DeviceBus()
