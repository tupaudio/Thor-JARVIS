"""
brain_core.py — Ponto único de entrada para comandos do J.A.R.V.I.S.

Terminal, Telegram e iPhone chamam `processar_comando(texto, origem)`. Antes, a lógica de
roteamento estava duplicada em main.py e telegram_service.py, e o telegram_service ainda
importava `main` (carregando o programa duas vezes). Agora há um só caminho:

  1. Intenção local (sistema, hardware, SSD, Ollama, luzes, braço, hora) -> código determinístico,
     com prazo curto: se um dispositivo não responder, o usuário recebe uma resposta educada
     e o loop principal não trava.
  2. Modo `local_only` sem intenção reconhecida -> conversa no Ollama.
  3. Caso contrário -> nuvem (Gemini com function calling via GeminiSession; OpenAI/Claude via REST).
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime

from ai_router import ai_router, normalizar

# Pool dinâmico para ações locais com prazo (evita esgotamento se dispositivos IoT demorarem para responder).
_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="jarvis-local")


def com_prazo(fn, prazo: float, msg_estouro: str):
    """Executa fn() e devolve seu resultado; se passar do prazo devolve msg_estouro e cancela o future."""
    fut = _pool.submit(fn)
    try:
        return fut.result(timeout=prazo)
    except FutTimeout:
        fut.cancel()
        return msg_estouro
    except Exception as e:
        return f"Não consegui concluir a ação, senhor: {e}"


def _acao_luz(t: str) -> str:
    from iot_service import iot_service
    if re.search(r"\b(apag\w+|deslig\w+)\b", t):
        return com_prazo(lambda: iot_service.controlar("luz", "desligar"), 6,
                         "Os dispositivos de iluminação não responderam a tempo, senhor.")
    if re.search(r"\b(lig\w+|acend\w+)\b", t):
        return com_prazo(lambda: iot_service.controlar("luz", "ligar"), 6,
                         "Os dispositivos de iluminação não responderam a tempo, senhor.")
    if re.search(r"\b(status|como (esta|estao))\b", t):
        return com_prazo(lambda: iot_service.listar_status(), 4, "A consulta aos dispositivos demorou demais, senhor.")
    return ""  # cor/brilho/dispositivo específico: deixa a nuvem escolher a ferramenta certa


def _acao_braco(t: str) -> str:
    from hardware_simulator import hardware
    gestos = [(r"\b(acen\w+|tchau)\b", "acenar", "Saudação executada"),
              (r"\b(apont\w+)\b", "apontar", "Direcionamento visual"),
              (r"\b(repouso|descans\w+|abaix\w+ (o )?braco)\b", "repouso", "Posição de descanso"),
              (r"\b(positivo|joinha)\b", "positivo", "Confirmação afirmativa")]
    for rx, gesto, detalhe in gestos:
        if re.search(rx, t):
            return com_prazo(lambda: hardware.mover_braco(gesto, detalhe), 4,
                             "O braço não confirmou o movimento a tempo, senhor.")
    return ""


def executar_intencao_local(intencao: str, texto: str) -> str:
    """Retorna a resposta ou '' (quando a nuvem deve assumir)."""
    from system_service import system_service
    t = normalizar(texto)
    try:
        if intencao == "status":
            return com_prazo(system_service.obter_telemetria, 5, "A coleta de telemetria demorou demais, senhor.")
        if intencao == "hardware":
            return com_prazo(system_service.obter_detalhes_hardware, 5, "A leitura de hardware demorou demais, senhor.")
        if intencao == "armazenamento":
            return com_prazo(system_service.obter_armazenamento, 5, "A leitura do disco demorou demais, senhor.")
        if intencao == "ollama":
            return com_prazo(system_service.obter_status_ollama_texto, 4, "O Ollama não respondeu a tempo, senhor.")
        if intencao == "luz":
            return _acao_luz(t)
        if intencao == "braco":
            return _acao_braco(t)
        if intencao == "hora":
            return f"Agora são {datetime.now():%H:%M}, senhor."
        if intencao == "data":
            return f"Hoje é dia {datetime.now():%d/%m/%Y}, senhor."
    except Exception as e:
        return f"Falha ao executar o comando local: {e}"
    return ""


def processar_comando(texto: str, origem: str = "cli", timeout: float = 75.0) -> str:
    """Processa um comando e devolve o texto da resposta. `origem`: 'voz' | 'cli' | 'telegram'."""
    texto = (texto or "").strip()
    if not texto:
        return ""

    print(f"\n⚡ [COMANDO ({origem.upper()})]: \"{texto}\"")
    from dispatcher import contexto_origem
    contexto_origem.set(origem)   # laço OpenAI/Claude roda nesta thread; o Gemini define no worker

    def _responder(r: str) -> str:
        print(f"🎙️ [J.A.R.V.I.S.]: \"{r}\"\n")
        return r

    from traces_service import traces_service

    with traces_service.medir(origem=origem, entrada=texto) as tr:
        modo = ai_router.obter_status()["modo"]  # sem rede

        if modo in ("hybrid", "local_only"):
            intencao = ai_router.detectar_intencao_local(texto)
            if intencao:
                tr["rota"] = "local_intencao"
                tr["modelo"] = intencao
                resp = executar_intencao_local(intencao, texto)
                if resp:
                    return _responder(resp)
            if modo == "local_only":
                tr["rota"] = "ollama_local"
                tr["modelo"] = ai_router.local_model
                r = ai_router.executar_local(texto)
                if r.get("sucesso") and r.get("resposta"):
                    return _responder(r["resposta"])
                return _responder("Estou em modo 100% local e o Ollama não conseguiu responder a este pedido, senhor.")

        from jarvis_tools import JARVIS_SYSTEM_INSTRUCTION
        provedor = ai_router.cloud_provider
        tr["rota"] = f"nuvem_{provedor}"
        tr["modelo"] = provedor
        resp_nuvem = ""

        # PLANEJADOR HIERÁRQUICO MULTI-ETAPAS (Pendência 2 / OpenJarvis Planner Loop)
        from planner_service import planner_service
        if provedor not in ("openai", "claude") and planner_service.eh_instrucao_composta(texto):
            tr["rota"] = "planner_multi_etapas"
            resp_plano = planner_service.decompor_e_executar(texto)
            if resp_plano:
                return _responder(resp_plano)
        
        if provedor == "openai":
            resp_nuvem = ai_router.executar_nuvem_openai(texto, system_instruction=JARVIS_SYSTEM_INSTRUCTION)
        elif provedor == "claude":
            resp_nuvem = ai_router.executar_nuvem_claude(texto, system_instruction=JARVIS_SYSTEM_INSTRUCTION)
        else:
            from gemini_session import gemini_session
            resp_nuvem = gemini_session.enviar(texto, origem=origem, timeout=timeout)

        # FAILOVER AUTOMÁTICO PARA OLLAMA LOCAL (MP2 / F9):
        # Se estiver no modo híbrido e o provedor de nuvem falhar por sobrecarga, timeout ou queda de conexão,
        # consulta o modelo local do Ollama para não deixar o usuário sem resposta.
        falhou_nuvem = any(termo in resp_nuvem.lower() for termo in [
            "sobrecarregados", "imprevisto ao processar", "muitos pedidos em fila",
            "não consegui falar", "respondeu com erro", "instabilidade"
        ])
        if modo == "hybrid" and falhou_nuvem:
            if ai_router.testar_ollama_online():
                print("🔄 [CORE] Nuvem indisponível: acionando failover transparente para o Ollama local.")
                tr["rota"] = "failover_ollama"
                tr["modelo"] = ai_router.local_model
                r = ai_router.executar_local(texto)
                if r.get("sucesso") and r.get("resposta"):
                    return _responder(f"{r['resposta']} (respondido via Ollama local offline)")

        return _responder(resp_nuvem)


def processar_async(texto: str, origem: str, ao_terminar, timeout: float = 75.0):
    """Processa em thread própria e chama ao_terminar(resposta). Usado pelo HUD para não segurar o HTTP."""
    def _run():
        try:
            resp = processar_comando(texto, origem=origem, timeout=timeout)
        except Exception as e:
            resp = f"Tive um imprevisto, senhor: {e}"
        try:
            ao_terminar(resp)
        except Exception as e:
            print(f"⚠️ [CORE] Erro no callback de resposta: {e}")
    threading.Thread(target=_run, daemon=True, name=f"jarvis-cmd-{origem}").start()
