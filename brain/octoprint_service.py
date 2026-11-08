"""
Integração do J.A.R.V.I.S. com o OctoPrint (impressora 3D).
- Consulta estado da impressora, temperaturas e progresso do trabalho.
- Liga/desliga a tomada de segurança via plugin PSU Control (com trava: não desliga durante impressão).
- A câmera do iPhone 11 é exposta ao OctoPrint pelo Stark Dock (/camera/stream.mjpg e /camera/snapshot.jpg).

Configuração no brain/.env:
    OCTOPRINT_URL=http://IP_DO_OCTOPRINT        (ex: http://192.168.15.50)
    OCTOPRINT_API_KEY=sua_chave                 (OctoPrint > Configurações > Application Keys)
"""

import os
import sys
import time
import threading
import requests
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


class OctoPrintService:
    def __init__(self):
        self.url = os.getenv("OCTOPRINT_URL", "").strip().rstrip("/")
        self.api_key = os.getenv("OCTOPRINT_API_KEY", "").strip()

    def is_configured(self) -> bool:
        return bool(self.url and self.api_key)

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    def _get(self, path: str, timeout: float = 4.0):
        r = requests.get(f"{self.url}{path}", headers=self._headers(), timeout=timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict, timeout: float = 5.0):
        r = requests.post(f"{self.url}{path}", headers=self._headers(), json=payload, timeout=timeout)
        r.raise_for_status()
        return r

    def esta_imprimindo(self) -> bool:
        """True se houver impressão em andamento (ou pausada). Em caso de erro, assume True por segurança."""
        try:
            job = self._get("/api/job")
            return job.get("state", "") in ("Printing", "Pausing", "Paused", "Resuming", "Starting")
        except Exception:
            return True

    def obter_status(self) -> str:
        if not self.is_configured():
            return "OctoPrint não configurado no .env, senhor."
        try:
            job = self._get("/api/job")
            printer = self._get("/api/printer")
            estado = job.get("state", "desconhecido")
            prog = job.get("progress", {}) or {}
            pct = prog.get("completion")
            restante = prog.get("printTimeLeft")
            temps = printer.get("temperature", {})
            bico = temps.get("tool0", {}).get("actual")
            mesa = temps.get("bed", {}).get("actual")
            partes = [f"Impressora: {estado}."]
            if pct is not None:
                partes.append(f"Progresso {pct:.0f}%.")
            if restante:
                partes.append(f"Restam cerca de {int(restante // 60)} minutos.")
            if bico is not None and mesa is not None:
                partes.append(f"Bico {bico:.0f}°C, mesa {mesa:.0f}°C.")
            return " ".join(partes)
        except Exception as e:
            return f"Não consegui consultar o OctoPrint (impressora desligada ou offline?): {e}"

    def ligar_tomada(self) -> bool:
        """Liga a tomada via plugin PSU Control."""
        try:
            self._post("/api/plugin/psucontrol", {"command": "turnPSUOn"})
            return True
        except Exception as e:
            print(f"⚠️ [OCTOPRINT] Falha ao ligar a tomada: {e}")
            return False

    def desligar_tomada(self, forcar: bool = False) -> tuple:
        """Desliga a tomada via PSU Control, recusando se houver impressão em andamento."""
        if not forcar and self.esta_imprimindo():
            return False, "Impressão em andamento: desligamento bloqueado por segurança."
        try:
            self._post("/api/plugin/psucontrol", {"command": "turnPSUOff"})
            return True, "Tomada desligada."
        except Exception as e:
            return False, f"Falha ao desligar a tomada: {e}"

    def status_tomada(self):
        """True/False conforme o PSU Control, ou None se indisponível."""
        try:
            r = self._post("/api/plugin/psucontrol", {"command": "getPSUState"})
            return bool(r.json().get("isPSUOn"))
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Monitoramento Proativo com Fotos no Telegram
    # -------------------------------------------------------------------------
    def iniciar_monitoramento_telegram(self, intervalo: float = 15.0):
        """Inicia thread em background para monitorar a impressão e enviar fotos/marcos no Telegram."""
        if not self.is_configured():
            print("ℹ️ [OCTOPRINT] URL ou API Key ausente no .env. Monitoramento suspenso.")
            return
        t = threading.Thread(target=self._loop_monitoramento, args=(intervalo,), daemon=True, name="OctoPrintMonitor")
        t.start()
        print("🖨️ [OCTOPRINT] Monitoramento proativo com fotos no Telegram ativado.")

    def _obter_foto_camera(self):
        """Tenta obter o JPEG mais recente da câmera remota do iPhone ou fallback local."""
        try:
            from camera_manager import camera_manager
            jpg = camera_manager.obter_ultimo_jpeg_remoto(max_age_sec=30.0)
            if jpg:
                return jpg
            if os.path.exists(camera_manager.default_photo_path):
                with open(camera_manager.default_photo_path, "rb") as f:
                    return f.read()
        except Exception:
            pass
        return None

    def _notificar_telegram(self, texto: str, com_foto: bool = True):
        from telegram_service import telegram_service
        foto = self._obter_foto_camera() if com_foto else None
        if foto:
            ok = telegram_service.enviar_foto(foto, legenda=texto)
            if ok:
                return
        telegram_service.enviar_mensagem(texto)

    def _loop_monitoramento(self, intervalo: float):
        time.sleep(10)  # aguarda subida dos serviços
        imprimindo_anterior = False
        ultimo_arquivo = ""
        marcos_notificados = set()

        while True:
            try:
                time.sleep(intervalo)
                if not self.is_configured():
                    continue

                try:
                    job = self._get("/api/job")
                except Exception:
                    continue

                estado = job.get("state", "")
                arquivo_info = job.get("job", {}).get("file", {}) or {}
                nome_arquivo = arquivo_info.get("display") or arquivo_info.get("name") or "Trabalho 3D"
                prog = job.get("progress", {}) or {}
                pct = prog.get("completion")
                restante = prog.get("printTimeLeft")
                imprimindo_agora = estado in ("Printing", "Paused", "Pausing", "Resuming")

                if nome_arquivo != ultimo_arquivo:
                    ultimo_arquivo = nome_arquivo
                    marcos_notificados.clear()

                # 1. Início de Impressão
                if imprimindo_agora and not imprimindo_anterior:
                    imprimindo_anterior = True
                    marcos_notificados.clear()
                    tempo_est = f"~{int(restante // 60)} min" if restante else "calculando..."
                    msg = (
                        f"🚀 *Impressão Iniciada na Ender 3 S1 Pro!*\n"
                        f"📁 *Arquivo:* `{nome_arquivo}`\n"
                        f"⏱️ *Estimativa:* {tempo_est}\n"
                        f"Status: {estado}"
                    )
                    self._notificar_telegram(msg, com_foto=True)

                # 2. Marcos de Progresso (25%, 50%, 75%)
                elif imprimindo_agora and pct is not None:
                    pct_int = int(pct)
                    for marco in (25, 50, 75):
                        if pct_int >= marco and marco not in marcos_notificados:
                            marcos_notificados.add(marco)
                            tempo_rest = f"~{int(restante // 60)} min" if restante else "poucos minutos"
                            temps_str = ""
                            try:
                                printer = self._get("/api/printer")
                                t_tool = printer.get("temperature", {}).get("tool0", {}).get("actual", 0)
                                t_bed = printer.get("temperature", {}).get("bed", {}).get("actual", 0)
                                temps_str = f"\n🌡️ Bico: {t_tool:.0f}°C | Mesa: {t_bed:.0f}°C"
                            except Exception:
                                pass

                            msg = (
                                f"📊 *Progresso da Impressão: {marco}%*\n"
                                f"📁 *Arquivo:* `{nome_arquivo}`\n"
                                f"⏳ *Restante:* {tempo_rest}"
                                f"{temps_str}"
                            )
                            self._notificar_telegram(msg, com_foto=True)

                # 3. Impressão Concluída (transição para Operational/Done ou 100%)
                elif imprimindo_anterior and (estado in ("Operational", "Done") or (pct is not None and pct >= 99.8)):
                    imprimindo_anterior = False
                    if 100 not in marcos_notificados:
                        marcos_notificados.add(100)
                        tempo_total = prog.get("printTime")
                        duracao = f"~{int(tempo_total // 60)} min" if tempo_total else "concluído"
                        msg = (
                            f"🎉 *Impressão Concluída com Sucesso!*\n"
                            f"📁 *Arquivo:* `{nome_arquivo}`\n"
                            f"⏱️ *Duração:* {duracao}\n"
                            f"A mesa começará a esfriar. Parabéns pela peça, senhor!"
                        )
                        self._notificar_telegram(msg, com_foto=True)

                # 4. Falha / Cancelamento
                elif imprimindo_anterior and estado in ("Error", "Cancelling", "Cancelled", "Offline"):
                    imprimindo_anterior = False
                    msg = (
                        f"⚠️ *Alerta da Impressora: Impressão Interrompida!*\n"
                        f"📁 *Arquivo:* `{nome_arquivo}`\n"
                        f"Estado: *{estado}*"
                    )
                    self._notificar_telegram(msg, com_foto=True)

            except Exception as e:
                time.sleep(5)


octoprint_service = OctoPrintService()
