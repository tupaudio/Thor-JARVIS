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


env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class SerialCommController:
    """Controlador serial com autodeteção e sincronização Arduino + Simulador."""
    def __init__(self):
        self.porta_configurada = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
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

        # Autoconexão em segundo plano no startup para que o Arduino esteja pronto imediatamente
        if os.getenv("ARDUINO_ENABLED", "0") == "1" and self.porta_configurada.lower() not in ("none", "", "disabled"):
            threading.Thread(target=self._autoconectar_inicial, name="JarvisSerialInit", daemon=True).start()

    def _autoconectar_inicial(self):
        time.sleep(1.0)
        self.conectar()

    def _get_simulator(self):
        """Lazy loading do simulador para evitar import circular."""
        if self._simulator is None:
            from hardware_simulator import HardwareSimulator
            self._simulator = HardwareSimulator()
        return self._simulator

    def conectar(self) -> bool:
        """Tenta abrir a comunicação serial com a placa Arduino."""
        # Se Arduino estiver desativado ou configurado como none, usa simulador para não bloquear a impressora 3D
        if os.getenv("ARDUINO_ENABLED", "0") != "1" or self.porta_configurada.lower() in ("none", "", "disabled"):
            self.conectado = False
            return False

        with self._lock:
            if self.conectado and self._serial is not None and self._serial.is_open:
                return True

            try:
                import serial
                import serial.tools.list_ports

                todas_portas = list(serial.tools.list_ports.comports())
                
                # TRAVA DE SEGURANÇA CRÍTICA:
                # Protege a porta serial da impressora Creality Ender 3 contra envio acidental de comandos.
                caminho_arduino_config = os.path.realpath(self.porta_configurada) if self.porta_configurada else ""
                porta_octo_env = os.getenv("OCTOPRINT_SERIAL_PORT", "").strip()
                bloqueadas = set()
                if porta_octo_env and porta_octo_env.lower() not in ("none", "", "disabled"):
                    caminho_octo = os.path.realpath(porta_octo_env)
                    # Só bloqueia a porta do OctoPrint para auto-varredura se ela for diferente da do Arduino
                    if caminho_octo != caminho_arduino_config:
                        bloqueadas.add(caminho_octo)

                portas_usb_reais = []
                for p in todas_portas:
                    dev_nome = (p.device or "").lower()
                    desc = (p.description or "").lower()
                    hwid = (p.hwid or "").lower()
                    if "bluetooth" in desc or "bthmodem" in hwid:
                        continue
                    if os.path.realpath(p.device or "") in bloqueadas:
                        continue
                    portas_usb_reais.append(p)

                porta_alvo = None

                # 0. Consulta primeiro o DeviceBus (gerenciador de auto-descoberta plug-and-play)
                try:
                    from device_bus import device_bus
                    p_bus = device_bus.obter_porta("arm")
                    if p_bus and os.path.exists(p_bus):
                        porta_alvo = p_bus
                except Exception:
                    pass

                # 1. Porta definida no .env (ex: /dev/ttyUSB0, /dev/ttyUSB2 ou /dev/ttyACM0)
                if not porta_alvo and self.porta_configurada and self.porta_configurada.lower() not in ("none", "", "disabled"):
                    caminho_real = os.path.realpath(self.porta_configurada)
                    if caminho_real in bloqueadas:
                        print(f"⛔ [SERIAL] ARDUINO_PORT={self.porta_configurada} aponta para a porta da impressora. Ignorada.")
                    elif os.path.exists(self.porta_configurada):
                        porta_alvo = self.porta_configurada
                    else:
                        for p in portas_usb_reais:
                            if p.device.upper() == self.porta_configurada.upper():
                                porta_alvo = p.device
                                break

                # 2. Linux: nós de dispositivo nativos (/dev/ttyACM*) ou portas USB não-bloqueadas (/dev/ttyUSB1, /dev/ttyUSB2...)
                import glob
                candidatas_acm = sorted(glob.glob("/dev/ttyACM*"))
                candidatas_usb = [p for p in sorted(glob.glob("/dev/ttyUSB*")) if os.path.realpath(p) not in bloqueadas]
                candidatas = candidatas_acm + candidatas_usb

                portas_para_tentar = []
                if porta_alvo and os.path.realpath(porta_alvo) not in bloqueadas:
                    portas_para_tentar.append(porta_alvo)
                for c in candidatas:
                    if c not in portas_para_tentar:
                        portas_para_tentar.append(c)

                # Se nenhuma porta USB real for encontrada
                if not portas_para_tentar:
                    if not self._tentou_conectar:
                        portas_desc = [f"{p.device} ({p.description})" for p in todas_portas]
                        desc_str = ", ".join(portas_desc) if portas_desc else "nenhuma porta serial /dev/tty* disponível"
                        print(f"ℹ️ [SERIAL] Arduino físico não detectado via USB ({desc_str}). Modo Simulador Virtual ativo.")
                        self._tentou_conectar = True
                    self.conectado = False
                    return False

                porta_conectada = None
                for cand in portas_para_tentar:
                    try:
                        print(f"🔌 [SERIAL] Conectando ao Arduino na porta {cand} ({self.baudrate} baud)...")
                        s = serial.Serial(cand, self.baudrate, timeout=1.0)
                        # O Arduino UNO reinicia via DTR ao abrir a serial. Aguarda inicialização limpa (até 3.0s).
                        t_limite = time.time() + 3.0
                        conectou = False
                        while time.time() < t_limite:
                            if s.in_waiting > 0:
                                linha = s.readline().decode("utf-8", errors="ignore").strip()
                                if "READY" in linha or "ONLINE" in linha or "JARVIS" in linha:
                                    conectou = True
                                    break
                            time.sleep(0.05)
                        if not conectou:
                            s.write(b"CMD:PING\n")
                            s.flush()
                            time.sleep(0.2)
                            resp = s.read(s.in_waiting or 64).decode("utf-8", errors="ignore")
                            if "JARVIS" in resp or "PONG" in resp:
                                conectou = True

                        if conectou:
                            self._serial = s
                            porta_conectada = cand
                            break
                        else:
                            s.close()
                    except Exception as err_cand:
                        print(f"⚠️ [SERIAL] Porta {cand} indisponível ou sem resposta: {err_cand}")
                        continue

                if not porta_conectada:
                    print(f"⚠️ [SERIAL] Nenhuma porta USB respondeu ao handshake do Arduino. Alternando para simulador.")
                    self.conectado = False
                    self._tentou_conectar = True
                    return False

                self._serial.reset_input_buffer()
                self.conectado = True
                self._tentou_conectar = True
                self.porta_configurada = porta_conectada
                print(f"✅ [SERIAL] Arduino UNO conectado e sincronizado com sucesso na porta {porta_conectada}!")

                try:
                    from device_bus import device_bus
                    device_bus.registrar_porta_externa("arm", porta_conectada)
                except Exception:
                    pass

                # Sincroniza a persona ativa imediatamente no badge OLED
                try:
                    from persona_manager import persona_manager
                    p = persona_manager.obter_persona()
                    cmd_p = f"CMD:PERSONA:{p['nome'][:15]}\n".encode("utf-8")
                    self._serial.write(cmd_p)
                    self._serial.flush()
                except Exception:
                    pass

                return True

            except Exception as e:
                print(f"⚠️ [SERIAL] Falha ao conectar ao Arduino: {e}. Alternando para simulador.")
                self.conectado = False
                if "ermission" in str(e):
                    print("💡 [SERIAL] Sem permissão na porta: adicione o usuário ao grupo 'dialout' (sudo usermod -aG dialout $USER) e faça login de novo.")
                return False

    def is_conectado(self) -> bool:
        return self.conectado and self._serial is not None and self._serial.is_open

    def tentar_reconectar_se_necessario(self) -> bool:
        """Tenta reconectar ao Arduino físico a cada 10s se estiver desconectado."""
        if self.is_conectado():
            return True
        agora = time.time()
        if not hasattr(self, "_ultimo_retry_serial"):
            self._ultimo_retry_serial = 0
        if agora - self._ultimo_retry_serial > 10.0:
            self._ultimo_retry_serial = agora
            return self.conectar()
        return False

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

        # 2. Fallback para conexão Serial USB direta com o Arduino (com tentativa de reconexão)
        if not self.is_conectado():
            if not self.tentar_reconectar_se_necessario():
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
                print(f"⚠️ [SERIAL] Conexão USB com o Arduino perdida ({e}). Alternando para simulador.")
                try:
                    if self._serial:
                        self._serial.close()
                except Exception:
                    pass
                self._serial = None
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
        elif any(w in acao_limpa for w in ["positivo", "confirmar", "sim"]):
            cmd = "CMD:WAVE"
        elif any(w in acao_limpa for w in ["pronto", "ready", "prontidão", "acordar"]):
            cmd = "CMD:READY"
        elif any(w in acao_limpa for w in ["abrir garra", "garra aberta", "open claw", "open"]):
            cmd = "CMD:GARRA:OPEN"
        elif any(w in acao_limpa for w in ["fechar garra", "garra fechada", "close claw", "close"]):
            cmd = "CMD:GARRA:CLOSE"
        elif any(w in acao_limpa for w in ["girar base", "varrer base", "base", "sweep"]):
            cmd = "CMD:SWEEP:BASE"

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
        elif "FOCADO" in exp:
            cmd = "CMD:FACE:FOCUS"
        elif "RESET" in exp or "REINICIAR" in exp:
            cmd = "CMD:OLED:RESET"

        if self.conectar():
            self.enviar_comando(cmd, aguardar_ack=False)

        try:
            from iphone_dock_server import dock_state
            dock_state.atualizar_face(exp)
        except Exception:
            pass

        sim = self._get_simulator()
        sim.desenhar_rosto_oled(expressao)

    def atualizar_tela(self, titulo: str, subtitulo: str, icone: str = "🤖"):
        """Atualiza o painel informativo no terminal, no iPhone 11 Dock e na tela TFT 4.0\" do ESP32-S3."""
        try:
            from iphone_dock_server import dock_state
            dock_state.atualizar_hud(titulo=titulo, subtitulo=subtitulo, icone=icone)
        except Exception:
            pass

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

    def definir_persona(self, nome: str):
        """Envia comando para o Arduino atualizar o nome da persona no topo do display OLED 1.5\"."""
        if self.is_conectado() or self.conectar():
            self.enviar_comando(f"CMD:PERSONA:{nome[:15]}", aguardar_ack=False)
        sim = self._get_simulator()
        if hasattr(sim, "definir_persona"):
            sim.definir_persona(nome)

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
