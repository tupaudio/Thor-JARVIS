import os, sys, time, json, threading, subprocess, importlib, inspect, types
os.environ["JARVIS_CONFIRM_TTL"] = "0.6"
import tempfile, shutil
# Uso: python tests/test_v3.py [/caminho/do/seu/brain]   (padrão: ../brain)
# Os testes rodam numa CÓPIA temporária: nada é gravado no seu brain/ (memory.db, traces.db etc.).
_SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "brain"))
BRAIN = os.path.join(tempfile.mkdtemp(prefix="jarvis_test_"), "brain")
shutil.copytree(_SRC, BRAIN, ignore=shutil.ignore_patterns("__pycache__", "*.db", "*.db-*", ".env", "*.pem", "token.json"))
sys.path.insert(0, BRAIN)
os.chdir(BRAIN)
RES = []
def check(nome, cond, extra=""):
    RES.append((nome, bool(cond)))
    print(("PASS " if cond else "FAIL ") + nome + (f"  [{extra}]" if extra and not cond else ""))

# ---------------------------------------------------------------- stub do Telegram (para o dispatcher)
class TGStub:
    chat_id = "42"
    modo = "ok"      # ok | no | silencio
    enviados = []
    def is_configured(self): return True
    def enviar_teclado_inline(self, texto, botoes, chat_id=None):
        self.enviados.append((texto, botoes))
        nonce = botoes[0][0]["callback_data"].split(":")[1]
        if self.modo in ("ok", "no"):
            import dispatcher
            threading.Timer(0.15, lambda: dispatcher.resolver_confirmacao(nonce, self.modo == "ok")).start()
        return True
stub_mod = types.ModuleType("telegram_service"); tg = TGStub(); stub_mod.telegram_service = tg
sys.modules["telegram_service"] = stub_mod

import dispatcher as D
exec_log = []
def cancelar_impressao_3d() -> str:
    "Cancela a impressão."
    exec_log.append("cancelar"); return "cancelado"
def enviar_email(destinatario: str, assunto: str) -> str:
    "Envia e-mail."
    exec_log.append(("email", destinatario)); return "enviado"
def consultar_clima() -> str:
    "Clima."
    exec_log.append("clima"); return "sol"
def controlar_dispositivos_casa_inteligente(dispositivo: str, acao: str, valor: str = "") -> str:
    "Controla dispositivos."
    exec_log.append(("iot", dispositivo, acao)); return "feito"
def mover_braco_mecanico(gesto: str) -> str:
    "Braço."
    exec_log.append(("braco", gesto)); return "movido"
import re
def regra(nome, args):
    if nome == "controlar_dispositivos_casa_inteligente":
        if str(args.get("acao","")).lower() in ("desligar","alternar") and re.search(r"impressora|3d|tomada|\btudo\b|\btodos\b", str(args.get("dispositivo","")).lower()):
            return "atinge impressora"
D.configurar(confirmar_sempre={"cancelar_impressao_3d","enviar_email"}, regra_extra=regra)
tools = [cancelar_impressao_3d, enviar_email, consultar_clima, controlar_dispositivos_casa_inteligente, mover_braco_mecanico]
D.registrar(tools, {"cancelar_impressao_3d":2,"enviar_email":3,"consultar_clima":0,"controlar_dispositivos_casa_inteligente":2,"mover_braco_mecanico":2})
W = {f.__name__: f for f in D.envolver_todas(tools)}

# assinatura/doc preservadas (o SDK do Gemini gera o schema a partir disso)
check("wrapper preserva assinatura", inspect.signature(W["enviar_email"]) == inspect.signature(enviar_email))
check("wrapper preserva docstring/nome", W["enviar_email"].__doc__ == "Envia e-mail." and W["enviar_email"].__name__ == "enviar_email")
check("wrapper preserva anotações", W["enviar_email"].__annotations__ == enviar_email.__annotations__)

