"""
Módulo de Controle e Automação do Windows para o J.A.R.V.I.S.
Gerencia volume do sistema, segurança (bloqueio de tela), inicialização de aplicativos,
telemetria de hardware (CPU/RAM/Bateria), visão de tela e captura de fotos pela webcam.
"""

import os
import sys
import time
import ctypes
import subprocess
from datetime import datetime
from PIL import ImageGrab
import psutil
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

PROGRAMAS_CONHECIDOS = {
    "vs code": "code",
    "vscode": "code",
    "código": "code",
    "chrome": "chrome",
    "navegador": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "steam": "steam",
    "spotify": "spotify",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "calc": "calc",
    "gerenciador de tarefas": "taskmgr",
    "explorador": "explorer",
    "arquivos": "explorer",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "whatsapp": "whatsapp:"
}

class WindowsService:
    def __init__(self):
        self.screenshot_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "screenshot_jarvis.png"))
        self.webcam_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "webcam_jarvis.jpg"))

    def _obter_volume_endpoint(self):
        """Retorna o endpoint de áudio master do Windows via pycaw."""
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            return speakers.EndpointVolume
        except Exception as e:
            print(f"⚠️ [WINDOWS] Erro ao acessar pycaw: {e}")
            return None

    def controlar_volume(self, acao: str, valor: int = 0) -> str:
        """
        Ajusta o volume master do Windows.
        
        Args:
            acao: 'definir' (ex: valor=50), 'aumentar', 'diminuir', 'mutar', 'desmutar' ou 'consultar'.
            valor: Porcentagem de 0 a 100 (usado quando acao for 'definir', 'aumentar' ou 'diminuir').
        """
        vol_endpoint = self._obter_volume_endpoint()
        if not vol_endpoint:
            return "Não foi possível acessar os controles de áudio do Windows, senhor."

        acao_limpa = acao.lower().strip()
        current_scalar = vol_endpoint.GetMasterVolumeLevelScalar()
        current_percent = round(current_scalar * 100)

        try:
            if "mut" in acao_limpa and "des" not in acao_limpa:
                vol_endpoint.SetMute(1, None)
                return "Áudio do computador mutado, senhor."
            
            elif "desmut" in acao_limpa:
                vol_endpoint.SetMute(0, None)
                return f"Áudio do computador restaurado em {current_percent}%, senhor."

            elif "aument" in acao_limpa or "subir" in acao_limpa:
                incremento = valor if valor > 0 else 10
                novo_valor = min(100, current_percent + incremento)
                vol_endpoint.SetMute(0, None)
                vol_endpoint.SetMasterVolumeLevelScalar(novo_valor / 100.0, None)
                return f"Volume do computador aumentado para {novo_valor}%, senhor."

            elif "diminu" in acao_limpa or "baixar" in acao_limpa:
                decremento = valor if valor > 0 else 10
                novo_valor = max(0, current_percent - decremento)
                vol_endpoint.SetMasterVolumeLevelScalar(novo_valor / 100.0, None)
                return f"Volume do computador reduzido para {novo_valor}%, senhor."

            elif "defin" in acao_limpa or "ajust" in acao_limpa or valor > 0:
                novo_valor = max(0, min(100, valor))
                vol_endpoint.SetMute(0, None)
                vol_endpoint.SetMasterVolumeLevelScalar(novo_valor / 100.0, None)
                return f"Volume do computador ajustado para {novo_valor}%, senhor."

            else:
                is_muted = vol_endpoint.GetMute()
                status_mute = " (mutado)" if is_muted else ""
                return f"O volume atual do computador está em {current_percent}%{status_mute}, senhor."

        except Exception as e:
            return f"Erro ao controlar volume do Windows: {e}"

    def bloquear_computador(self) -> str:
        """Bloqueia a tela da estação de trabalho do Windows."""
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Estação de trabalho bloqueada com sucesso, senhor."
        except Exception as e:
            return f"Não foi possível bloquear o computador: {e}"

    def abrir_aplicativo(self, nome_app: str) -> str:
        """
        Inicia um programa ou ferramenta no Windows.
        
        Args:
            nome_app: Nome do programa (ex: 'VS Code', 'Chrome', 'Calculadora', 'Steam').
        """
        nome_limpo = nome_app.lower().strip()
        comando = PROGRAMAS_CONHECIDOS.get(nome_limpo)
        
        if not comando:
            # Tenta busca parcial no catálogo
            for k, v in PROGRAMAS_CONHECIDOS.items():
                if k in nome_limpo or nome_limpo in k:
                    comando = v
                    break
        
        comando_exec = comando if comando else nome_app
        print(f"\n🚀 [WINDOWS LANÇADOR] Abrindo '{comando_exec}'...")
        
        try:
            if comando_exec.startswith("http") or ":" in comando_exec:
                os.startfile(comando_exec)
            else:
                subprocess.Popen(["cmd.exe", "/c", f"start {comando_exec}"], shell=True)
            return f"Abrindo {nome_app} no seu computador, senhor."
        except Exception as e:
            return f"Não foi possível abrir '{nome_app}': {e}"

    def fechar_aplicativo(self, nome_processo: str) -> str:
        """Encerra um aplicativo pelo nome do processo ou programa."""
        nome_limpo = nome_processo.lower().strip().replace(".exe", "")
        encerrados = 0
        
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info["name"].lower()
                if nome_limpo in pname:
                    proc.terminate()
                    encerrados += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if encerrados > 0:
            return f"Aplicativo '{nome_processo}' encerrado com sucesso ({encerrados} processo(s) finalizados), senhor."
        return f"Não encontrei nenhum processo ativo correspondente a '{nome_processo}' para encerrar, senhor."

    def obter_telemetria(self) -> str:
        """Retorna o uso de CPU, RAM, Disco e Bateria do computador."""
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            ram_usada_gb = round(ram.used / (1024**3), 1)
            ram_total_gb = round(ram.total / (1024**3), 1)
            ram_pct = ram.percent
            
            # Disco principal C:
            disco = psutil.disk_usage("C:\\")
            disco_livre_gb = round(disco.free / (1024**3), 1)

            # Bateria (se notebook)
            detalhe_bateria = ""
            bateria = psutil.sensors_battery()
            if bateria:
                status_tomada = "conectado à tomada" if bateria.power_plugged else "na bateria"
                detalhe_bateria = f" Bateria em {bateria.percent}% ({status_tomada})."

            resposta = (
                f"Telemetria do sistema operacional, senhor: "
                f"Uso da CPU em {cpu}%. "
                f"Memória RAM em {ram_pct}% ({ram_usada_gb} GB usados de {ram_total_gb} GB). "
                f"Espaço livre no disco C: {disco_livre_gb} GB.{detalhe_bateria} "
                f"Todos os sistemas operacionais estão estáveis."
            )
            return resposta
        except Exception as e:
            return f"Erro ao coletar métricas do computador: {e}"

    def capturar_tela(self) -> str:
        """Captura o screenshot da tela atual e salva em disco."""
        try:
            img = ImageGrab.grab()
            img.save(self.screenshot_path, "PNG")
            return self.screenshot_path
        except Exception as e:
            print(f"⚠️ [WINDOWS] Erro ao capturar tela: {e}")
            return ""

    def tirar_foto_webcam(self) -> str:
        """Captura uma foto em tempo real pela câmera frontal (webcam) via CameraManager."""
        try:
            from camera_manager import camera_manager
            caminho = camera_manager.capturar_foto(self.webcam_path)
            if caminho and os.path.exists(caminho):
                print(f"📸 [WEBCAM] Foto capturada com sucesso em '{caminho}'")
                return caminho
            return ""
        except Exception as e:
            print(f"⚠️ [WEBCAM] Erro ao capturar foto da webcam: {e}")
            return ""

    def tirar_foto_e_enviar_telegram(self, legenda: str = "") -> str:
        """Tira uma foto pela webcam e envia direto para o Telegram do usuário."""
        caminho = self.tirar_foto_webcam()
        if not caminho or not os.path.exists(caminho):
            return "Não foi possível acessar a câmera frontal do seu computador no momento, senhor."
        
        from telegram_service import telegram_service
        agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
        legenda_final = legenda if legenda else f"📸 Foto capturada pela câmera frontal do seu computador em {agora_str}."
        
        sucesso = telegram_service.enviar_foto(caminho_arquivo=caminho, legenda=legenda_final)
        if sucesso:
            return "Foto capturada pela câmera frontal e enviada com sucesso para o seu Telegram, senhor!"
        return "Capturei a foto, mas houve uma oscilação no envio para o Telegram. O arquivo está salvo localmente."

    def _get_gemini_client(self):
        if not hasattr(self, "_gemini_client") or self._gemini_client is None:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            self._gemini_client = genai.Client(api_key=api_key)
        return self._gemini_client

    def analisar_tela(self, pergunta: str = "") -> str:
        """Tira um print da tela e analisa com a visão multimodal do Gemini."""
        caminho = self.capturar_tela()
        if not caminho or not os.path.exists(caminho):
            return "Não consegui capturar a imagem da sua tela no momento, senhor."

        try:
            from PIL import Image
            
            client = self._get_gemini_client()
            imagem = Image.open(caminho)
            
            prompt = pergunta if pergunta else "Analise o que está visível na tela deste computador e faça um resumo conciso e objetivo para o usuário."
            
            resposta = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[prompt, imagem]
            )
            return resposta.text if resposta.text else "Analisei sua tela, senhor, mas não detectei nenhum elemento crítico em destaque."
        except Exception as e:
            return f"Erro ao analisar a tela com a IA: {e}"

    def analisar_ambiente_webcam(self, pergunta: str = "") -> str:
        """Captura imagem da webcam e analisa o que/quem está na frente do PC."""
        caminho = self.tirar_foto_webcam()
        if not caminho or not os.path.exists(caminho):
            return "Não foi possível acessar a câmera frontal, senhor."

        try:
            from PIL import Image
            
            client = self._get_gemini_client()
            imagem = Image.open(caminho)
            
            prompt = pergunta if pergunta else "Descreva o que a câmera frontal do computador está vendo agora. Seja educado, conciso e chame o usuário de senhor."
            
            resposta = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[prompt, imagem]
            )
            return resposta.text if resposta.text else "Câmera ativada, senhor."
        except Exception as e:
            return f"Erro ao analisar visão da câmera: {e}"

windows_service = WindowsService()
