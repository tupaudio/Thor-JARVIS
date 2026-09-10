"""
Gerenciador Central de Autenticação e Serviços da Google API para o J.A.R.V.I.S.
Implementa Lazy Loading (carregamento sob demanda), cache de clientes e thread-safety.
Elimina a tripla autenticação no startup do assistente.
"""

import os
import sys
import threading
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/youtube.readonly'
]

class GoogleAuthManager:
    """Fonte única de credenciais e clientes Google (Calendar, Gmail, Tasks, Sheets)."""
    def __init__(self):
        self._creds = None
        self._services = {}
        self._lock = threading.Lock()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.token_path = os.path.join(base_dir, "token.json")
        self.credentials_path = os.path.join(base_dir, "credentials.json")

    def _garantir_credenciais(self) -> bool:
        """Garante que credenciais válidas estejam disponíveis sob demanda."""
        if self._creds and self._creds.valid:
            return True

        with self._lock:
            # Dupla checagem sob lock
            if self._creds and self._creds.valid:
                return True

            if os.path.exists(self.token_path):
                try:
                    self._creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                except Exception:
                    self._creds = None

            if not self._creds or not self._creds.valid:
                if self._creds and self._creds.expired and self._creds.refresh_token:
                    try:
                        self._creds.refresh(Request())
                    except Exception:
                        self._creds = None

                if not self._creds:
                    if not os.path.exists(self.credentials_path):
                        return False
                    try:
                        print("\n🔐 [GOOGLE AUTH] Abrindo navegador para autorização da sua conta Google...")
                        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                        self._creds = flow.run_local_server(port=0)
                    except Exception as e:
                        print(f"⚠️ [GOOGLE AUTH] Falha no fluxo OAuth: {e}")
                        return False

                if self._creds and self._creds.valid:
                    try:
                        with open(self.token_path, "w", encoding="utf-8") as f:
                            f.write(self._creds.to_json())
                    except Exception as e:
                        print(f"⚠️ [GOOGLE AUTH] Erro ao salvar token: {e}")

        return bool(self._creds and self._creds.valid)

    def get_service(self, nome_api: str, versao: str):
        """
        Retorna (e armazena em cache) um cliente autenticado da Google API.
        Ex: get_service('calendar', 'v3'), get_service('gmail', 'v1'), get_service('tasks', 'v1').
        """
        chave = f"{nome_api}:{versao}"
        if chave in self._services:
            return self._services[chave]

        with self._lock:
            if chave in self._services:
                return self._services[chave]

            if not self._garantir_credenciais():
                return None

            try:
                service = build(nome_api, versao, credentials=self._creds)
                self._services[chave] = service
                return service
            except Exception as e:
                print(f"⚠️ [GOOGLE AUTH] Erro ao construir serviço '{chave}': {e}")
                return None

google_auth_manager = GoogleAuthManager()