D.contexto_origem.set("voz")
exec_log.clear(); tg.modo = "ok"
r = W["cancelar_impressao_3d"]()
check("sensível + dono autoriza -> executa", exec_log == ["cancelar"] and r == "cancelado", (exec_log, r))
exec_log.clear(); tg.modo = "no"
r = W["cancelar_impressao_3d"]()
check("sensível + dono nega -> NÃO executa", exec_log == [] and "não executada" in r.lower(), (exec_log, r))
exec_log.clear(); tg.modo = "silencio"; t0 = time.time()
r = W["enviar_email"]("a@b.c", "oi")
check("sensível + sem resposta (TTL) -> NÃO executa", exec_log == [] and 0.5 <= time.time()-t0 < 3, (exec_log, time.time()-t0))
check("pedido de autorização mostra a chamada exata", "enviar_email" in tg.enviados[-1][0] and "a@b.c" in tg.enviados[-1][0])
exec_log.clear(); r = W["enviar_email"]("a@b.c", "oi")  # posicional
exec_log.clear(); tg.modo = "ok"
r = W["enviar_email"]("x@y.z", "assunto")   # argumentos posicionais também mapeados
check("args posicionais mapeados e executados", exec_log == [("email","x@y.z")], exec_log)
exec_log.clear()
r = W["consultar_clima"]()
check("LEITURA executa sem pedir autorização", exec_log == ["clima"])
n_antes = len(tg.enviados)
r = W["mover_braco_mecanico"]("acenar")
check("FISICO leve por voz executa sem pedir", exec_log[-1] == ("braco","acenar") and len(tg.enviados) == n_antes)
exec_log.clear(); n_antes = len(tg.enviados)
W["controlar_dispositivos_casa_inteligente"]("luz do quarto", "desligar")
check("desligar luz comum não pede", exec_log == [("iot","luz do quarto","desligar")] and len(tg.enviados) == n_antes)
exec_log.clear(); tg.modo = "no"
r = W["controlar_dispositivos_casa_inteligente"]("tudo", "desligar")
check("'desligar tudo' exige autorização (negado -> não executa)", exec_log == [], exec_log)
exec_log.clear(); tg.modo = "no"
r = W["controlar_dispositivos_casa_inteligente"]("tomada da impressora", "desligar")
check("tomada da impressora exige autorização", exec_log == [])
exec_log.clear(); tg.modo = "ok"
W["controlar_dispositivos_casa_inteligente"]("todas as luzes", "desligar")
check("'todas as luzes' não é pega pela regra", exec_log == [("iot","todas as luzes","desligar")])
exec_log.clear(); tg.modo = "no"
r = D.despachar("mover_braco_mecanico", {"gesto": "acenar"}, origem="planner")
check("origem planner + FISICO exige autorização", exec_log == [])
exec_log.clear(); r = D.despachar("mover_braco_mecanico", {"gesto": "acenar"}, origem="mcp")
check("origem mcp + FISICO exige autorização", exec_log == [])
os.environ["JARVIS_SEM_CONFIRMACAO"] = "enviar_email"; exec_log.clear(); tg.modo = "no"
W["enviar_email"]("a@b.c", "x")
check("JARVIS_SEM_CONFIRMACAO dispensa o botão (opt-out do dono)", exec_log == [("email","a@b.c")])
del os.environ["JARVIS_SEM_CONFIRMACAO"]
# fail-closed: Telegram não configurado
tg.is_configured = lambda: False
exec_log.clear(); r = W["cancelar_impressao_3d"]()
check("sem Telegram configurado -> FALHA FECHADO", exec_log == [])
tg.is_configured = lambda: True
# nonce de uso único / expirado
res = {}
def pend():
    tg.modo = "silencio"; res["r"] = W["cancelar_impressao_3d"]()
th = threading.Thread(target=pend); th.start(); time.sleep(0.15)
nonce = tg.enviados[-1][1][0][0]["callback_data"].split(":")[1]
a = D.resolver_confirmacao(nonce, True); b = D.resolver_confirmacao(nonce, True)
th.join()
check("nonce de autorização: 1º toque vale, 2º não", a is True and b is False)
check("resolver nonce inexistente -> False", D.resolver_confirmacao("naoexiste", True) is False)
n = D.criar_nonce("print_job", {"arquivo": "a.gcode"}, ttl=5)
check("nonce de job: tipo errado -> None", D.consumir_nonce(n, "outro") is None)
n = D.criar_nonce("print_job", {"arquivo": "a.gcode"}, ttl=5)
d1 = D.consumir_nonce(n, "print_job"); d2 = D.consumir_nonce(n, "print_job")
check("nonce de job: uso único", d1 == {"arquivo":"a.gcode"} and d2 is None)
n = D.criar_nonce("print_job", {"arquivo": "a"}, ttl=0.05); time.sleep(0.1)
check("nonce de job: expira", D.consumir_nonce(n, "print_job") is None)
check("ferramenta desconhecida -> mensagem, sem exceção", "desconhecida" in D.despachar("inventada", {}))

