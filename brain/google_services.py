"""
Módulo de Serviços Adicionais do Google para o JARVIS:
- Google Tasks (Tarefas do Google)
- Google Sheets (Planilhas Google para controle financeiro)
- YouTube (Busca de vídeos e reprodução de músicas)
"""

import os
import sys
import webbrowser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Escopos unificados completos para todos os serviços Google do JARVIS
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/youtube.readonly'
]

class GoogleExtendedServices:
    def __init__(self):
        self.creds = None
        self.tasks_service = None
        self.sheets_service = None
        self.youtube_service = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.token_path = os.path.join(self.base_dir, "token.json")
        self.credentials_path = os.path.join(self.base_dir, "credentials.json")
        self._conectar()

    def _conectar(self):
        """Inicializa as credenciais compartilhadas."""
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                self.creds = None

        if self.creds and self.creds.valid:
            try:
                self.tasks_service = build('tasks', 'v1', credentials=self.creds)
            except Exception:
                pass
            try:
                self.sheets_service = build('sheets', 'v4', credentials=self.creds)
            except Exception:
                pass
            try:
                self.youtube_service = build('youtube', 'v3', credentials=self.creds)
            except Exception:
                pass

    # =========================================================================
    # GOOGLE TASKS (TAREFAS)
    # =========================================================================
    def adicionar_tarefa(self, titulo: str, notas: str = "") -> str:
        """Adiciona uma nova tarefa na lista principal do Google Tasks."""
        try:
            if not self.tasks_service:
                self._conectar()
            task = {'title': titulo, 'notes': notas}
            res = self.tasks_service.tasks().insert(tasklist='@default', body=task).execute()
            print(f"✅ [GOOGLE TASKS] Tarefa adicionada: '{titulo}'")
            return f"Tarefa '{titulo}' adicionada à sua lista do Google Tasks com sucesso, senhor."
        except Exception as e:
            return f"Erro ao adicionar no Google Tasks: {e}"

    def listar_tarefas(self, max_tarefas: int = 5) -> str:
        """Lista as tarefas pendentes do Google Tasks."""
        try:
            if not self.tasks_service:
                self._conectar()
            tasks_res = self.tasks_service.tasks().list(tasklist='@default', maxResults=max_tarefas, showCompleted=False).execute()
            items = tasks_res.get('items', [])
            if not items:
                return "O senhor não possui tarefas pendentes no Google Tasks no momento."
            resposta = "Suas tarefas pendentes no Google Tasks são:\n"
            for t in items:
                resposta += f"- {t.get('title')}\n"
            return resposta
        except Exception as e:
            return f"Erro ao listar Google Tasks: {e}"

    # =========================================================================
    # YOUTUBE (BUSCA E REPRODUÇÃO NO NAVEGADOR)
    # =========================================================================
    def tocar_youtube(self, termo: str) -> str:
        """Busca o vídeo mais relevante no YouTube e abre no navegador."""
        try:
            print(f"🎵 [YOUTUBE] Pesquisando e reproduzindo: '{termo}'...")
            if self.youtube_service:
                search_response = self.youtube_service.search().list(
                    q=termo, part='id,snippet', maxResults=1, type='video'
                ).execute()
                items = search_response.get('items', [])
                if items:
                    video_id = items[0]['id']['videoId']
                    video_title = items[0]['snippet']['title']
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    webbrowser.open(url)
                    return f"Reproduzindo no YouTube agora: '{video_title}', senhor."
            
            # Fallback direto via busca web
            url_busca = f"https://www.youtube.com/results?search_query={termo.replace(' ', '+')}"
            webbrowser.open(url_busca)
            return f"Abrindo resultados do YouTube para '{termo}' no seu navegador, senhor."
        except Exception as e:
            url_busca = f"https://www.youtube.com/results?search_query={termo.replace(' ', '+')}"
            webbrowser.open(url_busca)
            return f"Abrindo YouTube para '{termo}' no navegador."

    # =========================================================================
    # GOOGLE SHEETS (PLANILHAS / REGISTRO FINANCEIRO)
    # =========================================================================
    def registrar_gasto_planilha(self, item: str, valor: float, categoria: str = "Geral", id_planilha: str = "") -> str:
        """Registra um gasto ou entrada financeira."""
        # Se o usuário não passou um ID fixo de planilha, tenta ler do .env
        sheet_id = id_planilha or os.getenv("GOOGLE_SHEETS_ID")
        if not sheet_id:
            return f"Gasto de R$ {valor:.2f} com '{item}' registrado (Para salvar diretamente na nuvem, defina GOOGLE_SHEETS_ID no arquivo .env, senhor)."
        try:
            from datetime import datetime
            agora = datetime.now().strftime("%d/%m/%Y")
            valores = [[agora, item, categoria, valor]]
            body = {'values': valores}
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=sheet_id, range='A1',
                valueInputOption='USER_ENTERED', body=body
            ).execute()
            return f"Gasto de R$ {valor:.2f} em '{item}' ({categoria}) registrado com sucesso na sua Planilha Google, senhor."
        except Exception as e:
            return f"Gasto anotado de R$ {valor:.2f} com '{item}', mas houve falha ao salvar na planilha: {e}"

google_extended = GoogleExtendedServices()
