"""
Módulo de Comunicação Serial com o Arduino UNO para o J.A.R.V.I.S.
Gerencia a conexão bidirecional via USB/Serial (pyserial) com o braço mecânico
e o display OLED 1.5" (firmware/arduino_arm/arduino_arm.ino).
Inclui fallback automático e transparente para o simulador virtual no terminal.
"""

import os
import sys
import time
import threading
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class SerialCommController:
    """Controlador serial com autodeteção e sincronização Arduino + Simulador."""
    def __init__(self):
        self.porta_configurada = os.getenv("ARDUINO_PORT", "COM3")
        try:
            self.baudrate = int(os.getenv("ARDUINO_BAUD", "115200"))
        except ValueError:
            self.baudrate = 115200

        self.esp32_ip = os.getenv("ESP32_IP", "").strip()
        self._serial = None
        self._lock = threading.Lock()
        self.conectado = False
        self._tentou_conectar = False
        self._simulator = None

    def _get_simulator(self):
        """Lazy loading do simulador para evitar import circular."""
        if self._simulator is None:
            from hardware_simulator import HardwareSimulator
            self._simulator = HardwareSimulator()
        return self._simulator

    def conectar(self) -> bool:
        """Tenta abrir a comunicação serial com a placa Arduino."""
        with self._lock:
            if self.conectado and self._serial is not None and self._serial.is_open:
                return True

            try:
                import serial
                import serial.tools.list_ports

                todas_portas = list(serial.tools.list_ports.comports())
                
                # Filtra portas virtuais de Bluetooth para evitar hang do Windows RFCOMM
                portas_usb_reais = []
                for p in todas_portas:
                    desc = (p.description or "").lower()
                    hwid = (p.hwid or "").lower()
                    if "bluetooth" in desc or "bthmodem" in hwid:
                        continue
                    portas_usb_reais.append(p)

                porta_alvo = None

                # 1. Procura portas que sejam reconhecidamente Arduino ou conversores USB-Serial
                for p in portas_usb_reais:
                    desc = (p.description or "").lower()
                    hwid = (p.hwid or "").lower()
                    if any(k in desc or k in hwid for k in ["arduino", "ch340", "ch341", "cp210", "ftdi", "usb-serial", "usb serial"]):
                        porta_alvo = p.device
                        break

                # 2. Se a porta configurada no .env for uma porta USB real presente
                if not porta_alvo and self.porta_configurada:
                    for p in portas_usb_reais:
                        if p.device.upper() == self.porta_configurada.upper():
                            porta_alvo = p.device
                            break

                # Se nenhuma porta USB real for encontrada
                if not porta_alvo:
                    if not self._tentou_conectar:
                        portas_desc = [f"{p.device} ({p.description})" for p in todas_portas]
                        desc_str = ", ".join(portas_desc) if portas_desc else "nenhuma porta COM disponível"
                        print(f"ℹ️ [SERIAL] Arduino físico não detectado via USB ({desc_str}). Modo Simulador Virtual ativo.")
                        self._tentou_conectar = True
                    self.conectado = False
                    return False

                print(f"🔌 [SERIAL] Conectando ao Arduino na porta {porta_alvo} ({self.baudrate} baud)...")
                self._serial = serial.Serial(porta_alvo, self.baudrate, timeout=2.0)
                time.sleep(2.0)
                self._serial.reset_input_buffer()
                self.conectado = True
                self._tentou_conectar = True
                print(f"✅ [SERIAL] Arduino UNO conectado e sincronizado com sucesso na porta {porta_alvo}!")
                return True

            except Exception as e:
                if not self._tentou_conectar:
                    print(f"⚠️ [SERIAL] Falha ao conectar ao Arduino: {e}. Alternando para simulador.")
                    self._tentou_conectar = True
                self.conectado = False
                return False

    def is_conectado(self) -> bool:
        return self.conectado and self._serial is not None and self._serial.is_open

    def enviar_comando(self, comando: str, aguardar_ack: bool = True, timeout: float = 3.0) -> str:
        """Envia uma string de comando para o Arduino via Wi-Fi (ESP32-S3) ou Serial USB."""
        # 1. Tenta envio sem fio via Satélite ESP32-S3 se IP estiver configurado no .env
        if self.esp32_ip:
            try:
                import requests
                url = f"http://{self.esp32_ip}/api/arm"
                res = requests.post(url, json={"cmd": comando.strip()}, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("arduino_ack", "OK_WIFI")
            except Exception:
                pass

        # 2. Fallback para conexão Serial USB direta com o Arduino
        if not self.is_conectado():
            if not self.conectar():
                return ""

        with self._lock:
            try:
                cmd_bytes = comando.strip().encode("utf-8") + b"\n"
                self._serial.write(cmd_bytes)
                self._serial.flush()

                if aguardar_ack:
                    tempo_limite = time.time() + timeout
                    while time.time() < tempo_limite:
                        if self._serial.in_waiting > 0:
                            linha = self._serial.readline().decode("utf-8", errors="ignore").strip()
                            if linha:
                                return linha
                        time.sleep(0.05)
                return "OK"
            except Exception as e:
                print(f"⚠️ [SERIAL] Erro ao transmitir comando '{comando}': {e}")
                self.conectado = False
                return ""

    def mover_braco(self, acao: str, detalhes: str = "") -> str:
        """
        Move o braço robótico físico se conectado e atualiza o terminal.
        """
        acao_limpa = acao.lower().strip()
        cmd = None

        if any(w in acao_limpa for w in ["aceno", "acenar", "wave", "ola", "cumprimentar"]):
            cmd = "CMD:WAVE"
        elif any(w in acao_limpa for w in ["repouso", "rest", "dormir", "desligar", "recolher"]):
            cmd = "CMD:REST"
        elif any(w in acao_limpa for w in ["apontar", "point", "indicar"]):
            cmd = "CMD:POINT"
        elif any(w in acao_limpa for w in ["pronto", "ready", "prontidão", "acordar"]):
            cmd = "CMD:READY"

        resposta_serial = ""
        if cmd and self.conectar():
            print(f"🦾 [SERIAL] Transmitindo para o Arduino: {cmd}...")
            resposta_serial = self.enviar_comando(cmd, aguardar_ack=True, timeout=5.0)

        # Sempre executa no simulador virtual para feedback no terminal
        sim = self._get_simulator()
        resultado_sim = sim.mover_braco(acao=acao, detalhes=detalhes)

        if resposta_serial:
            return f"Braço robótico acionado via Arduino ({resposta_serial}). {resultado_sim}"
        return resultado_sim

    def desenhar_rosto_oled(self, expressao: str):
        """
        Atualiza o display OLED 1.5" do Arduino e o desenho no terminal.
        """
        exp = expressao.upper().strip()
        cmd = "CMD:FACE:NEUTRAL"
        if "FELIZ" in exp:
            cmd = "CMD:FACE:HAPPY"
        elif "OUVINDO" in exp:
            cmd = "CMD:FACE:LISTEN"
        elif "SONO" in exp:
            cmd = "CMD:FACE:SLEEP"

        if self.conectar():
            self.enviar_comando(cmd, aguardar_ack=False)

        sim = self._get_simulator()
        sim.desenhar_rosto_oled(expressao)

    def atualizar_tela(self, titulo: str, subtitulo: str, icone: str = "🤖"):
        """Atualiza o painel informativo no terminal e na tela TFT 4.0\" do ESP32-S3."""
        if self.esp32_ip:
            def _sync_esp32():
                try:
                    import requests
                    url = f"http://{self.esp32_ip}/api/display"
                    requests.post(url, json={"title": titulo, "status": subtitulo, "icon": icone}, timeout=1.5)
                except Exception:
                    pass
            threading.Thread(target=_sync_esp32, daemon=True).start()

        sim = self._get_simulator()
        return sim.atualizar_tela(titulo=titulo, subtitulo=subtitulo, icone=icone)

    def fechar(self):
        """Encerra a conexão serial com segurança."""
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self.conectado = False

serial_controller = SerialCommController()
hardware = serial_controller