# ---------------------------------------------------------------- planner
import planner_service as P
pl = P.PlannerService()
check("planner desligado por padrão", pl.eh_instrucao_composta("verifique a impressora e depois desligue a tomada") is False)
os.environ["JARVIS_PLANNER"] = "1"
check("planner ligado: 'e depois' dispara", pl.eh_instrucao_composta("verifique a impressora e depois desligue a tomada"))
check("'depois de amanhã' NÃO dispara mais", pl.eh_instrucao_composta("me lembre de ligar para o João depois de amanhã") is False)
class GS:
    plano = ""
    textos = []
    def gerar_json(self, p): GS.textos.append(p); return GS.plano
    def gerar_texto(self, p): return "RESUMO: " + p[-60:].replace("\n"," ")
gsmod = types.ModuleType("gemini_session"); gsmod.gemini_session = GS(); sys.modules["gemini_session"] = gsmod
def consultar_status_impressora_3d() -> str:
    "Status."
    exec_log.append("status"); return "Impressora: Printing. 40%"
D.registrar([consultar_status_impressora_3d], {"consultar_status_impressora_3d": 0})
GS.plano = json.dumps([
  {"passo":1,"ferramenta":"consultar_status_impressora_3d","argumentos":{}},
  {"passo":2,"ferramenta":"cancelar_impressao_3d","argumentos":{},"se":{"passo":1,"contem":"Operational"}},
  {"passo":3,"ferramenta":"mover_braco_mecanico","argumentos":{"gesto":"acenar"},"se":{"passo":1,"contem":"Printing"}}])
exec_log.clear(); tg.modo = "ok"
out = pl.decompor_e_executar("veja a impressora e se terminou cancele, senão acene")
check("condição FALSA -> passo pulado (cancelar NÃO roda)", "cancelar" not in exec_log, exec_log)
check("condição VERDADEIRA -> passo roda", ("braco","acenar") in exec_log, exec_log)
check("síntese menciona pulado", "pulado" in out.lower() or "RESUMO" in out)
GS.plano = json.dumps([{"passo":1,"ferramenta":"consultar_status_impressora_3d","argumentos":{}},{"passo":2,"ferramenta":"apagar_tudo","argumentos":{}}])
exec_log.clear()
check("ferramenta inventada -> plano inteiro descartado", pl.decompor_e_executar("a e depois b c d e f") == "" and exec_log == [])
GS.plano = json.dumps([{"passo":1,"ferramenta":"consultar_status_impressora_3d","argumentos":{}},{"passo":2,"ferramenta":"consultar_clima","argumentos":{},"se":{"passo":9,"contem":"x"}}])
exec_log.clear(); pl.decompor_e_executar("a e depois b c d e f")
check("condição que referencia passo inexistente -> não executa", exec_log == ["status"], exec_log)
GS.plano = "isto não é json"
check("JSON inválido -> '' (fluxo normal)", pl.decompor_e_executar("a e depois b c d e f") == "")
GS.plano = json.dumps([{"passo":1,"ferramenta":"cancelar_impressao_3d","argumentos":{}},{"passo":2,"ferramenta":"consultar_clima","argumentos":{}}])
exec_log.clear(); tg.modo = "no"; pl.decompor_e_executar("a e depois b c d e f")
check("planner: ação sensível passa pela autorização", "cancelar" not in exec_log)

