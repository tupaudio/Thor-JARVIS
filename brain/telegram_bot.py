"""
Runner dedicado para o J.A.R.V.I.S. Bot do Telegram + Servidor Stark Dock (iPhone 11).
Permite manter o bot e o painel do iPhone 11 ativos recebendo comandos
sem precisar abrir a interface de voz local no computador.
"""

import sys
import os


from telegram_service import telegram_service
from iphone_dock_server import iniciar_dock_server

def main():
    print("="*60)
    print("      J.A.R.V.I.S. - MÓDULO REMOTO TELEGRAM & iPHONE DOCK")
    print("="*60)

    # Inicia o servidor WebApp HUD do iPhone 11 em segundo plano
    iniciar_dock_server()
    
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
