"""
J.A.R.V.I.S. — inicialização do servidor (Debian headless).

Este arquivo só sobe os serviços e, se houver terminal interativo, um loop de teclado.
Lógica de roteamento: brain_core.py | ferramentas e prompt: jarvis_tools.py | Gemini: gemini_session.py
Sob systemd (sem TTY) o processo apenas aguarda sinais — sem loop de input() girando em EOFError.
"""

import os
import sys
import signal
import threading

from dotenv import load_dotenv

from env_utils import ENV_PATH

load_dotenv(ENV_PATH)

_encerrar = threading.Event()


def _sinal(signum, _frame):
    print(f"\n🛑 [JARVIS] Sinal {signum} recebido, encerrando...")
    _encerrar.set()


def _cabecalho():
    print("\n" + "=" * 60)
    print("       J.A.R.V.I.S. - PROTOCOLO INICIALIZADO")
    print("=" * 60)


def _loop_terminal():
    """Modo interativo (somente com TTY): digite um comando ou ENTER para usar o microfone do servidor."""
    from brain_core import processar_comando
    from hardware_simulator import hardware
    from voice_engine import voice_engine

    print("\nENTER = falar no microfone do servidor | texto = comando | 'sair' = encerrar\n")
    while not _encerrar.is_set():
        try:
            entrada = input("[JARVIS]> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if entrada.lower() in ("sair", "exit", "quit"):
            break
        if not entrada:
            hardware.desenhar_rosto_oled("OUVINDO")
            entrada = voice_engine.listen()
            if not entrada:
                hardware.desenhar_rosto_oled("NEUTRO")
                continue
        resposta = processar_comando(entrada, origem="cli")
        if resposta:
            voice_engine.speak(resposta)
        hardware.desenhar_rosto_oled("NEUTRO")


def main():
    _cabecalho()
    signal.signal(signal.SIGTERM, _sinal)
    signal.signal(signal.SIGINT, _sinal)

    from hardware_simulator import hardware
    from voice_engine import voice_engine
    from telegram_service import telegram_service
    from iphone_dock_server import iniciar_dock_server
    from octoprint_service import octoprint_service

    if not os.getenv("GEMINI_API_KEY", "").strip() and os.getenv("CLOUD_AI_PROVIDER", "gemini") == "gemini":
        print("⚠️  GEMINI_API_KEY ausente no .env: o modo nuvem Gemini não funcionará até configurá-la.")

    telegram_service.iniciar_em_segundo_plano()
    iniciar_dock_server()
    octoprint_service.iniciar_monitoramento_telegram()

    hardware.atualizar_tela(titulo="JARVIS ONLINE", subtitulo="Aguardando comandos...", icone="⚡")
    voice_engine.speak("Sistemas online e operantes, senhor. Como posso auxiliá-lo?")

    try:
        if sys.stdin is not None and sys.stdin.isatty():
            _loop_terminal()
        else:
            print("ℹ️  Sem terminal interativo (modo serviço). Aguardando eventos do HUD e do Telegram.")
            _encerrar.wait()
    finally:
        print("Encerrando J.A.R.V.I.S....")
        try:
            hardware.mover_braco("repouso")
        except Exception:
            pass
        try:
            from sentinel_service import sentinel_service
            sentinel_service.desativar()
        except Exception:
            pass


if __name__ == "__main__":
    main()
