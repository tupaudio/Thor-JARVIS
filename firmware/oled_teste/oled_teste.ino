/*
 * Teste isolado do OLED 1.5" 128x128 SPI (SH1107).
 * Testa a fiação física original do projeto: CS=10, DC=8, RST=7 (CLK=13, DIN=11)
 */
#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>

// PINOS ORIGINAIS DO PROJETO: CS=10, DC=8, RST=7 (Pinos de hardware SPI: CLK=13, DIN=11)
// Se os seus fios estiverem em DC=8 e RST=7, esta linha acende a tela na hora!
U8G2_SH1107_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 8, /* reset=*/ 7);

// Caso a fiação seja DC=9 e RST=8, descomente a linha abaixo:
// U8G2_SH1107_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

void setup() {
  Serial.begin(115200);
  Serial.println("INICIANDO_TESTE_OLED_SH1107");

  u8g2.begin();
  u8g2.setPowerSave(0);
  u8g2.setContrast(255);
}

void loop() {
  u8g2.firstPage();
  do {
    // Moldura externa 128x128
    u8g2.drawFrame(0, 0, 128, 128);
    
    // Linhas diagonais cruzadas em X
    u8g2.drawLine(0, 0, 127, 127);
    u8g2.drawLine(127, 0, 0, 127);
    
    // Texto de confirmação
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(32, 25, "JARVIS OLED");
    
    // Dois olhos robóticos centralizados
    u8g2.drawRBox(28, 50, 30, 26, 6);
    u8g2.drawRBox(70, 50, 30, 26, 6);
  } while (u8g2.nextPage());

  Serial.println("OLED_FRAME_DESENHADO");
  delay(1000);
}
