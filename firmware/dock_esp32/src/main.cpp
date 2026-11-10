/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" Touch (ESP32-S3 + ILI9488)
 * Firmware de Bancada: LovyanGFX + DMA + Rosto Expressivo + Touch XPT2046 + USB CDC
 * ==============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

// ==============================================================================
// 1. CONFIGURAÇÃO DE HARDWARE LOVYANGFX (ESP32-S3 -> ILI9488 + XPT2046)
// ==============================================================================
class LGFX_JarvisDock : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488  _panel_instance;
  lgfx::Bus_SPI        _bus_instance;
  lgfx::Light_PWM      _light_instance;
  lgfx::Touch_XPT2046  _touch_instance;

public:
  LGFX_JarvisDock() {
    // Configuração do Barramento SPI
    {
      auto cfg = _bus_instance.config();
      cfg.spi_host = SPI2_HOST;     // FSPI nativo do ESP32-S3
      cfg.spi_mode = 0;
      cfg.freq_write = 40000000;    // 40 MHz para estabilidade máxima em jumpers
      cfg.freq_read  = 16000000;
      cfg.use_lock   = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 12;            // SCK
      cfg.pin_mosi = 11;            // MOSI / SDI
      cfg.pin_miso = 13;            // MISO exclusivo do touch
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
      cfg.bus_shared   = true;
      cfg.readable     = false;     // SDO do display solto
      cfg.invert       = false;
      cfg.rgb_order    = false;     // Se as cores ficarem invertidas, altere para true
      cfg.dlen_16bit   = false;
      _panel_instance.config(cfg);
    }

    // Configuração do Backlight (PWM no pino LED)
    {
      auto cfg = _light_instance.config();
      cfg.pin_bl = 7;               // GPIO 7 para PWM de brilho
      cfg.freq   = 12000;           // 12 kHz anti-flicker
      cfg.pwm_channel = 1;
      _light_instance.config(cfg);
      _panel_instance.setLight(&_light_instance);
    }

    // Configuração do Touch XPT2046
    {
      auto cfg = _touch_instance.config();
      cfg.spi_host = SPI2_HOST;
      cfg.freq     = 2500000;       // 2.5 MHz estável para o XPT2046
      cfg.pin_sclk = 12;
      cfg.pin_mosi = 11;
      cfg.pin_miso = 13;            // T_DO
      cfg.pin_cs   = 5;             // T_CS
      cfg.pin_int  = 4;             // T_IRQ
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

// Sprites de double-buffering DMA para animação de alta performance dos olhos
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
const uint16_t COLOR_BG       = 0x0000; // Preto absoluto OLED/LCD
const uint16_t COLOR_CYAN     = 0x07FF; // Ciano vibrante Arc Reactor
const uint16_t COLOR_BLUE_GLOW= 0x03B9; // Azul profundo de brilho
const uint16_t COLOR_ORANGE   = 0xFD20; // Alerta Iron Man
const uint16_t COLOR_WHITE    = 0xFFFF; // Centro do olho

// ==============================================================================
// 3. ATUALIZAÇÃO E DESENHO DOS OLHOS VIA SPRITES PARCIAIS (DMA)
// ==============================================================================
void desenharOlhoNoSprite(LGFX_Sprite &spr, float h, float w, Mood mood, bool isLeft) {
  spr.fillScreen(COLOR_BG);

  if (h <= 4) {
    // Olho fechado / piscada rápida (linha horizontal suave)
    spr.fillRoundRect(8, (EY_MAX_H / 2) - 3, EYE_MAX_W - 16, 6, 3, COLOR_CYAN);
    return;
  }

  uint16_t eyeColor = (mood == MOOD_ALERT) ? COLOR_ORANGE : COLOR_CYAN;
  int x = (EYE_MAX_W - (int)w) / 2;
  int y = (EYE_MAX_H - (int)h) / 2;
  int r = min((int)w, (int)h) / 2;
  if (r > EYE_RADIUS) r = EYE_RADIUS;

  // Borda externa de brilho
  spr.fillRoundRect(x, y, (int)w, (int)h, r, COLOR_BLUE_GLOW);
  // Centro brilhante principal
  spr.fillRoundRect(x + 3, y + 3, (int)w - 6, (int)h - 6, max(2, r - 3), eyeColor);
  // Reflexo de luz branco no topo do olho (estilo anime / Pixar)
  spr.fillCircle(x + (int)w - 18, y + 16, 7, COLOR_WHITE);

  // Modificadores de humor
  if (mood == MOOD_HAPPY) {
    // Corta a parte inferior do olho para criar a expressão sorridente estilo EVE
    spr.fillRect(x, y + ((int)h * 0.65f), (int)w, (int)h * 0.4f, COLOR_BG);
  } else if (mood == MOOD_THINKING) {
    // Linha de pálpebra superior inclinada
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
      tgtEyeH = 2.0f; // Fechando
    } else if (elapsed < 160) {
      tgtEyeH = EYE_MAX_H; // Abrindo
    } else {
      isBlinking = false;
      lastBlinkTs = now;
      nextBlinkInterval = random(2500, 6000);
    }
  } else {
    tgtEyeH = (currentMood == MOOD_SLEEP) ? 6.0f : EYE_MAX_H;
  }

  // 2. Micro-sacadas de Olhar (Observando o ambiente)
  if (!isBlinking && (now - lastSaccadeTs > nextSaccadeInterval)) {
    lastSaccadeTs = now;
    nextSaccadeInterval = random(3000, 7000);
    int r = random(0, 5);
    if (r == 0) { tgtOffsetX = 0; tgtOffsetY = 0; }           // Centro
    else if (r == 1) { tgtOffsetX = -20; tgtOffsetY = 0; }    // Esquerda
    else if (r == 2) { tgtOffsetX = 20; tgtOffsetY = 0; }     // Direita
    else if (r == 3) { tgtOffsetX = 0; tgtOffsetY = -12; }    // Cima
    else if (r == 4) { tgtOffsetX = 12; tgtOffsetY = 10; }    // Baixo-Direita
  }

  // 3. Suavização Exponencial (Tweening)
  curEyeH += (tgtEyeH - curEyeH) * 0.35f;
  curEyeW += (tgtEyeW - curEyeW) * 0.35f;
  eyeOffsetX += (tgtOffsetX - eyeOffsetX) * 0.25f;
  eyeOffsetY += (tgtOffsetY - eyeOffsetY) * 0.25f;

  // 4. Desenho nos Sprites Parciais
  desenharOlhoNoSprite(eyeLeft, curEyeH, curEyeW, currentMood, true);
  desenharOlhoNoSprite(eyeRight, curEyeH, curEyeW, currentMood, false);

  // 5. Envio instantâneo via DMA nas posições relativas (Landscape 480x320)
  // Olho Esquerdo: centro em X=140, Olho Direito: centro em X=340
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
  lcd.print("STATUS: ONLINE // TOQUE NA TELA PARA TESTE");
}

// ==============================================================================
// 5. SETUP E LOOP PRINCIPAL
// ==============================================================================
void setup() {
  // Inicializa comunicação serial USB-C CDC
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("🤖 [JARVIS DOCK] Inicializando ESP32-S3 + ILI9488 4.0\"");
  Serial.println("🔌 Interface: LovyanGFX Hardware SPI DMA @ 40MHz");
  Serial.println("==================================================");

  // Inicializa o Display e Touch
  lcd.init();
  lcd.setRotation(1);           // 1 = Modo Paisagem (480 x 320)
  lcd.setBrightness(200);       // Brilho agradável (80%)
  lcd.fillScreen(COLOR_BG);

  // Criação dos Sprites de Olho na Memória Interna / PSRAM
  eyeLeft.setColorDepth(16);
  eyeLeft.createSprite(EYE_MAX_W, EYE_MAX_H);

  eyeRight.setColorDepth(16);
  eyeRight.createSprite(EYE_MAX_W, EYE_MAX_H);

  desenharHUD();

  Serial.println("✅ [SISTEMA PRONTO] Olhos e Touch Ativos!");
}

void loop() {
  // 1. Atualiza Animação Facial em Alta Taxa (Sprite DMA parcial)
  atualizarAnimacaoOlhos();

  // 2. Leitura do Touch XPT2046
  uint16_t touchX, touchY;
  if (lcd.getTouch(&touchX, &touchY)) {
    // Efeito visual de clique no ponto tocado
    lcd.fillCircle(touchX, touchY, 6, COLOR_WHITE);
    lcd.drawCircle(touchX, touchY, 14, COLOR_CYAN);

    // Envia evento via Serial para o Servidor Python
    Serial.printf("{\"type\":\"touch\",\"x\":%d,\"y\":%d}\n", touchX, touchY);

    // Feedback imediato no HUD inferior
    lcd.fillRect(15, 308, 300, 10, COLOR_BG);
    lcd.setCursor(15, 308);
    lcd.printf("TOUCH: X=%d Y=%d", touchX, touchY);
  }

  // 3. Processamento de Comandos Seriais do Servidor (JSON)
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      StaticJsonDocument<256> doc;
      DeserializationError err = deserializeJson(doc, linha);
      if (!err) {
        if (doc.containsKey("mood")) {
          String m = doc["mood"].as<String>();
          if (m == "happy") currentMood = MOOD_HAPPY;
          else if (m == "thinking") currentMood = MOOD_THINKING;
          else if (m == "alert") currentMood = MOOD_ALERT;
          else if (m == "sleep") currentMood = MOOD_SLEEP;
          else currentMood = MOOD_NEUTRAL;

          Serial.printf("{\"ack\":\"mood_updated\",\"mood\":\"%s\"}\n", m.c_str());
        }
      }
    }
  }

  delay(16); // ~60 FPS estáveis
}
