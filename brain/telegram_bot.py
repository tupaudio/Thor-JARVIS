"""
Runner dedicado para o J.A.R.V.I.S. Bot do Telegram.
Permite manter o bot ativo recebendo comandos do celular
sem precisar abrir a interface de voz local no computador.
"""

import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from telegram_service import telegram_service

def main():
    print("="*60)
    print("      J.A.R.V.I.S. - MÓDULO REMOTO TELEGRAM BOT")
    print("="*60)
    
    status = telegram_service.get_me()
    if not status.get("ok"):
        print(f"❌ Erro ao inicializar bot: {status.get('error')}")
        return

    bot_info = status.get("result", {})
    print(f"✅ Bot online: @{bot_info.get('username')}")
    print(f"👉 Acesse no seu celular: https://t.me/{bot_info.get('username')}")
    print("\nAguardando mensagens remotas (Pressione Ctrl+C para parar)...")
    print("="*60 + "\n")
    
    try:
        telegram_service.polling_loop()
    except KeyboardInterrupt:
        print("\nEncerrando bot do Telegram...")

if __name__ == "__main__":
    main()
