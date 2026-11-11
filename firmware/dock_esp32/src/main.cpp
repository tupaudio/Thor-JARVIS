/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" (ESP32-S3 + ILI9488 Touch)
 * Rosto Social Robótico Completo (Desenho Direto + Sprites Leves dos Olhos)
 * ==============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#define LED_BUILTIN_PIN 21

// ==============================================================================
// 1. CONFIGURAÇÃO DE HARDWARE LOVYANGFX (DISPLAY SPI2 + TOUCH SPI3)
// ==============================================================================
class LGFX_JarvisDock : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488  _panel_instance;
  lgfx::Bus_SPI        _bus_display;
  lgfx::Touch_XPT2046  _touch_instance;

public:
  LGFX_JarvisDock() {
    // Barramento Display (SPI2)
    {
      auto cfg = _bus_display.config();
      cfg.spi_host = SPI2_HOST;
      cfg.spi_mode = 0;
      cfg.freq_write = 15000000;
      cfg.freq_read  = 10000000;
      cfg.use_lock   = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 12;            // SDK
      cfg.pin_mosi = 11;            // SDI
      cfg.pin_miso = -1;
      cfg.pin_dc   = 9;             // C/D
      _bus_display.config(cfg);
      _panel_instance.setBus(&_bus_display);
    }

    // Painel 480x320
    {
      auto cfg = _panel_instance.config();
      cfg.pin_cs   = 10;            // CD
      cfg.pin_rst  = 8;             // RST
      cfg.panel_width  = 320;
      cfg.panel_height = 480;
      cfg.bus_shared   = false;
      cfg.readable     = false;
      cfg.invert       = false;
      cfg.rgb_order    = false;
      cfg.dlen_16bit   = false;
      _panel_instance.config(cfg);
    }

    // Barramento Touch (SPI3 independente)
    {
      auto cfg = _touch_instance.config();
      cfg.spi_host = SPI3_HOST;
      cfg.freq     = 2500000;
      cfg.pin_sclk = 6;             // TCK
      cfg.pin_mosi = 7;             // TDI
      cfg.pin_miso = 13;            // TDO
      cfg.pin_cs   = 5;             // TCS
      cfg.pin_int  = 4;             // PEN
      cfg.bus_shared = false;
      cfg.x_min    = 3900;          // Eixo X invertido
      cfg.x_max    = 300;
      cfg.y_min    = 300;
      cfg.y_max    = 3900;
      _touch_instance.config(cfg);
      _panel_instance.setTouch(&_touch_instance);
    }

    setPanel(&_panel_instance);
  }
};

LGFX_JarvisDock lcd;

// Sprites ultra-leves apenas para as áreas dos olhos (apenas 16 KB cada! Cabe com folga na SRAM)
const int EYE_MAX_W = 75;
const int EYE_MAX_H = 95;
LGFX_Sprite eyeLeft(&lcd);
LGFX_Sprite eyeRight(&lcd);

// ==============================================================================
// 2. PALETA DE CORES CYBERPUNK ROBOT
// ==============================================================================
const uint16_t COLOR_BG        = 0x0000; // Preto
const uint16_t COLOR_SHELL_EXT = 0x2124; // Cinza titânio
const uint16_t COLOR_SHELL_INT = 0x0841; // Preto do visor
const uint16_t COLOR_CYAN      = 0x07FF; // Ciano vibrante
const uint16_t COLOR_BLUE_GLOW = 0x03B9; // Brilho azul
const uint16_t COLOR_WHITE     = 0xFFFF; // Brilho dos olhos
const uint16_t COLOR_PINK_NEON = 0xF9D5; // Bochechas coradas
const uint16_t COLOR_ORANGE    = 0xFD20; // Alerta / Foco
const uint16_t COLOR_BTN_BG    = 0x0926; // Fundo do botão
const uint16_t COLOR_BTN_ACT   = 0x04F4; // Botão acionado

