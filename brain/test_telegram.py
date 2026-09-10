"""
Script de Teste de Conectividade do Bot do Telegram do J.A.R.V.I.S.
"""

import os
import sys
from dotenv import load_dotenv
from telegram_service import telegram_service

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

print("="*60)
print("     J.A.R.V.I.S. - DIAGNÓSTICO DO TELEGRAM BOT")
print("="*60)

print(f"\n1. Verificando Token...")
print(f"Token configurado: {telegram_service.token[:10]}...{telegram_service.token[-5:] if telegram_service.token else 'NÃO DEFINIDO'}")

print("\n2. Tentando comunicar com a API do Telegram (getMe)...")
resultado = telegram_service.get_me()

if resultado.get("ok"):
    bot_info = resultado.get("result", {})
    print("\n✅ [SUCESSO] Bot conectado com os servidores do Telegram!")
    print(f"• Nome do Bot: {bot_info.get('first_name')}")
    print(f"• Username: @{bot_info.get('username')}")
    print(f"• Link direto: https://t.me/{bot_info.get('username')}")
    print(f"• Pode receber mensagens em grupo: {bot_info.get('can_join_groups')}")
    print(f"• Suporta leitura de mensagens: {bot_info.get('can_read_all_group_messages')}")
else:
    print(f"\n❌ [ERRO] Não foi possível conectar ao Telegram:")
    print(f"Detalhes: {resultado.get('error', resultado)}")
    print("\n💡 Dica: Se o erro for de conexão ou SSL (EOF), execute como Administrador o script:")
    print("d:\\Jarvis\\ajustar_rede_telegram.bat")
