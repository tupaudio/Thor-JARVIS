/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" (ESP32-S3 + ILI9488)
 * Firmware de Bancada: LovyanGFX + DMA + Rosto Expressivo + USB CDC
 * (Modo de Diagnóstico Seguro para Jumpers de Bancada - Touch Desativado)
 * ==============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

// ==============================================================================
// 1. CONFIGURAÇÃO DE HARDWARE LOVYANGFX (ESP32-S3 -> ILI9488)
// ==============================================================================
class LGFX_JarvisDock : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488  _panel_instance;
  lgfx::Bus_SPI        _bus_instance;
  lgfx::Light_PWM      _light_instance;

public:
  LGFX_JarvisDock() {
    // Configuração do Barramento SPI
    {
      auto cfg = _bus_instance.config();
      cfg.spi_host = SPI2_HOST;     // FSPI nativo do ESP32-S3
      cfg.spi_mode = 0;
      cfg.freq_write = 15000000;    // 15 MHz: Estabilidade absoluta em jumpers de bancada
      cfg.freq_read  = 10000000;
      cfg.use_lock   = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 12;            // SCK
      cfg.pin_mosi = 11;            // MOSI / SDI
      cfg.pin_miso = -1;            // Sem MISO para o display
      cfg.pin_dc   = 9;             // DC / RS
      _bus_instance.config(cfg);
      _panel_instance.setBus(&_bus_instance);
    }

    // Configuração do Painel ILI9488 (480x320)
    {
      auto cfg = _panel_instance.config();
      cfg.pin_cs   = 10;            // TFT CS
      cfg.pin_rst  = 8;             // TFT RESET
      cfg.panel_width  = 320;       // Resolução nativa retrato
      cfg.panel_height = 480;
      cfg.offset_x     = 0;
      cfg.offset_y     = 0;
      cfg.bus_shared   = false;     // Barramento exclusivo do display por enquanto
      cfg.readable     = false;     // SDO solto
      cfg.invert       = false;
      cfg.rgb_order    = false;     // Padrão RGB
      cfg.dlen_16bit   = false;
      _panel_instance.config(cfg);
    }

    // Configuração do Backlight (PWM no pino LED)
    {
      auto cfg = _light_instance.config();
      cfg.pin_bl = 7;               // GPIO 7 para PWM de brilho
      cfg.freq   = 10000;           // 10 kHz
      cfg.pwm_channel = 1;
      _light_instance.config(cfg);
      _panel_instance.setLight(&_light_instance);
    }

    setPanel(&_panel_instance);
  }
};

LGFX_JarvisDock lcd;

// Sprites de double-buffering DMA para animação dos olhos
LGFX_Sprite eyeLeft(&lcd);
LGFX_Sprite eyeRight(&lcd);

// ==============================================================================
// 2. ESTADOS DAS EXPRESSÕES FACIAIS
// ==============================================================================
enum Mood {
  MOOD_NEUTRAL,
  MOOD_HAPPY,
  MOOD_LISTENING,
  MOOD_THINKING,
  MOOD_ALERT,
  MOOD_SLEEP
};

Mood currentMood = MOOD_NEUTRAL;

// Parâmetros geométricos dos olhos
const int EYE_MAX_W = 76;
const int EYE_MAX_H = 110;
const int EYE_RADIUS = 30;

float curEyeH = EYE_MAX_H;
float tgtEyeH = EYE_MAX_H;
float curEyeW = EYE_MAX_W;
float tgtEyeW = EYE_MAX_W;

int eyeOffsetX = 0;
int eyeOffsetY = 0;
int tgtOffsetX = 0;
int tgtOffsetY = 0;

unsigned long lastBlinkTs = 0;
unsigned long nextBlinkInterval = 3500;
bool isBlinking = false;
unsigned long blinkStartTs = 0;

unsigned long lastSaccadeTs = 0;
unsigned long nextSaccadeInterval = 4000;

// Paleta de Cores Cyberpunk JARVIS
const uint16_t COLOR_BG       = 0x0000; // Preto
const uint16_t COLOR_CYAN     = 0x07FF; // Ciano vibrante Arc Reactor
const uint16_t COLOR_BLUE_GLOW= 0x03B9; // Azul de brilho
const uint16_t COLOR_ORANGE   = 0xFD20; // Alerta
const uint16_t COLOR_WHITE    = 0xFFFF; // Centro do olho

