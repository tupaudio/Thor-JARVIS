/*
 * Teste isolado do OLED 1.5" 128x128 SPI (SH1107).
 * Fiação confirmada: SCL=13, SDA=11, CS=10, DC=9, RST=8
 */
#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>

U8G2_SH1107_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

void setup() {
  Serial.begin(115200);
  Serial.println("INICIANDO_TESTE_OLED_SH1107");

  u8g2.begin();
  u8g2.setPowerSave(0);
}

void loop() {
  u8g2.firstPage();
  do {
    // Moldura 128x128
    u8g2.drawFrame(0, 0, 128, 128);
    
    // Texto
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(30, 25, "JARVIS OLED");
    
    // Dois olhos robóticos centralizados
    u8g2.drawRBox(26, 50, 32, 28, 6);
    u8g2.drawRBox(70, 50, 32, 28, 6);
  } while (u8g2.nextPage());

  Serial.println("OLED_FRAME_DESENHADO");
  delay(1000);
}
