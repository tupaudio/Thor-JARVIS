"""
gemini_session.py — Dono único do cliente e do chat do Gemini (thread-safe, auto-recuperável).

Problemas que isto resolve:
  * "Cannot send a request, as the client has been closed": o telegram_service criava um
    `genai.Client` como variável LOCAL e guardava só o `chat`. Ao sair da função o Client era
    coletado pelo GC e fechava o transporte HTTP que o chat ainda usava. Aqui o Client é um
    atributo da sessão (referência forte durante toda a vida do processo) e, se mesmo assim o
    transporte aparecer fechado, a sessão se reconstrói preservando o histórico e repete o envio.
  * Chamadas simultâneas (iPhone + Telegram + terminal): TODAS passam por uma fila com prioridade
    (voz > terminal > Telegram) consumida por UMA thread. O chat do SDK nunca é tocado por duas
    threads ao mesmo tempo, sem lock global bloqueando quem chama: o chamador espera um Future
    com prazo e recebe uma mensagem educada se estourar, e o job abandonado é descartado.
  * Histórico infinito (servidor 24/7): é podado por turnos completos (sem quebrar pares
    function_call/function_response).
  * Sem timeout HTTP, uma requisição pendurada travaria a fila para sempre: o Client sobe com timeout.
"""

import os
import time
import queue
import random
import threading
import itertools
from concurrent.futures import Future, TimeoutError as FutTimeout
from dataclasses import dataclass, field

from dotenv import load_dotenv

from env_utils import ENV_PATH

load_dotenv(ENV_PATH)

PRIORIDADES = {"voz": 0, "cli": 1, "telegram": 2}


@dataclass(order=True)
class _Job:
    prioridade: int
    seq: int
    texto: str = field(compare=False)
    futuro: Future = field(compare=False)
    cancelado: bool = field(default=False, compare=False)


def _msg_erro_transitorio(e: Exception) -> bool:
    t = str(e).lower()
    return any(x in t for x in ("503", "unavailable", "high demand", "429", "resource_exhausted",
                                "timed out", "timeout", "deadline", "connection", "temporarily", "500", "502", "504"))


def _cliente_fechado(e: Exception) -> bool:
    t = str(e).lower()
    return "client has been closed" in t or "has been closed" in t


def _historico_invalido(e: Exception) -> bool:
    t = str(e).lower()
    return "function call turn" in t or "function response" in t or "invalid_argument" in t or "400" in t


