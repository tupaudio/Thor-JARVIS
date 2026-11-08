"""
ai_router.py — Roteamento de IA do J.A.R.V.I.S. (nuvem × Ollama local).

Mudanças principais em relação à versão anterior:
  * O "modo local" deixou de pedir a um LLM de 3B para improvisar respostas sobre o sistema
    (era uma das fontes das alucinações com "C:\\"). Pedidos de sistema/hardware/IoT/braço são
    reconhecidos por INTENÇÃO (regex com limite de palavra, sem acento) e executados por código.
    O Ollama só conversa livremente quando o modo é `local_only`.
  * Status do Ollama com cache de 5 s (antes cada comando do usuário fazia um GET bloqueante).
  * Histórico de OpenAI/Claude limitado e sempre iniciando com 'user' (a API da Anthropic exige).
  * Modelos de nuvem configuráveis por .env; escrita do .env atômica (env_utils).
"""

import os
import re
import time
import unicodedata
import threading
from collections import deque

import requests
from dotenv import load_dotenv

from env_utils import atualizar_env, ENV_PATH

load_dotenv(ENV_PATH)

# Pedidos que SEMPRE vão para a nuvem (precisam de ferramentas/rede), mesmo que contenham uma palavra "local".
_RE_NUVEM = re.compile(
    r"\b(pesquis\w*|busc\w*|noticia\w*|youtube|resum\w*|e-?mail\w*|spotify|to(ca|car|que)|musica\w*|"
    r"agenda\w*|compromiss\w*|clima|previsao|chuva|rota|transito|waze|notion|whatsapp|telegram|"
    r"gasto\w*|protocolo\w*|sentinela|persona\w*|personalidade|impressora|foto|camera)\b"
)

# (intenção, regex) — a primeira que casar vence. Texto já normalizado (minúsculo, sem acento).
_INTENCOES = [
    ("ollama",        re.compile(r"\bollama\b")),
    ("armazenamento", re.compile(r"\b(hd|ssd|nvme|disco|armazenamento|storage)\b")),
    ("hardware",      re.compile(r"\b(hardware|especificac\w+|optiplex|que maquina|modelo d[aeo] (maquina|cpu|processador)|qual (e )?o? ?processador|que processador)\b")),
    ("status",        re.compile(r"\b(status|estado|telemetria|como (esta|anda|vai))\b.*\b(servidor|sistema|computador|pc|maquina)\b"
                                 r"|\b(servidor|sistema|computador|pc)\b.*\b(status|estado|telemetria)\b"
                                 r"|\b(uso de (cpu|memoria|ram)|temperatura|cpu|memoria|ram)\b")),
    ("luz",           re.compile(r"\b(luz|luzes|lampada\w*|fita led|led|tomada\w*|dimmer)\b")),
    ("braco",         re.compile(r"\b(acen\w+|apont\w+|braco|repouso|joinha|positivo|tchau)\b")),
    ("hora",          re.compile(r"\b(que horas|hora atual|horario)\b")),
    ("data",          re.compile(r"\b(que dia|data de hoje)\b")),
]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower().strip())
    return "".join(c for c in t if not unicodedata.combining(c))


