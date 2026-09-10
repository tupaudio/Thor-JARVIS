"""
Módulo de Integração Real com a Google Calendar API para o JARVIS.
Permite criar, consultar e excluir eventos na conta Google do usuário.
"""

import os
import sys
from datetime import datetime, timedelta
import dateutil.parser

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

class GoogleCalendarService:
    def __init__(self):
        self.creds = None
        self.service = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.token_path = os.path.join(self.base_dir, "token.json")
        self.credentials_path = os.path.join(self.base_dir, "credentials.json")
        self._autenticar()

    def _autenticar(self):
        """Autentica o usuário via OAuth 2.0 e inicializa o serviço do Calendar."""
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                self.creds = None

        # Se não há credenciais válidas, realiza o login
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    print(f"⚠️ [CALENDAR AVISO] Arquivo '{self.credentials_path}' não encontrado.")
                    return
                print("\n🔐 [GOOGLE CALENDAR] Abrindo navegador para autorização da sua conta Google...")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)

            # Salva o token para as próximas vezes
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(self.creds.to_json())
            print("✅ [GOOGLE CALENDAR] Conexão autorizada e token salvo com sucesso!")

        self.service = build('calendar', 'v3', credentials=self.creds)

    def adicionar_evento(self, titulo: str, inicio_str: str, fim_str: str = None, descricao: str = "") -> str:
        """
        Adiciona um novo evento na Google Agenda.
        Formato de início esperado: 'YYYY-MM-DDTHH:MM:SS' ou data legível.
        """
        if not self.service:
            self._autenticar()
            if not self.service:
                return "Não foi possível conectar ao Google Calendar. Verifique o credentials.json."

        try:
            # Interpreta a data de início
            try:
                dt_inicio = dateutil.parser.parse(inicio_str)
            except Exception:
                dt_inicio = datetime.now() + timedelta(days=1, hours=2)

            # Se não especificou fim, assume 1 hora de duração
            if fim_str:
                try:
                    dt_fim = dateutil.parser.parse(fim_str)
                except Exception:
                    dt_fim = dt_inicio + timedelta(hours=1)
            else:
                dt_fim = dt_inicio + timedelta(hours=1)

            # Fuso horário padrão de Brasília (America/Sao_Paulo)
            fuso = "America/Sao_Paulo"
            evento = {
                'summary': titulo,
                'description': descricao if descricao else "Criado pelo assistente JARVIS",
                'start': {
                    'dateTime': dt_inicio.isoformat(),
                    'timeZone': fuso,
                },
                'end': {
                    'dateTime': dt_fim.isoformat(),
                    'timeZone': fuso,
                },
            }

            evento_criado = self.service.events().insert(calendarId='primary', body=evento).execute()
            link = evento_criado.get('htmlLink', '')
            horario_formatado = dt_inicio.strftime("%d/%m/%Y às %H:%M")
            print(f"📅 [CALENDAR SUCESSO] Evento '{titulo}' agendado para {horario_formatado}!")
            return f"Evento '{titulo}' agendado com sucesso no Google Agenda para {horario_formatado}."
        except Exception as e:
            print(f"❌ [CALENDAR ERRO]: {e}")
            return f"Erro ao adicionar evento na agenda: {e}"

    def listar_proximos_eventos(self, max_eventos: int = 5) -> str:
        """
        Retorna os próximos eventos agendados na conta do usuário.
        """
        if not self.service:
            self._autenticar()
            if not self.service:
                return "Serviço do Google Agenda indisponível."

        try:
            agora = datetime.utcnow().isoformat() + 'Z'
            events_result = self.service.events().list(
                calendarId='primary', timeMin=agora,
                maxResults=max_eventos, singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            if not events:
                return "O senhor não possui nenhum compromisso agendado para os próximos dias."

            resultado = "Seus próximos compromissos na agenda são:\n"
            for ev in events:
                start = ev['start'].get('dateTime', ev['start'].get('date'))
                try:
                    dt = dateutil.parser.parse(start)
                    dataFormatada = dt.strftime("%d/%m às %H:%M")
                except Exception:
                    dataFormatada = start
                resultado += f"- {ev.get('summary', 'Sem título')} em {dataFormatada}\n"

            return resultado
        except Exception as e:
            return f"Erro ao consultar eventos da agenda: {e}"

    def excluir_evento(self, termo_busca: str) -> str:
        """
        Busca e remove um evento pelo título ou palavra-chave.
        """
        if not self.service:
            self._autenticar()
            if not self.service:
                return "Serviço do Google Agenda indisponível."

        try:
            agora = datetime.utcnow().isoformat() + 'Z'
            events_result = self.service.events().list(
                calendarId='primary', timeMin=agora,
                maxResults=10, singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            for ev in events:
                summary = ev.get('summary', '').lower()
                if termo_busca.lower() in summary:
                    self.service.events().delete(calendarId='primary', eventId=ev['id']).execute()
                    return f"Compromisso '{ev.get('summary')}' foi removido com sucesso da sua agenda."

            return f"Não encontrei nenhum evento futuro com o termo '{termo_busca}' para excluir."
        except Exception as e:
            return f"Erro ao excluir evento: {e}"

# Instância global
calendar_service = GoogleCalendarService()
