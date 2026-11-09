/*
 * ==============================================================================
 * J.A.R.V.I.S. - Firmware Oficial: Braço Robótico 4-DOF + Rosto Robótico no OLED
 * Placa: Arduino UNO R3 (ou Nano) + Sensor Shield V5.0
 * Suporta Telas: OLED 128x64 (SSD1306 / SH1106) e 128x128 (SH1107 / SSD1327)
 * ==============================================================================
 *
 * ESQUEMA DE LIGAÇÃO DOS PINOS (Conexões Atualizadas do Usuário):
 *
 * [ SERVOMOTORES SG90 DO BRAÇO 4-DOF ]:
 * - Pino Digital 0 (D0): Servo da Base (Giro Inferior)
 * - Pino Digital 1 (D1): Servo da Elevação Primária (Ombro)
 * - Pino Digital 4 (D4): Servo da Elevação Secundária (Cotovelo)
 * - Pino Digital 5 (D5): Servo da Garra
 *
 * ⚠️ ATENÇÃO TÉCNICA SOBRE PINOS D0 E D1 NO ARDUINO UNO:
 * - Os pinos D0 e D1 são fisicamente compartilhados com a UART Serial (RX/TX) da USB.
 * - Ao enviar comandos seriais em alta taxa (115200 baud), os servos em D0/D1 podem
 *   apresentar pequeno tremor (jitter) se a USB estiver transmitindo continuamente.
 * - O código abaixo gerencia a attach/detach automática e suave para mitigar esse ruído.
 *
 * [ DISPLAY OLED (SPI 7 Pinos) ]:
 * - VCC  -> 3.3V ou 5V (conforme serigrafia do módulo)
 * - GND  -> GND (Trilha G)
 * - DIN  -> Pino Digital 11 (MOSI - Hardware SPI)
 * - CLK  -> Pino Digital 13 (SCK - Hardware SPI)
 * - CS   -> Pino Digital 10 (Chip Select)
 * - DC   -> Pino Digital 9  (Data / Command)
 * - RST  -> Pino Digital 8  (Reset)
 *
 * ATENÇÃO ELÉTRICA:
 * - Remova o jumper 'SEL' da Sensor Shield V5.0.
 * - Conecte fonte externa de 5V 3A nos bornes azuis para alimentar os servos!
 * - Garanta GND COMUM entre Arduino e Fonte Externa.
 *
 * BIBLIOTECA NECESSÁRIA NO ARDUINO IDE:
 * - 'U8g2' de olikraus (Instalar pelo Library Manager)
 */

#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Servo.h>

// ==============================================================================
// 1. SELEÇÃO DO MODELO E RESOLUÇÃO DO DISPLAY OLED
// ==============================================================================
// Descomente apenas UMA das opções abaixo correspondente ao seu display físico:

// OPÇÃO A: OLED 128x64 SSD1306 SPI 0.96" (Mais comum em kits de robótica)
#define OLED_128X64_SSD1306_SPI

// OPÇÃO B: OLED 128x64 SH1106 SPI 1.3"
// #define OLED_128X64_SH1106_SPI

// OPÇÃO C: OLED 128x128 SH1107 SPI 1.5" (GME128128)
// #define OLED_128X128_SH1107_SPI

// OPÇÃO D: OLED 128x64 SSD1306 I2C (Pinos A4=SDA, A5=SCL)
// #define OLED_128X64_SSD1306_I2C

#if defined(OLED_128X64_SSD1306_SPI)
  U8G2_SSD1306_128X64_NONAME_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);
#elif defined(OLED_128X64_SH1106_SPI)
  U8G2_SH1106_128X64_NONAME_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);
#elif defined(OLED_128X128_SH1107_SPI)
  U8G2_SH1107_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);
#elif defined(OLED_128X64_SSD1306_I2C)
  U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);
#else
  // Fallback padrão adaptativo
  U8G2_SSD1306_128X64_NONAME_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);
#endif

// ==============================================================================
// 2. PINOS DOS SERVOS (REMAPEADOS CONFORME SOLICITADO PELO USUÁRIO)
// ==============================================================================
const int PIN_BASE     = 0; // Giro Inferior (D0)
const int PIN_OMBRO    = 1; // Elevação Primária / Ombro (D1)
const int PIN_COTOVELO = 4; // Elevação Secundária / Cotovelo (D4)
const int PIN_GARRA    = 5; // Garra (D5)

Servo servoBase;
Servo servoOmbro;
Servo servoCotovelo;
Servo servoGarra;

int posBase     = 90;
int posOmbro    = 90;
int posCotovelo = 90;
int posGarra    = 30;

