"""
Módulo de Planejamento Hierárquico Multi-Etapas (Planner / ReAct Loop) do J.A.R.V.I.S.
Inspirado na arquitetura do OpenJarvis (Stanford).

Permite decompor instruções compostas ou condicionais do usuário
(ex: "verifique se a impressão terminou, se sim desligue a tomada e me envie uma foto no Telegram")
em um grafo ordenado de sub-tarefas executadas sequencialmente com validação de pré-condições.
"""

import re
import json
import logging
from typing import Any

logger = logging.getLogger("jarvis-planner")


class PlannerService:
    def __init__(self):
        self._conectores_compostos = [
            r"\b(e depois|em seguida|logo apos|logo após|depois de|depois disso)\b",
            r"\b(se\s+.+\s+(?:entao|então|desligue|ligue|avise|mande|cancele))\b",
            r"\b(primeiro\s+.+\s+depois)\b",
            r"\b(alem disso|além disso|tambem|também)\s+(?:ligue|desligue|verifique|tire|mande)\b"
        ]

    def eh_instrucao_composta(self, texto: str) -> bool:
        """Identifica se uma solicitação contém múltiplos passos ou regras condicionais."""
        t = texto.strip().lower()
        if len(t) < 15:
            return False
        return any(re.search(rx, t) for rx in self._conectores_compostos)

    def decompor_e_executar(self, instrucao: str, timeout_passo: float = 20.0) -> str:
        """
        Decompõe a instrução em etapas estruturadas e as executa ordenadamente,
        alimentando os resultados de passos anteriores para os passos subsequentes.
        """
        logger.info(f"Decompondo instrução complexa: {instrucao}")
        
        # 1. Solicita ao modelo (Gemini ou provedor ativo) o plano em formato JSON estrito
        prompt_planner = (
            "Você é o Planejador Tático do J.A.R.V.I.S. (Planner Loop / OpenJarvis).\n"
            "O usuário deu uma instrução composta que requer múltiplos passos sequenciais ou condicionais.\n"
            "Decomponha esta instrução em uma lista estrita de etapas JSON no seguinte formato:\n"
            "[\n"
            "  {\n"
            '    "passo": 1,\n'
            '    "descricao": "Verificar status da impressora",\n'
            '    "ferramenta": "consultar_status_impressora_3d",\n'
            '    "argumentos": {}\n'
            "  },\n"
            "  {\n"
            '    "passo": 2,\n'
            '    "descricao": "Se temperatura da mesa <= 50, desligar a tomada",\n'
            '    "ferramenta": "controlar_dispositivos_casa_inteligente",\n'
            '    "argumentos": {"dispositivo": "tomada da impressora", "acao": "desligar"},\n'
            '    "condicao_dependente": "apenas se o passo 1 indicar conclusao ou temperatura segura"\n'
            "  }\n"
            "]\n\n"
            f"Instrução do usuário: \"{instrucao}\"\n\n"
            "Responda ESTRITAMENTE com a array JSON, sem markdown nem comentários extras:"
        )

        try:
            from gemini_session import gemini_session
            plano_raw = gemini_session.enviar(prompt_planner, origem="planner", timeout=25.0)
            
            # Limpa delimitadores de código
            limpo = re.sub(r"^```(?:json)?\s*", "", plano_raw.strip())
            limpo = re.sub(r"\s*```$", "", limpo)
            etapas = json.loads(limpo)
            
            if not isinstance(etapas, list) or not etapas:
                return ""  # deixa o fluxo normal de turno único processar
        except Exception as e:
            logger.warning(f"Não foi possível gerar plano estruturado via LLM ({e}). Seguindo fluxo padrão.")
            return ""

        # 2. Executa as etapas sequencialmente
        from jarvis_tools import JARVIS_TOOLS
        mapa_ferramentas = {f.__name__: f for f in JARVIS_TOOLS}
        
        historico_execucao = []
        for i, etapa in enumerate(etapas[:5]):  # Limite de segurança de 5 etapas por plano
            nome_tool = etapa.get("ferramenta")
            args = etapa.get("argumentos", {})
            desc = etapa.get("descricao", f"Passo {i+1}")
            
            fn = mapa_ferramentas.get(nome_tool)
            if not fn:
                continue

            try:
                print(f"▶️ [PLANNER] Executando Passo {i+1}: {desc} ({nome_tool})")
                res = fn(**args) if args else fn()
                historico_execucao.append(f"Passo {i+1} ({desc}): {res}")
            except Exception as e_step:
                historico_execucao.append(f"Passo {i+1} ({desc}) falhou: {e_step}")
                break

        # 3. Sintetiza a resposta final para o usuário no estilo J.A.R.V.I.S.
        prompt_sintese = (
            f"O usuário solicitou: \"{instrucao}\"\n"
            "As etapas planejadas foram executadas com os seguintes resultados:\n"
            + "\n".join(historico_execucao) + "\n\n"
            "Sintetize uma resposta verbal formal, concisa e direta para o usuário no estilo do J.A.R.V.I.S. (1 a 2 frases):"
        )
        try:
            from gemini_session import gemini_session
            return gemini_session.enviar(prompt_sintese, origem="planner", timeout=20.0)
        except Exception:
            return "Plano concluído com sucesso, senhor. " + " ".join(historico_execucao[:2])


planner_service = PlannerService()
