/*
 * ==============================================================================
 * J.A.R.V.I.S. - Sketch Isolado de Bancada: Display OLED 1.5" SH1107 em Hardware SPI
 * Configuração Comprovada do commit 0bde085 (PIMORONI 128x128 HW-SPI)
 * 
 * MAPA DE LIGAÇÃO FÍSICA NO SENSOR SHIELD (Hardware SPI):
 * - SCL (CLK) -> Pino Digital 13 (SCK - Hardware SPI, fileira S)
 * - SDA (DIN) -> Pino Digital 11 (MOSI - Hardware SPI, fileira S)
 * - CS        -> Pino Digital 10 (Chip Select, fileira S)
 * - DC        -> Pino Digital 9  (Data/Command, fileira S)
 * - RST       -> Pino Digital 8  (Hardware Reset, fileira S)
 * - VCC       -> 5V (Fileira V)
 * - GND       -> GND (Fileira G)
 * ==============================================================================
 */

#include <Arduino.h>
#include <SPI.h>
#include <U8g2lib.h>

// Driver comprovado Pimoroni em Hardware SPI nativo
U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI u8g2(U8G2_R2, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

int xPos = 10;
int xDir = 2;
unsigned long ultimoLog = 0;

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println(F("\n=================================================="));
  Serial.println(F("🔬 [DIAGNOSTICO BANCADA] OLED 1.5\" SH1107 HARDWARE SPI"));
  Serial.println(F("📋 Driver: U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI"));
  Serial.println(F("🔌 Pinagem: SCL=13 | SDA=11 | CS=10 | DC=9 | RST=8"));
  Serial.println(F("=================================================="));

  // 1. Pulso elétrico manual de Hardware Reset no pino 8
  Serial.println(F("1. Disparando pulso de Reset no pino 8..."));
  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(20);
  digitalWrite(8, LOW);  delay(50);
  digitalWrite(8, HIGH); delay(50);
  Serial.println(F("   -> Reset concluído."));

  // 2. Garante pino 10 (CS/SS) como OUTPUT para evitar modo escravo do AVR
  pinMode(10, OUTPUT);
  digitalWrite(10, HIGH);

  // 3. Inicialização com velocidade segura de 1MHz
  Serial.println(F("2. Configurando clock SPI para 1 MHz e iniciando u8g2..."));
  u8g2.setBusClock(1000000);
  u8g2.begin();
  u8g2.setPowerSave(0);    // Força tela acesa (0xAF)
  u8g2.setContrast(255);   // Brilho máximo

  // 4. Teste de FLASH BRANCO TOTAL por 1,5 segundo
  Serial.println(F("3. Desenhando Box 128x128 TOTAL (se os pixels funcionarem, acenderá em branco)..."));
  u8g2.firstPage();
  do {
    u8g2.drawBox(0, 0, 128, 128);
  } while (u8g2.nextPage());
  delay(1500);

  // 5. Tela com texto informativo
  Serial.println(F("4. Desenhando tela de confirmação..."));
  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.drawFrame(2, 2, 124, 124);
    u8g2.setFont(u8g2_font_helvB10_tr);
    u8g2.drawStr(20, 35, "OLED TESTE");
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(22, 60, "HARDWARE SPI");
    u8g2.drawStr(16, 80, "PIMORONI SH1107");
    u8g2.drawDisc(64, 105, 12);
  } while (u8g2.nextPage());
  delay(1000);

  Serial.println(F("✅ [SETUP CONCLUIDO] Loop ativo e atualizando display..."));
}

void loop() {
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
    u8g2.drawStr(22, 65, "HARDWARE SPI");
    u8g2.drawDisc(xPos, 95, 8);
  } while (u8g2.nextPage());

  if (millis() - ultimoLog > 2000) {
    ultimoLog = millis();
    Serial.print(F("⏱️ [HEARTBEAT] Arduino rodando ativo... millis: "));
    Serial.println(millis());
  }
}