// Estados das Expressões Faciais do J.A.R.V.I.S.
enum Expressao {
  FACE_NEUTRO,
  FACE_PISCANDO,
  FACE_OUVINDO,
  FACE_FELIZ,
  FACE_FOCADO,
  FACE_SONO
};

Expressao expressaoAtual = FACE_NEUTRO;
unsigned long ultimoPiscar = 0;
unsigned long tempoInicioPiscar = 0;
bool emPiscar = false;

// Variáveis de geometria de tela dinâmicas (calculadas no setup)
int telaW = 128;
int telaH = 64;
int centroX = 64;
int centroY = 32;

// ==============================================================================
// 3. FUNÇÕES GRÁFICAS AUTOCENTRALIZADAS E ADAPTATIVAS (128x64 ou 128x128)
// ==============================================================================

void desenharOlhos(int alturaOlho, int raioBorda, int deslocX = 0, int deslocY = 0) {
  // Proporções dinâmicas conforme a altura da tela
  int largOlho = (telaH <= 64) ? 26 : 32;
  int separacao = (telaH <= 64) ? 22 : 26;
  
  int xEsq = centroX - separacao + deslocX;
  int xDir = centroX + separacao + deslocX;
  int yTop = centroY - (alturaOlho / 2) + deslocY;

  // Garante que não ultrapasse as bordas da tela
  if (yTop < 0) yTop = 0;
  if (yTop + alturaOlho > telaH) alturaOlho = telaH - yTop;

  u8g2.drawRBox(xEsq - (largOlho / 2), yTop, largOlho, alturaOlho, raioBorda);
  u8g2.drawRBox(xDir - (largOlho / 2), yTop, largOlho, alturaOlho, raioBorda);
}

void desenharFaceFeliz() {
  int raio = (telaH <= 64) ? 12 : 18;
  int separacao = (telaH <= 64) ? 22 : 26;
  int yArc = centroY + (telaH <= 64 ? 2 : 4);

  // Dois semicírculos sorridentes estilizados (^)
  u8g2.drawDisc(centroX - separacao, yArc, raio, U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT);
  u8g2.drawDisc(centroX + separacao, yArc, raio, U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT);
}

void desenharFaceOuvindo() {
  int altOlho = (telaH <= 64) ? 24 : 34;
  int raio = (telaH <= 64) ? 6 : 10;
  desenharOlhos(altOlho, raio, 0, (telaH <= 64 ? -4 : -6));

  // Mini Reator Arc pulsante centralizado na parte inferior da tela
  int yArc = (telaH <= 64) ? 54 : 110;
  int raioArc = (telaH <= 64) ? 4 : 6;
  u8g2.drawCircle(centroX, yArc, raioArc);
  u8g2.drawDisc(centroX, yArc, max(1, raioArc - 3));
}

void desenharFaceSono() {
  int largOlho = (telaH <= 64) ? 26 : 32;
  int separacao = (telaH <= 64) ? 22 : 26;
  int espessura = (telaH <= 64) ? 3 : 4;
  int yLinha = centroY;

  // Dois traços horizontais fechados
  u8g2.drawBox(centroX - separacao - (largOlho / 2), yLinha, largOlho, espessura);
  u8g2.drawBox(centroX + separacao - (largOlho / 2), yLinha, largOlho, espessura);
}

void atualizarDisplay() {
  u8g2.firstPage();
  do {
    switch (expressaoAtual) {
      case FACE_NEUTRO:
        desenharOlhos((telaH <= 64 ? 18 : 28), (telaH <= 64 ? 4 : 8), 0, 0);
        break;
      case FACE_PISCANDO:
        desenharOlhos((telaH <= 64 ? 3 : 4), 1, 0, 0);
        break;
      case FACE_OUVINDO:
        desenharFaceOuvindo();
        break;
      case FACE_FELIZ:
        desenharFaceFeliz();
        break;
      case FACE_FOCADO:
        desenharOlhos((telaH <= 64 ? 14 : 20), (telaH <= 64 ? 3 : 4), 3, -2);
        break;
      case FACE_SONO:
        desenharFaceSono();
        break;
    }
  } while (u8g2.nextPage());
}

// ==============================================================================
// 4. CONTROLE SUAVE DOS SERVOMOTORES
// ==============================================================================

void garantirServosAtivos() {
  if (!servoBase.attached())     servoBase.attach(PIN_BASE);
  if (!servoOmbro.attached())    servoOmbro.attach(PIN_OMBRO);
  if (!servoCotovelo.attached()) servoCotovelo.attach(PIN_COTOVELO);
  if (!servoGarra.attached())    servoGarra.attach(PIN_GARRA);
}

