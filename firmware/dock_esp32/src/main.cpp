/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" (ESP32-S3 + ILI9488 + Touch)
 * - Eixo X Invertido Corrigido (Acenar na Esquerda, Repouso na Direita)
 * - Botões Táteis Oficiais: [ ACENAR ] [ APONTAR ] [ REPOUSO ]
 * - Badge Dinâmico de Personalidade (Sincronizado com iPhone / PersonaManager)
 * - Tarja Dinâmica de Notificações e Telemetria em Tempo Real
 * ==============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#define LED_BUILTIN_PIN 21

// ==============================================================================
// 1. CONFIGURAÇÃO LOVYANGFX
// ==============================================================================
class LGFX_JarvisDock : public lgfx::LGFX_Device {
  lgfx::Panel_ILI9488  _panel_instance;
  lgfx::Bus_SPI        _bus_display;
  lgfx::Touch_XPT2046  _touch_instance;

public:
  LGFX_JarvisDock() {
    // Display SPI2
    {
      auto cfg = _bus_display.config();
      cfg.spi_host = SPI2_HOST;
      cfg.spi_mode = 0;
      cfg.freq_write = 15000000;
      cfg.freq_read  = 10000000;
      cfg.use_lock   = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 12;
      cfg.pin_mosi = 11;
      cfg.pin_miso = -1;
      cfg.pin_dc   = 9;
      _bus_display.config(cfg);
      _panel_instance.setBus(&_bus_display);
    }

    {
      auto cfg = _panel_instance.config();
      cfg.pin_cs   = 10;
      cfg.pin_rst  = 8;
      cfg.panel_width  = 320;
      cfg.panel_height = 480;
      cfg.bus_shared   = false;
      cfg.readable     = false;
      cfg.invert       = false;
      cfg.rgb_order    = false;
      cfg.dlen_16bit   = false;
      _panel_instance.config(cfg);
    }

    // Touch SPI3
    {
      auto cfg = _touch_instance.config();
      cfg.spi_host = SPI3_HOST;
      cfg.freq     = 1000000;
      cfg.pin_sclk = 6;
      cfg.pin_mosi = 7;
      cfg.pin_miso = 13;
      cfg.pin_cs   = 5;
      cfg.pin_int  = 4;
      cfg.bus_shared = false;
      _touch_instance.config(cfg);
      _panel_instance.setTouch(&_touch_instance);
    }

    setPanel(&_panel_instance);
  }
};

LGFX_JarvisDock lcd;

// Sprites de 16KB para os olhos (ultra-leves)
const int EYE_MAX_W = 75;
const int EYE_MAX_H = 95;
LGFX_Sprite eyeLeft(&lcd);
LGFX_Sprite eyeRight(&lcd);

// ==============================================================================
// 2. PALETA DE CORES CYBERPUNK
// ==============================================================================
const uint16_t COLOR_BG        = 0x0000;
const uint16_t COLOR_SHELL_EXT = 0x2124;
const uint16_t COLOR_SHELL_INT = 0x0841;
const uint16_t COLOR_CYAN      = 0x07FF;
const uint16_t COLOR_BLUE_GLOW = 0x03B9;
const uint16_t COLOR_WHITE     = 0xFFFF;
const uint16_t COLOR_PINK_NEON = 0xF9D5;
const uint16_t COLOR_ORANGE    = 0xFD20;
const uint16_t COLOR_YELLOW    = 0xFFE0;
const uint16_t COLOR_BTN_BG    = 0x0926;
const uint16_t COLOR_BTN_ACT   = 0x04F4;

// ==============================================================================
// 3. ESTADOS, PERSONALIDADE E NOTIFICAÇÃO
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

// Personalidade sincronizada dinamicamente
char nomePersona[24] = "J.A.R.V.I.S.";

// Tarja de Notificação Dinâmica
char textoNotificacao[64] = "SISTEMA: ONLINE // AGUARDANDO COMANDOS";
uint16_t corNotificacao = COLOR_CYAN;
unsigned long tempoFimNotificacao = 0;

// Botões Táteis Oficiais Solicitados
struct Botao {
  int x, y, w, h;
  const char* label;
  const char* cmd;
  bool pressionado;
};

Botao botoes[] = {
  { 15,  262, 135, 48, "ACENAR",   "WAVE",  false },
  { 172, 262, 135, 48, "APONTAR",  "POINT", false },
  { 330, 262, 135, 48, "REPOUSO",  "REST",  false }
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
  lcd.setCursor(botoes[i].x + (botoes[i].w - tw) / 2, botoes[i].y + 16);
  lcd.print(botoes[i].label);
}

// Atualiza o Badge de Personalidade no Topo
void desenharBadgePersona() {
  lcd.fillRect(150, 4, 180, 20, COLOR_BG);
  lcd.setFont(&fonts::Font0);
  lcd.setTextColor(COLOR_CYAN, COLOR_BG);
  
  char badge[32];
  snprintf(badge, sizeof(badge), "%s // CORE", nomePersona);
  int tw = lcd.textWidth(badge);
  int bx = (480 - (tw + 20)) / 2;

  lcd.drawRoundRect(bx, 3, tw + 20, 20, 4, COLOR_BLUE_GLOW);
  lcd.setCursor(bx + 10, 8);
  lcd.print(badge);
}

