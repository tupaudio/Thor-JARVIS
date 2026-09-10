# 🎩 J.A.R.V.I.S. - Personal AI Assistant & Robotics

Assistente pessoal virtual e robótico inspirado no **J.A.R.V.I.S.** da ficção (Tony Stark / Homem de Ferro). Combina inteligência artificial multimodal generativa (**Google Gemini**), síntese e reconhecimento de voz neural em tempo real, automações de sistema operacional Windows, casa inteligente, visão computacional e controle de braço mecânico articulado via Arduino.

---

## 🌟 Funcionalidades e Habilidades

* **🧠 Cérebro Multimodal (Gemini AI + Function Calling):** Compreensão contextual profunda, síntese de respostas diretas no estilo Tony Stark (*"senhor"*) e acionamento dinâmico de dezenas de ferramentas.
* **🎙️ Controle por Voz & Áudio Neural:** Síntese de fala de alta fidelidade com Microsoft Edge-TTS (`AntonioNeural`) e reconhecimento de voz com fallback inteligente.
* **📱 Acesso Remoto no Celular (Telegram Bot):** Comunicação bidirecional com o assistente por texto, notas de voz neurais e envio de fotos da webcam à distância.
* **🛡️ Modo Sentinela & Câmera Frontal:** Monitoramento óptico de mesa via OpenCV. Ao detectar intrusos/movimento, tranca o PC e envia foto de alerta urgente no Telegram.
* **🖥️ Automação Completa do Windows:** Controle do volume master do sistema, bloqueio de tela (`LockWorkStation`), lançador/finalizador de programas e telemetria em tempo real (CPU, RAM, Disco, Bateria).
* **🌐 Busca Web em Tempo Real & Resumos do YouTube:** Consulta cotações, notícias e artigos no DuckDuckGo e resume vídeos longos do YouTube em tópicos executivos com IA.
* **⚡ Protocolos Stark (Cenas e Macros):** Modos automatizados de um só comando:
  * *Protocolo Foco/Trabalho* (abre VS Code/Chrome, volume 35%, luz ciano, Lo-Fi no Spotify).
  * *Protocolo Cinema* (luzes reduzidas, áudio em 75%, tela cheia).
  * *Protocolo Sair da Base* (tranca o PC, apaga luzes, foto de segurança no Telegram).
  * *Protocolo Bom Dia* (briefing com clima, status da máquina e música).
* **🏠 Casa Inteligente / IoT:** Controle de lâmpadas, fitas LED e tomadas via Tuya/Smart Life, Tasmota, Home Assistant, Webhooks ou simulação de estado.
* **📂 Organizador de Arquivos & Downloads:** Varredura e categorização automática de arquivos soltos em pastas dedicadas.
* **💬 WhatsApp Real & Spotify:** Disparo de mensagens pelo aplicativo oficial do WhatsApp e controle total de playlists, artistas e faixas no Spotify.
* **🦾 Atuação Física (Hardware):** Firmware Arduino C++ para controle de braço robótico de 4 servomotores (Base, Ombro, Cotovelo, Garra) e display OLED 1.5" SPI de status.

---

## 🚀 Como Configurar e Executar

### 1. Pré-requisitos
* Python 3.10+ instalado no Windows.
* Git instalado.

### 2. Clonar o Repositório
```bash
git clone https://github.com/SEU_USUARIO/jarvis.git
cd jarvis
```

### 3. Instalar Dependências
```bash
python -m venv venv
venv\Scripts\activate
pip install -r brain/requirements.txt
```

### 4. Configurar Variáveis de Ambiente
Copie o modelo de ambiente e insira suas credenciais:
```bash
copy brain\.env.example brain\.env
```
Abra o arquivo `brain/.env` e configure:
* `GEMINI_API_KEY`: Sua chave gratuita do Google AI Studio.
* `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`: Token do BotFather e seu ID de usuário.
* `SPOTIPY_CLIENT_ID` e `SPOTIPY_CLIENT_SECRET`: Credenciais do painel de desenvolvedores do Spotify.

### 5. Iniciar o Assistente
* **No Computador (Voz e Tela):** Dê um duplo-clique em `iniciar_jarvis.bat`.
* **Modo Servidor Telegram Remoto:** Dê um duplo-clique em `iniciar_telegram_bot.bat`.

---

## 🔒 Segurança e Privacidade
Este projeto já inclui um `.gitignore` rigoroso configurado para garantir que **chaves de API, arquivos `.env`, tokens OAuth, contatos pessoais e fotos capturadas pela webcam nunca sejam rastreados ou enviados para o Git**.
