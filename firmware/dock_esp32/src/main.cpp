/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" (ESP32-S3 + ILI9488 + Touch)
 * Firmware de Bancada: LovyanGFX + DMA + Rosto Expressivo + Touch XPT2046
 * ==============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#define LED_BUILTIN_PIN 21

// ==============================================================================
// 1. CONFIGURAÇÃO DE HARDWARE LOVYANGFX (DISPLAY + TOUCH NO MESMO SPI)
// ==============================================================================
class LGFX_JarvisDock : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488  _panel_instance;
  lgfx::Bus_SPI        _bus_instance;
  lgfx::Touch_XPT2046  _touch_instance;

public:
  LGFX_JarvisDock() {
    // Barramento SPI Compartilhado
    {
      auto cfg = _bus_instance.config();
      cfg.spi_host = SPI2_HOST;     // FSPI nativo
      cfg.spi_mode = 0;
      cfg.freq_write = 15000000;    // 15 MHz estável
      cfg.freq_read  = 10000000;
      cfg.use_lock   = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 12;            // SDK e TCK
      cfg.pin_mosi = 11;            // SDI e TDI
      cfg.pin_miso = 13;            // TDO (exclusivo do touch, SDO do LCD fica solto)
      cfg.pin_dc   = 9;             // C/D (Command / Data)
      _bus_instance.config(cfg);
      _panel_instance.setBus(&_bus_instance);
    }

    // Painel ILI9488 (480x320)
    {
      auto cfg = _panel_instance.config();
      cfg.pin_cs   = 10;            // CD (Chip Select LCD)
      cfg.pin_rst  = 8;             // RST (Reset)
      cfg.panel_width  = 320;
      cfg.panel_height = 480;
      cfg.offset_x     = 0;
      cfg.offset_y     = 0;
      cfg.bus_shared   = true;      // Barramento compartilhado com o touch
      cfg.readable     = false;
      cfg.invert       = false;
      cfg.rgb_order    = false;
      cfg.dlen_16bit   = false;
      _panel_instance.config(cfg);
    }

    // Controlador de Touch XPT2046
    {
      auto cfg = _touch_instance.config();
      cfg.spi_host = SPI2_HOST;
      cfg.freq     = 2500000;       // 2.5 MHz para XPT2046
      cfg.pin_sclk = 12;            // TCK
      cfg.pin_mosi = 11;            // TDI
      cfg.pin_miso = 13;            // TDO
      cfg.pin_cs   = 5;             // TCS
      cfg.pin_int  = 4;             // PEN
      cfg.bus_shared = true;
      cfg.x_min    = 300;
      cfg.x_max    = 3900;
      cfg.y_min    = 300;
      cfg.y_max    = 3900;
      _touch_instance.config(cfg);
      _panel_instance.setTouch(&_touch_instance);
    }

    setPanel(&_panel_instance);
  }
};

LGFX_JarvisDock lcd;

// Sprites de double-buffering DMA para os olhos
LGFX_Sprite eyeLeft(&lcd);
LGFX_Sprite eyeRight(&lcd);

enum Mood {
  MOOD_NEUTRAL,
  MOOD_HAPPY,
  MOOD_THINKING,
  MOOD_ALERT,
  MOOD_SLEEP
};

Mood currentMood = MOOD_NEUTRAL;

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

const uint16_t COLOR_BG       = 0x0000;
const uint16_t COLOR_CYAN     = 0x07FF;
const uint16_t COLOR_BLUE_GLOW= 0x03B9;
const uint16_t COLOR_ORANGE   = 0xFD20;
const uint16_t COLOR_WHITE    = 0xFFFF;

void desenharOlhoNoSprite(LGFX_Sprite &spr, float h, float w, Mood mood, bool isLeft) {
  spr.fillScreen(COLOR_BG);

  if (h <= 4) {
    spr.fillRoundRect(8, (EYE_MAX_H / 2) - 3, EYE_MAX_W - 16, 6, 3, COLOR_CYAN);
    return;
  }

  uint16_t eyeColor = (mood == MOOD_ALERT) ? COLOR_ORANGE : COLOR_CYAN;
  int x = (EYE_MAX_W - (int)w) / 2;
  int y = (EYE_MAX_H - (int)h) / 2;
  int r = min((int)w, (int)h) / 2;
  if (r > EYE_RADIUS) r = EYE_RADIUS;

  spr.fillRoundRect(x, y, (int)w, (int)h, r, COLOR_BLUE_GLOW);
  spr.fillRoundRect(x + 3, y + 3, (int)w - 6, (int)h - 6, max(2, r - 3), eyeColor);
  spr.fillCircle(x + (int)w - 18, y + 16, 7, COLOR_WHITE);

  if (mood == MOOD_HAPPY) {
    spr.fillRect(x, y + ((int)h * 0.65f), (int)w, (int)h * 0.4f, COLOR_BG);
  } else if (mood == MOOD_THINKING) {
    if (isLeft) spr.fillTriangle(x, y, x + (int)w, y, x + (int)w, y + 25, COLOR_BG);
    else spr.fillTriangle(x, y, x + (int)w, y, x, y + 25, COLOR_BG);
  }
}

