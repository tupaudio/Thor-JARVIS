"""
Módulo de Integração com o Gmail para o JARVIS.
Permite ler os últimos e-mails não lidos e enviar e-mails por comando de voz.
"""

import os
import sys
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Escopos combinados: Calendar + Gmail (Leitura e Envio)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/youtube.readonly'
]

class GmailService:
    def __init__(self):
        self.creds = None
        self.service = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.token_path = os.path.join(self.base_dir, "token.json")
        self.credentials_path = os.path.join(self.base_dir, "credentials.json")
        self._autenticar()

    def _autenticar(self):
        """Autentica o usuário para o Gmail aproveitando as credenciais do Google."""
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                self.creds = None

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    print(f"⚠️ [GMAIL AVISO] Arquivo '{self.credentials_path}' não encontrado.")
                    return
                print("\n🔐 [GMAIL] Abrindo navegador para autorizar permissões de e-mail...")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)

            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(self.creds.to_json())
            print("✅ [GMAIL] Conexão com Gmail autorizada com sucesso!")

        self.service = build('gmail', 'v1', credentials=self.creds)

    def ler_ultimos_emails(self, quantidade: int = 3, apenas_nao_lidos: bool = True) -> str:
        """
        Consulta os últimos e-mails recebidos na caixa de entrada.
        """
        if not self.service:
            self._autenticar()
            if not self.service:
                return "Serviço do Gmail indisponível no momento."

        try:
            query = "is:unread in:inbox" if apenas_nao_lidos else "in:inbox"
            results = self.service.users().messages().list(userId='me', q=query, maxResults=quantidade).execute()
            messages = results.get('messages', [])

            if not messages:
                status_tipo = "não lidos" if apenas_nao_lidos else "recentes"
                return f"O senhor não possui e-mails {status_tipo} na caixa de entrada."

            resumo = f"Encontrei os seguintes e-mails recentes para o senhor:\n"
            for i, msg_ref in enumerate(messages, 1):
                msg = self.service.users().messages().get(
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
        if not self.service:
            self._autenticar()
            if not self.service:
                return "Serviço do Gmail indisponível."

        try:
            mensagem = MIMEText(corpo)
            mensagem['to'] = destinatario
            mensagem['subject'] = assunto

            raw = base64.urlsafe_b64encode(mensagem.as_bytes()).decode()
            self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
            
            print(f"📧 [GMAIL ENVIADO] Para: {destinatario} | Assunto: {assunto}")
            return f"E-mail enviado com sucesso para {destinatario} com o assunto '{assunto}', senhor."
        except Exception as e:
            return f"Erro ao enviar e-mail pelo Gmail: {e}"

gmail_service = GmailService()