# ---------------------------------------------------------------- octoprint
sys.modules.pop("telegram_service", None)  # será re-stubado adiante
import octoprint_service as O
o = O.OctoPrintService(); o.url = "http://x"; o.api_key = "k"
estado = {"s": "Printing"}; posts = []
o._get = lambda path, timeout=4.0: {"state": estado["s"], "job": {"file": {"display": "peca.gcode"}}, "progress": {"completion": 41.0}}
o._post = lambda path, payload, timeout=5.0: posts.append((path, payload)) or types.SimpleNamespace()
ok, msg = o.pausar_impressao()
check("pausar: Printing -> POST pause/pause", ok and posts[-1] == ("/api/job", {"command":"pause","action":"pause"}), posts)
estado["s"] = "Paused"; posts.clear()
ok, msg = o.pausar_impressao()
check("pausar: já Paused -> recusa (nada de toggle às cegas)", (not ok) and posts == [], posts)
ok, msg = o.retomar_impressao()
check("retomar: Paused -> POST resume", ok and posts[-1][1] == {"command":"pause","action":"resume"})
estado["s"] = "Printing"; posts.clear()
ok, msg = o.retomar_impressao()
check("retomar: Printing -> recusa", (not ok) and posts == [])
estado["s"] = "Printing"; posts.clear(); ok, _ = o.alternar_pausa()
check("alternar: Printing -> pausa", ok and posts[-1][1]["action"] == "pause")
estado["s"] = "Paused"; posts.clear(); ok, _ = o.alternar_pausa()
check("alternar: Paused -> retoma", ok and posts[-1][1]["action"] == "resume")
estado["s"] = "Operational"; posts.clear(); ok, m = o.alternar_pausa()
check("alternar: Operational -> não faz nada", (not ok) and posts == [])
ok, m = o.cancelar_impressao()
check("cancelar: sem impressão ativa -> recusa", (not ok) and posts == [])
estado["s"] = "Paused"; ok, m = o.cancelar_impressao()
check("cancelar: Paused -> envia cancel", ok and posts[-1][1] == {"command":"cancel"})
def boom(*a, **k): raise RuntimeError("fora do ar")
o._get = boom; posts.clear()
ok, m = o.pausar_impressao(); ok2, m2 = o.cancelar_impressao()
check("OctoPrint inacessível: nada é enviado e o motivo é dito", (not ok) and (not ok2) and posts == [] and "consultar" in m.lower())

# ---------------------------------------------------------------- telegram: botões com nonce e impasse
import telegram_service as T
ts = T.telegram_service
ts.chat_id = "42"; ts.token = "TOKEN123"
ts.session.post = lambda *a, **k: None
msgs, cbs, kbs = [], [], []
ts.enviar_mensagem = lambda texto, chat_id=None: msgs.append(texto) or "ok"
ts.responder_callback = lambda cb_id, texto="": cbs.append(texto)
ts.enviar_teclado_inline = lambda texto, botoes, chat_id=None: kbs.append((texto, botoes)) or True
import octoprint_service as O2
op = O2.octoprint_service
calls = []
op.estado_job = lambda: {"estado": cur["s"], "arquivo": cur["a"], "pct": 41.0}
op.cancelar_impressao = lambda: calls.append("cancel") or (True, "cancelado")
op.retomar_impressao = lambda: calls.append("resume") or (True, "retomada")
cur = {"s": "Printing", "a": "peca.gcode"}
def cb(data, uid="42"): return {"callback_query": {"id": "1", "from": {"id": int(uid)}, "data": data, "message": {"chat": {"id": 42}}}}
def msg(text): return {"message": {"chat": {"id": 42, "username": "dono"}, "from": {"id": 42}, "text": text}}

ts.tratar_atualizacao(msg("/cancelar"))
check("/cancelar gera botão com nonce (callback_data pj:<nonce>:c)", kbs and kbs[-1][1][0][0]["callback_data"].startswith("pj:") and kbs[-1][1][0][0]["callback_data"].endswith(":c"))
data_c = kbs[-1][1][0][0]["callback_data"]; data_n = kbs[-1][1][0][1]["callback_data"]
check("callback_data cabe em 64 bytes", len(data_c.encode()) <= 64)
calls.clear(); ts.tratar_atualizacao(cb(data_c, uid="999"))
check("botão tocado por outro usuário: não autorizado", calls == [] and "Não autorizado." in cbs[-1])
ts.tratar_atualizacao(cb(data_c))
check("botão válido cancela UMA vez", calls == ["cancel"], calls)
calls.clear(); ts.tratar_atualizacao(cb(data_c))
check("MESMO botão de novo: expirado/usado (não cancela)", calls == [] and "expirado" in cbs[-1].lower())
ts.tratar_atualizacao(msg("/cancelar")); data_c2 = kbs[-1][1][0][0]["callback_data"]
cur["a"] = "outra_peca.gcode"; calls.clear()
ts.tratar_atualizacao(cb(data_c2))
check("botão antigo com OUTRO job em andamento: nada é cancelado", calls == [] and any("não é o do alerta" in m for m in msgs), msgs[-1:])
cur["a"] = "peca.gcode"
ts.tratar_atualizacao(msg("/cancelar")); data_n2 = kbs[-1][1][0][1]["callback_data"]; data_c3 = kbs[-1][1][0][0]["callback_data"]
calls.clear(); ts.tratar_atualizacao(cb(data_n2))
check("'Manter' não cancela", calls == [])
ts.tratar_atualizacao(cb(data_c3)); 
check("'Manter' invalida o botão 'Cancelar' do mesmo alerta", calls == [])
cur["s"] = "Operational"; kbs.clear(); ts.tratar_atualizacao(msg("/cancelar"))
check("/cancelar sem impressão ativa: não oferece botão", kbs == [] and "Nenhuma impressão ativa" in msgs[-1])
ts.tratar_atualizacao(cb("cancel_print_confirm"))
check("callback_data ANTIGO (cancel_print_confirm) não cancela mais", calls == [] and "antigo" in cbs[-1].lower())
# alerta do LP1: retomar
cur.update(s="Paused", a="peca.gcode")
n = D.criar_nonce("print_job", {"arquivo": "peca.gcode"}, ttl=60)
calls.clear(); ts.tratar_atualizacao(cb(f"pj:{n}:r"))
check("botão 'Retomar' retoma", calls == ["resume"])

