"""
Módulo de Serviços Adicionais do Google para o JARVIS:
- Google Tasks (Tarefas do Google)
- Google Sheets (Planilhas Google para controle financeiro)
- YouTube (Busca de vídeos e reprodução de músicas)
"""

import os
import sys
import webbrowser
from google_auth_manager import google_auth_manager

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

class GoogleExtendedServices:
    def __init__(self):
        pass

    @property
    def tasks_service(self):
        """Retorna o serviço do Google Tasks sob demanda (lazy loading)."""
        return google_auth_manager.get_service('tasks', 'v1')

    @property
    def sheets_service(self):
        """Retorna o serviço do Google Sheets sob demanda (lazy loading)."""
        return google_auth_manager.get_service('sheets', 'v4')

    @property
    def youtube_service(self):
        """Retorna o serviço do YouTube API sob demanda (lazy loading)."""
        return google_auth_manager.get_service('youtube', 'v3')

    def _conectar(self):
        return True

    # =========================================================================
    # GOOGLE TASKS (TAREFAS)
    # =========================================================================
    def adicionar_tarefa(self, titulo: str, notas: str = "") -> str:
        """Adiciona uma nova tarefa na lista principal do Google Tasks."""
        try:
            tasks = self.tasks_service
            if not tasks:
                return "Serviço do Google Tasks indisponível no momento. Verifique o credentials.json."
            task = {'title': titulo, 'notes': notas}
            res = tasks.tasks().insert(tasklist='@default', body=task).execute()
            print(f"✅ [GOOGLE TASKS] Tarefa adicionada: '{titulo}'")
            return f"Tarefa '{titulo}' adicionada à sua lista do Google Tasks com sucesso, senhor."
        except Exception as e:
            return f"Erro ao adicionar no Google Tasks: {e}"

    def listar_tarefas(self, max_tarefas: int = 5) -> str:
        """Lista as tarefas pendentes do Google Tasks."""
        try:
            tasks = self.tasks_service
            if not tasks:
                return "Serviço do Google Tasks indisponível no momento. Verifique o credentials.json."
            tasks_res = tasks.tasks().list(tasklist='@default', maxResults=max_tarefas, showCompleted=False).execute()
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
            yt = self.youtube_service
            if yt:
                search_response = yt.search().list(
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
            sheets = self.sheets_service
            if not sheets:
                return f"Gasto anotado de R$ {valor:.2f} com '{item}', mas o serviço de Planilhas Google está indisponível. Verifique o credentials.json."
            from datetime import datetime
            agora = datetime.now().strftime("%d/%m/%Y")
            valores = [[agora, item, categoria, valor]]
            body = {'values': valores}
            sheets.spreadsheets().values().append(
                spreadsheetId=sheet_id, range='A1',
                valueInputOption='USER_ENTERED', body=body
            ).execute()
            return f"Gasto de R$ {valor:.2f} em '{item}' ({categoria}) registrado com sucesso na sua Planilha Google, senhor."
        except Exception as e:
            return f"Gasto anotado de R$ {valor:.2f} com '{item}', mas houve falha ao salvar na planilha: {e}"

google_extended = GoogleExtendedServices()
