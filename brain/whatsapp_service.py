"""
Módulo de Envio de Mensagens do WhatsApp para o J.A.R.V.I.S.
Integrado com o Aplicativo WhatsApp Desktop do Windows e WhatsApp Web,
com suporte a agenda de contatos inteligente e envio automatizado.
"""

import os
import re
import sys
import json
import time
import urllib.parse
import webbrowser
import subprocess
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

class WhatsAppService:
    def __init__(self):
        self.contatos_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "contatos.json"))
        self.default_ddd = os.getenv("DEFAULT_DDD", "27").strip()

    def _carregar_contatos(self) -> dict:
        """Carrega a agenda de contatos do arquivo JSON."""
        if not os.path.exists(self.contatos_path):
            return {}
        try:
            with open(self.contatos_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _salvar_contatos(self, contatos: dict):
        """Salva o dicionário de contatos no arquivo JSON."""
        try:
            with open(self.contatos_path, "w", encoding="utf-8") as f:
                json.dump(contatos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ [WHATSAPP] Erro ao salvar contatos.json: {e}")

    def formatar_numero(self, numero_ou_texto: str) -> str:
        """
        Formata um número para o padrão internacional com DDI e DDD (ex: 5527999999999).
        """
        apenas_digitos = re.sub(r"\D", "", numero_ou_texto)
        
        # 8 ou 9 dígitos: adiciona DDD padrão (27) e DDI (55)
        if len(apenas_digitos) in [8, 9]:
            apenas_digitos = f"55{self.default_ddd}{apenas_digitos}"
        # 10 ou 11 dígitos (com DDD): adiciona DDI (55)
        elif len(apenas_digitos) in [10, 11]:
            apenas_digitos = f"55{apenas_digitos}"
        # Já tem DDI (12 ou 13 dígitos)
        elif len(apenas_digitos) in [12, 13] and apenas_digitos.startswith("55"):
            pass
        
        return apenas_digitos

    def resolver_destinatario(self, destinatario: str):
        """
        Descobre o número de telefone a partir do nome do contato ou string de telefone.
        Retorna (nome_exibicao, numero_formatado).
        """
        dest_limpo = destinatario.strip().lower()
        contatos = self._carregar_contatos()
        
        # Busca exata ou parcial pelo nome na agenda
        for nome, num in contatos.items():
            if nome and (nome.lower() in dest_limpo or dest_limpo in nome.lower()):
                if num:
                    return nome.capitalize(), self.formatar_numero(num)

        # Se não achou na agenda, verifica se o próprio destinatário já é um número
        digitos = re.sub(r"\D", "", destinatario)
        if len(digitos) >= 8:
            return destinatario, self.formatar_numero(destinatario)

        return destinatario, None

    def salvar_contato(self, nome: str, numero: str) -> str:
        """Cadastra ou atualiza um contato na agenda do JARVIS."""
        num_formatado = self.formatar_numero(numero)
        if not num_formatado or len(num_formatado) < 10:
            return f"Número '{numero}' inválido. Por favor forneça o número com DDD (ex: 27 99123-4567)."

        contatos = self._carregar_contatos()
        nome_chave = nome.strip().lower()
        contatos[nome_chave] = num_formatado
        self._salvar_contatos(contatos)
        
        return f"Contato '{nome.capitalize()}' salvo com sucesso com o número +{num_formatado}."

    def listar_contatos(self) -> str:
        """Retorna a lista de contatos salvos na agenda."""
        contatos = self._carregar_contatos()
        contatos_validos = {k: v for k, v in contatos.items() if v}
        if not contatos_validos:
            return "Nenhum contato com número cadastrado na agenda ainda, senhor."
        
        linhas = [f"• {k.capitalize()}: +{v}" for k, v in contatos_validos.items()]
        return "Contatos cadastrados no WhatsApp:\n" + "\n".join(linhas)

    def enviar_mensagem(self, destinatario: str, mensagem: str) -> str:
        """
        Dispara uma mensagem real no WhatsApp (App do Windows ou Web).
        
        Args:
            destinatario: Nome do contato (ex: 'Carlos', 'Mãe') ou número com DDD.
            mensagem: Conteúdo do texto a ser enviado.
        """
        nome_exibicao, numero_formatado = self.resolver_destinatario(destinatario)
        
        if not numero_formatado:
            return (
                f"Senhor, não encontrei o contato '{destinatario}' na sua agenda do WhatsApp. "
                f"Por favor, me informe o número com DDD para que eu possa cadastrar e enviar."
            )

        print(f"\n📱 [WHATSAPP REAL] Disparando para {nome_exibicao} (+{numero_formatado}): \"{mensagem}\"")

        texto_codificado = urllib.parse.quote(mensagem)
        
        # 1. Tentativa via Aplicativo Oficial do WhatsApp Desktop (Windows)
        try:
            import pyautogui
            
            # Abre diretamente a conversa com o texto no WhatsApp Desktop via Windows Shell
            uri = f"whatsapp://send?phone={numero_formatado}&text={texto_codificado}"
            os.startfile(uri)
            
            # Aguarda a janela do WhatsApp carregar e focar
            time.sleep(2.5)
            
            # Pressiona Enter para enviar
            pyautogui.press("enter")
            
            return f"Mensagem enviada com sucesso para {nome_exibicao} (+{numero_formatado}) via WhatsApp Desktop, senhor."
            
        except Exception as e:
            print(f"⚠️ [WHATSAPP] Falha no aplicativo desktop ({e}), tentando WhatsApp Web...")

        # 2. Fallback via WhatsApp Web
        try:
            import pywhatkit
            pywhatkit.sendwhatmsg_instantly(
                phone_no=f"+{numero_formatado}",
                message=mensagem,
                wait_time=12,
                tab_close=True,
                close_time=3
            )
            return f"Mensagem enviada com sucesso para {nome_exibicao} via WhatsApp Web, senhor."
        except Exception as e_web:
            # Fallback seguro: abre a conversa no navegador
            url = f"https://web.whatsapp.com/send?phone={numero_formatado}&text={texto_codificado}"
            webbrowser.open(url)
            return f"Abri a conversa de {nome_exibicao} com o texto pronto no WhatsApp para o senhor confirmar."

whatsapp_service = WhatsAppService()
