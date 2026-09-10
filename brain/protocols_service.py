"""
Módulo de Protocolos Stark para o J.A.R.V.I.S.
Orquestra comandos macros e cenas de produtividade, lazer, segurança e rotina diária.
Combina áudio, programas do Windows, Spotify, iluminação inteligente, câmera e Telegram.
"""

import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class ProtocolsService:
    def __init__(self):
        pass

    def executar(self, nome_protocolo: str) -> str:
        """
        Executa uma rotina ou protocolo Stark completo.
        
        Args:
            nome_protocolo: 'foco' (ou trabalho), 'cinema' (ou descanso/lazer), 'sair_da_base' (ou seguranca/sair), 'bom_dia'.
        """
        proto = nome_protocolo.lower().strip()

        if any(k in proto for k in ["foco", "trabalho", "estudo", "programar"]):
            return self._protocolo_foco()
        elif any(k in proto for k in ["cinema", "filme", "serie", "lazer", "descanso"]):
            return self._protocolo_cinema()
        elif any(k in proto for k in ["sair", "bloqueio", "base", "ausente", "seguranca"]):
            return self._protocolo_sair_da_base()
        elif any(k in proto for k in ["bom dia", "manhã", "acordar", "iniciar dia"]):
            return self._protocolo_bom_dia()
        else:
            return (
                f"Protocolo '{nome_protocolo}' não reconhecido, senhor. "
                f"Os protocolos ativos são: 'Foco/Trabalho', 'Cinema', 'Sair da Base' e 'Bom Dia'."
            )

    def _protocolo_foco(self) -> str:
        """Configura ambiente ideal para produtividade e código."""
        from hardware_simulator import hardware
        from windows_service import windows_service
        from spotify_service import spotify_service
        from iot_service import iot_service

        hardware.atualizar_tela(titulo="PROTOCOLO FOCO", subtitulo="Iniciando ambiente...", icone="💻")
        
        # 1. Ajustar volume
        windows_service.controlar_volume("definir", 35)

        # 2. Abrir ferramentas
        windows_service.abrir_aplicativo("VS Code")
        windows_service.abrir_aplicativo("Chrome")

        # 3. Ajustar iluminação
        iot_service.controlar("luz do quarto", "brilho", "60")
        iot_service.controlar("fita led", "cor", "azul ciano")
        iot_service.controlar("fita led", "brilho", "70")

        # 4. Música de foco no Spotify
        spotify_service.tocar("Synthwave Chill", tipo="playlist")

        return (
            "Protocolo de Foco ativado com sucesso, senhor. "
            "Volume em 35%, VS Code e Chrome abertos, iluminação azul ciano e trilha sonora de foco iniciada. Bom trabalho!"
        )

    def _protocolo_cinema(self) -> str:
        """Ambiente relaxante para filmes ou vídeos."""
        from hardware_simulator import hardware
        from windows_service import windows_service
        from spotify_service import spotify_service
        from iot_service import iot_service

        hardware.atualizar_tela(titulo="PROTOCOLO CINEMA", subtitulo="Luzes e som...", icone="🎬")

        # 1. Pausa Spotify
        spotify_service.pausar()

        # 2. Ajusta som do PC
        windows_service.controlar_volume("definir", 75)

        # 3. Luzes de cinema
        iot_service.controlar("luz do quarto", "desligar")
        iot_service.controlar("fita led", "cor", "ambar")
        iot_service.controlar("fita led", "brilho", "20")

        # 4. Abre navegador
        windows_service.abrir_aplicativo("https://www.youtube.com")

        return (
            "Protocolo Cinema ativo, senhor. "
            "Luz do quarto apagada, fita LED em âmbar suave a 20%, som elevado para 75% e tela de streaming aberta."
        )

    def _protocolo_sair_da_base(self) -> str:
        """Tranca o PC, apaga luzes, tira foto de perímetro e avisa no Telegram."""
        from hardware_simulator import hardware
        from windows_service import windows_service
        from spotify_service import spotify_service
        from telegram_service import telegram_service
        from iot_service import iot_service

        hardware.atualizar_tela(titulo="PROTOCOLO SAIR", subtitulo="Trancando sistemas...", icone="🔒")

        # 1. Pausa música
        spotify_service.pausar()

        # 2. Apaga luzes
        iot_service.controlar("tudo", "desligar")

        # 3. Tira foto de perímetro
        foto_path = windows_service.tirar_foto_webcam()
        agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
        
        if foto_path and os.path.exists(foto_path):
            telegram_service.enviar_foto(
                caminho_arquivo=foto_path,
                legenda=f"🛡️ [PROTOCOLO SAIR DA BASE] Estação de trabalho trancada e segura em {agora_str}, senhor."
            )
        else:
            telegram_service.enviar_mensagem(f"🛡️ [PROTOCOLO SAIR DA BASE] Estação trancada e segura em {agora_str}, senhor.")

        # 4. Tranca o Windows
        windows_service.bloquear_computador()

        return "Protocolo Sair da Base executado com sucesso. Luzes apagadas, foto enviada ao seu Telegram e computador trancado, senhor."

    def _protocolo_bom_dia(self) -> str:
        """Briefing matinal completo: Clima, Telemetria do PC, Iluminação e Música."""
        from hardware_simulator import hardware
        from weather_service import weather_service
        from windows_service import windows_service
        from spotify_service import spotify_service
        from iot_service import iot_service

        hardware.atualizar_tela(titulo="BOM DIA SENHOR", subtitulo="Sistemas online", icone="☀️")

        # 1. Iluminação matinal
        iot_service.controlar("luz do quarto", "ligar")
        iot_service.controlar("luz do quarto", "brilho", "100")
        iot_service.controlar("fita led", "cor", "branco quente")

        # 2. Coletar dados
        clima = weather_service.consultar_clima()
        telemetria = windows_service.obter_telemetria()

        # 3. Música suave
        spotify_service.tocar("Morning Coffee", tipo="playlist")

        return (
            f"Bom dia, senhor Dafnhe! Sistemas J.A.R.V.I.S. totalmente operacionais.\n\n"
            f"🌦️ {clima}\n\n"
            f"💻 {telemetria}\n\n"
            f"A iluminação foi ajustada para o dia e sua playlist matinal foi iniciada."
        )

protocols_service = ProtocolsService()