class GeminiSession:
    def __init__(self):
        self._lock = threading.RLock()          # protege _client/_chat durante reconstrução
        self._client = None                     # referência forte: nunca deixe o Client virar variável local
        self._chat = None
        self._modelo_primario = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self._modelo_fallback = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
        self._modelo_atual = self._modelo_primario
        self._voltar_primario_em = 0.0
        self._max_contents = int(os.getenv("GEMINI_MAX_HISTORY", "40"))
        self._http_timeout_ms = int(os.getenv("GEMINI_HTTP_TIMEOUT_MS", "40000"))
        self._fila: "queue.PriorityQueue[_Job]" = queue.PriorityQueue()
        self._seq = itertools.count()
        self._worker = None
        self._worker_lock = threading.Lock()
        self._fila_max = int(os.getenv("GEMINI_QUEUE_MAX", "6"))

    # ----------------------------------------------------------- construção
    def _novo_client(self):
        from google import genai
        from google.genai import types
        chave = os.getenv("GEMINI_API_KEY", "").strip()
        if not chave or "sua_chave" in chave:
            raise RuntimeError("GEMINI_API_KEY não configurada no .env")
        try:
            return genai.Client(api_key=chave, http_options=types.HttpOptions(timeout=self._http_timeout_ms))
        except TypeError:  # SDK sem http_options
            return genai.Client(api_key=chave)

    def _garantir_client(self, forcar: bool = False):
        with self._lock:
            if self._client is None or forcar:
                antigo = self._client
                self._client = self._novo_client()
                if antigo is not None:
                    try:
                        antigo.close()
                    except Exception:
                        pass
            return self._client

    def _construir_chat(self, historico=None, forcar_client: bool = False):
        from google.genai import types
        from jarvis_tools import JARVIS_TOOLS, JARVIS_SYSTEM_INSTRUCTION  # import tardio: evita ciclo
        with self._lock:
            client = self._garantir_client(forcar=forcar_client)
            cfg = types.GenerateContentConfig(
                system_instruction=JARVIS_SYSTEM_INSTRUCTION, tools=JARVIS_TOOLS, temperature=0.7)
            kwargs = {"model": self._modelo_atual, "config": cfg}
            if historico:
                kwargs["history"] = historico
            self._chat = client.chats.create(**kwargs)
            return self._chat

    def _historico_atual(self) -> list:
        try:
            return list(self._chat.get_history(curated=True)) if self._chat else []
        except Exception:
            return []

    def resetar(self) -> str:
        """Descarta o histórico (novo chat limpo) — útil se a conversa ficar corrompida."""
        with self._lock:
            self._construir_chat(historico=None)
        return "Memória de conversa reiniciada, senhor."

    # ---------------------------------------------------------------- poda
    @staticmethod
    def _inicia_turno_usuario(content) -> bool:
        if getattr(content, "role", None) != "user":
            return False
        partes = getattr(content, "parts", None) or []
        return bool(partes) and not any(getattr(p, "function_response", None) for p in partes)

    def _podar_historico(self):
        hist = self._historico_atual()
        if len(hist) <= self._max_contents:
            return
        corte = len(hist) - self._max_contents // 2
        while corte < len(hist) and not self._inicia_turno_usuario(hist[corte]):
            corte += 1
        if corte >= len(hist):
            return
        try:
            self._construir_chat(historico=hist[corte:])
        except Exception as e:
            print(f"⚠️ [GEMINI] Falha ao podar histórico: {e}")

    # --------------------------------------------------------- envio (worker)
    def _enviar_unico(self, texto: str) -> str:
        if self._modelo_atual != self._modelo_primario and time.monotonic() > self._voltar_primario_em:
            self._modelo_atual = self._modelo_primario
            self._construir_chat(historico=self._historico_atual())
        if self._chat is None:
            self._construir_chat()
        resp = self._chat.send_message(texto)
        return (getattr(resp, "text", None) or "").strip() or "Comando executado, senhor."

    def _enviar_com_recuperacao(self, texto: str) -> str:
        ultimo_erro = None
        reconstruiu_client = reiniciou_historico = False
        for tentativa in range(4):
            try:
                resposta = self._enviar_unico(texto)
                self._podar_historico()
                return resposta
            except Exception as e:
                ultimo_erro = e
                if _cliente_fechado(e) and not reconstruiu_client:
                    print("🔄 [GEMINI] Cliente fechado: reconstruindo conexão e mantendo o histórico.")
                    reconstruiu_client = True
                    try:
                        self._construir_chat(historico=self._historico_atual(), forcar_client=True)
                    except Exception as e2:
                        ultimo_erro = e2
                    continue  # repete já, sem espera
                if _msg_erro_transitorio(e):
                    if tentativa == 1 and self._modelo_atual != self._modelo_fallback:
                        print(f"🔄 [GEMINI] Alternando para {self._modelo_fallback} por 5 min.")
                        self._modelo_atual = self._modelo_fallback
                        self._voltar_primario_em = time.monotonic() + 300
                        try:
                            self._construir_chat(historico=self._historico_atual())
                        except Exception:
                            pass
                        continue
                    time.sleep(min(2 ** tentativa + random.uniform(0.1, 0.9), 6))
                    continue
                if _historico_invalido(e) and not reiniciou_historico:
                    print("🔄 [GEMINI] Histórico inconsistente: reiniciando a conversa.")
                    reiniciou_historico = True
                    try:
                        self._construir_chat(historico=None)
                    except Exception as e2:
                        ultimo_erro = e2
                    continue
                break
        print(f"❌ [GEMINI] Falha definitiva: {ultimo_erro}")
        if ultimo_erro is not None and _msg_erro_transitorio(ultimo_erro):
            return "Os servidores do Gemini estão sobrecarregados, senhor. Tente novamente em instantes."
        return f"Tive um imprevisto ao processar o pedido, senhor: {str(ultimo_erro)[:140]}"

    def _loop_worker(self):
        while True:
            job = self._fila.get()
            if job.cancelado:           # o chamador já desistiu: não gasta chamada de API
                continue
            try:
                job.futuro.set_result(self._enviar_com_recuperacao(job.texto))
            except Exception as e:      # nunca deixar o worker morrer
                if not job.futuro.done():
                    job.futuro.set_result(f"Erro interno na sessão do Gemini: {e}")

    def _garantir_worker(self):
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop_worker, daemon=True, name="GeminiSessionWorker")
                self._worker.start()

    # -------------------------------------------------------------- API pública
    def enviar(self, texto: str, origem: str = "cli", timeout: float = 75.0) -> str:
        """Envia uma mensagem ao chat. Seguro para chamar de qualquer thread."""
        if threading.current_thread() is self._worker:
            return "Pedido recursivo bloqueado para evitar impasse, senhor."
        if self._fila.qsize() >= self._fila_max:
            return "Estou com muitos pedidos em fila, senhor. Aguarde um instante e repita."
        self._garantir_worker()
        job = _Job(PRIORIDADES.get(origem, 1), next(self._seq), texto, Future())
        self._fila.put(job)
        try:
            return job.futuro.result(timeout=timeout)
        except FutTimeout:
            job.cancelado = True
            return "Ainda estou processando o pedido anterior, senhor. Tente de novo em alguns segundos."

    def gerar_com_imagem(self, prompt: str, imagem, tentativas: int = 2) -> str:
        """Análise de visão sem estado (fora do chat e da fila), reutilizando o MESMO Client."""
        for i in range(tentativas):
            try:
                client = self._garantir_client()
                r = client.models.generate_content(model=self._modelo_primario, contents=[prompt, imagem])
                return (r.text or "").strip()
            except Exception as e:
                if _cliente_fechado(e) and i + 1 < tentativas:
                    self._garantir_client(forcar=True)
                    continue
                raise
        return ""

    def status(self) -> dict:
        return {"modelo": self._modelo_atual, "fila": self._fila.qsize(),
                "historico": len(self._historico_atual()), "worker_vivo": bool(self._worker and self._worker.is_alive())}


gemini_session = GeminiSession()