// ==============================================================================
// 3. ATUALIZAÇÃO E DESENHO DOS OLHOS
// ==============================================================================
void desenharOlhoNoSprite(LGFX_Sprite &spr, float h, float w, Mood mood, bool isLeft) {
  spr.fillScreen(COLOR_BG);

  if (h <= 4) {
    // Olho fechado / piscada
    spr.fillRoundRect(8, (EYE_MAX_H / 2) - 3, EYE_MAX_W - 16, 6, 3, COLOR_CYAN);
    return;
  }

  uint16_t eyeColor = (mood == MOOD_ALERT) ? COLOR_ORANGE : COLOR_CYAN;
  int x = (EYE_MAX_W - (int)w) / 2;
  int y = (EYE_MAX_H - (int)h) / 2;
  int r = min((int)w, (int)h) / 2;
  if (r > EYE_RADIUS) r = EYE_RADIUS;

  // Borda externa de brilho
  spr.fillRoundRect(x, y, (int)w, (int)h, r, COLOR_BLUE_GLOW);
  // Centro brilhante
  spr.fillRoundRect(x + 3, y + 3, (int)w - 6, (int)h - 6, max(2, r - 3), eyeColor);
  // Reflexo de luz branco
  spr.fillCircle(x + (int)w - 18, y + 16, 7, COLOR_WHITE);

  // Modificadores de humor
  if (mood == MOOD_HAPPY) {
    spr.fillRect(x, y + ((int)h * 0.65f), (int)w, (int)h * 0.4f, COLOR_BG);
  } else if (mood == MOOD_THINKING) {
    if (isLeft) spr.fillTriangle(x, y, x + (int)w, y, x + (int)w, y + 25, COLOR_BG);
    else spr.fillTriangle(x, y, x + (int)w, y, x, y + 25, COLOR_BG);
  }
}

void atualizarAnimacaoOlhos() {
  unsigned long now = millis();

  // 1. Lógica Autônoma de Piscar
  if (!isBlinking && (now - lastBlinkTs > nextBlinkInterval)) {
    isBlinking = true;
    blinkStartTs = now;
  }

  if (isBlinking) {
    unsigned long elapsed = now - blinkStartTs;
    if (elapsed < 80) {
      tgtEyeH = 2.0f;
    } else if (elapsed < 160) {
      tgtEyeH = EYE_MAX_H;
    } else {
      isBlinking = false;
      lastBlinkTs = now;
      nextBlinkInterval = random(2500, 6000);
    }
  } else {
    tgtEyeH = (currentMood == MOOD_SLEEP) ? 6.0f : EYE_MAX_H;
  }

  // 2. Micro-sacadas de Olhar
  if (!isBlinking && (now - lastSaccadeTs > nextSaccadeInterval)) {
    lastSaccadeTs = now;
    nextSaccadeInterval = random(3000, 7000);
    int r = random(0, 5);
    if (r == 0) { tgtOffsetX = 0; tgtOffsetY = 0; }
    else if (r == 1) { tgtOffsetX = -20; tgtOffsetY = 0; }
    else if (r == 2) { tgtOffsetX = 20; tgtOffsetY = 0; }
    else if (r == 3) { tgtOffsetX = 0; tgtOffsetY = -12; }
    else if (r == 4) { tgtOffsetX = 12; tgtOffsetY = 10; }
  }

  // 3. Suavização Exponencial
  curEyeH += (tgtEyeH - curEyeH) * 0.35f;
  curEyeW += (tgtEyeW - curEyeW) * 0.35f;
  eyeOffsetX += (tgtOffsetX - eyeOffsetX) * 0.25f;
  eyeOffsetY += (tgtOffsetY - eyeOffsetY) * 0.25f;

  // 4. Desenho nos Sprites
  desenharOlhoNoSprite(eyeLeft, curEyeH, curEyeW, currentMood, true);
  desenharOlhoNoSprite(eyeRight, curEyeH, curEyeW, currentMood, false);

  // 5. Envio instantâneo via DMA (Landscape 480x320)
  int posX_L = 140 - (EYE_MAX_W / 2) + eyeOffsetX;
  int posY_L = 160 - (EYE_MAX_H / 2) + eyeOffsetY;
  int posX_R = 340 - (EYE_MAX_W / 2) + eyeOffsetX;
  int posY_R = 160 - (EYE_MAX_H / 2) + eyeOffsetY;

  eyeLeft.pushSprite(posX_L, posY_L);
  eyeRight.pushSprite(posX_R, posY_R);
}

