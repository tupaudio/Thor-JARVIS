"""
dispatcher.py — Portão único de execução de ferramentas do J.A.R.V.I.S.

Por que existe
--------------
Antes, o function calling do Gemini, o laço OpenAI/Claude (ai_router), o planejador e o MCP chamavam
as funções de `jarvis_tools` diretamente. O enum de risco existia, mas ninguém o consultava. Agora TODAS
as listas de ferramentas entregues a esses caminhos são versões "envolvidas" por este módulo, que:

  1. decide se a chamada exige autorização do dono (ação sensível, origem não presencial, regra extra);
  2. se exige, envia um botão no Telegram com um nonce de uso único e espera até o TTL;
  3. falha FECHADO: sem Telegram configurado, negado, expirado ou erro -> a ferramenta NÃO executa.

Este módulo não importa nada do projeto no topo (evita ciclos). O Telegram é importado só quando preciso.

Variáveis de ambiente (opcionais)
---------------------------------
  JARVIS_CONFIRM_TTL=45              segundos para o dono tocar no botão
  JARVIS_SEM_CONFIRMACAO=a,b         nomes de ferramentas que o dono decide NÃO confirmar (por conta e risco)
  JARVIS_CONFIRMAR_TODO_FISICO=1     exige confirmação para toda ferramenta FÍSICA/EXTERNA, de qualquer origem
"""

import contextvars
import functools
import inspect
import logging
import os
import secrets
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("jarvis-dispatcher")

# Origem do comando em andamento ('voz' | 'cli' | 'telegram' | 'planner' | 'mcp' ...).
# É definida em brain_core.processar_comando e, para o Gemini, na thread do worker a cada job.
contexto_origem = contextvars.ContextVar("jarvis_origem", default="desconhecida")

# Valores iguais aos de RiscoFerramenta (IntEnum) em jarvis_tools.py
LEITURA, ESCRITA, FISICO, EXTERNO = 0, 1, 2, 3

_lock = threading.Lock()
_REGISTRO: dict = {}      # nome -> (funcao_original, risco)
_CONFIG = {"confirmar_sempre": set(), "regra_extra": None}
_PENDENTES: dict = {}     # nonce -> {"ev", "ok", "exp"}      (confirmações de ferramentas)
_NONCES: dict = {}        # nonce -> {"tipo", "dados", "exp"}  (botões de impressão etc.)


# --------------------------------------------------------------------------- configuração
def configurar(confirmar_sempre=(), regra_extra: Optional[Callable] = None):
    """`regra_extra(nome, args) -> str|None`: devolve o motivo se a chamada exigir confirmação."""
    _CONFIG["confirmar_sempre"] = set(confirmar_sempre)
    _CONFIG["regra_extra"] = regra_extra


def registrar(fns, riscos: dict, padrao: int = EXTERNO):
    """Registra as funções originais. Ferramenta sem classificação é tratada como EXTERNO (mais restrito)."""
    for fn in fns:
        _REGISTRO[fn.__name__] = (fn, int(riscos.get(fn.__name__, padrao)))


def listar_ferramentas() -> list:
    """[(nome, risco, primeira linha da docstring)] — usado pelo planejador."""
    out = []
    for nome, (fn, risco) in _REGISTRO.items():
        doc = (inspect.getdoc(fn) or "").strip().splitlines()
        out.append((nome, risco, doc[0] if doc else ""))
    return out


def existe(nome: str) -> bool:
    return nome in _REGISTRO


# --------------------------------------------------------------------------- política
def _ttl() -> float:
    try:
        return float(os.getenv("JARVIS_CONFIRM_TTL", "45"))
    except ValueError:
        return 45.0


def precisa_confirmar(nome: str, args: dict, origem: str) -> Optional[str]:
    """Devolve o motivo (str) se a chamada exigir autorização do dono, ou None."""
    if nome not in _REGISTRO:
        return None
    sem = {x.strip() for x in os.getenv("JARVIS_SEM_CONFIRMACAO", "").split(",") if x.strip()}
    if nome in sem:
        return None
    risco = _REGISTRO[nome][1]
    if nome in _CONFIG["confirmar_sempre"]:
        return "ação sensível"
    if origem in ("planner", "mcp") and risco >= FISICO:
        return f"pedida via {origem}"
    if os.getenv("JARVIS_CONFIRMAR_TODO_FISICO", "0") == "1" and risco >= FISICO:
        return "política de confirmação total"
    regra = _CONFIG["regra_extra"]
    if regra:
        try:
            motivo = regra(nome, args)
            if motivo:
                return motivo
        except Exception as e:  # regra quebrada não pode abrir a porta
            logger.error(f"regra_extra falhou em {nome}: {e}")
            return "falha ao avaliar a regra de segurança"
    return None


