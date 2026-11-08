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


octoprint_service = OctoPrintService()
