"""
Módulo de Casa Inteligente e IoT para o J.A.R.V.I.S.
Gerencia lâmpadas inteligentes, fitas LED, tomadas conectadas e dispositivos IoT.
Suporta controle local Tuya / Smart Life (tinytuya), Tasmota/Sonoff/ESP32 (HTTP),
Home Assistant REST API, Webhooks genéricos (IFTTT/Alexa) e simulação de estado.
"""

import os
import sys
import json
import time
import requests
from dotenv import load_dotenv


env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

JSON_DISPOSITIVOS = os.path.join(os.path.dirname(__file__), "dispositivos_iot.json")

CORES_RGB = {
    "vermelho": [255, 0, 0],
    "verde": [0, 255, 0],
    "azul": [0, 100, 255],
    "azul ciano": [0, 255, 255],
    "ciano": [0, 255, 255],
    "roxo": [180, 0, 255],
    "rosa": [255, 20, 147],
    "amarelo": [255, 255, 0],
    "laranja": [255, 140, 0],
    "ambar": [255, 191, 0],
    "branco": [255, 255, 255],
    "branco frio": [240, 248, 255],
    "branco quente": [255, 214, 170]
}

class IoTService:
    def __init__(self):
        self.session = requests.Session()
        self.dispositivos = self._carregar_dispositivos()

    def _carregar_dispositivos(self) -> dict:
        if not os.path.exists(JSON_DISPOSITIVOS):
            return {}
        try:
            with open(JSON_DISPOSITIVOS, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception as e:
            print(f"⚠️ [IOT] Erro ao ler {JSON_DISPOSITIVOS}: {e}")
            return {}

    def _salvar_dispositivos(self):
        try:
            with open(JSON_DISPOSITIVOS, "w", encoding="utf-8") as fp:
                json.dump(self.dispositivos, fp, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ [IOT] Erro ao salvar {JSON_DISPOSITIVOS}: {e}")

    def _identificar_alvos(self, termo: str) -> list:
        termo_limpo = termo.lower().strip()

        # Correspondência exata pela chave do dispositivo (ex: botões do iPhone Dock)
        if termo_limpo in self.dispositivos:
            return [termo_limpo]

        # Casos gerais de escopo total
        if any(w in termo_limpo for w in ["tudo", "todas as luzes", "todos os dispositivos", "tudo que estiver ligado"]):
            return list(self.dispositivos.keys())
        
        # Filtro por tipo
        if "luz" in termo_limpo or "lampada" in termo_limpo or "lâmpada" in termo_limpo:
            alvos = [k for k, v in self.dispositivos.items() if v.get("tipo") in ["lampada", "led"]]
            if alvos:
                # Se especificar comodo
                if "quarto" in termo_limpo:
                    alvos_comodo = [k for k in alvos if self.dispositivos[k].get("comodo") == "quarto"]
                    return alvos_comodo or alvos
                elif "mesa" in termo_limpo or "estacao" in termo_limpo or "estação" in termo_limpo:
                    alvos_comodo = [k for k in alvos if self.dispositivos[k].get("comodo") == "estacao"]
                    return alvos_comodo or alvos
                return alvos

        alvos = []
        for k, v in self.dispositivos.items():
            nome = v.get("nome", "").lower()
            comodo = v.get("comodo", "").lower()
            tipo = v.get("tipo", "").lower()
            if termo_limpo in k or k in termo_limpo or termo_limpo in nome or nome in termo_limpo:
                alvos.append(k)
            elif termo_limpo in comodo:
                alvos.append(k)
            elif termo_limpo == tipo:
                alvos.append(k)
                
        return list(set(alvos))

    def _executar_dispositivo(self, chave: str, comando: str, valor: str = "") -> bool:
        disp = self.dispositivos.get(chave)
        if not disp:
            return False

        proto = disp.get("protocolo", "simulado").lower()
        ip = disp.get("ip", "")
        dev_id = disp.get("device_id", "")
        local_key = disp.get("local_key", "")

        # TRAVA CENTRAL DE SEGURANÇA FÍSICA:
        # Se for comando de desligar e o dispositivo for crítico (ex: tomada da impressora 3D),
        # verifica se a impressora está em operação antes de qualquer protocolo (Tuya, Tasmota, OctoPrint, etc.)
        e_critico = disp.get("critico", False) or "impressora" in chave.lower() or "ender" in chave.lower() or proto == "octoprint"
        if comando == "desligar" and e_critico:
            try:
                from octoprint_service import octoprint_service
                if octoprint_service.esta_imprimindo():   # fail-closed (devolve True em caso de erro na checagem)
                    print(f"🛑 [IOT TRAVA DE SEGURANÇA] Desligamento de '{chave}' bloqueado: Impressão 3D ativa!")
                    return False
            except Exception as e:
                print(f"🛑 [IOT TRAVA DE SEGURANÇA] Falha ao verificar estado da impressora: {e}. Bloqueando desligamento.")
                return False

        # Tuya / Smart Life
        if proto == "tuya" and ip and dev_id and local_key:
            try:
                import tinytuya
                tipo = disp.get("tipo", "lampada")
                if tipo == "lampada" or tipo == "led":
                    d = tinytuya.BulbDevice(dev_id, ip, local_key)
                    d.set_version(3.3)
                    if comando == "ligar":
                        d.turn_on()
                    elif comando == "desligar":
                        d.turn_off()
                    elif comando == "brilho" and valor.isdigit():
                        d.set_brightness_percentage(int(valor))
                    elif comando == "cor":
                        rgb = CORES_RGB.get(valor.lower(), [255, 255, 255])
                        d.set_colour(rgb[0], rgb[1], rgb[2])
                else:
                    d = tinytuya.OutletDevice(dev_id, ip, local_key)
                    d.set_version(3.3)
                    if comando == "ligar":
                        d.turn_on()
                    elif comando == "desligar":
                        d.turn_off()
            except Exception as e:
                print(f"⚠️ [IOT TUYA] Falha na comunicação física com {chave}: {e}")

        # Tomada da impressora 3D via OctoPrint (plugin PSU Control)
        elif proto == "octoprint":
            try:
                from octoprint_service import octoprint_service
                if comando == "ligar":
                    octoprint_service.ligar_tomada()
                elif comando == "desligar":
                    ok, msg = octoprint_service.desligar_tomada()
                    if not ok:
                        print(f"🛑 [IOT OCTOPRINT] {msg}")
                        disp["status"] = "ligado"
                        return False
            except Exception as e:
                print(f"⚠️ [IOT OCTOPRINT] Falha em {chave}: {e}")

        # Tasmota / ESP32 / Sonoff HTTP
        elif proto == "tasmota" and ip:
            try:
                cmd_tasmota = "ON" if comando == "ligar" else "OFF"
                self.session.get(f"http://{ip}/cm?cmnd=Power%20{cmd_tasmota}", timeout=3)
            except Exception as e:
                print(f"⚠️ [IOT TASMOTA] Falha em {chave}: {e}")

        # Webhook (IFTTT / Node-RED / Alexa)
        elif proto == "webhook":
            url = disp.get("webhook_on") if comando == "ligar" else disp.get("webhook_off")
            if url:
                try:
                    self.session.get(url, timeout=4)
                except Exception as e:
                    print(f"⚠️ [IOT WEBHOOK] Falha em {chave}: {e}")

        # Home Assistant
        elif proto == "homeassistant":
            hass_url = os.getenv("HASS_URL")
            hass_token = os.getenv("HASS_TOKEN")
            if hass_url and hass_token:
                try:
                    servico = "turn_on" if comando == "ligar" else "turn_off"
                    domain = "light" if disp.get("tipo") in ["lampada", "led"] else "switch"
                    url = f"{hass_url.rstrip('/')}/api/services/{domain}/{servico}"
                    headers = {"Authorization": f"Bearer {hass_token}", "Content-Type": "application/json"}
                    payload = {"entity_id": dev_id or chave}
                    if comando == "brilho" and valor.isdigit():
                        payload["brightness_pct"] = int(valor)
                    self.session.post(url, headers=headers, json=payload, timeout=4)
                except Exception as e:
                    print(f"⚠️ [IOT HOMEASSISTANT] Falha em {chave}: {e}")

        return True

    def controlar(self, dispositivo: str, acao: str, valor: str = "") -> str:
        """
        Controla lâmpadas, fitas LED ou tomadas inteligentes.
        
        Args:
            dispositivo: Nome ou termo do aparelho (ex: 'luz do quarto', 'fita led', 'tudo', 'abajur').
            acao: 'ligar', 'desligar', 'alternar', 'brilho', 'cor' ou 'consultar'.
            valor: Porcentagem de brilho (0 a 100) ou nome da cor (ex: 'azul', 'vermelho', 'ambar').
        """
        acao_limpa = acao.lower().strip()
        
        if acao_limpa in ["consultar", "status", "listar"]:
            return self.listar_status(dispositivo=dispositivo)

        alvos = self._identificar_alvos(dispositivo)
        if not alvos:
            return f"Não localizei o dispositivo '{dispositivo}' na central de automação residencial, senhor."

        alterados = []
        for chave in alvos:
            disp = self.dispositivos[chave]
            nome = disp.get("nome", chave)

            if acao_limpa in ["ligar", "acender", "ativar"]:
                ok = self._executar_dispositivo(chave, "ligar")
                if ok:
                    disp["status"] = "ligado"
                    alterados.append(f"{nome} (ligado)")
                else:
                    alterados.append(f"{nome} (falha ao ligar)")

            elif acao_limpa in ["desligar", "apagar", "desativar"]:
                ok = self._executar_dispositivo(chave, "desligar")
                if ok:
                    disp["status"] = "desligado"
                    alterados.append(f"{nome} (desligado)")
                else:
                    disp["status"] = "ligado"
                    alterados.append(f"{nome} (mantido ligado: impressão 3D em andamento)")

            elif acao_limpa in ["alternar", "toggle"]:
                novo = "desligado" if disp.get("status") == "ligado" else "ligado"
                ok = self._executar_dispositivo(chave, novo)
                if ok:
                    disp["status"] = novo
                    alterados.append(f"{nome} ({novo})")
                else:
                    disp["status"] = "ligado"
                    alterados.append(f"{nome} (mantido ligado: impressão 3D em andamento)")

            elif acao_limpa in ["brilho", "intensidade"]:
                try:
                    pct = max(0, min(100, int(valor)))
                    disp["brilho"] = pct
                    disp["status"] = "ligado" if pct > 0 else "desligado"
                    self._executar_dispositivo(chave, "brilho", str(pct))
                    alterados.append(f"{nome} em {pct}%")
                except ValueError:
                    pass

            elif acao_limpa in ["cor", "colorir"]:
                cor_escolhida = valor.lower().strip()
                disp["cor"] = cor_escolhida
                disp["status"] = "ligado"
                self._executar_dispositivo(chave, "cor", cor_escolhida)
                alterados.append(f"{nome} em {cor_escolhida}")

        self._salvar_dispositivos()
        
        detalhe = ", ".join(alterados)
        return f"Ação de automação concluída, senhor: {detalhe}."

    def listar_status(self, dispositivo: str = "") -> str:
        """Retorna o status atual dos dispositivos IoT."""
        alvos = self._identificar_alvos(dispositivo) if dispositivo else list(self.dispositivos.keys())
        if not alvos:
            return "Nenhum dispositivo cadastrado na central de Casa Inteligente, senhor."

        relatorio = []
        for chave in alvos:
            d = self.dispositivos[chave]
            status = d.get("status", "desligado").upper()
            detalhes = []
            if d.get("tipo") in ["lampada", "led"]:
                if status == "LIGADO":
                    detalhes.append(f"Brilho: {d.get('brilho', 100)}%")
                    if d.get("cor"):
                        detalhes.append(f"Cor: {d.get('cor')}")
            det_str = f" ({', '.join(detalhes)})" if detalhes else ""
            relatorio.append(f"• {d.get('nome')}: [{status}]{det_str}")

        return "Status dos dispositivos de Casa Inteligente, senhor:\n" + "\n".join(relatorio)

    def cadastrar_dispositivo(self, id_chave: str, nome: str, tipo: str, comodo: str = "geral", 
                              protocolo: str = "simulado", ip: str = "", device_id: str = "", local_key: str = "") -> str:
        """Cadastra ou atualiza um dispositivo na rede do assistente."""
        chave_limpa = id_chave.lower().strip().replace(" ", "_")
        self.dispositivos[chave_limpa] = {
            "nome": nome,
            "tipo": tipo.lower(),
            "comodo": comodo.lower(),
            "protocolo": protocolo.lower(),
            "status": "desligado",
            "brilho": 100,
            "cor": "branco",
            "ip": ip,
            "device_id": device_id,
            "local_key": local_key,
            "webhook_on": "",
            "webhook_off": ""
        }
        self._salvar_dispositivos()
        return f"Dispositivo '{nome}' registrado com sucesso na rede inteligente sob o ID '{chave_limpa}', senhor."

iot_service = IoTService()
