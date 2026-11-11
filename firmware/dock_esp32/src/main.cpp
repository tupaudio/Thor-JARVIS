/*
 * ==============================================================================
 * J.A.R.V.I.S. - Dock Terminal Inteligente 4.0" (ESP32-S3 + ILI9488 Touch)
 * Rosto Social Robótico Completo (Estilo Emoji / Astro Bot / EVE em Cores HD)
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
      cfg.x_min    = 3900;          // Invertido para acertar a orientação
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

// Sprite de rosto completo renderizado com DMA para zero flickering
LGFX_Sprite faceCanvas(&lcd);

// ==============================================================================
// 2. PALETA DE CORES CYBERPUNK ROBOT
// ==============================================================================
const uint16_t COLOR_BG        = 0x0000; // Preto
const uint16_t COLOR_SHELL_EXT = 0x2124; // Cinza titânio da carcaça do robô
const uint16_t COLOR_SHELL_INT = 0x0841; // Preto profundo do visor
const uint16_t COLOR_CYAN      = 0x07FF; // Ciano elétrico Arc Reactor
const uint16_t COLOR_BLUE_GLOW = 0x03B9; // Brilho azul
const uint16_t COLOR_WHITE     = 0xFFFF; // Brilho dos olhos
const uint16_t COLOR_PINK_NEON = 0xF9D5; // Bochechinhas felizes
const uint16_t COLOR_ORANGE    = 0xFD20; // Alerta / Foco
const uint16_t COLOR_BTN_BG    = 0x0926; // Fundo de botões táteis
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

// Botões táteis na base da tela
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

// ==============================================================================
// 4. DESENHO ARTÍSTICO DA CABEÇA DO ROBÔ SOCIAL EM CORES HD
// ==============================================================================
void desenharRostoRobo() {
  faceCanvas.fillScreen(COLOR_BG);

  // 1. Badge JARVIS no topo com moldura cibernética
  faceCanvas.setFont(&fonts::Font0);
  faceCanvas.setTextColor(COLOR_CYAN, COLOR_BG);
  faceCanvas.drawRoundRect(170, 4, 140, 18, 4, COLOR_BLUE_GLOW);
  faceCanvas.setCursor(185, 9);
  faceCanvas.print("J.A.R.V.I.S. // 4.0\"");

  // 2. Carcaça Externa da Cabeça do Robô (Curvas suaves estilo EVE / Astro Bot)
  // Largura: 420px, Altura: 215px, centralizado em X=30, Y=28
  faceCanvas.fillRoundRect(30, 28, 420, 225, 36, COLOR_SHELL_EXT);
  faceCanvas.drawRoundRect(28, 26, 424, 229, 38, COLOR_BLUE_GLOW);

  // Orelhinhas / Antenas laterais do robô com iluminação neon
  faceCanvas.fillRoundRect(12, 105, 18, 70, 8, COLOR_CYAN);
  faceCanvas.fillRoundRect(450, 105, 18, 70, 8, COLOR_CYAN);

  // 3. Visor de Vidro Escuro Interno
  faceCanvas.fillRoundRect(45, 42, 390, 197, 26, COLOR_SHELL_INT);
  faceCanvas.drawRoundRect(45, 42, 390, 197, 26, 0x18E3);

  // 4. Expressões Faciais com Suavização de Olhar
  int ox = olharOffset;

  switch (expressaoAtual) {
    case FACE_NEUTRO:
      // Sobrancelhas elegantes
      faceCanvas.drawFastHLine(115, 75, 60, COLOR_BLUE_GLOW);
      faceCanvas.drawFastHLine(305, 75, 60, COLOR_BLUE_GLOW);

      // Olhos grandes estilo Pílula brilhante com reflexo duplo de anime
      // Olho Esquerdo:
      faceCanvas.fillRoundRect(120 + ox, 92, 55, 75, 24, COLOR_CYAN);
      faceCanvas.fillCircle(136 + ox, 110, 10, COLOR_WHITE); // Reflexo grande
      faceCanvas.fillCircle(155 + ox, 142, 5, COLOR_WHITE);  // Reflexo pequeno

      // Olho Direito:
      faceCanvas.fillRoundRect(305 + ox, 92, 55, 75, 24, COLOR_CYAN);
      faceCanvas.fillCircle(321 + ox, 110, 10, COLOR_WHITE);
      faceCanvas.fillCircle(340 + ox, 142, 5, COLOR_WHITE);

      // Sorriso amigável suave
      faceCanvas.drawArc(240, 175, 35, 32, 20, 160, COLOR_CYAN);
      break;

    case FACE_PISCANDO:
      // Sobrancelhas relaxadas
      faceCanvas.drawFastHLine(115, 82, 60, COLOR_BLUE_GLOW);
      faceCanvas.drawFastHLine(305, 82, 60, COLOR_BLUE_GLOW);

      // Pálpebras fechadas em linha suave
      faceCanvas.fillRoundRect(115, 128, 65, 8, 4, COLOR_CYAN);
      faceCanvas.fillRoundRect(300, 128, 65, 8, 4, COLOR_CYAN);

      // Sorriso calmo
      faceCanvas.drawArc(240, 175, 35, 32, 30, 150, COLOR_CYAN);
      break;

    case FACE_FELIZ:
      // Olhos sorridentes em arco para cima (^ ^)
      faceCanvas.drawArc(145 + ox, 135, 40, 32, 200, 340, COLOR_CYAN);
      faceCanvas.drawArc(145 + ox, 134, 40, 32, 200, 340, COLOR_WHITE);

      faceCanvas.drawArc(335 + ox, 135, 40, 32, 200, 340, COLOR_CYAN);
      faceCanvas.drawArc(335 + ox, 134, 40, 32, 200, 340, COLOR_WHITE);

      // Bochechinhas coradas brilhantes
      faceCanvas.fillRoundRect(85 + ox, 145, 30, 14, 7, COLOR_PINK_NEON);
      faceCanvas.fillRoundRect(365 + ox, 145, 30, 14, 7, COLOR_PINK_NEON);

      // Grande sorriso aberto de robô alegre
      faceCanvas.fillRoundRect(205, 170, 70, 32, 14, COLOR_CYAN);
      faceCanvas.fillRoundRect(210, 173, 60, 12, 6, COLOR_WHITE); // Dente/brilho
      break;

    case FACE_OUVINDO:
      // Olhos arregalados e muito curiosos
      faceCanvas.fillCircle(145 + ox, 125, 38, COLOR_CYAN);
      faceCanvas.fillCircle(140 + ox, 115, 12, COLOR_WHITE);

      faceCanvas.fillCircle(335 + ox, 125, 38, COLOR_CYAN);
      faceCanvas.fillCircle(330 + ox, 115, 12, COLOR_WHITE);

      // Ondas de radar sonoro saindo das orelhas
      faceCanvas.drawCircle(20, 140, 15, COLOR_CYAN);
      faceCanvas.drawCircle(20, 140, 25, COLOR_BLUE_GLOW);
      faceCanvas.drawCircle(460, 140, 15, COLOR_CYAN);
      faceCanvas.drawCircle(460, 140, 25, COLOR_BLUE_GLOW);

      // Boquinha curiosa em 'O'
      faceCanvas.drawCircle(240, 185, 14, COLOR_CYAN);
      break;

    case FACE_FOCADO:
      // Sobrancelhas inclinadas determinadas
      faceCanvas.drawLine(110, 75, 175, 95, COLOR_ORANGE);
      faceCanvas.drawLine(370, 75, 305, 95, COLOR_ORANGE);

      // Olhos estreitos de concentração
      faceCanvas.fillRoundRect(120, 105, 55, 38, 12, COLOR_ORANGE);
      faceCanvas.fillCircle(135, 115, 6, COLOR_WHITE);

      faceCanvas.fillRoundRect(305, 105, 55, 38, 12, COLOR_ORANGE);
      faceCanvas.fillCircle(320, 115, 6, COLOR_WHITE);

      // Boca em linha firme
      faceCanvas.drawFastHLine(215, 182, 50, COLOR_ORANGE);
      break;

    case FACE_SONO:
      // Olhos caídos dormindo
      faceCanvas.drawArc(145, 125, 30, 24, 20, 160, COLOR_BLUE_GLOW);
      faceCanvas.drawArc(335, 125, 30, 24, 20, 160, COLOR_BLUE_GLOW);

      // Letras Z z z flutuando
      faceCanvas.setFont(&fonts::Font0);
      faceCanvas.setTextColor(COLOR_CYAN, COLOR_SHELL_INT);
      faceCanvas.setCursor(375, 65);  faceCanvas.print("Z");
      faceCanvas.setCursor(390, 52);  faceCanvas.print("z");
      faceCanvas.setCursor(402, 42);  faceCanvas.print("z");
      break;
  }

  // 5. Desenha os 3 Botões Táteis na Base
  for (int i = 0; i < 3; i++) {
    uint16_t bg = botoes[i].pressionado ? COLOR_BTN_ACT : COLOR_BTN_BG;
    uint16_t borda = botoes[i].pressionado ? COLOR_WHITE : COLOR_CYAN;
    uint16_t txt = botoes[i].pressionado ? COLOR_BG : COLOR_WHITE;

    faceCanvas.fillRoundRect(botoes[i].x, botoes[i].y, botoes[i].w, botoes[i].h, 8, bg);
    faceCanvas.drawRoundRect(botoes[i].x, botoes[i].y, botoes[i].w, botoes[i].h, 8, borda);

    faceCanvas.setFont(&fonts::Font2);
    faceCanvas.setTextColor(txt, bg);
    int tw = faceCanvas.textWidth(botoes[i].label);
    faceCanvas.setCursor(botoes[i].x + (botoes[i].w - tw) / 2, botoes[i].y + 14);
    faceCanvas.print(botoes[i].label);
  }

  // Empurra o quadro inteiro para o display via DMA em milissegundos
  faceCanvas.pushSprite(0, 0);
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
  Serial.println("🤖 [JARVIS DOCK] ROSTO SOCIAL HD + TOUCH CALIBRADO");
  Serial.println("==================================================");

  // Reset físico
  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(50);
  digitalWrite(8, LOW);  delay(100);
  digitalWrite(8, HIGH); delay(200);

  pinMode(10, OUTPUT); digitalWrite(10, HIGH);
  pinMode(5, OUTPUT);  digitalWrite(5, HIGH);

  lcd.init();
  lcd.setRotation(1); // Paisagem 480x320
  lcd.fillScreen(COLOR_BG);

  // Aloca o canvas do rosto completo em memória de vídeo
  faceCanvas.setColorDepth(16);
  faceCanvas.createSprite(480, 320);

  desenharRostoRobo();
  Serial.println("✅ [SISTEMA PRONTO] Rosto Social Ativo!");
}

unsigned long lastTouchTs = 0;
unsigned long lastLogTs = 0;

void loop() {
  unsigned long agora = millis();

  // 1. Animação Autônoma da Face (Piscadas a cada 3.8s)
  if (expressaoAtual == FACE_NEUTRO) {
    if (!emPiscar && (agora - ultimoPiscar > 3800)) {
      emPiscar = true;
      tempoInicioPiscar = agora;
      expressaoAtual = FACE_PISCANDO;
      desenharRostoRobo();
    } else if (emPiscar && (agora - tempoInicioPiscar > 160)) {
      emPiscar = false;
      ultimoPiscar = agora;
      expressaoAtual = FACE_NEUTRO;
      desenharRostoRobo();
    }

    // Micro-sacadas de olhar (observando o ambiente a cada 6s)
    if (!emPiscar && (agora - ultimoOlhar > 6000)) {
      ultimoOlhar = agora;
      static int seq = 0;
      seq = (seq + 1) % 4;
      if (seq == 1) olharTarget = 15;
      else if (seq == 3) olharTarget = -15;
      else olharTarget = 0;
    }

    if (olharOffset != olharTarget) {
      olharOffset += (olharTarget - olharOffset) * 0.4f;
      desenharRostoRobo();
    }
  }

  // 2. Leitura e Detecção do Touch
  uint16_t tx, ty;
  if (lcd.getTouch(&tx, &ty)) {
    lastTouchTs = agora;
    Serial.printf("👆 [TOUCH DETECTADO] X=%d Y=%d\n", tx, ty);

    // Verifica clique em cada botão
    for (int i = 0; i < 3; i++) {
      // Área de toque com margem de tolerância para o dedo
      bool dentro = (tx >= (botoes[i].x - 10) && tx <= (botoes[i].x + botoes[i].w + 10) &&
                     ty >= (botoes[i].y - 15) && ty <= (botoes[i].y + botoes[i].h + 20));

      if (dentro && !botoes[i].pressionado) {
        botoes[i].pressionado = true;
        expressaoAtual = FACE_FELIZ; // Fica feliz ao ser tocado!
        desenharRostoRobo();

        Serial.printf("{\"type\":\"arm_cmd\",\"action\":\"%s\"}\n", botoes[i].cmd);
      }
    }
  } else {
    // Soltou o dedo da tela
    if (agora - lastTouchTs > 180) {
      bool precisaRedesenhar = false;
      for (int i = 0; i < 3; i++) {
        if (botoes[i].pressionado) {
          botoes[i].pressionado = false;
          precisaRedesenhar = true;
        }
      }
      if (precisaRedesenhar) {
        expressaoAtual = FACE_NEUTRO;
        desenharRostoRobo();
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

        desenharRostoRobo();
        Serial.printf("{\"ack\":\"face_updated\",\"mood\":\"%s\"}\n", m);
      }
    }
  }

  delay(20);
}
