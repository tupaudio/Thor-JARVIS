/*
 * ==============================================================================
 * J.A.R.V.I.S. - Firmware Completo: Braço Robótico + Rosto Robótico no OLED 1.5"
 * Placa: Arduino UNO + Sensor Shield V5.0
 * Display: OLED 1.5" 128x128 SPI (Waveshare SSD1327)
 * ==============================================================================
 * 
 * ESQUEMA DE LIGAÇÃO DOS PINOS (Na Sensor Shield V5.0):
 * 
 * [ DISPLAY OLED 1.5" SPI ]:
 * - VCC  -> 5V ou 3.3V (Trilha V)
 * - GND  -> GND (Trilha G)
 * - DIN  -> Pino Digital 11 (MOSI - Hardware SPI)
 * - CLK  -> Pino Digital 13 (SCK - Hardware SPI)
 * - CS   -> Pino Digital 10 (Chip Select)
 * - DC   -> Pino Digital 8  (Data / Command)
 * - RST  -> Pino Digital 7  (Reset)
 * 
 * [ SERVOMOTORES DO BRAÇO ]:
 * - Pino Digital 2: Servo da Base (Giro)
 * - Pino Digital 3: Servo do Ombro
 * - Pino Digital 5: Servo do Cotovelo
 * - Pino Digital 6: Servo da Garra
 * 
 * ATENÇÃO ELÉTRICA:
 * - Remova o jumper 'SEL' da Sensor Shield V5.0.
 * - Ligue a fonte externa 5V 3A no borne azul de parafuso para alimentar os servos!
 * 
 * BIBLIOTECA NECESSÁRIA NO ARDUINO IDE:
 * - 'U8g2' de olikraus (instale pelo Gerenciador de Bibliotecas da Arduino IDE)
 */

#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Servo.h>

// Construtor do Display SSD1327 128x128 SPI usando Page Buffer (Gasta só 128 bytes de RAM!)
U8G2_SSD1327_WS_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 8, /* reset=*/ 7);

// Servos
Servo servoBase;
Servo servoOmbro;
Servo servoCotovelo;
Servo servoGarra;

const int PIN_BASE     = 2;
const int PIN_OMBRO    = 3;
const int PIN_COTOVELO = 5;
const int PIN_GARRA    = 6;

int posBase     = 90;
int posOmbro    = 90;
int posCotovelo = 90;
int posGarra    = 30;

// Estados das Expressões Faciais
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

// ==============================================================================
// FUNÇÕES DE DESENHO DO ROSTO ROBÓTICO (Procedural Vector Eyes)
// ==============================================================================

void desenharOlhos(int alturaOlho, int raioBorda, int deslocX = 0, int deslocY = 0) {
  // Olho Esquerdo: centro em x=42, y=64
  // Olho Direito:  centro em x=86, y=64
  int largura = 32;
  int yTop = 64 - (alturaOlho / 2) + deslocY;
  
  u8g2.drawRBox(42 - (largura / 2) + deslocX, yTop, largura, alturaOlho, raioBorda);
  u8g2.drawRBox(86 - (largura / 2) + deslocX, yTop, largura, alturaOlho, raioBorda);
}

void desenharFaceFeliz() {
  // Dois arcos sorridentes estilizados (^)
  u8g2.drawDisc(42, 60, 18, U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT);
  u8g2.drawDisc(86, 60, 18, U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT);
}

void desenharFaceOuvindo() {
  // Olhos arregalados e reator Arc sutil pulsante
  desenharOlhos(34, 10, 0, 0);
  u8g2.drawCircle(64, 110, 6);
  u8g2.drawDisc(64, 110, 2);
}

void desenharFaceSono() {
  // Olhos fechados (duas linhas horizontais espessas)
  u8g2.drawBox(26, 64, 32, 4);
  u8g2.drawBox(70, 64, 32, 4);
}

void atualizarDisplay() {
  u8g2.firstPage();
  do {
    switch (expressaoAtual) {
      case FACE_NEUTRO:
        desenharOlhos(28, 8, 0, 0);
        break;
      case FACE_PISCANDO:
        desenharOlhos(4, 2, 0, 0);
        break;
      case FACE_OUVINDO:
        desenharFaceOuvindo();
        break;
      case FACE_FELIZ:
        desenharFaceFeliz();
        break;
      case FACE_FOCADO:
        desenharOlhos(20, 4, 4, -4);
        break;
      case FACE_SONO:
        desenharFaceSono();
        break;
    }
  } while (u8g2.nextPage());
}

// ==============================================================================
// MOVIMENTAÇÃO SUAVE DOS SERVOS
// ==============================================================================

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
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();
  moverSuave(servoGarra, posGarra, 30);
  moverSuave(servoCotovelo, posCotovelo, 90);
  moverSuave(servoOmbro, posOmbro, 90);
  moverSuave(servoBase, posBase, 90);
}

void posturaDescanso() {
  expressaoAtual = FACE_SONO;
  atualizarDisplay();
  moverSuave(servoGarra, posGarra, 10);
  moverSuave(servoCotovelo, posCotovelo, 45);
  moverSuave(servoOmbro, posOmbro, 45);
  moverSuave(servoBase, posBase, 90);
}

void rotinaAcenar() {
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
  expressaoAtual = FACE_FOCADO;
  atualizarDisplay();
  moverSuave(servoBase, posBase, 90);
  moverSuave(servoOmbro, posOmbro, 120);
  moverSuave(servoCotovelo, posCotovelo, 120);
  moverSuave(servoGarra, posGarra, 60);
  delay(1200);
  posturaProntidao();
}

void setup() {
  Serial.begin(115200);
  
  u8g2.begin();
  
  servoBase.attach(PIN_BASE);
  servoOmbro.attach(PIN_OMBRO);
  servoCotovelo.attach(PIN_COTOVELO);
  servoGarra.attach(PIN_GARRA);
  
  posturaProntidao();
  Serial.println("JARVIS_ONLINE_READY");
}

void loop() {
  // Piscar de olhos autônomo e natural a cada 3 a 5 segundos
  unsigned long agora = millis();
  if (expressaoAtual == FACE_NEUTRO) {
    if (!emPiscar && agora - ultimoPiscar > 3500) {
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

  // Escuta comandos do Python via Serial
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