// ==============================================================================
// 3. ESTADOS E ANIMAÇÕES DO ROSTO
// ==============================================================================
enum Expressao {
  FACE_NEUTRO,
  FACE_PISCANDO,
  FACE_OUVINDO,
  FACE_FELIZ,
  FACE_FOCADO,
  FACE_SONO
};

Expressao expressaoAtual = FACE_NEUTRO;
int olharOffset = 0;
int olharTarget = 0;

unsigned long ultimoPiscar = 0;
unsigned long tempoInicioPiscar = 0;
bool emPiscar = false;
unsigned long ultimoOlhar = 0;

struct Botao {
  int x, y, w, h;
  const char* label;
  const char* cmd;
  bool pressionado;
};

Botao botoes[] = {
  { 15,  265, 135, 45, "ACENAR",   "WAVE", false },
  { 172, 265, 135, 45, "GARRA",    "GARRA_TOGGLE", false },
  { 330, 265, 135, 45, "DESCANSO", "REST", false }
};

void desenharBotao(int i) {
  uint16_t bg = botoes[i].pressionado ? COLOR_BTN_ACT : COLOR_BTN_BG;
  uint16_t borda = botoes[i].pressionado ? COLOR_WHITE : COLOR_CYAN;
  uint16_t txt = botoes[i].pressionado ? COLOR_BG : COLOR_WHITE;

  lcd.fillRoundRect(botoes[i].x, botoes[i].y, botoes[i].w, botoes[i].h, 8, bg);
  lcd.drawRoundRect(botoes[i].x, botoes[i].y, botoes[i].w, botoes[i].h, 8, borda);

  lcd.setFont(&fonts::Font2);
  lcd.setTextColor(txt, bg);
  int tw = lcd.textWidth(botoes[i].label);
  lcd.setCursor(botoes[i].x + (botoes[i].w - tw) / 2, botoes[i].y + 14);
  lcd.print(botoes[i].label);
}

// Desenha a carcaça fixa da cabeça do robô diretamente no LCD (zero consumo de RAM)
void desenharMolduraCabeca() {
  lcd.fillScreen(COLOR_BG);

  // 1. Badge JARVIS no topo
  lcd.setFont(&fonts::Font0);
  lcd.setTextColor(COLOR_CYAN, COLOR_BG);
  lcd.drawRoundRect(170, 4, 140, 18, 4, COLOR_BLUE_GLOW);
  lcd.setCursor(185, 9);
  lcd.print("J.A.R.V.I.S. // 4.0\"");

  // 2. Carcaça Externa da Cabeça do Robô (Curvas suaves estilo Astro Bot / EVE)
  lcd.fillRoundRect(30, 26, 420, 228, 36, COLOR_SHELL_EXT);
  lcd.drawRoundRect(28, 24, 424, 232, 38, COLOR_BLUE_GLOW);

  // Orelhinhas / Antenas laterais iluminadas
  lcd.fillRoundRect(12, 105, 18, 70, 8, COLOR_CYAN);
  lcd.fillRoundRect(450, 105, 18, 70, 8, COLOR_CYAN);

  // 3. Visor de Vidro Escuro Interno
  lcd.fillRoundRect(45, 40, 390, 200, 26, COLOR_SHELL_INT);
  lcd.drawRoundRect(45, 40, 390, 200, 26, 0x18E3);

  // 4. Desenha os 3 botões na base
  for (int i = 0; i < 3; i++) {
    desenharBotao(i);
  }
}

