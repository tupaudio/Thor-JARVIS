"""
Módulo de Roteamento de Inteligência Artificial para o J.A.R.V.I.S.
Gerencia múltiplos motores de IA e roteamento híbrido (Local vs Nuvem):
- Motores Locais: Ollama (Llama 3.2, Qwen 2.5, Mistral, Phi-3, etc.)
- Motores na Nuvem: Google Gemini, OpenAI (ChatGPT), Anthropic (Claude)
- Modo Híbrido: Tarefas rápidas/IoT/Windows localmente; raciocínio complexo na nuvem.
"""

import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

# Palavras-chave que caracterizam tarefas locais de baixa complexidade (IoT, Windows, Servos, Hora)
PALAVRAS_CHAVE_LOCAL = [
    # Luzes e IoT
    "luz", "luzes", "lampada", "lâmpada", "fita led", "led", "tomada", "acender", "apagar",
    "ligar a luz", "desligar a luz", "cor da luz", "brilho", "casa inteligente",
    # Volume e som do PC
    "volume", "mutar", "mudo", "desmutar", "som do windows", "aumentar volume", "abaixar volume",
    # Controle do Windows
    "bloquear", "bloqueie", "trancar", "tranque", "tela", "computador", "pc",
    "abrir programa", "abra o", "fechar programa", "feche o", "status do pc", "cpu", "memoria", "memória",
    # Braço robótico
    "acenar", "acene", "apontar", "aponte", "braco", "braço", "repouso", "positivo",
    # Consultas rápidas locais
    "que horas", "hora atual", "que dia", "data de hoje"
]