// ==============================================================================
// 4. BARRA DE STATUS / HUD SUPERIOR
// ==============================================================================
void desenharHUD() {
  lcd.setFont(&fonts::Font0);
  lcd.setTextColor(COLOR_CYAN, COLOR_BG);
  lcd.setCursor(15, 10);
  lcd.print("J.A.R.V.I.S. DOCK 4.0 // ESP32-S3 CORE");

  lcd.setCursor(370, 10);
  lcd.printf("USB 115.2k");

  lcd.drawFastHLine(10, 24, 460, COLOR_BLUE_GLOW);
  lcd.drawFastHLine(10, 305, 460, COLOR_BLUE_GLOW);

  lcd.setCursor(15, 308);
  lcd.print("STATUS: ONLINE // SISTEMA ATIVO");
}

// ==============================================================================
// 5. SETUP E LOOP PRINCIPAL
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("🤖 [JARVIS DOCK] Inicializando ESP32-S3 + ILI9488 4.0\"");
  Serial.println("🔌 Interface: LovyanGFX Hardware SPI @ 15MHz");
  Serial.println("📌 Pinagem: CS=10, RST=8, DC=9, MOSI=11, SCK=12, BL=7");
  Serial.println("==================================================");

  // 1. Pulso físico de Reset no pino 8
  Serial.println("1. Disparando pulso de Hardware Reset no pino 8...");
  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(20);
  digitalWrite(8, LOW);  delay(60);
  digitalWrite(8, HIGH); delay(150);
  Serial.println("   -> Reset concluído.");

  // 2. Inicialização do display
  Serial.println("2. Inicializando controlador ILI9488 com lcd.init()...");
  lcd.init();
  lcd.setRotation(1);           // 1 = Modo Paisagem (480 x 320)
  lcd.setBrightness(220);       // Backlight em nível alto
  Serial.println("   -> Display inicializado!");

  // 3. Teste visual rápido de cores primárias (verificação imediata do painel)
  Serial.println("3. Executando flash de teste RGB...");
  lcd.fillScreen(0xF800); delay(400); // Vermelho
  lcd.fillScreen(0x07E0); delay(400); // Verde
  lcd.fillScreen(0x001F); delay(400); // Azul
  lcd.fillScreen(COLOR_BG);           // Preto

  // 4. Criação dos Sprites de Olho
  Serial.println("4. Criando sprites de olho para renderizacao...");
  eyeLeft.setColorDepth(16);
  eyeLeft.createSprite(EYE_MAX_W, EYE_MAX_H);

  eyeRight.setColorDepth(16);
  eyeRight.createSprite(EYE_MAX_W, EYE_MAX_H);

  desenharHUD();

  Serial.println("✅ [SISTEMA PRONTO] Olhos e Interface Ativos no Loop!");
}

unsigned long lastHeartbeat = 0;

void loop() {
  // 1. Atualiza Animação Facial
  atualizarAnimacaoOlhos();

  // 2. Batimento cardíaco no Serial a cada 3 segundos
  unsigned long now = millis();
  if (now - lastHeartbeat > 3000) {
    lastHeartbeat = now;
    Serial.printf("⏱️ [HEARTBEAT] Dock ativo... millis=%lu\n", now);
  }

  // 3. Processamento de Comandos Seriais do Servidor (JSON v7)
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, linha);
      if (!err) {
        if (doc["mood"].is<const char*>()) {
          const char* m = doc["mood"];
          if (strcmp(m, "happy") == 0) currentMood = MOOD_HAPPY;
          else if (strcmp(m, "thinking") == 0) currentMood = MOOD_THINKING;
          else if (strcmp(m, "alert") == 0) currentMood = MOOD_ALERT;
          else if (strcmp(m, "sleep") == 0) currentMood = MOOD_SLEEP;
          else currentMood = MOOD_NEUTRAL;

          Serial.printf("{\"ack\":\"mood_updated\",\"mood\":\"%s\"}\n", m);
        }
      }
    }
  }

  delay(16); // ~60 FPS
}