void atualizarAnimacaoOlhos() {
  unsigned long now = millis();

  if (!isBlinking && (now - lastBlinkTs > nextBlinkInterval)) {
    isBlinking = true;
    blinkStartTs = now;
  }

  if (isBlinking) {
    unsigned long elapsed = now - blinkStartTs;
    if (elapsed < 80) tgtEyeH = 2.0f;
    else if (elapsed < 160) tgtEyeH = EYE_MAX_H;
    else {
      isBlinking = false;
      lastBlinkTs = now;
      nextBlinkInterval = random(2500, 6000);
    }
  } else {
    tgtEyeH = (currentMood == MOOD_SLEEP) ? 6.0f : EYE_MAX_H;
  }

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

  curEyeH += (tgtEyeH - curEyeH) * 0.35f;
  curEyeW += (tgtEyeW - curEyeW) * 0.35f;
  eyeOffsetX += (tgtOffsetX - eyeOffsetX) * 0.25f;
  eyeOffsetY += (tgtOffsetY - eyeOffsetY) * 0.25f;

  desenharOlhoNoSprite(eyeLeft, curEyeH, curEyeW, currentMood, true);
  desenharOlhoNoSprite(eyeRight, curEyeH, curEyeW, currentMood, false);

  int posX_L = 140 - (EYE_MAX_W / 2) + eyeOffsetX;
  int posY_L = 160 - (EYE_MAX_H / 2) + eyeOffsetY;
  int posX_R = 340 - (EYE_MAX_W / 2) + eyeOffsetX;
  int posY_R = 160 - (EYE_MAX_H / 2) + eyeOffsetY;

  eyeLeft.pushSprite(posX_L, posY_L);
  eyeRight.pushSprite(posX_R, posY_R);
}

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
  lcd.print("TOUCH: TOQUE NA TELA // SISTEMA ATIVO");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN_PIN, OUTPUT);
  digitalWrite(LED_BUILTIN_PIN, HIGH);

  unsigned long t0 = millis();
  while (!Serial && (millis() - t0 < 2500)) {
    digitalWrite(LED_BUILTIN_PIN, !digitalRead(LED_BUILTIN_PIN));
    delay(100);
  }

  Serial.println("\n\n==================================================");
  Serial.println("🤖 [JARVIS DOCK] ESP32-S3 + ILI9488 + TOUCH XPT2046");
  Serial.println("🔌 Pinagem: CD=10, RST=8, C/D=9, SDI=11, SDK=12");
  Serial.println("👆 Touch: TCK=12, TDI=11, TDO=13, TCS=5, PEN=4");
  Serial.println("==================================================");

  // 1. Reset elétrico físico no pino RST (GPIO 8)
  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(50);
  digitalWrite(8, LOW);  delay(100);
  digitalWrite(8, HIGH); delay(200);

  // 2. Chip Selects em HIGH
  pinMode(10, OUTPUT); digitalWrite(10, HIGH);
  pinMode(5, OUTPUT);  digitalWrite(5, HIGH);

  // 3. Inicialização LovyanGFX
  Serial.println("2. Inicializando Display e Touch...");
  lcd.init();
  lcd.setRotation(1); // Paisagem 480x320
  lcd.fillScreen(COLOR_BG);

  // 4. Criação dos Sprites
  eyeLeft.setColorDepth(16);
  eyeLeft.createSprite(EYE_MAX_W, EYE_MAX_H);

  eyeRight.setColorDepth(16);
  eyeRight.createSprite(EYE_MAX_W, EYE_MAX_H);

  desenharHUD();
  Serial.println("✅ [SISTEMA PRONTO] Olhos e Touch Ativos no Loop!");
}

unsigned long lastLog = 0;
bool ledState = false;

void loop() {
  // 1. Renderiza olhos expressivos
  atualizarAnimacaoOlhos();

  // 2. Leitura do Touch XPT2046
  uint16_t touchX, touchY;
  if (lcd.getTouch(&touchX, &touchY)) {
    // Desenha cursor de feedback onde tocou
    lcd.fillCircle(touchX, touchY, 6, COLOR_WHITE);
    lcd.drawCircle(touchX, touchY, 14, COLOR_CYAN);

    // Atualiza barra inferior
    lcd.fillRect(15, 308, 300, 10, COLOR_BG);
    lcd.setCursor(15, 308);
    lcd.printf("TOUCH: X=%d Y=%d", touchX, touchY);

    // Envia evento via serial para o servidor
    Serial.printf("{\"type\":\"touch\",\"x\":%d,\"y\":%d}\n", touchX, touchY);
  }

  // 3. Heartbeat e Comandos Seriais
  unsigned long now = millis();
  if (now - lastLog > 3000) {
    lastLog = now;
    ledState = !ledState;
    digitalWrite(LED_BUILTIN_PIN, ledState);
  }

  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, linha);
      if (!err && doc["mood"].is<const char*>()) {
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

  delay(16);
}
