# J.A.R.V.I.S. Home Station & 3D Print Lab
## Especificação Técnica da Arquitetura, Servidor e Módulos

### 1. Visão Geral do Sistema
O **Thor-JARVIS** é um assistente pessoal cibernético e controlador de estação residencial com foco em:
* Automação física e robótica (braço robótico, ESP32, Arduino).
* Monitoramento inteligente e telemetria de manufatura aditiva (Impressora 3D Creality Ender 3 S1 Pro com OctoPrint).
* Interface multimodal e percepção visual/auditiva contínua através de dock dedicado com **iPhone 11** (HUD Stark WebApp, streaming MJPEG de baixa latência e áudio bidirecional).
* Roteamento híbrido de Inteligência Artificial: execução de modelos locais (Ollama) para privacidade e baixa latência + fallback/orquestração para LLMs em nuvem de ponta (Google Gemini 2.5 Pro/Flash, OpenAI GPT-4o).
* Centro de comando via mensageria (Bot do Telegram com envio automático de fotos em tempo real e comandos remotos).

---

### 2. Infraestrutura de Hardware e Topologia de Rede

#### 2.1 Servidor Central (Host Debian)
* **Hardware:** Dell OptiPlex 3060 Micro.
* **Sistema Operacional:** Debian GNU/Linux 13 (Trixie), arquitetura x86_64.
* **Gerenciador de Processos:** Systemd (`jarvis.service`, reinicialização automática sob falha).
* **Ambiente Python:** Virtualenv gerenciada em `/home/thor/projetos/Jarvis/.venv`.
* **Conectividade:**
  * **IP Local (LAN):** `192.168.15.199`
  * **IP VPN Mesh (Tailscale):** `100.120.152.123` (acesso remoto seguro ponto-a-ponto sem expor portas ao roteador).

#### 2.2 Portas e Serviços em Execução
* **Porta 5000 (HTTP):** OctoPrint (Daemon de controle de impressão 3D e G-code streamer).
* **Porta 8080 (HTTP):** J.A.R.V.I.S. iPhone Dock Server (Redirecionamento, snapshots e streaming MJPEG).
* **Porta 8443 (HTTPS):** J.A.R.V.I.S. iPhone Dock Server Seguro (necessário para o iOS Safari liberar acesso a WebRTC/getUserMedia e microfone).
* **Porta 11434 (HTTP):** Ollama Local LLM Runtime.
* **Porta 445 (SMB):** Samba File Share para desenvolvimento remoto (`Thor-Workspace` mapeado como `Y:` no Windows).

#### 2.3 Periféricos Físicos Conectados
* **Impressora 3D:** Creality Ender 3 S1 Pro conectada via porta serial USB `/dev/ttyUSB0` (chip serial CH340, baudrate 115200 bps).
* **iPhone 11 (Dedicated Dock Station):**
  * Montado fisicamente voltado para a mesa de impressão / estação de trabalho.
  * Executa PWA em tela cheia do HUD Stark via Safari HTTPS (`https://192.168.15.199:8443/`).
  * Envia silenciosamente frames JPEG redimensionados (~35 KB cada) para `/api/camera/frame`.
  * Fornece síntese de voz (TTS Web Speech API) e captura de áudio com ativação por toque inicial.
* **Controlador Arduino/ESP32 (Planejado/Em integração):**
  * Conexão via `/dev/ttyACM*` (excluindo `/dev/ttyUSB0` reservado para OctoPrint).

---

### 3. Módulos e Componentes de Software (`brain/`)

1. **`main.py`:**
   Ponto de entrada do daemon. Carrega variáveis de ambiente, inicializa o watchdog sentinela, inicia o servidor HTTP/HTTPS do iPhone Dock, dispara o monitoramento assíncrono do OctoPrint e gerencia o encerramento gracioso (*graceful shutdown*).

