"""
Módulo de Integração com o Gmail para o JARVIS.
Permite ler os últimos e-mails não lidos e enviar e-mails por comando de voz.
"""

import os
import sys
import base64
from email.mime.text import MIMEText
from google_auth_manager import google_auth_manager

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

class GmailService:
    def __init__(self):
        pass

    @property
    def service(self):
        """Retorna o serviço do Gmail carregado sob demanda (lazy loading)."""
        return google_auth_manager.get_service('gmail', 'v1')

    def _autenticar(self):
        return self.service is not None

    def ler_ultimos_emails(self, quantidade: int = 3, apenas_nao_lidos: bool = True) -> str:
        """
        Consulta os últimos e-mails recebidos na caixa de entrada.
        """
        service = self.service
        if not service:
            return "Serviço do Gmail indisponível no momento. Verifique o credentials.json."

        try:
            query = "is:unread in:inbox" if apenas_nao_lidos else "in:inbox"
            results = service.users().messages().list(userId='me', q=query, maxResults=quantidade).execute()
            messages = results.get('messages', [])

            if not messages:
                status_tipo = "não lidos" if apenas_nao_lidos else "recentes"
                return f"O senhor não possui e-mails {status_tipo} na caixa de entrada."

            resumo = f"Encontrei os seguintes e-mails recentes para o senhor:\n"
            for i, msg_ref in enumerate(messages, 1):
                msg = service.users().messages().get(
                    userId='me', id=msg_ref['id'], format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()

                headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
                remetente = headers.get('From', 'Desconhecido')
                # Simplificar o nome do remetente (remover o <email@...>)
                nome_remetente = remetente.split('<')[0].strip().replace('"', '')
                assunto = headers.get('Subject', 'Sem assunto')
                snippet = msg.get('snippet', '')

                resumo += f"\n{i}. De {nome_remetente}: '{assunto}'. Resumo: {snippet[:90]}..."

            return resumo
        except Exception as e:
            return f"Erro ao ler e-mails do Gmail: {e}"

    def enviar_email(self, destinatario: str, assunto: str, corpo: str) -> str:
        """
        Envia um novo e-mail a partir da sua conta Google.
        """
        service = self.service
        if not service:
            return "Serviço do Gmail indisponível. Verifique o credentials.json."

        try:
            mensagem = MIMEText(corpo)
            mensagem['to'] = destinatario
            mensagem['subject'] = assunto

            raw = base64.urlsafe_b64encode(mensagem.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            
            print(f"📧 [GMAIL ENVIADO] Para: {destinatario} | Assunto: {assunto}")
            return f"E-mail enviado com sucesso para {destinatario} com o assunto '{assunto}', senhor."
        except Exception as e:
            return f"Erro ao enviar e-mail pelo Gmail: {e}"

gmail_service = GmailService()