class AIRouter:
    def __init__(self):
        self._lock = threading.Lock()
        self._http = requests.Session()
        self._cache_ollama = (0.0, None)
        self.historico = deque(maxlen=12)  # mensagens user/assistant alternadas, limitadas
        self.carregar_configuracoes()

    # ---------------------------------------------------------------- config
    def carregar_configuracoes(self):
        self.ai_mode = os.getenv("AI_MODE", "hybrid").lower().strip()
        self.cloud_provider = os.getenv("CLOUD_AI_PROVIDER", "gemini").lower().strip()
        self.local_model = os.getenv("LOCAL_AI_MODEL", "llama3.2").strip()
        self.ollama_url = os.getenv("LOCAL_OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()

    def definir_modo(self, modo: str) -> str:
        modo = normalizar(modo)
        if modo in ("hybrid", "hibrido"):
            self.ai_mode = "hybrid"
            msg = "Modo híbrido: comandos de sistema, luzes e braço rodam localmente; o resto vai para a nuvem."
        elif modo in ("local", "local_only", "offline"):
            self.ai_mode = "local_only"
            msg = f"Modo local/offline ({self.local_model} via Ollama)."
        elif modo in ("cloud", "cloud_only", "online", "nuvem"):
            self.ai_mode = "cloud_only"
            msg = f"Modo nuvem exclusiva ({self.cloud_provider.upper()})."
        else:
            return f"Modo '{modo}' não reconhecido. Opções: hybrid, cloud_only, local_only."
        atualizar_env("AI_MODE", self.ai_mode)
        return msg

    def definir_provedor_nuvem(self, provedor: str) -> str:
        p = normalizar(provedor)
        if "gemini" in p or "google" in p:
            self.cloud_provider, nome = "gemini", "Google Gemini"
        elif "openai" in p or "chatgpt" in p or "gpt" in p:
            self.cloud_provider, nome = "openai", "OpenAI"
        elif "claude" in p or "anthropic" in p:
            self.cloud_provider, nome = "claude", "Anthropic Claude"
        else:
            return f"Provedor '{provedor}' não suportado. Opções: gemini, openai, claude."
        atualizar_env("CLOUD_AI_PROVIDER", self.cloud_provider)
        self.historico.clear()
        return f"Motor de nuvem alterado para {nome}."

    def definir_modelo_local(self, modelo: str) -> str:
        self.local_model = modelo.strip()
        atualizar_env("LOCAL_AI_MODEL", self.local_model)
        return f"Modelo local do Ollama definido para {self.local_model}."

    # ------------------------------------------------------------- intenções
    def detectar_intencao_local(self, texto: str):
        """Retorna 'status', 'hardware', 'armazenamento', 'ollama', 'luz', 'braco', 'hora', 'data' ou None."""
        t = normalizar(texto)
        if len(t) > 140 or _RE_NUVEM.search(t):
            return None
        for nome, rx in _INTENCOES:
            if rx.search(t):
                return nome
        return None

    def is_tarefa_local(self, texto: str) -> bool:  # compatibilidade
        return self.detectar_intencao_local(texto) is not None

    # ---------------------------------------------------------------- Ollama
    def status_ollama(self, force: bool = False) -> dict:
        """Estado do Ollama com cache (5 s online / 3 s offline). Nunca levanta exceção."""
        agora = time.monotonic()
        with self._lock:
            ts, dado = self._cache_ollama
            if not force and dado is not None and agora - ts < (5.0 if dado["online"] else 3.0):
                return dado
        try:
            r = self._http.get(f"{self.ollama_url}/api/tags", timeout=(0.5, 1.5))
            r.raise_for_status()
            modelos = [m["name"] for m in r.json().get("models", []) if m.get("name")]
            carregados = []
            try:
                p = self._http.get(f"{self.ollama_url}/api/ps", timeout=(0.5, 1.0))
                carregados = [m["name"] for m in p.json().get("models", []) if m.get("name")]
            except Exception:
                pass
            resumo = (f"online, {len(modelos)} modelo(s) baixado(s): {', '.join(modelos) or 'nenhum'}"
                      + (f"; em memória agora: {', '.join(carregados)}" if carregados else ""))
            dado = {"online": True, "url": self.ollama_url, "modelos": modelos, "carregados": carregados, "resumo": resumo, "msg": resumo}
        except Exception:
            dado = {"online": False, "url": self.ollama_url, "modelos": [], "carregados": [],
                    "resumo": f"offline (sem resposta em {self.ollama_url}; verifique 'systemctl status ollama')"}
            dado["msg"] = dado["resumo"]
        with self._lock:
            self._cache_ollama = (agora, dado)
        return dado

    def testar_ollama_online(self) -> bool:
        return self.status_ollama()["online"]

    def executar_local(self, prompt: str, system_prompt: str = "") -> dict:
        """Conversa livre no Ollama (usado só no modo local_only)."""
        if not self.testar_ollama_online():
            return {"sucesso": False, "erro": f"Ollama offline em {self.ollama_url}."}
        sistema = (
            "Você é o J.A.R.V.I.S., assistente de bancada rodando em um servidor Debian GNU/Linux. "
            "Responda em português, de forma curta e objetiva. "
            "NUNCA invente informações sobre arquivos, discos, hardware ou o estado do sistema, e nunca "
            "mencione Windows ou unidades como C:. Se não souber, diga que precisa consultar o servidor."
        )
        if system_prompt:
            sistema += f"\n{system_prompt}"
        payload = {
            "model": self.local_model, "prompt": prompt, "system": sistema, "stream": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),  # mantém o modelo na RAM: corta a latência de partida a frio
            "options": {"temperature": 0.3, "num_predict": 160},
        }
        try:
            t0 = time.monotonic()
            r = self._http.post(f"{self.ollama_url}/api/generate", json=payload, timeout=(1.0, 25))
            if r.status_code == 200:
                texto = r.json().get("response", "").strip()
                return {"sucesso": True, "resposta": texto, "modelo": self.local_model, "tempo": time.monotonic() - t0}
            return {"sucesso": False, "erro": f"Ollama HTTP {r.status_code}"}
        except Exception as e:
            return {"sucesso": False, "erro": str(e)}

    # ------------------------------------------------------ nuvem via REST
    def _montar_mensagens(self, prompt: str) -> list:
        msgs = list(self.historico)
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _registrar(self, prompt: str, resposta: str):
        self.historico.append({"role": "user", "content": prompt})
        self.historico.append({"role": "assistant", "content": resposta})

    def executar_nuvem_openai(self, prompt: str, system_instruction: str = "") -> str:
        chave = os.getenv("OPENAI_API_KEY", "").strip()
        if not chave or "sua_chave" in chave:
            return "A chave OPENAI_API_KEY não está configurada no .env, senhor."
        msgs = ([{"role": "system", "content": system_instruction}] if system_instruction else []) + self._montar_mensagens(prompt)
        try:
            r = self._http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave}"},
                json={"model": self.openai_model, "messages": msgs, "temperature": 0.7},
                timeout=(3, 25),
            )
            if r.status_code == 200:
                texto = r.json()["choices"][0]["message"]["content"].strip()
                self._registrar(prompt, texto)
                return texto
            return f"A OpenAI respondeu com erro {r.status_code}, senhor."
        except Exception as e:
            return f"Não consegui falar com a OpenAI: {e}"

    def executar_nuvem_claude(self, prompt: str, system_instruction: str = "") -> str:
        chave = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not chave or "sua_chave" in chave:
            return "A chave ANTHROPIC_API_KEY não está configurada no .env, senhor."
        try:
            r = self._http.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": chave, "anthropic-version": "2023-06-01"},
                json={"model": self.anthropic_model, "max_tokens": 1024,
                      "system": system_instruction or "Você é o J.A.R.V.I.S.",
                      "messages": self._montar_mensagens(prompt)},
                timeout=(3, 25),
            )
            if r.status_code == 200:
                texto = r.json()["content"][0]["text"].strip()
                self._registrar(prompt, texto)
                return texto
            return f"A Anthropic respondeu com erro {r.status_code}, senhor."
        except Exception as e:
            return f"Não consegui falar com a Anthropic: {e}"

    # ---------------------------------------------------------------- status
    def obter_status(self, check_ollama: bool = False) -> dict:
        """Por padrão NÃO faz rede (o roteamento de cada comando só precisa do modo)."""
        st = {"modo": self.ai_mode, "provedor_nuvem": self.cloud_provider,
              "modelo_local": self.local_model, "url_ollama": self.ollama_url}
        if check_ollama:
            st["ollama_online"] = self.status_ollama()["online"]
        return st


ai_router = AIRouter()
