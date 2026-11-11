/*
 * ==============================================================================
 * J.A.R.V.I.S. - Calibrador de Touch Screen XPT2046 + Eixo Cartesiano (4.0" 480x320)
 * 1. Guia o toque em 4 cruzes nos cantos (Calibração Geométrica LovyanGFX)
 * 2. Imprime a matriz de calibração no Serial USB
 * 3. Abre tela de Eixo Cartesiano com régua e desenho de rastro para testes precisos
 * ==============================================================================
 */

#include <Arduino.h>
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#define LED_BUILTIN_PIN 21

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

    // Barramento Touch (SPI3 independente)
    {
      auto cfg = _touch_instance.config();
      cfg.spi_host = SPI3_HOST;
      cfg.freq     = 2500000;
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

uint16_t calData[8];
bool calibrado = false;

// Desenha a malha quadriculada do eixo cartesiano
void desenharEixoCartesiano() {
  lcd.fillScreen(TFT_BLACK);

  // Grade secundária a cada 20 pixels
  for (int x = 0; x < 480; x += 20) {
    lcd.drawFastVLine(x, 0, 320, 0x18C3); // Cinza muito escuro
  }
  for (int y = 0; y < 320; y += 20) {
    lcd.drawFastHLine(0, y, 480, 0x18C3);
  }

  // Grade principal a cada 100 pixels
  for (int x = 0; x < 480; x += 100) {
    lcd.drawFastVLine(x, 0, 320, 0x39E7); // Cinza médio
  }
  for (int y = 0; y < 320; y += 100) {
    lcd.drawFastHLine(0, y, 480, 0x39E7);
  }

  // Eixos centrais cartesianos principais (X=240, Y=160)
  lcd.drawFastVLine(240, 0, 320, TFT_RED);
  lcd.drawFastHLine(0, 160, 480, TFT_BLUE);

  // Pontos de Referência Notáveis com mira:
  // Centro (240, 160)
  lcd.drawCircle(240, 160, 10, TFT_YELLOW);
  lcd.drawCircle(240, 160, 20, TFT_YELLOW);
  lcd.setTextColor(TFT_YELLOW, TFT_BLACK);
  lcd.setCursor(248, 165);
  lcd.print("C (240,160)");

  // Ponto A: Top-Left (40, 40)
  lcd.drawCircle(40, 40, 8, TFT_GREEN);
  lcd.drawCircle(40, 40, 16, TFT_GREEN);
  lcd.setTextColor(TFT_GREEN, TFT_BLACK);
  lcd.setCursor(48, 45);
  lcd.print("A (40,40)");

  // Ponto B: Top-Right (440, 40)
  lcd.drawCircle(440, 40, 8, TFT_GREEN);
  lcd.drawCircle(440, 40, 16, TFT_GREEN);
  lcd.setCursor(360, 45);
  lcd.print("B (440,40)");

  // Ponto C: Bottom-Right (440, 280)
  lcd.drawCircle(440, 280, 8, TFT_GREEN);
  lcd.drawCircle(440, 280, 16, TFT_GREEN);
  lcd.setCursor(340, 260);
  lcd.print("C (440,280)");

  // Ponto D: Bottom-Left (40, 280)
  lcd.drawCircle(40, 280, 8, TFT_GREEN);
  lcd.drawCircle(40, 280, 16, TFT_GREEN);
  lcd.setCursor(48, 260);
  lcd.print("D (40,280)");

  // Botão Limpar Tela no topo centro
  lcd.fillRoundRect(190, 4, 100, 24, 4, 0x4208);
  lcd.drawRoundRect(190, 4, 100, 24, 4, TFT_WHITE);
  lcd.setTextColor(TFT_WHITE, 0x4208);
  lcd.setCursor(205, 10);
  lcd.print("LIMPAR");

  // Barra de Status Superior
  lcd.fillRect(10, 4, 160, 20, TFT_BLACK);
  lcd.setTextColor(TFT_CYAN, TFT_BLACK);
  lcd.setCursor(10, 8);
  lcd.print("EIXO CARTESIANO 480x320");
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

  Serial.println("\n==================================================");
  Serial.println("🎯 [JARVIS DOCK] CALIBRAÇÃO ASSISTIDA DO TOUCH");
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
  lcd.fillScreen(TFT_BLACK);

  // 1. Tela de Instruções de Calibração
  lcd.setTextColor(TFT_CYAN, TFT_BLACK);
  lcd.setFont(&fonts::Font2);
  lcd.setCursor(70, 70);
  lcd.print("CALIBRACAO PRECISA DO TOUCH");

  lcd.setTextColor(TFT_WHITE, TFT_BLACK);
  lcd.setFont(&fonts::Font0);
  lcd.setCursor(60, 110);
  lcd.print("Toque com cuidado no centro das 4 cruzes que vao aparecer.");
  lcd.setCursor(100, 130);
  lcd.print("Use uma caneta touch ou ponta fina para precisao.");

  lcd.setTextColor(TFT_YELLOW, TFT_BLACK);
  lcd.setCursor(130, 170);
  lcd.print("Iniciando em 2 segundos...");
  delay(2500);

  // 2. Executa a rotina nativa de calibração afim do LovyanGFX
  // Desenha 4 cruzes nos 4 cantos e calcula rotação, escala e espelhamento exatos
  Serial.println("👉 [CALIBRANDO] Toque no centro de cada cruz na tela...");
  lcd.calibrateTouch(calData, TFT_RED, TFT_WHITE, 25);

  // 3. Imprime os dados de calibração no Serial para salvar
  Serial.println("\n🎉 [CALIBRACAO CONCLUIDA COM SUCESSO!]");
  Serial.print("📋 Matriz calculada: { ");
  for (int i = 0; i < 8; i++) {
    Serial.print(calData[i]);
    if (i < 7) Serial.print(", ");
  }
  Serial.println(" }");
  Serial.println("==================================================\n");

  // 4. Entra na tela de Eixo Cartesiano com marcas
  desenharEixoCartesiano();
  calibrado = true;
}

int lastX = -1, lastY = -1;

void loop() {
  uint16_t x, y;
  if (lcd.getTouch(&x, &y)) {
    // Verifica se tocou no botão "LIMPAR" (190, 4, 100, 24)
    if (x >= 190 && x <= 290 && y >= 4 && y <= 35) {
      desenharEixoCartesiano();
      delay(200);
      return;
    }

    // Desenha a marca do toque no ponto exato (círculo sólido com borda ciano)
    lcd.fillCircle(x, y, 4, TFT_MAGENTA);
    lcd.drawCircle(x, y, 8, TFT_CYAN);

    // Se estiver arrastando, desenha linha contínua entre os pontos
    if (lastX >= 0 && lastY >= 0) {
      lcd.drawLine(lastX, lastY, x, y, TFT_WHITE);
    }
    lastX = x;
    lastY = y;

    // Atualiza barra de coordenadas no topo direito
    lcd.fillRect(310, 4, 160, 20, TFT_BLACK);
    lcd.setTextColor(TFT_GREEN, TFT_BLACK);
    lcd.setFont(&fonts::Font0);
    lcd.setCursor(315, 8);
    lcd.printf("X=%3d | Y=%3d", x, y);

    // Imprime em tempo real no Serial
    Serial.printf("🎯 TOUCH: X=%3d  Y=%3d\n", x, y);
  } else {
    lastX = -1;
    lastY = -1;
  }

  delay(15);
}