# impasse: pedido de autorização feito DENTRO de um handler de chat precisa ser resolvido por callback fora da fila FIFO
os.environ["JARVIS_CONFIRM_TTL"] = "6"
stub2 = types.ModuleType("x")
ts.processar_comando_remoto = lambda texto, chat_id="": D.despachar("enviar_email", {"destinatario": "a@b.c", "assunto": "oi"}, origem="telegram")
exec_log.clear(); kbs.clear()
sys.modules["telegram_service"] = types.ModuleType("telegram_service"); sys.modules["telegram_service"].telegram_service = ts
ts.enviar_teclado_inline = lambda texto, botoes, chat_id=None: kbs.append((texto, botoes)) or True
ts.sintetizar_audio_resposta = lambda t: None
t0 = time.time()
ts.despachar_update({"update_id": 1, **msg("mande um email para a@b.c")})
for _ in range(50):
    if kbs: break
    time.sleep(0.1)
if not kbs:
    print("DEBUG: kbs está vazio! exec_log:", exec_log, "chat_queues:", ts._chat_queues)
check("pedido de autorização enviado enquanto o handler do chat espera", len(kbs) >= 1 and exec_log == [])
nonce = kbs[-1][1][0][0]["callback_data"].split(":")[1]
ts.despachar_update({"update_id": 2, **cb(f"dsp:{nonce}:ok")})
for _ in range(40):
    if exec_log: break
    time.sleep(0.1)
check("toque em 'Autorizar' resolve SEM esperar o TTL (sem impasse)", exec_log == [("email","a@b.c")] and time.time()-t0 < 4, (exec_log, time.time()-t0))
os.environ["JARVIS_CONFIRM_TTL"] = "0.6"

# ---------------------------------------------------------------- redação de token no erro
check("_limpar_erro redige o token", "TOKEN123" not in ts._limpar_erro(Exception("url /botTOKEN123/getUpdates falhou")))

# ---------------------------------------------------------------- MCP (processo real, stdio)
def mcp(linhas, env_extra=None):
    env = dict(os.environ); env.update(env_extra or {})
    p = subprocess.run([sys.executable, "mcp_server.py"], input="\n".join(linhas) + "\n", capture_output=True, text=True, env=env, cwd=BRAIN, timeout=60)
    return p
def parse(out):
    return [json.loads(l) for l in out.splitlines() if l.strip()]
rpc = lambda i, m, p=None: json.dumps({"jsonrpc":"2.0","id":i,"method":m, **({"params":p} if p is not None else {})})
p = mcp([rpc(1,"initialize",{}), "[]", "1", '{"jsonrpc":"2.0","id":7,"method":"tools/list","params":null}', rpc(2,"tools/list"),
         rpc(3,"tools/call",{"name":"cancelar_impressao_3d","arguments":{}}), rpc(4,"tools/call",{"name":"controlar_dispositivo_iot","arguments":{"dispositivo":"tudo","ligar":False}}),
         rpc(5,"tools/call",{"name":"obter_status_impressora_3d"}), rpc(6,"tools/call",{"name":"listar_dispositivos_iot","arguments":None}), rpc(8,"tools/call",{"name":"capturar_foto_bancada","arguments":{}})])
