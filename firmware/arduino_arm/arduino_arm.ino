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
 * - D2: Base (Giro)   - D3: Ombro   - D4: Cotovelo   - D5: Garra
 *   (D0/D1 são a Serial USB: só use-os definindo SERVOS_EM_D0_D1, perdendo o controle pelo HUD)
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
// 1. SELEÇÃO DO MODELO E RESOLUÇÃO DO DISPLAY OLED 1.5" 128x128 SPI (SH1107)
// ==============================================================================
// O chip confirmado no verso é o SH1107 com 5V nos terminais V e G.
// A variante SEEED é a que ativa a bomba de carga (Charge Pump) e contraste
// nos módulos OLED 1.5" chineses GME128128 e genéricos de 7 pinos.

// ==============================================================================
// 1. PINOS E DRIVER DO DISPLAY OLED 1.5" 128x128 SPI (Driver SH1107)
// ==============================================================================
// Fiação Real Confirmada pelo Usuário:
// SCL/CLK -> D13 | SDA/DIN -> D11 | CS -> D10 | DC -> D9 | RST -> D8 | VCC/GND -> D13
//
// Driver oficial com offset zero (PIMORONI layout para módulos 1.5" SH1107 de 7 pinos):
// Elimina o deslocamento horizontal de 32px e o espelhamento de texto (letras invertidas).
U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI u8g2(U8G2_R0, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

// ==============================================================================
// 2. PINOS DOS SERVOS
// ==============================================================================
// ⚠️ D0/D1 SÃO A SERIAL USB (RX/TX) DO ARDUINO UNO. Com servos em D0/D1 o sinal PWM
// do servo disputa a linha RX com o conversor USB: os comandos vindos do servidor/HUD
// chegam corrompidos (ou não chegam) e o TX do Arduino faz os servos tremerem.
// Por isso o padrão é D2/D3 + D4/D5. Só habilite D0/D1 se NÃO precisar de comandos via USB.
//
//   Padrão (comandos do HUD funcionam):  Base=D2  Ombro=D3  Cotovelo=D4  Garra=D5
//   Opcional (SEM controle via USB):      Base=D0  Ombro=D1  Cotovelo=D4  Garra=D5
// #define SERVOS_EM_D0_D1
#ifdef SERVOS_EM_D0_D1
const int PIN_BASE     = 0; // Giro Inferior (D0)  - conflita com USB
const int PIN_OMBRO    = 1; // Elevação Primária (D1) - conflita com USB
#else
const int PIN_BASE     = 2; // Giro Inferior (D2)
const int PIN_OMBRO    = 3; // Elevação Primária / Ombro (D3)
#endif
const int PIN_COTOVELO = 4; // Elevação Secundária / Cotovelo (D4)
const int PIN_GARRA    = 5; // Garra (D5)

Servo servoBase;
Servo servoOmbro;
Servo servoCotovelo;
Servo servoGarra;

int posBase     = 90;
int posOmbro    = 90;
int posCotovelo = 90;
// Garra: calibrada para fechamento seguro sem travar o batente (105 graus) e abertura (30 graus)
int GARRA_ABERTA  = 30;
int GARRA_FECHADA = 105;
int posGarra      = 105;

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

// ==============================================================================
// 3. FUNÇÕES DE DESENHO DO ROSTO ROBÓTICO (128x128 SH1107 ORIGINAL)
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

// Corta o sinal PWM da garra após movimentá-la para eliminar corrente de stall e superaquecimento
void relaxarGarra() {
  delay(200);
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
  moverSuave(servoGarra, posGarra, GARRA_FECHADA);
  relaxarGarra(); // Corta corrente da garra: zero aquecimento!
  moverSuave(servoCotovelo, posCotovelo, 90);
  moverSuave(servoOmbro, posOmbro, 90);
  // Movimento de teste da Base: varredura ampla (130 -> 50 -> 90) para superar atrito e comprovar giro
  moverSuave(servoBase, posBase, 130, 15);
  moverSuave(servoBase, posBase, 50, 15);
  moverSuave(servoBase, posBase, 90, 15);
}

void posturaDescanso() {
  garantirServosAtivos();
  expressaoAtual = FACE_SONO;
  atualizarDisplay();
  moverSuave(servoGarra, posGarra, GARRA_FECHADA);
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
  moverSuave(servoGarra, posGarra, GARRA_FECHADA);
  delay(1200);
  posturaProntidao();
}

// ==============================================================================
// 5. SETUP E LOOP
// ==============================================================================

void setup() {
  Serial.begin(115200);

  // Pulso de Reset físico no D8 para inicialização limpa do controlador SH1107
  pinMode(8, OUTPUT);
  digitalWrite(8, LOW);
  delay(25);
  digitalWrite(8, HIGH);
  delay(50);

  u8g2.begin();
  u8g2.setPowerSave(0);
  u8g2.setContrast(255);

  // Tela de diagnóstico visual ao ligar
  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.setFont(u8g2_font_helvB10_tr);
    u8g2.drawStr(34, 45, "JARVIS");
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(42, 65, "ONLINE");
    u8g2.drawDisc(64, 95, 10);
    u8g2.drawCircle(64, 95, 14);
  } while (u8g2.nextPage());
  delay(1000);

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
    } else if (comando == "CMD:GARRA:OPEN") {
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, GARRA_ABERTA);
      relaxarGarra();
      Serial.println("ACK:GARRA_OPEN");
    } else if (comando == "CMD:GARRA:CLOSE") {
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, GARRA_FECHADA);
      relaxarGarra();
      Serial.println("ACK:GARRA_CLOSE");
    } else if (comando.startsWith("CMD:GARRA:")) {
      int ang = constrain(comando.substring(10).toInt(), 0, 180);
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, ang);
      relaxarGarra();
      Serial.print("ACK:GARRA_"); Serial.println(ang);
    } else if (comando.startsWith("CMD:BASE:")) {
      int ang = constrain(comando.substring(9).toInt(), 0, 180);
      garantirServosAtivos();
      moverSuave(servoBase, posBase, ang, 15);
      Serial.print("ACK:BASE_"); Serial.println(ang);
    } else if (comando == "CMD:SWEEP:BASE") {
      garantirServosAtivos();
      for (int k = 0; k < 2; k++) {
        moverSuave(servoBase, posBase, 130, 15);
        moverSuave(servoBase, posBase, 50, 15);
      }
      moverSuave(servoBase, posBase, 90, 15);
      Serial.println("ACK:SWEEP_BASE_DONE");
    } else if (comando == "CMD:OLED:RESET" || comando == "CMD:FACE:RESET") {
      pinMode(8, OUTPUT);
      digitalWrite(8, LOW);
      delay(25);
      digitalWrite(8, HIGH);
      delay(50);
      u8g2.begin();
      u8g2.setPowerSave(0);
      u8g2.setContrast(255);
      atualizarDisplay();
      Serial.println("ACK:OLED_RESET_DONE");
    } else if (comando == "CMD:FACE:FOCUS") {
      expressaoAtual = FACE_FOCADO;
      atualizarDisplay();
      Serial.println("ACK:FACE_FOCUS");
    } else if (comando == "CMD:FACE:NEUTRAL") {
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
      Serial.println("ACK:FACE_NEUTRAL");
    } else {
      Serial.println("ERR:UNKNOWN_CMD");
    }
  }
}
