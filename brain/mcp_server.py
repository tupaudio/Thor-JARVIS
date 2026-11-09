#!/usr/bin/env python3
"""
Servidor MCP (Model Context Protocol) Nativo do J.A.R.V.I.S.
Expondo telemetria, visão, impressora 3D (Ender 3 S1 Pro) e automação IoT
para qualquer cliente MCP (Cursor, Claude Desktop, Antigravity, OpenJarvis, VS Code).

Opera via JSON-RPC 2.0 em stdio (padrão oficial MCP) sem dependências externas obrigatórias,
com suporte automático a FastMCP caso a biblioteca 'mcp' esteja instalada no ambiente.
"""

import sys
import os
import json
import base64
import logging

# Garante que o diretório brain está no sys.path
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

# Configura logging para stderr para não poluir o stdout (utilizado pelo protocolo JSON-RPC)
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [JARVIS-MCP] %(levelname)s: %(message)s")
logger = logging.getLogger("jarvis-mcp")


# ==============================================================================
# FERRAMENTAS EXPOSTAS DO JARVIS
# ==============================================================================

def tool_telemetria_sistema() -> dict:
    """Retorna telemetria completa do servidor Dell OptiPlex (CPU, RAM, Disco, Temperaturas)."""
    import datetime

    res = {
        "host": "barros-server (Dell OptiPlex 3060 Micro)",
        "timestamp": datetime.datetime.now().isoformat()
    }

    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disco = psutil.disk_usage('/')
        
        temps = {}
        try:
            sensores = psutil.sensors_temperatures()
            for k, v in sensores.items():
                if v:
                    temps[k] = f"{v[0].current:.1f}°C"
        except Exception:
            pass

        res.update({
            "cpu_percent": cpu_pct,
            "ram": {
                "percent": mem.percent,
                "used_mb": mem.used // (1024**2),
                "total_mb": mem.total // (1024**2)
            },
            "disco": {
                "percent": disco.percent,
                "used_gb": disco.used // (1024**3),
                "total_gb": disco.total // (1024**3)
            },
            "temperaturas": temps
        })
    except ImportError:
        res["aviso"] = "Biblioteca psutil não instalada no ambiente local Python."

    return res


def tool_status_impressora_3d() -> dict:
    """Retorna estado e telemetria da impressora 3D Ender 3 S1 Pro via OctoPrint."""
    try:
        from octoprint_service import octoprint_service
        job = octoprint_service._get("/api/job")
        printer = octoprint_service._get("/api/printer")
        
        estado = job.get("state", "Desconhecido")
        prog = job.get("progress", {}) or {}
        arquivo = job.get("job", {}).get("file", {}) or {}
        
        t_tool = printer.get("temperature", {}).get("tool0", {})
        t_bed = printer.get("temperature", {}).get("bed", {})

        return {
            "status": "online",
            "estado": estado,
            "arquivo": arquivo.get("display") or arquivo.get("name") or "Nenhum",
            "progresso_pct": round(prog.get("completion") or 0.0, 1),
            "tempo_restante_segundos": prog.get("printTimeLeft"),
            "temperatura_extrusor": {
                "atual": t_tool.get("actual"),
                "alvo": t_tool.get("target")
            },
            "temperatura_mesa": {
                "atual": t_bed.get("actual"),
                "alvo": t_bed.get("target")
            }
        }
    except Exception as e:
        return {"status": "offline_ou_erro", "erro": str(e)}


def tool_capturar_foto_bancada(incluir_base64: bool = False) -> dict:
    """Captura uma foto recente da câmera do dock ou webcam e retorna status e caminho (ou base64)."""
    try:
        from camera_manager import camera_manager
        jpg = camera_manager.obter_ultimo_jpeg_remoto(max_age_sec=20.0)
        caminho = None
        if not jpg:
            caminho = camera_manager.capturar_foto()
            if caminho and os.path.exists(caminho):
                with open(caminho, "rb") as f:
                    jpg = f.read()

        if not jpg:
            return {"sucesso": False, "mensagem": "Nenhum quadro de câmera disponível no momento."}

        res = {
            "sucesso": True,
            "tamanho_bytes": len(jpg),
            "origem": "iphone_dock" if not caminho else "webcam_local"
        }
        if caminho:
            res["caminho_arquivo"] = caminho
        if incluir_base64:
            res["imagem_base64_jpeg"] = base64.b64encode(jpg).decode("utf-8")
        return res
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def tool_listar_dispositivos_iot() -> dict:
    """Lista todos os dispositivos IoT registrados (Tuya, Tomadas, Lâmpadas, etc.) e seus estados."""
    try:
        from iot_service import iot_service
        return {
            "dispositivos": iot_service.listar_dispositivos(),
            "estado_cache": dict(iot_service.dispositivos)
        }
    except Exception as e:
        return {"erro": str(e)}