// Atualiza a Tarja de Notificação e Telemetria
void atualizarTarjaNotificacao(const char* msg, uint16_t cor = COLOR_CYAN, int duracaoMs = 4000) {
  strncpy(textoNotificacao, msg, sizeof(textoNotificacao) - 1);
  corNotificacao = cor;
  tempoFimNotificacao = millis() + duracaoMs;

  lcd.fillRect(50, 238, 380, 18, COLOR_SHELL_INT);
  lcd.setFont(&fonts::Font0);
  lcd.setTextColor(corNotificacao, COLOR_SHELL_INT);
  int tw = lcd.textWidth(textoNotificacao);
  lcd.setCursor((480 - tw) / 2, 242);
  lcd.print(textoNotificacao);
}

void desenharMolduraCabeca() {
  lcd.fillScreen(COLOR_BG);

  desenharBadgePersona();

  // Carcaça Externa da Cabeça do Robô
  lcd.fillRoundRect(30, 26, 420, 226, 36, COLOR_SHELL_EXT);
  lcd.drawRoundRect(28, 24, 424, 230, 38, COLOR_BLUE_GLOW);

  // Orelhinhas neon
  lcd.fillRoundRect(12, 105, 18, 70, 8, COLOR_CYAN);
  lcd.fillRoundRect(450, 105, 18, 70, 8, COLOR_CYAN);

  // Visor de Vidro Escuro
  lcd.fillRoundRect(45, 38, 390, 202, 26, COLOR_SHELL_INT);
  lcd.drawRoundRect(45, 38, 390, 202, 26, 0x18E3);

  // Exibe notificação inicial
  atualizarTarjaNotificacao(textoNotificacao, COLOR_CYAN, 3000);

  for (int i = 0; i < 3; i++) {
    desenharBotao(i);
  }
}

void desenharOlhoSprite(LGFX_Sprite &spr, Expressao exp, bool isLeft) {
  spr.fillScreen(COLOR_SHELL_INT);

  switch (exp) {
    case FACE_NEUTRO:
      spr.drawFastHLine(6, 4, 55, COLOR_BLUE_GLOW);
      spr.fillRoundRect(10, 16, 55, 68, 22, COLOR_CYAN);
      spr.fillCircle(25, 32, 9, COLOR_WHITE);
      spr.fillCircle(45, 62, 5, COLOR_WHITE);
      break;

    case FACE_PISCANDO:
      spr.drawFastHLine(6, 12, 55, COLOR_BLUE_GLOW);
      spr.fillRoundRect(6, 48, 62, 8, 4, COLOR_CYAN);
      break;

    case FACE_FELIZ:
      spr.drawArc(37, 50, 34, 26, 200, 340, COLOR_CYAN);
      spr.drawArc(37, 49, 34, 26, 200, 340, COLOR_WHITE);
      spr.fillRoundRect(isLeft ? 4 : 45, 68, 26, 14, 7, COLOR_PINK_NEON);
      break;

    case FACE_OUVINDO:
      spr.fillCircle(37, 48, 34, COLOR_CYAN);
      spr.fillCircle(32, 38, 11, COLOR_WHITE);
      break;

    case FACE_FOCADO:
      if (isLeft) spr.drawLine(4, 4, 65, 20, COLOR_ORANGE);
      else spr.drawLine(65, 4, 4, 20, COLOR_ORANGE);
      spr.fillRoundRect(10, 28, 55, 38, 12, COLOR_ORANGE);
      spr.fillCircle(25, 38, 6, COLOR_WHITE);
      break;

    case FACE_SONO:
      spr.drawArc(37, 42, 28, 22, 20, 160, COLOR_BLUE_GLOW);
      break;
  }
}

void atualizarRostoExpressivo() {
  desenharOlhoSprite(eyeLeft, expressaoAtual, true);
  desenharOlhoSprite(eyeRight, expressaoAtual, false);

  int posX_L = 120 + olharOffset;
  int posX_R = 285 + olharOffset;
  int posY = 68;

  eyeLeft.pushSprite(posX_L, posY);
  eyeRight.pushSprite(posX_R, posY);

  // Boca dinâmica
  lcd.fillRect(190, 168, 100, 38, COLOR_SHELL_INT);

  if (expressaoAtual == FACE_FELIZ) {
    lcd.fillRoundRect(205, 172, 70, 30, 14, COLOR_CYAN);
    lcd.fillRoundRect(210, 174, 60, 10, 5, COLOR_WHITE);
  } else if (expressaoAtual == FACE_OUVINDO) {
    lcd.drawCircle(240, 185, 14, COLOR_CYAN);
    lcd.drawCircle(240, 185, 13, COLOR_CYAN);
  } else if (expressaoAtual == FACE_FOCADO) {
    lcd.drawFastHLine(215, 184, 50, COLOR_ORANGE);
    lcd.drawFastHLine(215, 185, 50, COLOR_ORANGE);
  } else if (expressaoAtual != FACE_SONO) {
    lcd.drawArc(240, 176, 32, 28, 20, 160, COLOR_CYAN);
  }
}

