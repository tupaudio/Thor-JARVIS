/*
 * Teste isolado do OLED 1.5" 128x128 SPI (SH1107). Sem servos e sem serial.
 * Pinos: CLK(D0 da tela)=13, DIN(D1 da tela)=11, CS=10, DC=9, RST=8.
 * Troque o driver abaixo (descomente UM) se a tela continuar apagada ou torta.
 * Grave com: arduino-cli compile/upload --fqbn arduino:avr:uno firmware/oled_teste
 */
#include <U8g2lib.h>
#include <SPI.h>

U8G2_SH1107_128X128_1_4W_SW_SPI u8g2(U8G2_R0, 13, 11, 10, 9, 8);          // 1) SH1107 original, SPI por software
//U8G2_SH1107_128X128_1_4W_HW_SPI u8g2(U8G2_R0, 10, 9, 8);                 // 2) SH1107 original, SPI por hardware
//U8G2_SH1107_PIMORONI_128X128_1_4W_SW_SPI u8g2(U8G2_R0, 13, 11, 10, 9, 8); // 3) Pimoroni
//U8G2_SH1107_SEEED_128X128_1_4W_SW_SPI u8g2(U8G2_R0, 13, 11, 10, 9, 8);   // 4) Seeed
//U8G2_SSD1327_WS_128X128_1_4W_SW_SPI u8g2(U8G2_R0, 13, 11, 10, 9, 8);     // 5) SSD1327

void setup() {
  u8g2.begin();
  u8g2.setPowerSave(0);
}

void loop() {
  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.drawLine(0, 0, 127, 127);
    u8g2.drawLine(127, 0, 0, 127);
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(34, 20, "TESTE OLED");
    u8g2.drawRBox(30, 50, 26, 28, 6);
    u8g2.drawRBox(72, 50, 26, 28, 6);
  } while (u8g2.nextPage());
  delay(500);
}
