"""
Módulo de Integração Real com a Google Calendar API para o JARVIS.
Permite criar, consultar e excluir eventos na conta Google do usuário.
"""

import os
import sys
from datetime import datetime, timedelta
import dateutil.parser

from google_auth_manager import google_auth_manager

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

class GoogleCalendarService:
    def __init__(self):
        pass

    @property
    def service(self):
        """Retorna o serviço do Google Calendar carregado sob demanda (lazy loading)."""
        return google_auth_manager.get_service('calendar', 'v3')

    def _autenticar(self):
        return self.service is not None

    def adicionar_evento(self, titulo: str, inicio_str: str, fim_str: str = None, descricao: str = "") -> str:
        """
        Adiciona um novo evento na Google Agenda.
        Formato de início esperado: 'YYYY-MM-DDTHH:MM:SS' ou data legível.
        """
        service = self.service
        if not service:
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
        service = self.service
        if not service:
            return "Serviço do Google Agenda indisponível. Verifique o credentials.json."

        try:
            agora = datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
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
        service = self.service
        if not service:
            return "Serviço do Google Agenda indisponível. Verifique o credentials.json."

        try:
            agora = datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(
                calendarId='primary', timeMin=agora,
                maxResults=10, singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            for ev in events:
                summary = ev.get('summary', '').lower()
                if termo_busca.lower() in summary:
                    service.events().delete(calendarId='primary', eventId=ev['id']).execute()
                    return f"Compromisso '{ev.get('summary')}' foi removido com sucesso da sua agenda."

            return f"Não encontrei nenhum evento futuro com o termo '{termo_busca}' para excluir."
        except Exception as e:
            return f"Erro ao excluir evento: {e}"

# Instância global
calendar_service = GoogleCalendarService()