try:
    out = parse(p.stdout); parse_ok = True
except Exception as e:
    out = []; parse_ok = False
check("MCP: stdout contém SÓ JSON-RPC válido", parse_ok, p.stdout[:300])
check("MCP: não morreu com linha não-objeto ([] / 1)", p.returncode == 0 and sum(1 for o_ in out if o_.get("error",{}).get("code") == -32600) == 2, (p.returncode, p.stderr[-300:]))
tl = [o_ for o_ in out if o_.get("id") == 2][0]["result"]["tools"]; nomes = {t["name"] for t in tl}
check("MCP: ferramentas físicas ocultas por padrão", not ({"cancelar_impressao_3d","pausar_impressao_3d","retomar_impressao_3d","controlar_dispositivo_iot"} & nomes), nomes)
check("MCP: ferramentas de leitura seguem visíveis", {"obter_status_impressora_3d","capturar_foto_bancada","consultar_memoria"} <= nomes)
r3 = [o_ for o_ in out if o_.get("id") == 3][0]["result"]
check("MCP: chamar 'cancelar' direto é recusado", r3.get("isError") is True and "desativada" in r3["content"][0]["text"].lower())
r4 = [o_ for o_ in out if o_.get("id") == 4][0]["result"]
check("MCP: chamar IoT físico direto é recusado", r4.get("isError") is True)
check("MCP: params:null não derruba", any(o_.get("id") == 7 for o_ in out))
check("MCP: tools/call com leitura funciona e responde", all(any(o_.get("id") == i for o_ in out) for i in (5,6,8)))
p2 = mcp([rpc(1,"tools/list")], {"JARVIS_MCP_ALLOW_PHYSICAL": "1"}); n2 = {t["name"] for t in parse(p2.stdout)[0]["result"]["tools"]}
check("MCP: ALLOW_PHYSICAL=1 libera pausar/retomar/IoT mas NÃO cancelar", {"pausar_impressao_3d","retomar_impressao_3d","controlar_dispositivo_iot"} <= n2 and "cancelar_impressao_3d" not in n2, n2)
p3 = mcp([rpc(1,"tools/list")], {"JARVIS_MCP_ALLOW_PHYSICAL": "1", "JARVIS_MCP_ALLOW_CANCEL": "1"}); n3 = {t["name"] for t in parse(p3.stdout)[0]["result"]["tools"]}
check("MCP: ALLOW_CANCEL=1 + ALLOW_PHYSICAL=1 libera cancelar", "cancelar_impressao_3d" in n3)
pr = subprocess.run([sys.executable, "-c", "import mcp_server, sys; print('LIXO_DE_SERVICO'); print('{\"jsonrpc\":\"2.0\"}', file=sys.stderr); mcp_server.responder_json({'ok':1})"],
                    capture_output=True, text=True, cwd=BRAIN, timeout=30)
check("MCP: print() de serviço vai para stderr, não para o stdout do protocolo", "LIXO_DE_SERVICO" not in pr.stdout and "LIXO_DE_SERVICO" in pr.stderr and json.loads(pr.stdout.strip()) == {"ok":1}, (pr.stdout, pr.stderr[-200:]))

# ---------------------------------------------------------------- Gemini worker propaga a origem (sem SDK)
sys.modules.pop("telegram_service", None); sys.modules.pop("gemini_session", None)
import gemini_session as G
gs = G.GeminiSession(); capt = {}
def fake(self_texto): capt["origem"] = D.contexto_origem.get(); return "ok"
gs._enviar_com_recuperacao = fake
r = gs.enviar("teste", origem="telegram", timeout=10)
check("Gemini worker define contexto_origem do job (telegram)", capt.get("origem") == "telegram" and r == "ok", capt)
r = gs.enviar("teste2", origem="voz", timeout=10)
check("Gemini worker define contexto_origem do job (voz)", capt.get("origem") == "voz", capt)
check("_Job tem campo origem", "origem" in G._Job.__dataclass_fields__)
check("Gemini: gerar_json/gerar_texto existem", hasattr(gs, "gerar_json") and hasattr(gs, "gerar_texto"))

falhas = [n for n, ok in RES if not ok]
print(f"\n{len(RES)-len(falhas)}/{len(RES)} testes passaram")
sys.exit(1 if falhas else 0)