2. **`ai_router.py` & `gemini_session.py`:**
   Roteador inteligente de inferência. Avalia a complexidade do prompt e a disponibilidade do Ollama local (`llama3.2:3b`, `hermes3:3b`). Se a tarefa exigir raciocínio avançado, visão computacional ou processamento de arquivos grandes, redireciona para Gemini 2.5 Pro ou OpenAI GPT-4o.

3. **`octoprint_service.py`:**
   Cliente REST da API do OctoPrint. Consulta o estado da impressora (`/api/printer`), temperatura da mesa/extrusor e status do trabalho (`/api/job`). Contém a thread em segundo plano `_loop_monitoramento` que calcula marcos de progresso (0%, 25%, 50%, 75%, 100%) e extrai frames da câmera para reportar no Telegram.

4. **`iphone_dock_server.py`:**
   Servidor web assíncrono duplo (HTTP:8080 / HTTPS:8443). Serve o HUD futurista Stark em HTML5/JS/Canvas, gerencia SSE (*Server-Sent Events*) para sincronização de estado, recebe frames de câmera via POST `/api/camera/frame` e expõe:
   * `/camera/snapshot.jpg`: Último frame capturado em JPEG puro.
   * `/camera/stream.mjpg`: Stream contínuo multipart MJPEG de baixa latência com controle de semáforo e `socket.flush()` individual por quadro.

5. **`camera_manager.py`:**
   Buffer circular em memória com controle de versão/sequência dos frames recebidos (`aguardar_frame_novo`), suportando múltiplos consumidores concorrentes (OctoPrint, Telegram, Visão Computacional).

6. **`telegram_service.py` & `telegram_bot.py`:**
   Interface de mensageria com a biblioteca Telegram Bot API. Suporta comandos de controle `/status`, `/foto`, `/temperatura`, `/cancelar` e disparo de fotos diretamente de buffers de memória (`BytesIO`).

7. **`serial_comm.py`:**
   Camada de comunicação de baixo nível para comandos G-code e protocolo Arduino/ESP32, com isolamento de portas para prevenção de concorrência com o OctoPrint.

8. **Serviços de Terceiros e IoT:**
   * `spotify_service.py`: Controle de reprodução Spotify Connect.
   * `google_calendar.py` & `gmail_service.py`: Autenticação OAuth2 Google para compromissos e e-mails.
   * `weather_service.py` & `waze_service.py`: Condições meteorológicas e tempo de trânsito em tempo real.
   * `notion_service.py`: Sincronização de tarefas e notas.
   * `iot_service.py`: Controle de relés e tomadas inteligentes (Home Assistant / Sonoff / Tuya).

---

### 4. Firmware e Modelagem CAD 3D (`cad_3d/`, `firmware/`)
* **`cad_3d/`:** Scripts paramétricos em OpenSCAD (`cabeca_braco_oled.scad`, `console_satelite_tft.scad`, `pod_acustico_satelite.scad`) para prototipagem de carcaças e suportes na impressora 3D.
* **`firmware/arduino_arm`:** Firmware C/C++ para controle cinemático de servos do braço robótico de bancada.
* **`firmware/esp32_satellite`:** Firmware ESP32 com microfone I2S e display TFT/OLED para satélites de escuta em outros cômodos.

---

### 5. Comparativo Arquitetural de Referência: Thor-JARVIS vs. OpenJarvis (`open-jarvis/OpenJarvis`)
* **OpenJarvis (Stanford Hazy Research):** Framework focado no empacotamento formal de agentes locais em computadores pessoais (macOS/Windows/Linux), orquestração de múltiplos backends de inferência (vLLM, SGLang, Ollama, llama.cpp), benchmarks rigorosos de energia/latência/custo (FLOPs-aware) e integração com o protocolo MCP (Model Context Protocol).
* **Thor-JARVIS (Este Projeto):** Ecossistema ciberfísico aplicado, focado na integração prática de hardware real, estúdio de manufatura 3D (Ender 3 + OctoPrint), dock móvel como sensor de visão computacional/áudio (iPhone 11 HUD) e telemetria remota imediata via Telegram e Tailscale.
