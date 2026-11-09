"""
Módulo de Integração com Telegram Bot do J.A.R.V.I.S.
Permite controlar o assistente pelo celular (texto e áudio de voz),
receber respostas faladas com Edge-TTS e enviar notificações proativas.
"""

import os
import io
import sys
import time
import json
import asyncio
import threading
import random
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv


env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class TelegramBotService:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.api_url = os.getenv("TELEGRAM_API_URL", "https://api.telegram.org").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "JARVIS-Assistant/1.0"})
        self._poll_session = requests.Session()   # sessão exclusiva do long polling (não compartilhada com os envios)
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tg-msg")
        self.polling_active = False
        self.last_update_id = 0

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
            return {"ok": False, "error": self._limpar_erro(e)}

    def _limpar_erro(self, e: Exception) -> str:
        """Remove o token do bot de strings de erro para evitar vazamento em logs e retornos ao LLM."""
        msg = str(e)
        if self.token:
            msg = msg.replace(self.token, "[TOKEN_REDACTED]")
        return msg

    def salvar_chat_id(self, chat_id: str):
        """Registra o Chat ID do dono no .env (escrita atômica)."""
        from env_utils import atualizar_env
        self.chat_id = str(chat_id)
        if atualizar_env("TELEGRAM_CHAT_ID", self.chat_id):
            print(f"📱 [TELEGRAM] Chat ID {self.chat_id} registrado no .env.")

    def enviar_mensagem(self, texto: str, chat_id: str = None) -> str:
        """
        Envia uma mensagem de texto para o Telegram do usuário.
        """
        if not self.is_configured():
            return "Telegram não configurado no arquivo .env."
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return "Destinatário do Telegram não definido. Envie /start para o seu bot @Dafnhe_JARVIS_bot primeiro."

        if len(texto) > 4000:   # limite do Telegram: 4096 caracteres por mensagem
            retorno = ""
            for i in range(0, len(texto), 4000):
                retorno = self.enviar_mensagem(texto[i:i + 4000], chat_id=chat_id)
            return retorno

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
            return f"Erro de conexão ao enviar mensagem no Telegram: {self._limpar_erro(e)}"

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
            print(f"⚠️ [TELEGRAM] Erro ao enviar áudio de voz: {self._limpar_erro(e)}")
            return False

    def enviar_foto(self, foto, chat_id: str = None, legenda: str = "") -> bool:
        """
        Envia uma foto (caminho em disco ou bytes JPEG) para o Telegram do usuário.
        """
        if not self.is_configured():
            return False
        
        target_chat = chat_id or self.chat_id
        if not target_chat:
            return False

        url = f"{self.base_url}/sendPhoto"
        try:
            files = None
            if isinstance(foto, bytes):
                files = {"photo": ("snapshot.jpg", io.BytesIO(foto), "image/jpeg")}
            elif isinstance(foto, str) and os.path.exists(foto):
                files = {"photo": open(foto, "rb")}
            else:
                return False

            data = {"chat_id": target_chat}
            if legenda:
                data["caption"] = legenda
                data["parse_mode"] = "Markdown"
            resp = self.session.post(url, data=data, files=files, timeout=30)
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Erro ao enviar foto: {self._limpar_erro(e)}")
            return False

    def sintetizar_audio_resposta(self, texto: str) -> str:
        """Gera áudio com Edge-TTS para envio pelo Telegram."""
        import edge_tts
        import tempfile
        from voice_engine import limpar_para_fala
        voice_name = os.getenv("JARVIS_VOICE", "pt-BR-AntonioNeural")
        falavel = limpar_para_fala(texto)[:1500]
        if not falavel:
            return ""
        fd, caminho = tempfile.mkstemp(prefix="jarvis_tg_", suffix=".mp3")   # arquivo próprio: sem corrida entre mensagens
        os.close(fd)

        async def _gerar():
            await asyncio.wait_for(edge_tts.Communicate(falavel, voice_name).save(caminho), timeout=25)

        novo_loop = asyncio.new_event_loop()
        try:
            novo_loop.run_until_complete(_gerar())
            return caminho
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Falha ao sintetizar áudio: {e}")
            try:
                os.unlink(caminho)
            except OSError:
                pass
            return ""
        finally:
            novo_loop.close()

    def conectar_gemini(self, gemini_chat=None, chat_lock=None):
        """Compatibilidade: a sessão do Gemini agora é única e vive em gemini_session.py."""
        return None

    def processar_comando_remoto(self, texto_comando: str, chat_id: str = "") -> str:
        """Encaminha o comando ao núcleo (roteamento local/nuvem + fila única do Gemini)."""
        from brain_core import processar_comando
        print(f"\n📱 [TELEGRAM] \"{texto_comando}\"")
        resposta = processar_comando(texto_comando, origem="telegram")
        print(f"🎙️ [J.A.R.V.I.S.]: \"{resposta}\"")
        return resposta

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
        if not self.chat_id:
            if os.getenv("TELEGRAM_ALLOW_AUTO_REGISTER", "0") != "1":
                print(f"⚠️ [TELEGRAM] TELEGRAM_CHAT_ID não definido; ignorando ID {chat_id}. "
                      f"Defina TELEGRAM_CHAT_ID no .env (ou TELEGRAM_ALLOW_AUTO_REGISTER=1 só para o primeiro pareamento).")
                return
            self.salvar_chat_id(chat_id)
        if texto == "/start":
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
                try:
                    self.enviar_audio_voz(caminho_audio, chat_id=chat_id)
                finally:
                    try:
                        os.unlink(caminho_audio)
                    except OSError:
                        pass
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Não foi possível enviar áudio de resposta: {e}")

    def _tratar_seguro(self, update: dict):
        try:
            self.tratar_atualizacao(update)
        except Exception as e:
            print(f"⚠️ [TELEGRAM] Erro ao tratar mensagem: {e}")

    def polling_loop(self):
        """Loop contínuo de escuta (Long Polling) para mensagens do Telegram."""
        print("🤖 [TELEGRAM] Listener de mensagens ativado em segundo plano...")
        self.polling_active = True
        
        while self.polling_active:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                resp = self._poll_session.get(f"{self.base_url}/getUpdates", params=params, timeout=(5, 30))
                
                if resp.status_code == 200:
                    dados = resp.json()
                    if dados.get("ok"):
                        for update in dados.get("result", []):
                            self.last_update_id = update.get("update_id", self.last_update_id)
                            # Em pool: uma resposta lenta do Gemini não congela a leitura de novas mensagens
                            self._pool.submit(self._tratar_seguro, update)
                else:
                    time.sleep(3)
            except Exception:
                time.sleep(3)

    def iniciar_em_segundo_plano(self, gemini_chat=None, chat_lock=None):
        """Inicia a escuta de mensagens do Telegram em uma thread separada."""
        if not self.is_configured():
            print("ℹ️  [TELEGRAM] TELEGRAM_BOT_TOKEN não configurado. Listener remoto desativado.")
            return
        
        thread = threading.Thread(target=self.polling_loop, daemon=True, name="JarvisTelegramBot")
        thread.start()
        print("✅ [TELEGRAM] Módulo conectado com sucesso e aguardando mensagens no Telegram.")

telegram_service = TelegramBotService()