def _descrever(nome: str, args: dict) -> str:
    partes = ", ".join(f"{k}={str(v)[:80]!r}" for k, v in args.items())
    return f"{nome}({partes})"[:300].replace("`", "'")


# --------------------------------------------------------------------------- confirmação fora da banda
def confirmar_fora_da_banda(descricao: str, motivo: str = "") -> bool:
    """Envia botões ao dono no Telegram e bloqueia até a resposta ou o TTL. Falha fechado."""
    try:
        from telegram_service import telegram_service
        if not (telegram_service.is_configured() and telegram_service.chat_id):
            logger.warning(f"Confirmação impossível: is_cfg={telegram_service.is_configured()} chat_id={telegram_service.chat_id}")
            return False
    except Exception as e:
        logger.warning(f"Confirmação impossível: {e}")
        return False

    ttl = _ttl()
    nonce = secrets.token_hex(6)
    item = {"ev": threading.Event(), "ok": None, "exp": time.monotonic() + ttl}
    with _lock:
        _limpar_expirados()
        _PENDENTES[nonce] = item
    botoes = [[
        {"text": "✅ Autorizar", "callback_data": f"dsp:{nonce}:ok"},
        {"text": "🚫 Negar", "callback_data": f"dsp:{nonce}:no"},
    ]]
    texto = (f"🔐 *Autorização necessária*\n`{descricao}`\n"
             f"Motivo: {motivo or 'ação sensível'}. Expira em {int(ttl)} s.")
    try:
        enviado = telegram_service.enviar_teclado_inline(texto, botoes)
    except Exception as e:
        logger.warning(f"Falha ao enviar pedido de autorização: {e}")
        enviado = False
    if not enviado:
        with _lock:
            _PENDENTES.pop(nonce, None)
        return False

    item["ev"].wait(ttl)
    with _lock:
        _PENDENTES.pop(nonce, None)
    return item["ok"] is True


def resolver_confirmacao(nonce: str, aprovado: bool) -> bool:
    """Chamado pelo Telegram quando o dono toca no botão. Uso único; False se expirou/já respondido."""
    with _lock:
        item = _PENDENTES.get(nonce)
        if not item or item["ok"] is not None or time.monotonic() > item["exp"]:
            return False
        item["ok"] = bool(aprovado)
    item["ev"].set()
    return True


# --------------------------------------------------------------------------- nonces de botões (impressão etc.)
def criar_nonce(tipo: str, dados: dict, ttl: float = 1800.0) -> str:
    n = secrets.token_hex(6)
    with _lock:
        _limpar_expirados()
        _NONCES[n] = {"tipo": tipo, "dados": dict(dados), "exp": time.monotonic() + ttl}
    return n


def consumir_nonce(nonce: str, tipo: str) -> Optional[dict]:
    """Uso único: devolve os dados e invalida o nonce (e, portanto, todos os botões que o usam)."""
    with _lock:
        item = _NONCES.pop(nonce, None)
    if not item or item["tipo"] != tipo or time.monotonic() > item["exp"]:
        return None
    return item["dados"]


def _limpar_expirados():
    agora = time.monotonic()
    for d in (_PENDENTES, _NONCES):
        for k in [k for k, v in d.items() if v["exp"] < agora]:
            d.pop(k, None)


# --------------------------------------------------------------------------- execução
def despachar(nome: str, args: Optional[dict] = None, origem: Optional[str] = None):
    """Único caminho de execução de ferramentas. Devolve o resultado (str) da ferramenta."""
    origem = origem or contexto_origem.get()
    if nome not in _REGISTRO:
        return f"Ferramenta desconhecida: {nome}."
    fn, _risco = _REGISTRO[nome]
    args = dict(args or {})
    motivo = precisa_confirmar(nome, args, origem)
    if motivo:
        desc = _descrever(nome, args)
        if not confirmar_fora_da_banda(desc, motivo):
            logger.warning(f"Ação negada/sem autorização: {desc} (origem={origem})")
            return ("Ação não executada: o dono não autorizou pelo Telegram "
                    "(negada, expirada ou canal indisponível). Informe isso e não insista.")
        logger.info(f"Ação autorizada pelo dono: {desc} (origem={origem})")
    return fn(**args)


def envolver(fn):
    """Versão protegida de `fn`, com a mesma assinatura/docstring (o SDK gera o schema a partir dela)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        sig = None

    @functools.wraps(fn)
    def protegida(*a, **kw):
        if sig is not None:
            try:
                args = dict(sig.bind(*a, **kw).arguments)
            except TypeError:
                args = dict(kw)
        else:
            args = dict(kw)
        return despachar(fn.__name__, args)

    return protegida


def envolver_todas(fns) -> list:
    return [envolver(f) for f in fns]