// ==============================================================================
// 4. LEITURA CALIBRADA DO TOUCH COM EIXO X INVERTIDO (DIREITA/ESQUERDA 100% OK)
// ==============================================================================
bool obterTouchCalibrado(int &calX, int &calY) {
  uint16_t rawX, rawY;
  if (!lcd.getTouch(&rawX, &rawY)) {
    return false;
  }

  long sumX = rawX, sumY = rawY;
  int count = 1;
  for (int i = 0; i < 3; i++) {
    delayMicroseconds(200);
    uint16_t rx, ry;
    if (lcd.getTouch(&rx, &ry)) {
      sumX += rx;
      sumY += ry;
      count++;
    }
  }
  rawX = sumX / count;
  rawY = sumY / count;

  // CORREÇÃO CIRÚRGICA: Inverte a escala de X (440 na esquerda, 40 na direita)
  calX = map(rawX, 85, 470, 440, 40);
  calX = constrain(calX, 0, 479);

  // Y permanece padrão (topo=40, base=280)
  calY = map(rawY, 20, 260, 40, 280);
  calY = constrain(calY, 0, 319);

  return true;
}

// ==============================================================================
// 5. SETUP E LOOP
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
  Serial.println("🤖 [JARVIS DOCK] SISTEMA COMPLETO: ROSTO + TOUCH + NOTIFICACOES");
  Serial.println("==================================================");

  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(50);
  digitalWrite(8, LOW);  delay(100);
  digitalWrite(8, HIGH); delay(200);

  pinMode(10, OUTPUT); digitalWrite(10, HIGH);
  pinMode(5, OUTPUT);  digitalWrite(5, HIGH);

  lcd.init();
  lcd.setRotation(1);

  eyeLeft.setColorDepth(16);
  eyeLeft.createSprite(EYE_MAX_W, EYE_MAX_H);

  eyeRight.setColorDepth(16);
  eyeRight.createSprite(EYE_MAX_W, EYE_MAX_H);

  desenharMolduraCabeca();
  atualizarRostoExpressivo();

  Serial.println("✅ [SISTEMA PRONTO] Inicialização Concluída!");
}

unsigned long lastTouchTs = 0;

void loop() {
  unsigned long agora = millis();

  // 1. Limpa notificação expirada
  if (tempoFimNotificacao > 0 && agora > tempoFimNotificacao) {
    tempoFimNotificacao = 0;
    atualizarTarjaNotificacao("SISTEMA: ONLINE // MONITORANDO BANCADA", COLOR_BLUE_GLOW, 0);
  }

  // 2. Piscadas Autônomas
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

  // 3. Leitura Filtrada e Calibrada do Touch
  int tx, ty;
  if (obterTouchCalibrado(tx, ty)) {
    lastTouchTs = agora;

    for (int i = 0; i < 3; i++) {
      bool dentro = (tx >= (botoes[i].x - 10) && tx <= (botoes[i].x + botoes[i].w + 10) &&
                     ty >= (botoes[i].y - 15) && ty <= (botoes[i].y + botoes[i].h + 20));

      if (dentro && !botoes[i].pressionado) {
        botoes[i].pressionado = true;
        desenharBotao(i);
        expressaoAtual = FACE_FELIZ;
        atualizarRostoExpressivo();

        char notif[48];
        snprintf(notif, sizeof(notif), "COMANDO: %s ENVIADO!", botoes[i].label);
        atualizarTarjaNotificacao(notif, COLOR_YELLOW, 2500);

        Serial.printf("{\"type\":\"arm_cmd\",\"action\":\"%s\"}\n", botoes[i].cmd);
      }
    }
  } else {
    if (agora - lastTouchTs > 150) {
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

  // 4. Comandos Seriais do Servidor (Expressões, Personalidade, Notificações e Telemetria)
  if (Serial.available()) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();
    if (linha.length() > 0) {
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, linha);
      if (!err) {
        // A. Atualização da Personalidade (Sincronizado com iPhone)
        if (doc["persona"].is<const char*>() || doc["name"].is<const char*>()) {
          const char* p = doc["persona"].is<const char*>() ? doc["persona"] : doc["name"];
          strncpy(nomePersona, p, sizeof(nomePersona) - 1);
          desenharBadgePersona();

          char notif[48];
          snprintf(notif, sizeof(notif), "PERSONALIDADE: %s ATIVA", nomePersona);
          atualizarTarjaNotificacao(notif, COLOR_CYAN, 3000);
        }

        // B. Notificação de Texto / Telemetria do Servidor
        if (doc["notify"].is<const char*>() || doc["text"].is<const char*>()) {
          const char* txt = doc["notify"].is<const char*>() ? doc["notify"] : doc["text"];
          atualizarTarjaNotificacao(txt, COLOR_YELLOW, 4000);
        }

        // C. Mudança de Expressão Facial
        if (doc["mood"].is<const char*>()) {
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
  }

  delay(20);
}