void desenergizarServos() {
  servoBase.detach();
  servoOmbro.detach();
  servoCotovelo.detach();
  servoGarra.detach();
}

void moverSuave(Servo &servo, int &posAtual, int posAlvo, int delayMs = 12) {
  if (posAtual < posAlvo) {
    for (int i = posAtual; i <= posAlvo; i++) {
      servo.write(i);
      delay(delayMs);
    }
  } else {
    for (int i = posAtual; i >= posAlvo; i--) {
      servo.write(i);
      delay(delayMs);
    }
  }
  posAtual = posAlvo;
}

void posturaProntidao() {
  garantirServosAtivos();
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();
  moverSuave(servoGarra, posGarra, 30);
  moverSuave(servoCotovelo, posCotovelo, 90);
  moverSuave(servoOmbro, posOmbro, 90);
  moverSuave(servoBase, posBase, 90);
}

void posturaDescanso() {
  garantirServosAtivos();
  expressaoAtual = FACE_SONO;
  atualizarDisplay();
  moverSuave(servoGarra, posGarra, 10);
  moverSuave(servoCotovelo, posCotovelo, 45);
  moverSuave(servoOmbro, posOmbro, 45);
  moverSuave(servoBase, posBase, 90);
  delay(200);
  desenergizarServos(); // Elimina jitter e resfria os SG90
}

void rotinaAcenar() {
  garantirServosAtivos();
  expressaoAtual = FACE_FELIZ;
  atualizarDisplay();
  for (int j = 0; j < 3; j++) {
    moverSuave(servoBase, posBase, 115, 8);
    moverSuave(servoBase, posBase, 65, 8);
  }
  moverSuave(servoBase, posBase, 90, 8);
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();
}

void rotinaApontar() {
  garantirServosAtivos();
  expressaoAtual = FACE_FOCADO;
  atualizarDisplay();
  moverSuave(servoBase, posBase, 90);
  moverSuave(servoOmbro, posOmbro, 120);
  moverSuave(servoCotovelo, posCotovelo, 120);
  moverSuave(servoGarra, posGarra, 60);
  delay(1200);
  posturaProntidao();
}

// ==============================================================================
// 5. SETUP E LOOP
// ==============================================================================

void setup() {
  // Inicialização serial em 115200 baud
  Serial.begin(115200);

  // Inicializa display U8g2 e detecta dimensão real
  u8g2.begin();
  telaW = u8g2.getDisplayWidth();
  telaH = u8g2.getDisplayHeight();
  centroX = telaW / 2;
  centroY = telaH / 2;

  // Ativa servos nos novos pinos D0, D1, D4, D5
  garantirServosAtivos();
  posturaProntidao();

  Serial.println("JARVIS_ONLINE_READY");
}

void loop() {
  // Animação autônoma de piscar os olhos a cada 3.5 a 5 segundos
  unsigned long agora = millis();
  if (expressaoAtual == FACE_NEUTRO) {
    if (!emPiscar && agora - ultimoPiscar > 3800) {
      emPiscar = true;
      tempoInicioPiscar = agora;
      expressaoAtual = FACE_PISCANDO;
      atualizarDisplay();
    } else if (emPiscar && agora - tempoInicioPiscar > 160) {
      emPiscar = false;
      ultimoPiscar = agora;
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
    }
  }

  // Leitura de comandos vindos do Python (J.A.R.V.I.S. Brain)
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "CMD:WAVE") {
      rotinaAcenar();
      Serial.println("ACK:WAVE_DONE");
    } else if (comando == "CMD:REST") {
      posturaDescanso();
      Serial.println("ACK:REST_DONE");
    } else if (comando == "CMD:READY") {
      posturaProntidao();
      Serial.println("ACK:READY_DONE");
    } else if (comando == "CMD:POINT") {
      rotinaApontar();
      Serial.println("ACK:POINT_DONE");
    } else if (comando == "CMD:FACE:LISTEN") {
      expressaoAtual = FACE_OUVINDO;
      atualizarDisplay();
      Serial.println("ACK:FACE_LISTEN");
    } else if (comando == "CMD:FACE:HAPPY") {
      expressaoAtual = FACE_FELIZ;
      atualizarDisplay();
      Serial.println("ACK:FACE_HAPPY");
    } else if (comando == "CMD:FACE:SLEEP") {
      expressaoAtual = FACE_SONO;
      atualizarDisplay();
      Serial.println("ACK:FACE_SLEEP");
    } else if (comando == "CMD:FACE:NEUTRAL") {
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
      Serial.println("ACK:FACE_NEUTRAL");
    } else {
      Serial.println("ERR:UNKNOWN_CMD");
    }
  }
}
