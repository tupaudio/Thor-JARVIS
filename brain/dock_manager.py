"""
J.A.R.V.I.S. - Dock Manager Bridge (ESP32-S3 + ILI9488 4.0" Touch)
Faz a ponte entre a tela Touch do Dock, o servidor JARVIS e o Braço Robótico.
"""

import os
import sys
import time
import json
import threading
import serial
import serial.tools.list_ports
from dotenv import load_dotenv

# Carrega variáveis de ambiente do brain
DIR_BRAIN = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(DIR_BRAIN, ".env"))

class DockManager:
    def __init__(self):
        self.porta_dock = os.getenv("DOCK_PORT", "/dev/ttyACM0")
        self.baudrate = int(os.getenv("DOCK_BAUD", "115200"))
        self._serial = None
        self.conectado = False
        self._lock = threading.Lock()
        self._rodando = True
        self._thread_leitura = None
        self._thread_telemetria = None
        self._garra_aberta = False

    def iniciar(self):
        """Inicia os loops em segundo plano para comunicação com o Dock."""
        if self._thread_leitura is None or not self._thread_leitura.is_alive():
            self._thread_leitura = threading.Thread(target=self._loop_leitura, name="DockReader", daemon=True)
            self._thread_leitura.start()
        
        if self._thread_telemetria is None or not self._thread_telemetria.is_alive():
            self._thread_telemetria = threading.Thread(target=self._loop_telemetria, name="DockTelemetry", daemon=True)
            self._thread_telemetria.start()

    def _conectar(self) -> bool:
        with self._lock:
            if self.conectado and self._serial and self._serial.is_open:
                return True

            import glob
            candidatas = []
            
            # 1. Procura primeiro pelos links persistentes em /dev/serial/by-id/
            for l in glob.glob("/dev/serial/by-id/*"):
                base = os.path.basename(l).lower()
                if "espressif" in base or "esp32" in base or "jtag" in base:
                    candidatas.append(os.path.realpath(l))
                    break

            # 2. Procura via list_ports
            try:
                for p in serial.tools.list_ports.comports():
                    info = f"{p.device} {p.description} {p.hwid}".lower()
                    if "esp32" in info or "espressif" in info or "jtag" in info:
                        if p.device not in candidatas:
                            candidatas.append(p.device)
            except Exception:
                pass

            # 3. Fallbacks comuns configurados
            for padrao in [self.porta_dock, "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2"]:
                if padrao and padrao not in candidatas and os.path.exists(padrao):
                    candidatas.append(padrao)

            for cand in candidatas:
                if cand and os.path.exists(cand):
                    try:
                        self._serial = serial.Serial(cand, self.baudrate, timeout=0.1)
                        self._serial.dtr = True  # CRUCIAL para ESP32-S3 USB CDC
                        self._serial.rts = True
                        self.porta_dock = cand
                        self.conectado = True
                        print(f"✅ [DOCK MANAGER] Conectado ao ESP32-S3 Dock em {cand}!", flush=True)
                        
                        # Sincroniza a persona ativa imediatamente no boot
                        self._sincronizar_persona_inicial()
                        return True
                    except Exception as e:
                        pass

            self.conectado = False
            return False

    def _sincronizar_persona_inicial(self):
        try:
            from persona_manager import persona_manager
            p = persona_manager.obter_persona()
            nome = p.get("nome", "J.A.R.V.I.S.")
            self.enviar_persona(nome)
        except Exception:
            self.enviar_persona("J.A.R.V.I.S.")

    def enviar_json(self, payload: dict) -> bool:
        """Envia um comando JSON formatado de uma linha para o Dock."""
        if not self._conectar():
            return False
        try:
            linha = json.dumps(payload) + "\n"
            with self._lock:
                self._serial.write(linha.encode("utf-8"))
                self._serial.flush()
            return True
        except Exception as e:
            self.conectado = False
            return False

    def enviar_persona(self, nome: str):
        """Atualiza o badge de personalidade no topo da tela do Dock."""
        self.enviar_json({"persona": nome})

    def enviar_notificacao(self, texto: str):
        """Exibe uma tarja informativa de notificação no Dock."""
        self.enviar_json({"notify": texto})

    def definir_expressao(self, expressao: str):
        """Altera a expressão facial do robô (happy, listen, focus, sleep, neutral)."""
        self.enviar_json({"mood": expressao})

    def _processar_evento_dock(self, linha: str):
        """Processa eventos enviados pelo ESP32 (toque nos botões, status, etc.)."""
        try:
            d = json.loads(linha)
            tipo = d.get("type", "")
            
            if tipo == "arm_cmd":
                acao = d.get("action", "").lower()
                print(f"\n🤖 [DOCK TOUCH] Comando recebido da tela: {acao.upper()}")
                
                # Encaminha o comando com envio garantido para o Arduino Uno do braço
                try:
                    from serial_comm import serial_comm
                    if acao == "wave":
                        print("  -> Executando ACENAR no Arduino...")
                        serial_comm.enviar_comando("CMD:WAVE")
                        serial_comm.mover_braco("acenar")
                    elif acao == "point":
                        print("  -> Executando APONTAR no Arduino...")
                        serial_comm.enviar_comando("CMD:POINT")
                        serial_comm.mover_braco("apontar")
                    elif acao in ("rest", "repouso", "descanso"):
                        print("  -> Executando REPOUSO no Arduino...")
                        serial_comm.enviar_comando("CMD:REST")
                        serial_comm.mover_braco("repouso")
                    elif "garra" in acao:
                        self._garra_aberta = not self._garra_aberta
                        cmd_g = "CMD:GARRA:OPEN" if self._garra_aberta else "CMD:GARRA:CLOSE"
                        print(f"  -> Alternando Garra: {cmd_g}...")
                        serial_comm.enviar_comando(cmd_g)
                        self.enviar_notificacao(f"GARRA: {'ABERTA' if self._garra_aberta else 'FECHADA'}")
                except Exception as e:
                    print(f"⚠️ [DOCK] Erro ao repassar comando para o braço: {e}")

        except json.JSONDecodeError:
            pass

    def _loop_leitura(self):
        while self._rodando:
            if not self._conectar():
                time.sleep(3.0)
                continue
            try:
                linha = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if linha:
                    if linha.startswith("{") and linha.endswith("}"):
                        self._processar_evento_dock(linha)
            except Exception:
                self.conectado = False
                time.sleep(2.0)

    def _loop_telemetria(self):
        """Envia dados úteis para a tarja do Dock periodicamente."""
        while self._rodando:
            time.sleep(15.0)
            if not self.conectado:
                continue
            try:
                # 1. Verifica se a impressora 3D está imprimindo
                from octoprint_service import octoprint_service
                octo_status = octoprint_service.obter_status_impressao()
                if octo_status and octo_status.get("imprimindo"):
                    temp_bico = octo_status.get("temperatura_bico", 0)
                    progresso = octo_status.get("progresso", 0)
                    self.enviar_notificacao(f"IMPRESSORA: {temp_bico:.0f}°C | {progresso:.0f}%")
                    continue
            except Exception:
                pass

            try:
                # 2. Informação de CPU do servidor
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                self.enviar_notificacao(f"SERVIDOR: CPU {cpu:.0f}% | RAM {ram:.0f}%")
            except Exception:
                pass

dock_manager = DockManager()

if __name__ == "__main__":
    print("🚀 [TESTE DE BANCADA] Iniciando Dock Manager Bridge em modo manual...")
    print("Toque nos botões da tela TFT 4.0\" para ver os comandos serem repassados ao Arduino!")
    dock_manager.iniciar()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando teste.")
