/*
 * ==============================================================================
 * J.A.R.V.I.S. - Firmware Oficial: Satélite de Mesa & Gateway Wi-Fi
 * Placa: ESP32-S3 DevKit (Dual-Core 240MHz, Wi-Fi 2.4GHz)
 * Componentes:
 * 1. Tela TFT Touch 4.0" ILI9488 SPI (480x320) com Touch XPT2046
 * 2. Amplificador de Áudio I2S Classe D MAX98357A (3W) + Alto-falante 4Ω 3W
 * 3. Ponte Serial UART Bidirecional para o Arduino UNO (Braço Robótico)
 * 4. Servidor Web REST API / WebSocket para integração sem fio com o PC
 * ==============================================================================
 *
 * ESQUEMA DE LIGAÇÃO NA PROTOBOARD (ESP32-S3):
 *
 * [ DISPLAY TFT 4.0" SPI ILI9488 ]:
 * - VCC    -> 3.3V (ou 5V se o verso tiver regulador LDO de 3.3V)
 * - GND    -> GND
 * - CS     -> GPIO 10
 * - RESET  -> GPIO 5
 * - DC/RS  -> GPIO 4
 * - MOSI   -> GPIO 11 (SPI MOSI)
 * - SCK    -> GPIO 12 (SPI CLK)
 * - LED/BL -> 3.3V (ou GPIO 6 para controle de brilho PWM)
 * - MISO   -> GPIO 13 (SPI MISO)
 * - T_CS   -> GPIO 9  (Touch Chip Select XPT2046)
 * - T_CLK  -> GPIO 12 (Compartilha SCK com display)
 * - T_DIN  -> GPIO 11 (Compartilha MOSI com display)
 * - T_DO   -> GPIO 13 (Compartilha MISO com display)
 *
 * [ AMPLIFICADOR I2S MAX98357A + ALTO-FALANTE 4Ω 3W ]:
 * - Vin    -> 5V (Para potência total de 3W no alto-falante)
 * - GND    -> GND
 * - BCLK   -> GPIO 15 (Bit Clock)
 * - LRC/WS -> GPIO 16 (Word Select / Left-Right Clock)
 * - DIN    -> GPIO 17 (Data Input)
 * - GAIN   -> Desconectado (Ganho padrão de 12dB)
 * - SD_MODE-> Desconectado (Mix estéreo padrão)
 * - Bornes +/- -> Conectados ao Alto-Falante 4Ω 3W
 *
 * [ PONTE SERIAL COM O ARDUINO UNO ]:
 * - ESP32-S3 GND -> Arduino UNO GND (MUITO IMPORTANTE: GND Compartilhado!)
 * - ESP32-S3 TX (GPIO 18) -> Arduino UNO RX (Pino Digital 0)
 * - ESP32-S3 RX (GPIO 8)  <- Divisor de Tensão (5V -> 3.3V) <- Arduino UNO TX (Pino Digital 1)
 *
 * ATENÇÃO DE NÍVEL LÓGICO:
 * O Arduino opera em 5V e o ESP32-S3 opera em 3.3V.
 * O pino TX do Arduino envia 5V. Use 2 resistores (1kΩ e 2kΩ) como divisor de tensão
 * no fio que vai do TX do Arduino para o RX do ESP32-S3 para proteger o ESP32!
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <SPI.h>
#include <driver/i2s.h>
#include <ArduinoJson.h>

// Bibliotecas gráficas recomendadas: Adafruit_GFX + Adafruit_ILI9488 ou LovyanGFX
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9488.h>

// ==============================================================================
// 1. CONFIGURAÇÕES DE REDE WI-FI
// ==============================================================================
const char* WIFI_SSID     = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";

WebServer server(80);

// ==============================================================================
// 2. PINAGEM DO HARDWARE
// ==============================================================================
#define TFT_CS    10
#define TFT_DC     4
#define TFT_RST    5
#define TFT_MOSI  11
#define TFT_SCLK  12
#define TFT_MISO  13

// Alto-falante / Saída de Áudio (MAX98357A em I2S_NUM_0)
#define I2S_SPK_BCLK  15
#define I2S_SPK_LRC   16
#define I2S_SPK_DOUT  17

// Microfone Digital Omnidirecional (INMP441 em I2S_NUM_1)
#define I2S_MIC_BCLK   1  // SCK no INMP441
#define I2S_MIC_WS     2  // WS no INMP441
#define I2S_MIC_SD     3  // SD no INMP441

#define ARDUINO_UART_TX 18
#define ARDUINO_UART_RX  8

// Objeto do Display TFT
Adafruit_ILI9488 tft = Adafruit_ILI9488(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST, TFT_MISO);

// Hardware Serial 1 para comunicação direta com o Arduino UNO
HardwareSerial SerialArduino(1);

// Estado atual do sistema para exibição no HUD
String hudTitulo    = "SISTEMAS ONLINE";
String hudSubtitulo = "Aguardando comandos...";
String hudIcone     = "J.A.R.V.I.S.";
String ultimoStatusArduino = "PRONTO";
unsigned long ultimoPing = 0;

// ==============================================================================
// 3. INICIALIZAÇÃO DO ÁUDIO I2S (MAX98357A Alto-Falante & INMP441 Microfone)
// ==============================================================================
void setupI2SAudio() {
  // Configuração do Alto-Falante (I2S_NUM_0 - TX Master)
  i2s_config_t spk_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = 22050,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = true
  };

  i2s_pin_config_t spk_pins = {
    .bck_io_num = I2S_SPK_BCLK,
    .ws_io_num = I2S_SPK_LRC,
    .data_out_num = I2S_SPK_DOUT,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  i2s_driver_install(I2S_NUM_0, &spk_config, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &spk_pins);
  i2s_zero_dma_buffer(I2S_NUM_0);
  Serial.println("🔊 [I2S_NUM_0] Driver de alto-falante MAX98357A inicializado.");
}

void setupI2SMicrophone() {
  // Configuração do Microfone Digital MEMS (I2S_NUM_1 - RX Master)
  i2s_config_t mic_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, // INMP441 transmite 24-bit em slots de 32-bit
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 512,
    .use_apll = false
  };

  i2s_pin_config_t mic_pins = {
    .bck_io_num = I2S_MIC_BCLK,
    .ws_io_num = I2S_MIC_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_MIC_SD
  };

  i2s_driver_install(I2S_NUM_1, &mic_config, 0, NULL);
  i2s_set_pin(I2S_NUM_1, &mic_pins);
  i2s_zero_dma_buffer(I2S_NUM_1);
  Serial.println("🎙️ [I2S_NUM_1] Driver de microfone INMP441 inicializado com sucesso (16kHz).");
}

// Emite um bipe sintetizado de ativação (Stark Chime)
void tocarTomNotificacao(int frequencia = 880, int duracaoMs = 150) {
  int taxaAmostragem = 22050;
  int numAmostras = (taxaAmostragem * duracaoMs) / 1000;
  int16_t amostras[256];
  
  float fase = 0.0;
  float incrementoFase = 2.0 * PI * frequencia / taxaAmostragem;
  
  int totalGravado = 0;
  while (totalGravado < numAmostras) {
    int lote = min(128, numAmostras - totalGravado);
    for (int i = 0; i < lote; i++) {
      int16_t val = (int16_t)(sin(fase) * 12000.0);
      amostras[i * 2]     = val; // Canal Esquerdo
      amostras[i * 2 + 1] = val; // Canal Direito
      fase += incrementoFase;
      if (fase >= 2.0 * PI) fase -= 2.0 * PI;
    }
    size_t bytesEscritos;
    i2s_write(I2S_NUM_0, amostras, lote * 4, &bytesEscritos, portMAX_DELAY);
    totalGravado += lote;
  }
}

// Chime duplo estilo Iron Man ao iniciar
void tocarChimeInicial() {
  tocarTomNotificacao(659, 100); // E5
  delay(30);
  tocarTomNotificacao(880, 200); // A5
}

// ==============================================================================
// 4. INTERFACE GRÁFICA HUD (DISPLAY 4.0" 480x320)
// ==============================================================================
// Cores inspiradas no HUD do Homem de Ferro / Stark Tech
#define STARK_CYAN    0x07FF
#define STARK_BLUE    0x001F
#define STARK_DARK    0x0008
#define STARK_AMBER   0xFD00
#define STARK_RED     0xF800
#define STARK_WHITE   0xFFFF

void desenharLayoutHUD() {
  tft.fillScreen(STARK_DARK);

  // Moldura externa elegante
  tft.drawRect(4, 4, 472, 312, STARK_CYAN);
  tft.drawRect(6, 6, 468, 310, 0x03E0);

  // Barra de Status Superior (Header)
  tft.fillRect(8, 8, 464, 38, 0x0110);
  tft.drawFastHLine(8, 46, 464, STARK_CYAN);

  tft.setTextColor(STARK_CYAN);
  tft.setTextSize(2);
  tft.setCursor(18, 18);
  tft.print("J.A.R.V.I.S. // DESK SATELLITE");

  // Status de Rede no canto superior direito
  tft.setTextSize(1);
  tft.setTextColor(STARK_WHITE);
  tft.setCursor(330, 22);
  tft.print("IP: ");
  tft.print(WiFi.localIP().toString());

  // Painel de Dados Central
  tft.drawRoundRect(20, 60, 440, 160, 8, STARK_CYAN);
  tft.fillRoundRect(22, 62, 436, 156, 8, 0x0084);

  // Rodapé com Botões de Toque Virtuais
  desenharBotoesVirtuais();
}

void atualizarCardHUD(String titulo, String subtitulo, String icone = "INFO") {
  hudTitulo = titulo;
  hudSubtitulo = subtitulo;
  hudIcone = icone;

  // Limpa apenas o interior do card central para atualização suave sem piscar a tela inteira
  tft.fillRoundRect(24, 64, 432, 152, 6, 0x0084);

  // Ícone / Categoria
  tft.setTextColor(STARK_AMBER);
  tft.setTextSize(2);
  tft.setCursor(40, 80);
  tft.print("[ ");
  tft.print(hudIcone);
  tft.print(" ]");

  // Título Principal
  tft.setTextColor(STARK_WHITE);
  tft.setTextSize(2);
  tft.setCursor(40, 115);
  tft.print(hudTitulo.substring(0, 32));

  // Subtítulo / Descrição
  tft.setTextColor(STARK_CYAN);
  tft.setTextSize(2);
  tft.setCursor(40, 155);
  tft.print(hudSubtitulo.substring(0, 35));
}

void desenharBotoesVirtuais() {
  // Botão 1: ACENO
  tft.drawRoundRect(20, 240, 100, 60, 6, STARK_CYAN);
  tft.fillRoundRect(22, 242, 96, 56, 6, 0x0110);
  tft.setTextColor(STARK_CYAN);
  tft.setTextSize(2);
  tft.setCursor(35, 260);
  tft.print("ACENO");

  // Botão 2: APONTAR
  tft.drawRoundRect(130, 240, 105, 60, 6, STARK_CYAN);
  tft.fillRoundRect(132, 242, 101, 56, 6, 0x0110);
  tft.setCursor(140, 260);
  tft.print("APONTAR");

  // Botão 3: REPOUSO
  tft.drawRoundRect(245, 240, 105, 60, 6, STARK_CYAN);
  tft.fillRoundRect(247, 242, 101, 56, 6, 0x0110);
  tft.setCursor(252, 260);
  tft.print("REPOUSO");

  // Botão 4: SENTINELA
  tft.drawRoundRect(360, 240, 100, 60, 6, STARK_RED);
  tft.fillRoundRect(362, 242, 96, 56, 6, 0x2000);
  tft.setTextColor(STARK_RED);
  tft.setCursor(372, 260);
  tft.print("SENTIN.");
}

// ==============================================================================
// 5. PONTE SERIAL UART COM O ARDUINO UNO
// ==============================================================================
String enviarComandoArduino(String cmd) {
  cmd.trim();
  Serial.printf("➡️ [GATEWAY -> ARDUINO]: %s\n", cmd.c_str());
  
  // Limpa buffer anterior
  while (SerialArduino.available()) {
    SerialArduino.read();
  }

  SerialArduino.println(cmd);

  // Aguarda resposta ACK do Arduino por até 3.5 segundos
  unsigned long limite = millis() + 3500;
  String resposta = "";

  while (millis() < limite) {
    if (SerialArduino.available()) {
      resposta = SerialArduino.readStringUntil('\n');
      resposta.trim();
      if (resposta.length() > 0) {
        Serial.printf("⬅️ [ARDUINO -> GATEWAY]: %s\n", resposta.c_str());
        ultimoStatusArduino = resposta;
        return resposta;
      }
    }
    delay(10);
  }
  return "TIMEOUT_NO_ACK";
}

// ==============================================================================
// 6. SERVIÇOS WEB E REST API (COMUNICAÇÃO COM O PC PYTHON)
// ==============================================================================
void setupRotasWebServer() {
  // Rota de Boas-Vindas e Status Geral
  server.on("/", HTTP_GET, []() {
    StaticJsonDocument<256> doc;
    doc["satellite"] = "JARVIS_ESP32_S3";
    doc["status"] = "online";
    doc["ip"] = WiFi.localIP().toString();
    doc["uptime_sec"] = millis() / 1000;
    doc["arduino_status"] = ultimoStatusArduino;
    doc["free_heap"] = ESP.getFreeHeap();

    String resposta;
    serializeJson(doc, resposta);
    server.send(200, "application/json", resposta);
  });

  // Rota para Enviar Comandos ao Braço Robótico (Arduino)
  // Ex: POST /api/arm com JSON {"cmd": "CMD:WAVE"} ou texto puro "CMD:WAVE"
  server.on("/api/arm", HTTP_POST, []() {
    String corpo = server.arg("plain");
    String cmd = "";

    if (corpo.indexOf("{") >= 0) {
      StaticJsonDocument<256> doc;
      deserializeJson(doc, corpo);
      cmd = doc["cmd"].as<String>();
    } else {
      cmd = corpo;
    }

    if (cmd.length() == 0) {
      server.send(400, "application/json", "{\"erro\": \"Comando ausente\"}");
      return;
    }

    tocarTomNotificacao(980, 60); // Feedback sonoro de comando recebido
    String ack = enviarComandoArduino(cmd);

    StaticJsonDocument<256> resp;
    resp["status"] = "success";
    resp["command"] = cmd;
    resp["arduino_ack"] = ack;

    String jsonStr;
    serializeJson(resp, jsonStr);
    server.send(200, "application/json", jsonStr);
  });

  // Rota para Atualizar a Tela TFT 4.0" (HUD Card)
  // Ex: POST /api/display com {"title": "Spotify", "status": "Tocando Queen", "icon": "MUSICA"}
  server.on("/api/display", HTTP_POST, []() {
    String corpo = server.arg("plain");
    StaticJsonDocument<512> doc;
    DeserializationError erro = deserializeJson(doc, corpo);

    if (erro) {
      server.send(400, "application/json", "{\"erro\": \"JSON invalido\"}");
      return;
    }

    String titulo    = doc["title"].as<String>();
    String subtitulo = doc["status"].as<String>();
    String icone     = doc.containsKey("icon") ? doc["icon"].as<String>() : "INFO";

    atualizarCardHUD(titulo, subtitulo, icone);
    tocarTomNotificacao(750, 40);

    server.send(200, "application/json", "{\"status\": \"display_updated\"}");
  });

  // Rota para Emitir Notificação Sonora no Alto-falante
  // Ex: POST /api/chime com {"freq": 880, "ms": 150}
  server.on("/api/chime", HTTP_POST, []() {
    String corpo = server.arg("plain");
    int freq = 880;
    int ms = 150;
    if (corpo.length() > 0) {
      StaticJsonDocument<128> doc;
      deserializeJson(doc, corpo);
      if (doc.containsKey("freq")) freq = doc["freq"].as<int>();
      if (doc.containsKey("ms")) ms = doc["ms"].as<int>();
    }

    tocarTomNotificacao(freq, ms);
    server.send(200, "application/json", "{\"status\": \"chime_played\"}");
  });

  server.begin();
  Serial.println("🌐 [HTTP] Servidor Web REST iniciado na porta 80.");
}

// ==============================================================================
// 7. SETUP GERAL
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n🚀 [JARVIS SATELLITE] Inicializando ESP32-S3...");

  // Inicializa UART para o Arduino UNO
  SerialArduino.begin(115200, SERIAL_8N1, ARDUINO_UART_RX, ARDUINO_UART_TX);
  Serial.println("🔌 [UART] Conexão com Arduino configurada em 115200 baud.");

  // Inicializa Display TFT 4.0"
  tft.begin();
  tft.setRotation(1); // Modo Paisagem (Landscape: 480x320)
  tft.fillScreen(STARK_DARK);
  tft.setTextColor(STARK_CYAN);
  tft.setTextSize(2);
  tft.setCursor(30, 50);
  tft.println("INICIALIZANDO J.A.R.V.I.S...");
  tft.setTextSize(1);
  tft.setTextColor(STARK_WHITE);
  tft.setCursor(30, 90);
  tft.println("Conectando a rede Wi-Fi...");

  // Inicializa Áudio I2S (Saída no alto-falante e Entrada no microfone)
  setupI2SAudio();
  setupI2SMicrophone();

  // Conexão Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 25) {
    delay(500);
    Serial.print(".");
    tft.print(".");
    tentativas++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ [WI-FI] Conectado com sucesso!");
    Serial.print("📡 Endereço IP: ");
    Serial.println(WiFi.localIP());

    // Desenha o HUD definitivo na tela
    desenharLayoutHUD();
    atualizarCardHUD("SISTEMAS ONLINE", "Ponte Wi-Fi e audio ativos", "STATUS");

    // Chime sonoro de inicialização bem-sucedida
    tocarChimeInicial();

    // Notifica o Arduino que o satélite está pronto
    enviarComandoArduino("CMD:READY");
  } else {
    Serial.println("\n⚠️ [WI-FI] Falha ao conectar. Operando em modo offline.");
    tft.fillScreen(STARK_RED);
    tft.setCursor(30, 50);
    tft.setTextColor(STARK_WHITE);
    tft.setTextSize(2);
    tft.println("ERRO WI-FI: VERIFIQUE O SSID/SENHA");
  }

  // Inicializa o servidor Web
  setupRotasWebServer();
}

// ==============================================================================
// 8. LOOP PRINCIPAL
// ==============================================================================
void loop() {
  server.handleClient();

  // Escuta dados espontâneos vindos do Arduino via UART (ex: ACK ou status do braço)
  if (SerialArduino.available()) {
    String msg = SerialArduino.readStringUntil('\n');
    msg.trim();
    if (msg.length() > 0) {
      Serial.printf("📢 [ARDUINO EVENTO]: %s\n", msg.c_str());
      ultimoStatusArduino = msg;
    }
  }

  // Heartbeat a cada 10 segundos
  if (millis() - ultimoPing > 10000) {
    ultimoPing = millis();
  }
}
