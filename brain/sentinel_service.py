"""
Módulo do Modo Sentinela e Vigilância por Câmera para o J.A.R.V.I.S.
Monitora a estação de trabalho em segundo plano via câmera frontal.
Ao detectar movimento de pessoas na frente da mesa:
1. Tranca imediatamente a estação de trabalho (LockWorkStation).
2. Captura uma foto do indivíduo em alta resolução.
3. Dispara alerta urgente com a foto diretamente para o Telegram do usuário.
"""

import os
import sys
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class SentinelService:
    def __init__(self):
        self.ativo = False
        self._thread = None
        self._stop_event = threading.Event()
        self.alert_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "alerta_sentinela.jpg"))
        self.eventos_registrados = []
        self.ultimo_disparo = 0

    def is_ativo(self) -> bool:
        return self.ativo and self._thread is not None and self._thread.is_alive()

    def ativar(self, duracao_minutos: int = 60) -> str:
        """
        Ativa a vigilância sentinela em segundo plano.
        
        Args:
            duracao_minutos: Tempo máximo de vigília em minutos (padrão 60 minutos).
        """
        if self.is_ativo():
            return "O Modo Sentinela já está em execução e vigiando sua estação, senhor."

        self.ativo = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop_vigilancia,
            args=(duracao_minutos,),
            daemon=True,
            name="JARVIS-SentinelThread"
        )
        self._thread.start()

        from hardware_simulator import hardware
        hardware.atualizar_tela(titulo="MODO SENTINELA", subtitulo=f"Vigiando ({duracao_minutos} min)", icone="🛡️")

        return (
            f"🛡️ Modo Sentinela ATIVADO com sucesso, senhor! "
            f"Estarei vigiando sua mesa pelas próximas {duracao_minutos} minutos. "
            f"Caso qualquer pessoa se aproxime, trancarei o computador e enviarei a foto imediatamente no seu Telegram."
        )

    def desativar(self) -> str:
        """Desativa o modo sentinela."""
        if not self.is_ativo():
            return "O Modo Sentinela já está desativado no momento, senhor."

        self.ativo = False
        self._stop_event.set()
        
        from hardware_simulator import hardware
        hardware.atualizar_tela(titulo="SENTINELA", subtitulo="Modo desativado", icone="🟢")

        return "Modo Sentinela DESATIVADO, senhor. Sistemas retornaram ao modo padrão de repouso."

    def consultar_status(self) -> str:
        """Retorna o status do sentinela e histórico de eventos."""
        if self.is_ativo():
            msg = f"🛡️ Modo Sentinela está ATIVO e monitorando a câmera neste momento."
            if self.eventos_registrados:
                msg += f" Foram registrados {len(self.eventos_registrados)} alerta(s) de movimento recente(s)."
            return msg
        else:
            if self.eventos_registrados:
                ult = self.eventos_registrados[-1]
                return f"Modo Sentinela está inativo. Último evento registrado: {ult}."
            return "Modo Sentinela está inativo no momento, senhor."

    def _loop_vigilancia(self, duracao_minutos: int):
        import cv2
        tempo_inicio = time.time()
        tempo_maximo = duracao_minutos * 60

        print(f"\n🛡️ [SENTINELA] Inicializando sensor óptico da câmera...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("⚠️ [SENTINELA] Erro ao abrir a webcam para vigília.")
            self.ativo = False
            return

        # Leitura inicial para adaptação de luminosidade
        for _ in range(5):
            cap.read()
            time.sleep(0.1)

        ret, frame_base = cap.read()
        if not ret or frame_base is None:
            cap.release()
            self.ativo = False
            return

        gray_base = cv2.cvtColor(frame_base, cv2.COLOR_BGR2GRAY)
        gray_base = cv2.GaussianBlur(gray_base, (21, 21), 0)

        print(f"👁️ [SENTINELA] Vigilância em andamento. Perímetro calibrado.")

        try:
            while not self._stop_event.is_set():
                # Verifica tempo limite
                if time.time() - tempo_inicio > tempo_maximo:
                    print("🛡️ [SENTINELA] Tempo limite de vigília atingido. Encerrando.")
                    break

                ret, frame_atual = cap.read()
                if not ret or frame_atual is None:
                    time.sleep(1)
                    continue

                gray_atual = cv2.cvtColor(frame_atual, cv2.COLOR_BGR2GRAY)
                gray_atual = cv2.GaussianBlur(gray_atual, (21, 21), 0)

                # Diferença absoluta entre frames
                frame_diff = cv2.absdiff(gray_base, gray_atual)
                thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)[1]
                thresh = cv2.dilate(thresh, None, iterations=2)

                contornos, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                movimento_detectado = False

                for c in contornos:
                    # Filtra ruídos pequenos (área mínima de 4000 pixels)
                    if cv2.contourArea(c) > 4000:
                        movimento_detectado = True
                        break

                agora = time.time()
                if movimento_detectado and (agora - self.ultimo_disparo > 45):
                    # Cooldown de 45 segundos entre disparos
                    self.ultimo_disparo = agora
                    horario_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
                    self.eventos_registrados.append(f"Movimento em {horario_str}")
                    print(f"\n🚨 [SENTINELA ALERTA] MOVIMENTO DETECTADO ÀS {horario_str}!")

                    # 1. Salvar imagem do invasor
                    cv2.imwrite(self.alert_path, frame_atual)

                    # 2. Bloquear computador imediatamente
                    try:
                        import ctypes
                        ctypes.windll.user32.LockWorkStation()
                    except Exception:
                        pass

                    # 3. Disparar foto para o Telegram
                    try:
                        from telegram_service import telegram_service
                        legenda = (
                            f"🚨 *ALERTA DO MODO SENTINELA J.A.R.V.I.S.*\n\n"
                            f"⚠️ Movimento detectado na sua estação de trabalho em *{horario_str}*!\n"
                            f"🔒 A tela do computador foi bloqueada imediatamente para proteção de dados.\n"
                            f"📸 Segue a captura de segurança da câmera frontal."
                        )
                        telegram_service.enviar_foto(caminho_arquivo=self.alert_path, legenda=legenda)
                    except Exception as e:
                        print(f"⚠️ [SENTINELA] Erro ao avisar Telegram: {e}")

                # Atualiza frame base gradualmente
                gray_base = gray_atual
                time.sleep(0.6)

        finally:
            cap.release()
            self.ativo = False
            print("🛡️ [SENTINELA] Câmera liberada e vigilância encerrada.")

sentinel_service = SentinelService()