// Desenha o conteúdo de cada olho no seu respectivo sprite leve
void desenharOlhoSprite(LGFX_Sprite &spr, Expressao exp, bool isLeft) {
  spr.fillScreen(COLOR_SHELL_INT);

  int ox = olharOffset;

  switch (exp) {
    case FACE_NEUTRO:
      // Sobrancelha
      spr.drawFastHLine(6, 4, 55, COLOR_BLUE_GLOW);

      // Olho pílula grande brilhante
      spr.fillRoundRect(10, 16, 55, 68, 22, COLOR_CYAN);
      spr.fillCircle(25, 32, 9, COLOR_WHITE); // Reflexo duplo de anime
      spr.fillCircle(45, 62, 5, COLOR_WHITE);
      break;

    case FACE_PISCANDO:
      // Pálpebra fechada
      spr.drawFastHLine(6, 12, 55, COLOR_BLUE_GLOW);
      spr.fillRoundRect(6, 48, 62, 8, 4, COLOR_CYAN);
      break;

    case FACE_FELIZ:
      // Olho em arco sorridente (^ ^)
      spr.drawArc(37, 50, 34, 26, 200, 340, COLOR_CYAN);
      spr.drawArc(37, 49, 34, 26, 200, 340, COLOR_WHITE);
      // Bochecha corada
      spr.fillRoundRect(isLeft ? 4 : 45, 68, 26, 14, 7, COLOR_PINK_NEON);
      break;

    case FACE_OUVINDO:
      // Olhos grandes arregalados
      spr.fillCircle(37, 48, 34, COLOR_CYAN);
      spr.fillCircle(32, 38, 11, COLOR_WHITE);
      break;

    case FACE_FOCADO:
      // Sobrancelha inclinada determinada
      if (isLeft) spr.drawLine(4, 4, 65, 20, COLOR_ORANGE);
      else spr.drawLine(65, 4, 4, 20, COLOR_ORANGE);

      spr.fillRoundRect(10, 28, 55, 38, 12, COLOR_ORANGE);
      spr.fillCircle(25, 38, 6, COLOR_WHITE);
      break;

    case FACE_SONO:
      // Olho caído dormindo
      spr.drawArc(37, 42, 28, 22, 20, 160, COLOR_BLUE_GLOW);
      break;
  }
}

// Atualiza a boca e os olhos sem redesenhar a moldura
void atualizarRostoExpressivo() {
  // 1. Renderiza e envia os olhos nos sprites leves
  desenharOlhoSprite(eyeLeft, expressaoAtual, true);
  desenharOlhoSprite(eyeRight, expressaoAtual, false);

  int posX_L = 120 + olharOffset;
  int posX_R = 285 + olharOffset;
  int posY = 75;

  eyeLeft.pushSprite(posX_L, posY);
  eyeRight.pushSprite(posX_R, posY);

  // 2. Boca dinâmica no visor
  lcd.fillRect(190, 175, 100, 40, COLOR_SHELL_INT);

  if (expressaoAtual == FACE_FELIZ) {
    // Sorriso grande aberto
    lcd.fillRoundRect(205, 178, 70, 30, 14, COLOR_CYAN);
    lcd.fillRoundRect(210, 180, 60, 10, 5, COLOR_WHITE);
  } else if (expressaoAtual == FACE_OUVINDO) {
    // Boquinha em 'O'
    lcd.drawCircle(240, 192, 14, COLOR_CYAN);
    lcd.drawCircle(240, 192, 13, COLOR_CYAN);
  } else if (expressaoAtual == FACE_FOCADO) {
    // Boca em linha reta
    lcd.drawFastHLine(215, 190, 50, COLOR_ORANGE);
    lcd.drawFastHLine(215, 191, 50, COLOR_ORANGE);
  } else if (expressaoAtual != FACE_SONO) {
    // Sorriso suave
    lcd.drawArc(240, 182, 32, 28, 20, 160, COLOR_CYAN);
  }
}

// ==============================================================================
// 4. SETUP E LOOP
// ==============================================================================
void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN_PIN, OUTPUT);
  digitalWrite(LED_BUILTIN_PIN, HIGH);

  unsigned long t0 = millis();
  while (!Serial && (millis() - t0 < 2500)) {
    digitalWrite(LED_BUILTIN_PIN, !digitalRead(LED_BUILTIN_PIN));
    delay(100);
  }

  Serial.println("\n==================================================");
  Serial.println("🤖 [JARVIS DOCK] ROSTO SOCIAL HD (MEMORIA LEVE)");
  Serial.println("==================================================");

  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(50);
  digitalWrite(8, LOW);  delay(100);
  digitalWrite(8, HIGH); delay(200);

  pinMode(10, OUTPUT); digitalWrite(10, HIGH);
  pinMode(5, OUTPUT);  digitalWrite(5, HIGH);

  lcd.init();
  lcd.setRotation(1);

  // Criação dos Sprites LEVES (apenas 16KB cada, sem risco de estourar a RAM)
  eyeLeft.setColorDepth(16);
  eyeLeft.createSprite(EYE_MAX_W, EYE_MAX_H);

  eyeRight.setColorDepth(16);
  eyeRight.createSprite(EYE_MAX_W, EYE_MAX_H);

  // Desenha a moldura completa uma única vez
  desenharMolduraCabeca();
  atualizarRostoExpressivo();

  Serial.println("✅ [SISTEMA PRONTO] Rosto Social Ativo!");
}

