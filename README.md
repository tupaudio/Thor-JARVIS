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

## 🏛️ Arquitetura de Hardware e Infraestrutura

O sistema opera de forma desacoplada e sem fios cruzando a mesa de trabalho, dividindo-se em um servidor central e dois docks físicos de bancada:

```
                       [ 🌐 Google Gemini API (Nuvem) ]
                                      ▲
                                      │ (Internet)
                                      ▼
               ┌──────────────────────────────────────────────┐
               │         🖥️ DELL OPTIPLEX MINI PC             │
               │         (Servidor J.A.R.V.I.S. 24/7)         │
               └──────┬────────────────────────────────┬──────┘
                      │ (Cabo USB Curto)               │ (Wi-Fi Local / WebSocket)
                      ▼                                ▼
       ┌──────────────────────────────┐ ┌──────────────────────────────┐
       │     🤖 DOCK BRAÇO ROBÓTICO   │ │     🖥️ DOCK CONSOLE DE MESA  │
       │                              │ │                              │
       │ • Arduino Uno                │ │ • ESP32-S3                   │
       │ • Sensor Shield V5.0         │ │ • Tela TFT 4.0" SPI Touch    │
       │ • Fonte Externa 5V 3A        │ │ • Falante 4Ω 3W (Esquerda)   │
       │ • 4x Servos SG90 (9g)        │ │ • Mic INMP441 I2S (Topo)     │
       │ • Display OLED 1.5" (Cabeça) │ │ • Coldre Stylus (Direita)    │
       │ • Cabo USB no Mini PC        │ │ • Alimentação via USB-C      │
       └──────────────────────────────┘ └──────────────────────────────┘
```

### 1. Servidor Dedicado 24/7 (Dell OptiPlex Micro)
- Roda o núcleo do JARVIS Brain em Python em segundo plano.
- Gerencia o Bot do Telegram com acesso remoto contínuo de qualquer lugar.
- Ponte local de baixa latência para a API do Google Gemini.
- Despacha comandos de cinemática para o braço e faz streaming de áudio/HUD para o console.

### 2. Dock Braço Robótico (Atuação Física)
- **Placa de Controle:** Arduino Uno com **Sensor Shield V5.0** acoplado.
- **Isolamento Elétrico de Força:** Jumper de energia do Shield removido, garantindo que os 4 servos SG90 sejam alimentados exclusivamente pela fonte dedicada de **5V 3A** pelo borne de parafuso, sem risco de queda de tensão (*brownout*) no Arduino.
- **Cabeça Articulada:** Suporte com aba de 3.0 mm montada diretamente sobre a garra acrílica (fixação nos parafusos de 14.8 mm e base de 23.0 mm), alojando display OLED 1.5" SPI de status (janela 34×34 mm, berço 35×48 mm) e trilho superior de câmera.
- **Comunicação:** Cabo USB comum ligado diretamente ao Dell Mini PC (Serial UART a 115200 bps).

### 3. Dock Console Satélite de Mesa (Interface Homem-Máquina)
- **Microcontrolador:** ESP32-S3 DevKit.
- **Alimentação:** Cabo USB-C padrão (5V 2A+ suporta com ampla folga o ESP32 + Tela + Áudio).
- **Painel Central:** Display TFT 4.0" Touch em ângulo ergonômico de 55° (`101.5 × 54.0 mm` entre furos).
- **Áudio Integrado:** Módulo DAC I2S MAX98357A e alto-falante 4Ω 3W (`27.8 × 36.7 mm`) em câmara traseira selada no lado esquerdo da tela.
- **Reconhecimento de Voz:** Microfone MEMS I2S INMP441 (`13.6 mm`) centralizado no topo do console, acusticamente desacoplado dos alto-falantes e alinhado à linha de fala.
- **Acessório:** Coldre embutido no flanco direito para a caneta Stylus de toque (`87.0 × 4.8 mm`).
- **Comunicação:** Totalmente sem fios via Wi-Fi (WebSocket) com o servidor Mini PC.

---

## 🎨 Projetos CAD 3D e Modelagem (`cad_3d/`)

O diretório [`cad_3d/`](file:///d:/Jarvis/cad_3d) contém toda a engenharia mecânica dos gabinetes calibrada por medições de paquímetro digital:
- [`cabeca_braco_oled.scad`](file:///d:/Jarvis/cad_3d/cabeca_braco_oled.scad): Código OpenSCAD da cabeça montada sobre a garra com aba de 3 mm.
- [`console_satelite_tft.scad`](file:///d:/Jarvis/cad_3d/console_satelite_tft.scad): Código OpenSCAD do console de mesa com alto-falante à esquerda, mic no topo e coldre lateral.
- [`tampa_inferior_satelite.scad`](file:///d:/Jarvis/cad_3d/tampa_inferior_satelite.scad): Base com ranhuras de fluxo térmico e pés de silicone.
- [`stls/`](file:///d:/Jarvis/cad_3d/stls): Arquivos `.stl` compilados prontos para fatiamento FDM (Cura, PrusaSlicer, OrcaSlicer, Bambu Studio).
- [`GUIA_FREECAD.md`](file:///d:/Jarvis/cad_3d/GUIA_FREECAD.md): Tutorial passo a passo de modelagem paramétrica nas bancadas PartDesign e Spreadsheet do FreeCAD.

---

## 🔒 Segurança e Privacidade
Este projeto inclui um `.gitignore` rigoroso configurado para garantir que **chaves de API, arquivos `.env`, tokens OAuth, contatos pessoais e fotos capturadas pela webcam nunca sejam rastreados ou enviados para o Git**.
