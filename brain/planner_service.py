"""
planner_service.py — Planejador multi-etapas do J.A.R.V.I.S. (versão 2, segura).

Correções em relação à versão anterior:
  * O plano é gerado por uma chamada SEM ferramentas e SEM histórico (gemini_session.gerar_json).
    Antes o prompt ia ao chat com function calling ligado: o modelo podia executar as ferramentas
    durante o "planejamento" e o planejador as executava de novo (execução em dobro).
  * As condições são avaliadas POR CÓDIGO sobre o resultado dos passos anteriores
    (campo "se": {"passo": N, "contem": "texto"} ou {"passo": N, "nao_contem": "texto"}).
    Antes o campo `condicao_dependente` era só texto e todos os passos rodavam.
  * Toda ferramenta passa por dispatcher.despachar(origem="planner"): ações físicas/externas exigem
    autorização do dono no Telegram.
  * Só ferramentas registradas, no máximo 5 passos, e só roda com JARVIS_PLANNER=1 (padrão: desligado).
  * Gatilhos mais estreitos ("depois de" sozinho não dispara mais; pegava "depois de amanhã").
"""

import json
import logging
import os
import re

logger = logging.getLogger("jarvis-planner")

MAX_PASSOS = 5


class PlannerService:
    def __init__(self):
        self._conectores = [
            r"\b(e depois|em seguida|logo apos|logo após|depois disso)\b",
            r"\bprimeiro\b.+\bdepois\b",
            r"\bse\b.+\b(entao|então)\b",
            r"\bse\b.+,\s*(desligue|ligue|avise|mande|cancele|pause|retome|me envie|envie)\b",
        ]

    def habilitado(self) -> bool:
        return os.getenv("JARVIS_PLANNER", "0").strip() == "1"

    def eh_instrucao_composta(self, texto: str) -> bool:
        if not self.habilitado():
            return False
        t = (texto or "").strip().lower()
        if len(t) < 20:
            return False
        return any(re.search(rx, t) for rx in self._conectores)

    # ------------------------------------------------------------------ plano
    def _prompt_plano(self, instrucao: str) -> str:
        from dispatcher import listar_ferramentas
        catalogo = "\n".join(f"- {n}: {d}" for n, _r, d in sorted(listar_ferramentas()))
        return (
            "Você é o planejador do J.A.R.V.I.S. Decomponha a instrução em até "
            f"{MAX_PASSOS} passos usando SOMENTE as ferramentas da lista.\n"
            "Responda com uma array JSON. Cada passo: "
            '{"passo": 1, "ferramenta": "nome", "argumentos": {}, '
            '"se": {"passo": 1, "contem": "texto"}}.\n'
            'O campo "se" é opcional e só pode olhar passos ANTERIORES; use "contem" ou "nao_contem" com um trecho '
            "curto que apareceria na resposta da ferramenta do passo referido. "
            "Não invente ferramentas. Se a instrução não precisar de várias etapas, responda [].\n\n"
            f"Ferramentas:\n{catalogo}\n\n"
            f'Instrução do usuário: "{instrucao}"'
        )

    def _validar(self, etapas) -> list:
        from dispatcher import existe
        if not isinstance(etapas, list):
            return []
        validas = []
        for et in etapas[:MAX_PASSOS]:
            if not isinstance(et, dict) or not existe(str(et.get("ferramenta", ""))):
                logger.warning(f"Plano descartado: passo inválido {et!r}")
                return []                      # plano com ferramenta inventada não é executado
            args = et.get("argumentos") or {}
            if not isinstance(args, dict):
                return []
            validas.append({"passo": int(et.get("passo", len(validas) + 1)), "ferramenta": et["ferramenta"],
                            "argumentos": args, "se": et.get("se")})
        return validas

    @staticmethod
    def _condicao_ok(et: dict, resultados: dict) -> bool:
        c = et.get("se")
        if not c:
            return True
        if not isinstance(c, dict) or c.get("passo") not in resultados:
            return False                       # condição que não dá para verificar = não executa
        ref = str(resultados[c["passo"]]).lower()
        if "contem" in c:
            return str(c["contem"]).lower() in ref
        if "nao_contem" in c:
            return str(c["nao_contem"]).lower() not in ref
        return False

    # ------------------------------------------------------------------ execução
    def decompor_e_executar(self, instrucao: str) -> str:
        """Devolve a resposta final, ou '' para deixar o fluxo normal (turno único) responder."""
        try:
            from gemini_session import gemini_session
            etapas = self._validar(json.loads(gemini_session.gerar_json(self._prompt_plano(instrucao))))
        except Exception as e:
            logger.warning(f"Planejamento indisponível ({e}); seguindo o fluxo normal.")
            return ""
        if len(etapas) < 2:
            return ""                          # não era composta de verdade

        from dispatcher import despachar
        resultados, linhas = {}, []
        for et in etapas:
            n = et["passo"]
            if not self._condicao_ok(et, resultados):
                resultados[n] = "(pulado: condição não satisfeita)"
                linhas.append(f"Passo {n} ({et['ferramenta']}): pulado, condição não satisfeita.")
                continue
            try:
                res = despachar(et["ferramenta"], et["argumentos"], origem="planner")
            except Exception as e:
                resultados[n] = f"erro: {e}"
                linhas.append(f"Passo {n} ({et['ferramenta']}) falhou: {e}")
                break
            resultados[n] = res
            linhas.append(f"Passo {n} ({et['ferramenta']}): {res}")

        try:
            return gemini_session.gerar_texto(
                f'O usuário pediu: "{instrucao}"\nResultados das etapas:\n' + "\n".join(linhas) +
                "\n\nResuma em 1 ou 2 frases formais no estilo J.A.R.V.I.S., dizendo o que foi feito e o que foi pulado.")
        except Exception:
            return "Plano executado, senhor. " + " ".join(linhas[:3])


planner_service = PlannerService()