unsigned long lastTouchTs = 0;

void loop() {
  unsigned long agora = millis();

  // 1. Piscadas Autônomas
  if (expressaoAtual == FACE_NEUTRO) {
    if (!emPiscar && (agora - ultimoPiscar > 3800)) {
      emPiscar = true;
      tempoInicioPiscar = agora;
      expressaoAtual = FACE_PISCANDO;
      atualizarRostoExpressivo();
    } else if (emPiscar && (agora - tempoInicioPiscar > 160)) {
      emPiscar = false;
      ultimoPiscar = agora;
      expressaoAtual = FACE_NEUTRO;
      atualizarRostoExpressivo();
    }

    // Micro-olhares para os lados a cada 6s
    if (!emPiscar && (agora - ultimoOlhar > 6000)) {
      ultimoOlhar = agora;
      static int seq = 0;
      seq = (seq + 1) % 4;
      if (seq == 1) olharTarget = 12;
      else if (seq == 3) olharTarget = -12;
      else olharTarget = 0;
    }

    if (olharOffset != olharTarget) {
      olharOffset += (olharTarget - olharOffset) * 0.4f;
      atualizarRostoExpressivo();
    }
  }

  // 2. Leitura do Touch nos Botões
  uint16_t tx, ty;
  if (lcd.getTouch(&tx, &ty)) {
    lastTouchTs = agora;
    Serial.printf("👆 [TOUCH] X=%d Y=%d\n", tx, ty);

    for (int i = 0; i < 3; i++) {
      bool dentro = (tx >= (botoes[i].x - 10) && tx <= (botoes[i].x + botoes[i].w + 10) &&
                     ty >= (botoes[i].y - 15) && ty <= (botoes[i].y + botoes[i].h + 20));

      if (dentro && !botoes[i].pressionado) {
        botoes[i].pressionado = true;
        desenharBotao(i);
        expressaoAtual = FACE_FELIZ;
        atualizarRostoExpressivo();

        Serial.printf("{\"type\":\"arm_cmd\",\"action\":\"%s\"}\n", botoes[i].cmd);
      }
    }
  } else {
    if (agora - lastTouchTs > 180) {
      bool precisaRedesenhar = false;
      for (int i = 0; i < 3; i++) {
        if (botoes[i].pressionado) {
          botoes[i].pressionado = false;
          desenharBotao(i);
          precisaRedesenhar = true;
        }
      }
      if (precisaRedesenhar) {
        expressaoAtual = FACE_NEUTRO;
        atualizarRostoExpressivo();
      }
    }
  }

  // 3. Comandos Seriais do Servidor
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, linha);
      if (!err && doc["mood"].is<const char*>()) {
        const char* m = doc["mood"];
        if (strcmp(m, "happy") == 0) expressaoAtual = FACE_FELIZ;
        else if (strcmp(m, "listen") == 0) expressaoAtual = FACE_OUVINDO;
        else if (strcmp(m, "focus") == 0) expressaoAtual = FACE_FOCADO;
        else if (strcmp(m, "sleep") == 0) expressaoAtual = FACE_SONO;
        else expressaoAtual = FACE_NEUTRO;

        atualizarRostoExpressivo();
        Serial.printf("{\"ack\":\"face_updated\",\"mood\":\"%s\"}\n", m);
      }
    }
  }

  delay(20);
}
