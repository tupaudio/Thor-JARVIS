"""
Módulo de Integração com Telegram Bot do J.A.R.V.I.S.
Permite controlar o assistente pelo celular (texto e áudio de voz),
receber respostas faladas com Edge-TTS e enviar notificações proativas.
"""

import os
import sys
import time
import json
import asyncio
import threading
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class TelegramBotService:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.api_url = os.getenv("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "JARVIS-Assistant/1.0"})
        self.polling_active = False
        self.last_update_id = 0
        self.gemini_chat = None
        self.temp_voice_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "jarvis_telegram_voice.mp3"))

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/bot{self.token}"

    def is_configured(self) -> bool:
        return bool(self.token and self.token != "seu_token_telegram_aqui")

    def get_me(self) -> dict:
        """Verifica a identidade e status do bot na API do Telegram."""
        if not self.is_configured():
            return {"ok": False, "error": "Token do Telegram não configurado no .env"}
        try:
            resp = self.session.get(f"{self.base_url}/getMe", timeout=10)
            return resp.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def salvar_chat_id(self, chat_id: str):
        """Salva o Chat ID do usuário automaticamente no arquivo .env."""
        self.chat_id = str(chat_id)
        os.environ["TELEGRAM_CHAT_ID"] = self.chat_id
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
        try:
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "TELEGRAM_CHAT_ID=" in content:
                    lines = content.splitlines()
                    new_lines = []
                    for line in lines:
                        if line.startswith("TELEGRAM_CHAT_ID="):
                            new_lines.append(f"TELEGRAM_CHAT_ID={self.chat_id}")
                        else:
                            new_lines.append(line)
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(new_lines) + "\n")
                else:
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\nTELEGRAM_CHAT_ID={self.chat_id}\n")
                print(f"📱 [TELEGRAM] Chat ID {self.chat_id} registrado com sucesso no .env!")
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Erro ao salvar CHAT_ID no .env: {e}")

    def enviar_mensagem(self, texto: str, chat_id: str = None) -> str:
        """
        Envia uma mensagem de texto para o Telegram do usuário.
        """
        if not self.is_configured():
            return "Telegram não configurado no arquivo .env."
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return "Destinatário do Telegram não definido. Envie /start para o seu bot @Dafnhe_JARVIS_bot primeiro."

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": texto,
            "parse_mode": "Markdown"
        }

        try:
            resp = self.session.post(url, json=payload, timeout=10)
            res_json = resp.json()
            if not res_json.get("ok"):
                # Tenta sem Markdown se der erro de formatação
                payload.pop("parse_mode", None)
                resp = self.session.post(url, json=payload, timeout=10)
                res_json = resp.json()
            
            if res_json.get("ok"):
                return f"Mensagem enviada com sucesso para o seu Telegram: '{texto[:30]}...'"
            else:
                return f"Falha ao enviar mensagem no Telegram: {res_json.get('description')}"
        except Exception as e:
            return f"Erro de conexão ao enviar mensagem no Telegram: {e}"

    def enviar_audio_voz(self, caminho_arquivo: str, chat_id: str = None, legenda: str = "") -> bool:
        """
        Envia um áudio de voz do JARVIS para o Telegram.
        """
        if not self.is_configured() or not os.path.exists(caminho_arquivo):
            return False
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return False

        url = f"{self.base_url}/sendVoice"
        try:
            with open(caminho_arquivo, "rb") as audio_fp:
                files = {"voice": audio_fp}
                data = {"chat_id": target_chat}
                if legenda:
                    data["caption"] = legenda
                resp = self.session.post(url, data=data, files=files, timeout=30)
                return resp.json().get("ok", False)
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Erro ao enviar áudio de voz: {e}")
            return False

    def enviar_foto(self, caminho_arquivo: str, chat_id: str = None, legenda: str = "") -> bool:
        """
        Envia uma foto da webcam ou screenshot para o Telegram do usuário.
        """
        if not self.is_configured() or not os.path.exists(caminho_arquivo):
            return False
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return False

        url = f"{self.base_url}/sendPhoto"
        try:
            with open(caminho_arquivo, "rb") as photo_fp:
                files = {"photo": photo_fp}
                data = {"chat_id": target_chat}
                if legenda:
                    data["caption"] = legenda
                resp = self.session.post(url, data=data, files=files, timeout=30)
                return resp.json().get("ok", False)
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Erro ao enviar foto: {e}")
            return False

    def sintetizar_audio_resposta(self, texto: str) -> str:
        """Gera áudio com Edge-TTS para envio pelo Telegram."""
        import edge_tts
        voice_name = os.getenv("JARVIS_VOICE", "pt-BR-AntonioNeural")
        
        async def _gerar():
            com = edge_tts.Communicate(texto, voice_name)
            await com.save(self.temp_voice_file)
        
        try:
            asyncio.run(_gerar())
            return self.temp_voice_file
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Falha ao sintetizar áudio: {e}")
            return ""

    def conectar_gemini(self, gemini_chat):
        """Associa a sessão do Gemini AI ao bot do Telegram."""
        self.gemini_chat = gemini_chat

    def processar_comando_remoto(self, texto_comando: str, chat_id: str) -> str:
        """
        Envia o comando do Telegram para o cérebro Gemini do JARVIS e devolve a resposta.
        """
        if not self.gemini_chat:
            from google import genai
            from google.genai import types
            import main
            
            api_key = os.getenv("GEMINI_API_KEY")
            client = genai.Client(api_key=api_key)
            self.gemini_chat = client.chats.create(
                model="gemini-3.5-flash-lite",
                config=types.GenerateContentConfig(
                    system_instruction=main.JARVIS_SYSTEM_INSTRUCTION,
                    tools=main.JARVIS_TOOLS,
                    temperature=0.7,
                )
            )

        print(f"\n📱 [TELEGRAM MENSAGEM RECEBIDA]: \"{texto_comando}\"")
        for tentativa in range(3):
            try:
                resposta = self.gemini_chat.send_message(texto_comando)
                return resposta.text if resposta.text else "Comando executado com sucesso, senhor."
            except Exception as e:
                err_msg = str(e)
                if any(t in err_msg for t in ["503", "UNAVAILABLE", "high demand", "429"]):
                    time.sleep(2)
                else:
                    return f"Desculpe, senhor. Tive um imprevisto ao processar sua solicitação: {e}"
        
        return "Desculpe senhor, os servidores da Google estão com alta demanda temporária. Por favor tente novamente em instantes."

    def tratar_atualizacao(self, update: dict):
        """Processa uma mensagem recebida do Telegram."""
        message = update.get("message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))
        username = chat.get("username", "Usuário")
        texto = message.get("text", "").strip()

        # Segurança: se CHAT_ID já estiver configurado e outro usuário tentar, ignora
        if self.chat_id and str(self.chat_id) != str(chat_id):
            print(f"⚠️ [TELEGRAM] Acesso negado para usuário não autorizado: ID {chat_id} (@{username})")
            payload = {
                "chat_id": chat_id,
                "text": "⛔ *Acesso Não Autorizado.* Este assistente J.A.R.V.I.S. é estritamente privado.",
                "parse_mode": "Markdown"
            }
            try:
                self.session.post(f"{self.base_url}/sendMessage", json=payload, timeout=5)
            except Exception:
                pass
            return

        # Primeiro contato ou comando /start
        if texto == "/start" or not self.chat_id:
            self.salvar_chat_id(chat_id)
            boas_vindas = (
                f"🎩 *Sistemas J.A.R.V.I.S. conectados com sucesso, senhor!*\n\n"
                f"Sua identidade foi registrada (`ID: {chat_id}`).\n"
                f"A partir de agora, o senhor pode me enviar comandos em texto ou por voz de onde estiver.\n\n"
                f"Experimente me pedir:\n"
                f"• *'Como está o trânsito até em casa?'*\n"
                f"• *'Quais meus compromissos de hoje?'*\n"
                f"• *'Qual a previsão do tempo para amanhã?'*\n"
                f"• *'Anote no Notion: Comprar jumpers'* \n"
                f"• *'Registre um gasto de 35 reais em almoço'*"
            )
            self.enviar_mensagem(boas_vindas, chat_id=chat_id)
            return

        if not texto:
            return

        # Indicar que está digitando / gravando áudio no Telegram
        try:
            self.session.post(f"{self.base_url}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
        except Exception:
            pass

        # Processar com o Gemini
        resposta_texto = self.processar_comando_remoto(texto, chat_id=chat_id)

        # Enviar resposta por texto
        self.enviar_mensagem(resposta_texto, chat_id=chat_id)

        # Enviar também áudio falado pelo JARVIS
        try:
            caminho_audio = self.sintetizar_audio_resposta(resposta_texto)
            if caminho_audio and os.path.exists(caminho_audio):
                self.enviar_audio_voz(caminho_audio, chat_id=chat_id)
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Não foi possível enviar áudio de resposta: {e}")

    def polling_loop(self):
        """Loop contínuo de escuta (Long Polling) para mensagens do Telegram."""
        print("🤖 [TELEGRAM] Listener de mensagens ativado em segundo plano...")
        self.polling_active = True
        
        while self.polling_active:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                resp = self.session.get(f"{self.base_url}/getUpdates", params=params, timeout=25)
                
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("ok"):
                        for update in dados.get("result", []):
                            self.last_update_id = update.get("update_id", self.last_update_id)
                            self.tratar_atualizacao(update)
                else:
                    time.sleep(3)
            except Exception:
                time.sleep(3)

    def iniciar_em_segundo_plano(self, gemini_chat=None):
        """Inicia a escuta de mensagens do Telegram em uma thread separada."""
        if not self.is_configured():
            print("ℹ️  [TELEGRAM] TELEGRAM_BOT_TOKEN não configurado. Listener remoto desativado.")
            return
        
        if gemini_chat:
            self.conectar_gemini(gemini_chat)
            
        thread = threading.Thread(target=self.polling_loop, daemon=True, name="JarvisTelegramBot")
        thread.start()
        print("✅ [TELEGRAM] Módulo conectado com sucesso e aguardando mensagens no Telegram.")

telegram_service = TelegramBotService()