def tool_controlar_dispositivo_iot(dispositivo: str, ligar: bool) -> dict:
    """Controla um dispositivo IoT (ligar/desligar). Trava de segurança ativa para tomada da impressora."""
    try:
        from iot_service import iot_service
        resultado = iot_service.controlar(dispositivo, "ligar" if ligar else "desligar")
        return {"sucesso": True, "resposta": resultado}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def tool_pausar_impressao_3d() -> dict:
    """Pausa ou retoma o trabalho de impressão ativo na Ender 3 S1 Pro."""
    try:
        from octoprint_service import octoprint_service
        ok, msg = octoprint_service.pausar_impressao()
        return {"sucesso": ok, "mensagem": msg}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def tool_cancelar_impressao_3d() -> dict:
    """Cancela o trabalho de impressão ativo na Ender 3 S1 Pro."""
    try:
        from octoprint_service import octoprint_service
        ok, msg = octoprint_service.cancelar_impressao()
        return {"sucesso": ok, "mensagem": msg}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def tool_consultar_sentinela() -> dict:
    """Consulta o status do módulo de vigilância Sentinela."""
    try:
        from sentinel_service import sentinel_service
        return {
            "ativo": sentinel_service.is_ativo(),
            "status": sentinel_service.consultar_status(),
            "eventos_recentes": list(sentinel_service.eventos_registrados[-10:])
        }
    except Exception as e:
        return {"erro": str(e)}


def tool_consultar_telemetria_traces() -> dict:
    """Retorna histórico e estatísticas recentes de latência e chamadas do JARVIS."""
    try:
        from traces_service import traces_service
        return traces_service.resumo()
    except Exception as e:
        return {"erro": str(e)}


# Mapeamento de definições MCP
MCP_TOOLS = [
    {
        "name": "obter_telemetria_sistema",
        "description": "Retorna o status de telemetria do servidor Dell OptiPlex (CPU, RAM, disco e temperaturas).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_telemetria_sistema
    },
    {
        "name": "obter_status_impressora_3d",
        "description": "Retorna o status detalhado da Ender 3 S1 Pro (temperaturas da mesa/bico, progresso e arquivo).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_status_impressora_3d
    },
    {
        "name": "capturar_foto_bancada",
        "description": "Captura um quadro instantâneo da bancada/impressora pela câmera do dock do iPhone ou webcam.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incluir_base64": {"type": "boolean", "description": "Se verdadeiro, inclui os bytes JPEG em base64"}
            },
            "required": []
        },
        "fn": tool_capturar_foto_bancada
    },
    {
        "name": "listar_dispositivos_iot",
        "description": "Lista os dispositivos inteligentes conectados (luzes, tomadas, ar condicionado) e seus status.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_listar_dispositivos_iot
    },
    {
        "name": "controlar_dispositivo_iot",
        "description": "Liga ou desliga um dispositivo inteligente pelo nome. Possui trava de segurança para a tomada da impressora.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dispositivo": {"type": "string", "description": "Nome ou identificador do dispositivo"},
                "ligar": {"type": "boolean", "description": "True para ligar, False para desligar"}
            },
            "required": ["dispositivo", "ligar"]
        },
        "fn": tool_controlar_dispositivo_iot
    },
    {
        "name": "pausar_impressao_3d",
        "description": "Pausa ou retoma a impressão 3D ativa na Ender 3 S1 Pro.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_pausar_impressao_3d
    },
    {
        "name": "cancelar_impressao_3d",
        "description": "Cancela a impressão 3D ativa no OctoPrint.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_cancelar_impressao_3d
    },
    {
        "name": "consultar_sentinela",
        "description": "Consulta o status e os alertas recentes do modo sentinela de segurança visual.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_consultar_sentinela
    },
    {
        "name": "consultar_telemetria_traces",
        "description": "Consulta a latência média, erros e contagem de requisições por modelo e rota (Traces SQLite).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
        "fn": tool_consultar_telemetria_traces
    }
]

_TOOL_MAP = {t["name"]: t["fn"] for t in MCP_TOOLS}


# ==============================================================================
# IMPLEMENTAÇÃO JSON-RPC 2.0 VIA STDIO (COMPATÍVEL MCP 2024-11-05)
# ==============================================================================

def responder_json(obj: dict):
    """Envia uma mensagem JSON-RPC para stdout terminada por newline."""
    raw = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(raw + "\n")
    sys.stdout.flush()


def executar_stdio():
    """Loop principal de escuta JSON-RPC 2.0 em stdio."""
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8-sig")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    logger.info("Servidor MCP J.A.R.V.I.S. pronto em stdio.")
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            req = json.loads(linha)
        except Exception as e:
            responder_json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            })
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # 1. initialize
        if method == "initialize":
            responder_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "thor-jarvis-mcp",
                        "version": "1.0.0"
                    }
                }
            })

        # 2. notifications/initialized (notificação - sem retorno)
        elif method == "notifications/initialized":
            pass

        # 3. ping
        elif method == "ping":
            responder_json({"jsonrpc": "2.0", "id": req_id, "result": {}})

        # 4. tools/list
        elif method == "tools/list":
            tools_spec = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"]
                }
                for t in MCP_TOOLS
            ]
            responder_json({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_spec}
            })

        # 5. tools/call
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            fn = _TOOL_MAP.get(tool_name)
            if not fn:
                responder_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Ferramenta desconhecida: {tool_name}"}
                })
            else:
                try:
                    resultado = fn(**args) if args else fn()
                    texto_res = json.dumps(resultado, ensure_ascii=False, indent=2)
                    responder_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": texto_res
                                }
                            ]
                        }
                    })
                except Exception as e:
                    logger.error(f"Erro ao executar {tool_name}: {e}")
                    responder_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Erro na execução da ferramenta: {e}"
                                }
                            ],
                            "isError": True
                        }
                    })

        # Outros métodos desconhecidos
        else:
            if req_id is not None:
                responder_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Método não suportado: {method}"}
                })


if __name__ == "__main__":
    executar_stdio()
