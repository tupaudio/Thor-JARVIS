/*
 * ==============================================================================
 * J.A.R.V.I.S. - Sketch Isolado de Diagnóstico de Bancada para OLED 1.5"
 * Foco: Isolar 100% o display (SEM SERVOS, SEM INTERRUPÇÕES, SEM CONSUMO DE RAM)
 * 
 * Pinagem testada (conforme alteração física do usuário):
 * - SCL (Clock):      Pino Digital 8
 * - SDA (Data/DIN):   Pino Digital 9
 * - DC  (Data/Cmd):   Pino Digital 10
 * - CS  (Chip Select):Pino Digital 11
 * - RST (Reset):      Pino Digital 12
 * - VCC: 5V (ou 3.3V se não houver regulador)
 * - GND: GND
 * ==============================================================================
 */

#include <Arduino.h>
#include <U8g2lib.h>

// ---------------- ESCOLHA DO DRIVER PARA TESTE ----------------
// 1 = SH1107 SEEED (Bomba de carga interna ativada para módulos chineses GME128128)
// 2 = SH1107 GENÉRICO
// 3 = SSD1327 WAVESHARE (Muitos módulos 1.5" 128x128 vendidos como SH1107 na verdade são SSD1327)
// 4 = SSD1327 MIDAS
// 5 = SH1107 PIMORONI
#define TESTE_DRIVER 1

const uint8_t PIN_SCL = 8;
const uint8_t PIN_SDA = 9;
const uint8_t PIN_DC  = 10;
const uint8_t PIN_CS  = 11;
const uint8_t PIN_RST = 12;

#if TESTE_DRIVER == 1
  #define NOME_DRIVER "SH1107 SEEED 128x128 SW-SPI"
  U8G2_SH1107_SEEED_128X128_1_4W_SW_SPI u8g2(U8G2_R0, PIN_SCL, PIN_SDA, PIN_CS, PIN_DC, PIN_RST);
#elif TESTE_DRIVER == 2
  #define NOME_DRIVER "SH1107 GENERICO 128x128 SW-SPI"
  U8G2_SH1107_128X128_1_4W_SW_SPI u8g2(U8G2_R0, PIN_SCL, PIN_SDA, PIN_CS, PIN_DC, PIN_RST);
#elif TESTE_DRIVER == 3
  #define NOME_DRIVER "SSD1327 WAVESHARE 128x128 SW-SPI"
  U8G2_SSD1327_WS_128X128_1_4W_SW_SPI u8g2(U8G2_R0, PIN_SCL, PIN_SDA, PIN_CS, PIN_DC, PIN_RST);
#elif TESTE_DRIVER == 4
  #define NOME_DRIVER "SSD1327 MIDAS 128x128 SW-SPI"
  U8G2_SSD1327_MIDAS_128X128_1_4W_SW_SPI u8g2(U8G2_R0, PIN_SCL, PIN_SDA, PIN_CS, PIN_DC, PIN_RST);
#elif TESTE_DRIVER == 5
  #define NOME_DRIVER "SH1107 PIMORONI 128x128 SW-SPI"
  U8G2_SH1107_PIMORONI_128X128_1_4W_SW_SPI u8g2(U8G2_R0, PIN_SCL, PIN_SDA, PIN_CS, PIN_DC, PIN_RST);
#endif

int xPos = 10;
int xDir = 2;
unsigned long ultimoLog = 0;

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println(F("\n=================================================="));
  Serial.println(F("🔬 [DIAGNOSTICO BANCADA] Teste de Display OLED 1.5\""));
  Serial.print(F("📋 Driver selecionado: "));
  Serial.println(F(NOME_DRIVER));
  Serial.println(F("🔌 Pinagem: SCL=8 | SDA=9 | DC=10 | CS=11 | RST=12"));
  Serial.println(F("=================================================="));

  // 1. Pulso elétrico manual de Hardware Reset no pino 12
  Serial.println(F("1. Disparando pulso de Hardware Reset no pino 12..."));
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, HIGH);
  delay(20);
  digitalWrite(PIN_RST, LOW);
  delay(100);
  digitalWrite(PIN_RST, HIGH);
  delay(100);
  Serial.println(F("   -> Reset concluído."));

  // 2. Chip Select no pino 11
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);

  // 3. Inicialização do U8g2
  Serial.println(F("2. Chamando u8g2.begin()..."));
  u8g2.begin();
  u8g2.setPowerSave(0);    // Força Display ON (0xAF)
  u8g2.setContrast(255);   // Brilho máximo

  // 4. Teste de FLASH BRANCO TOTAL (Acende 100% dos pixels por 1,5 segundo)
  Serial.println(F("3. Desenhando Box 128x128 TOTAL (se os pixels funcionarem, acenderá em branco)..."));
  u8g2.firstPage();
  do {
    u8g2.drawBox(0, 0, 128, 128);
  } while (u8g2.nextPage());
  delay(1500);

  // 5. Desenha tela de teste com moldura e texto
  Serial.println(F("4. Desenhando tela informativa de teste..."));
  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.drawFrame(2, 2, 124, 124);
    u8g2.setFont(u8g2_font_helvB10_tr);
    u8g2.drawStr(20, 35, "OLED TESTE");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(32, 60, "STATUS: OK");
    u8g2.drawStr(12, 80, NOME_DRIVER);
    u8g2.drawDisc(64, 105, 12);
  } while (u8g2.nextPage());
  delay(1000);

  Serial.println(F("✅ [SETUP CONCLUIDO] Iniciando animacao no loop..."));
}

void loop() {
  // Animação contínua de bolinha quicando para confirmar se o display atualiza
  xPos += xDir;
  if (xPos >= 110 || xPos <= 18) {
    xDir = -xDir;
  }

  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.setFont(u8g2_font_helvB10_tr);
    u8g2.drawStr(24, 40, "JARVIS OLED");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(20, 65, "Pinos 8 a 12 OK");
    u8g2.drawDisc(xPos, 95, 8);
  } while (u8g2.nextPage());

  if (millis() - ultimoLog > 2000) {
    ultimoLog = millis();
    Serial.print(F("⏱️ [HEARTBEAT] Arduino rodando ativo... millis: "));
    Serial.println(millis());
  }
}