class AIRouter:
    def __init__(self):
        self.carregar_configuracoes()

    def carregar_configuracoes(self):
        """Recarrega os parâmetros de configuração do .env."""
        # Modos: 'hybrid' (padrão), 'cloud_only', 'local_only'
        self.ai_mode = os.getenv("AI_MODE", "hybrid").lower().strip()
        
        # Provedor na Nuvem: 'gemini', 'openai', 'claude'
        self.cloud_provider = os.getenv("CLOUD_AI_PROVIDER", "gemini").lower().strip()
        
        # Provedor Local (Ollama)
        self.local_model = os.getenv("LOCAL_AI_MODEL", "llama3.2").strip()
        self.ollama_url = os.getenv("LOCAL_OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        
        # Chaves de API
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        
        # Histórico de conversação para provedores REST
        self.historico = []

    def definir_modo(self, modo: str) -> str:
        """Altera dinamicamente o modo de operação ('hybrid', 'cloud_only', 'local_only')."""
        modo = modo.lower().strip()
        if modo in ["hybrid", "hibrido", "híbrido"]:
            self.ai_mode = "hybrid"
            msg = "Modo de Inteligência alterado para HÍBRIDO (Tarefas rápidas locais via Ollama e tarefas complexas na nuvem)."
        elif modo in ["local", "local_only", "offline"]:
            self.ai_mode = "local_only"
            msg = f"Modo de Inteligência alterado para LOCAL/OFFLINE ({self.local_model} via Ollama)."
        elif modo in ["cloud", "cloud_only", "online", "nuvem"]:
            self.ai_mode = "cloud_only"
            msg = f"Modo de Inteligência alterado para NUVEM EXCLUSIVA ({self.cloud_provider.upper()})."
        else:
            return f"Modo '{modo}' não reconhecido. Opções: 'hybrid', 'cloud_only', 'local_only'."
        
        self._atualizar_env_var("AI_MODE", self.ai_mode)
        print(f"🔄 [AI ROUTER] {msg}")
        return msg

    def definir_provedor_nuvem(self, provedor: str) -> str:
        """Altera dinamicamente o provedor na nuvem ('gemini', 'openai', 'claude')."""
        prov = provedor.lower().strip()
        if "gemini" in prov or "google" in prov:
            self.cloud_provider = "gemini"
            nome = "Google Gemini"
        elif "openai" in prov or "chatgpt" in prov or "gpt" in prov:
            self.cloud_provider = "openai"
            nome = "OpenAI (ChatGPT)"
        elif "claude" in prov or "anthropic" in prov:
            self.cloud_provider = "claude"
            nome = "Anthropic (Claude)"
        else:
            return f"Provedor '{provedor}' não suportado. Opções: 'gemini', 'openai', 'claude'."

        self._atualizar_env_var("CLOUD_AI_PROVIDER", self.cloud_provider)
        msg = f"Motor de inteligência na nuvem alterado com sucesso para: {nome}."
        print(f"🔄 [AI ROUTER] {msg}")
        return msg

    def definir_modelo_local(self, modelo: str) -> str:
        """Define o modelo que o Ollama deve utilizar (ex: 'llama3.2', 'qwen2.5:3b', 'mistral')."""
        self.local_model = modelo.strip()
        self._atualizar_env_var("LOCAL_AI_MODEL", self.local_model)
        msg = f"Modelo local do Ollama definido para: {self.local_model}."
        print(f"🔄 [AI ROUTER] {msg}")
        return msg

    def _atualizar_env_var(self, chave: str, valor: str):
        """Persiste uma variável no arquivo .env."""
        try:
            if not os.path.exists(env_path):
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"{chave}={valor}\n")
                return

            with open(env_path, "r", encoding="utf-8") as f:
                linhas = f.readlines()

            achou = False
            novas_linhas = []
            for linha in linhas:
                if linha.strip().startswith(f"{chave}="):
                    novas_linhas.append(f"{chave}={valor}\n")
                    achou = True
                else:
                    novas_linhas.append(linha)

            if not achou:
                novas_linhas.append(f"{chave}={valor}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(novas_linhas)
        except Exception as e:
            print(f"⚠️ [AI ROUTER] Falha ao persistir {chave} no .env: {e}")

    def is_tarefa_local(self, texto: str) -> bool:
        """Determina heuristicamente se o comando é simples para resolver localmente."""
        t = texto.lower().strip()
        # Se for comando muito longo, pesquisa ou criação, encaminha pra nuvem
        if len(t) > 120 or "pesquis" in t or "busqu" in t or "noticia" in t or "youtube" in t or "resum" in t or "email" in t or "e-mail" in t:
            return False
        
        return any(termo in t for termo in PALAVRAS_CHAVE_LOCAL)

    def testar_ollama_online(self) -> bool:
        """Verifica se o servidor Ollama está respondendo localmente."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=1.5)
            return resp.status_code == 200
        except Exception:
            return False

    def executar_local(self, prompt: str, system_prompt: str = "") -> dict:
        """
        Executa inferência rápida no modelo local via API REST nativa do Ollama.
        """
        if not self.testar_ollama_online():
            return {
                "sucesso": False,
                "erro": f"Ollama não detectado em {self.ollama_url}. Verifique se o aplicativo Ollama está aberto no computador."
            }

        url = f"{self.ollama_url}/api/generate"
        
        instrucao_sistema = (
            "Você é o sub-sistema local de comando do J.A.R.V.I.S. "
            "Sua função é interpretar comandos simples de controle de luzes (IoT), volume, computador e braço robótico. "
            "Responda sempre de forma curta, direta e objetiva em português."
        )
        if system_prompt:
            instrucao_sistema += f"\nDiretriz adicional: {system_prompt}"

        payload = {
            "model": self.local_model,
            "prompt": prompt,
            "system": instrucao_sistema,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 128
            }
        }

        try:
            inicio = time.time()
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                dados = resp.json()
                texto_resposta = dados.get("response", "").strip()
                duracao = time.time() - inicio
                print(f"⚡ [OLLAMA LOCAL ({self.local_model}) - {duracao:.2f}s]: \"{texto_resposta}\"")
                return {
                    "sucesso": True,
                    "resposta": texto_resposta,
                    "modelo": self.local_model,
                    "tempo": duracao
                }
            else:
                return {"sucesso": False, "erro": f"Ollama HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"sucesso": False, "erro": str(e)}

    def executar_nuvem_openai(self, prompt: str, system_instruction: str = "") -> str:
        """Chama a API da OpenAI (ChatGPT) com o modelo gpt-4o-mini."""
        key = os.getenv("OPENAI_API_KEY", self.openai_key).strip()
        if not key or "sua_chave" in key:
            return "Chave OPENAI_API_KEY não configurada no arquivo .env, senhor."

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        
        # Mantém histórico recente
        for h in self.historico[-6:]:
            messages.append(h)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.7
        }
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                dados = resp.json()
                texto = dados["choices"][0]["message"]["content"].strip()
                self.historico.append({"role": "user", "content": prompt})
                self.historico.append({"role": "assistant", "content": texto})
                return texto
            return f"Erro OpenAI HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return f"Erro ao comunicar com a OpenAI: {e}"

    def executar_nuvem_claude(self, prompt: str, system_instruction: str = "") -> str:
        """Chama a API da Anthropic (Claude) com o modelo claude-3-5-haiku-latest."""
        key = os.getenv("ANTHROPIC_API_KEY", self.anthropic_key).strip()
        if not key or "sua_chave" in key:
            return "Chave ANTHROPIC_API_KEY não configurada no arquivo .env, senhor."

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        messages = []
        for h in self.historico[-6:]:
            messages.append(h)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 1024,
            "system": system_instruction if system_instruction else "Você é o J.A.R.V.I.S.",
            "messages": messages
        }
        try:
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                dados = resp.json()
                texto = dados["content"][0]["text"].strip()
                self.historico.append({"role": "user", "content": prompt})
                self.historico.append({"role": "assistant", "content": texto})
                return texto
            return f"Erro Anthropic HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return f"Erro ao comunicar com a Anthropic Claude: {e}"

    def obter_status(self) -> dict:
        """Retorna o estado atual dos motores para diagnóstico e exibição."""
        ollama_ativo = self.testar_ollama_online()
        return {
            "modo": self.ai_mode,
            "provedor_nuvem": self.cloud_provider,
            "modelo_local": self.local_model,
            "ollama_online": ollama_ativo,
            "url_ollama": self.ollama_url
        }

ai_router = AIRouter()
