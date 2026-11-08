# Correções — J.A.R.V.I.S. (migração Windows -> Debian)

Arquivos NOVOS: system_service.py (substitui windows_service.py), gemini_session.py, brain_core.py,
jarvis_tools.py (ferramentas + prompt, saíram do main.py), env_utils.py, requirements-audio-local.txt, jarvis.service.example.
Arquivos REESCRITOS: main.py, ai_router.py, voice_engine.py, camera_manager.py, file_manager_service.py, iphone_dock_server.py.
PATCHES: telegram_service, serial_comm, spotify_service, whatsapp_service, sentinel_service, protocols_service, requirements, .env.example.

Aplicar: backup da pasta; copie os arquivos por cima (NÃO sobrescreva .env, credentials.json, token.json,
contatos.json, dispositivos_iot.json, .spotify_cache); apague windows_service.py; `pip install -r requirements.txt`;
reinicie. No primeiro start é gerado JARVIS_DOCK_TOKEN no .env e a URL de pareamento aparece no log:
abra https://<ip>:8443/?token=... UMA vez no Safari do iPhone.

ROTACIONE as credenciais que estavam no zip (Telegram, Gemini, Google token, Spotify, chave TLS).
