/*
 * ==============================================================================
 * J.A.R.V.I.S. - Firmware Oficial: Braço Robótico 4-DOF + Rosto Robótico Realista no OLED
 * Placa: Arduino UNO R3 (ou Nano) + Sensor Shield V5.0
 * Suporta Telas: OLED 128x128 SPI (Driver SH1107 / Pimoroni layout)
 * ==============================================================================
 *
 * ESQUEMA DE LIGAÇÃO DOS PINOS:
 *
 * [ SERVOMOTORES SG90 DO BRAÇO 4-DOF ]:
 * - D2: Base (Giro)   - D3: Ombro   - D4: Cotovelo   - D5: Garra
 * - D6: Base Paralela Espelhada (Backup para Shield)
 *
 * [ DISPLAY OLED SH1107 1.5" SPI (7 Pinos) ]:
 * - VCC  -> 5V (Trilha V)
 * - GND  -> GND (Trilha G)
 * - DIN  -> Pino Digital 11 (MOSI - Hardware SPI)
 * - CLK  -> Pino Digital 13 (SCK - Hardware SPI)
 * - CS   -> Pino Digital 10 (Chip Select)
 * - DC   -> Pino Digital 9  (Data / Command)
 * - RST  -> Pino Digital 8  (Hardware Reset)
 *
 * ROTAÇÃO:
 * - U8G2_R2 (180 graus): compensa a montagem invertida para saída de cabos
 */

#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Servo.h>

#define U8G2_SEMICIRCLE_UPPER (U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT)
#define U8G2_SEMICIRCLE_LOWER (U8G2_DRAW_LOWER_RIGHT | U8G2_DRAW_LOWER_LEFT)

// ==============================================================================
// 1. DISPLAY OLED 1.5" SH1107 SPI (180 graus com U8G2_R2)
// ==============================================================================
U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI u8g2(U8G2_R2, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

// ==============================================================================
// 2. PINOS DOS SERVOMOTORES
// ==============================================================================
const int PIN_BASE     = 2; // Giro Inferior (D2)
const int PIN_BASE_D6  = 6; // Giro Inferior Espelhado (D6)
const int PIN_OMBRO    = 3; // Ombro (D3)
const int PIN_COTOVELO = 4; // Cotovelo (D4)
const int PIN_GARRA    = 5; // Garra (D5)

Servo servoBase;
Servo servoBase6;
Servo servoOmbro;
Servo servoCotovelo;
Servo servoGarra;

int posBase     = 90;
int posOmbro    = 90;
int posCotovelo = 90;
int GARRA_ABERTA  = 25;   // Abertura ampla calibrada
int GARRA_FECHADA = 105;  // Fechamento suave sem bater batente
int posGarra      = 105;

// Proteção Térmica Universal SG90 (Auto-detach de todos os servos)
unsigned long ultimoMovimentoTs = 0;
bool servosEnergizados = false;

// Estados das Expressões Faciais Humanoides
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
int olharOffset = 0;
unsigned long ultimoOlhar = 0;
char nomePersona[16] = "J.A.R.V.I.S.";

// ==============================================================================
// 3. CONTROLE TÉRMICO E ACIONAMENTO SUAVE DOS SERVOS
// ==============================================================================

void garantirServosAtivos() {
  if (!servoBase.attached())     servoBase.attach(PIN_BASE);
  if (!servoBase6.attached())    servoBase6.attach(PIN_BASE_D6);
  if (!servoOmbro.attached())    servoOmbro.attach(PIN_OMBRO);
  if (!servoCotovelo.attached()) servoCotovelo.attach(PIN_COTOVELO);
  if (!servoGarra.attached())    servoGarra.attach(PIN_GARRA);
  servosEnergizados = true;
  ultimoMovimentoTs = millis();
}

void desenergizarServos() {
  servoBase.detach();
  servoBase6.detach();
  servoOmbro.detach();
  servoCotovelo.detach();
  servoGarra.detach();
  servosEnergizados = false;
}

void moverSuave(Servo &servo, int &posAtual, int posAlvo, int delayMs = 12) {
  garantirServosAtivos();
  if (posAtual < posAlvo) {
    for (int i = posAtual; i <= posAlvo; i++) {
      servo.write(i);
      if (&servo == &servoBase && servoBase6.attached()) servoBase6.write(i);
      delay(delayMs);
    }
  } else {
    for (int i = posAtual; i >= posAlvo; i--) {
      servo.write(i);
      if (&servo == &servoBase && servoBase6.attached()) servoBase6.write(i);
      delay(delayMs);
    }
  }
  posAtual = posAlvo;
  ultimoMovimentoTs = millis();
}

// ==============================================================================
// 4. DESENHO DO ROSTO ROBÓTICO EXPRESSIVO NO OLED (128x128 SH1107)
// Estilo: Robô Social / Astro Bot / EVE / Emoji Casing
// ==============================================================================

void desenharCabecaRobo() {
  // 1. Badge dinâmico no topo com nome da Persona ativa
  u8g2.setFont(u8g2_font_5x8_tf);
  int w = u8g2.getStrWidth(nomePersona);
  int x = (128 - w) / 2;
  u8g2.drawLine(x - 5, 2, x + w + 4, 2);
  u8g2.drawLine(x - 5, 12, x + w + 4, 12);
  u8g2.drawLine(x - 5, 2, x - 5, 12);
  u8g2.drawLine(x + w + 4, 2, x + w + 4, 12);
  u8g2.drawStr(x, 10, nomePersona);

  // 2. Módulos de Áudio / Orelhas Laterais (Ear Pods em cápsula)
  // Orelha esquerda
  u8g2.drawRBox(6, 48, 10, 36, 4);
  u8g2.setDrawColor(0);
  u8g2.drawBox(9, 54, 2, 24);
  u8g2.setDrawColor(1);

  // Orelha direita
  u8g2.drawRBox(112, 48, 10, 36, 4);
  u8g2.setDrawColor(0);
  u8g2.drawBox(117, 54, 2, 24);
  u8g2.setDrawColor(1);

  // 3. Capacete / Carcaça do Robô (Duplo contorno suave de domo)
  u8g2.drawRFrame(17, 15, 94, 108, 26);
  u8g2.drawRFrame(18, 16, 92, 106, 25);

  // Sensor frontal no topo do capacete
  u8g2.drawDisc(64, 22, 2);
}

void desenharFaceRobo(Expressao exp) {
  desenharCabecaRobo();

  int ox = olharOffset;

  switch (exp) {
    case FACE_NEUTRO:
      // Sobrancelhas sutis
      u8g2.drawLine(34, 38, 52, 38);
      u8g2.drawLine(76, 38, 94, 38);

      // Olhos grandes brilhantes em pílula com reflexo de luz
      u8g2.drawRBox(33 + ox, 44, 18, 24, 8);
      u8g2.drawRBox(77 + ox, 44, 18, 24, 8);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(38 + ox, 49, 3);
      u8g2.drawDisc(82 + ox, 49, 3);
      u8g2.drawPixel(43 + ox, 58);
      u8g2.drawPixel(87 + ox, 58);
      u8g2.setDrawColor(1);

      // Sorriso suave e amigável
      u8g2.drawCircle(64, 82, 15, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(64, 81, 15, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(49, 85, 51, 82);
      u8g2.drawLine(79, 85, 77, 82);
      break;

    case FACE_PISCANDO:
      // Sobrancelhas relaxadas
      u8g2.drawLine(34, 40, 52, 40);
      u8g2.drawLine(76, 40, 94, 40);

      // Pálpebras fechadas em curvas suaves (︶ ︶)
      u8g2.drawCircle(42, 54, 13, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(42, 53, 13, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(86, 54, 13, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(86, 53, 13, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(29, 58, 33, 55);
      u8g2.drawLine(99, 58, 95, 55);

      // Boca serena
      u8g2.drawRBox(54, 86, 20, 3, 1);
      break;

    case FACE_FELIZ:
      // Olhos sorridentes em arco vibrante (^ ^)
      u8g2.drawCircle(42, 58, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(42, 57, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(42, 56, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(86, 58, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(86, 57, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(86, 56, 14, U8G2_SEMICIRCLE_UPPER);

      // Bochechas brilhantes de alegria (blush pills)
      u8g2.drawRBox(26, 68, 10, 4, 2);
      u8g2.drawRBox(92, 68, 10, 4, 2);

      // Sorriso aberto caloroso
      u8g2.drawCircle(64, 82, 18, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(64, 81, 18, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(46, 82, 82, 82);
      u8g2.drawLine(46, 83, 82, 83);
      break;

    case FACE_OUVINDO:
      // Olhos grandes totalmente circulares e alertas (O O)
      u8g2.drawDisc(42, 54, 14);
      u8g2.drawDisc(86, 54, 14);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(39, 50, 4);
      u8g2.drawDisc(83, 50, 4);
      u8g2.setDrawColor(1);

      // Boca aberta expressiva falando / ouvindo
      u8g2.drawRBox(56, 84, 16, 14, 6);
      u8g2.setDrawColor(0);
      u8g2.drawRBox(58, 86, 12, 10, 4);
      u8g2.setDrawColor(1);

      // Ondas sonoras nas orelhas
      u8g2.drawLine(2, 60, 4, 60);
      u8g2.drawLine(2, 72, 4, 72);
      u8g2.drawLine(124, 60, 126, 60);
      u8g2.drawLine(124, 72, 126, 72);
      break;

    case FACE_FOCADO:
      // VISEIRA CIBERNÉTICA SCI-FI (Estilo Daft Punk / Ciclope / Emoji da foto!)
      u8g2.drawRBox(25, 45, 78, 22, 5);
      u8g2.setDrawColor(0);
      u8g2.drawRBox(29, 49, 70, 14, 3);
      u8g2.setDrawColor(1);

      // Barra de escaneamento ótico luminosa dentro da viseira
      u8g2.drawBox(42 + ox * 4, 53, 26, 6);
      u8g2.drawPixel(38 + ox * 4, 55);
      u8g2.drawPixel(39 + ox * 4, 55);
      u8g2.drawPixel(70 + ox * 4, 55);
      u8g2.drawPixel(71 + ox * 4, 55);

      // Boca analítica concentrada
      u8g2.drawRBox(52, 90, 24, 4, 2);
      break;

    case FACE_SONO:
      // Olhos cerrados relaxados
      u8g2.drawCircle(42, 56, 12, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(42, 55, 12, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(86, 56, 12, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(86, 55, 12, U8G2_SEMICIRCLE_LOWER);

      // Boca serena
      u8g2.drawBox(56, 88, 16, 2);

      // Partículas flutuantes "Z z z"
      u8g2.setFont(u8g2_font_helvB10_tr);
      u8g2.drawStr(94, 36, "Z");
      u8g2.setFont(u8g2_font_6x10_tf);
      u8g2.drawStr(106, 26, "z");
      u8g2.setFont(u8g2_font_4x6_tf);
      u8g2.drawStr(114, 18, "z");
      break;
  }
}

void atualizarDisplay() {
  u8g2.firstPage();
  do {
    desenharFaceRobo(expressaoAtual);
  } while (u8g2.nextPage());
}

// ==============================================================================
// 5. ROTINAS DE MOVIMENTO E DIAGNÓSTICO
// ==============================================================================

// Executada APENAS UMA VEZ no setup() ao ligar o Arduino
void rotinaDiagnosticoInicial() {
  garantirServosAtivos();

  // 1. Diagnóstico da Garra: abre amplamente (25°), pausa visível (400ms) e fecha (105°)
  moverSuave(servoGarra, posGarra, GARRA_ABERTA, 10);
  delay(400);
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 10);
  delay(150);

  // 2. Diagnóstico da Base: varredura ampla (130 -> 50 -> 90) em D2 e D6
  moverSuave(servoBase, posBase, 130, 14);
  moverSuave(servoBase, posBase, 50, 14);
  moverSuave(servoBase, posBase, 90, 14);

  // 3. Diagnóstico do Ombro: varredura suave (110 -> 70 -> 90)
  moverSuave(servoOmbro, posOmbro, 110, 14);
  moverSuave(servoOmbro, posOmbro, 70, 14);
  moverSuave(servoOmbro, posOmbro, 90, 14);

  // 4. Diagnóstico do Cotovelo: varredura suave (110 -> 70 -> 90)
  moverSuave(servoCotovelo, posCotovelo, 110, 14);
  moverSuave(servoCotovelo, posCotovelo, 70, 14);
  moverSuave(servoCotovelo, posCotovelo, 90, 14);

  ultimoMovimentoTs = millis();
}

void posturaProntidao() {
  garantirServosAtivos();
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();

  // 1. Abre a garra primeiro
  moverSuave(servoGarra, posGarra, GARRA_ABERTA, 10);

  // 2. Faz o movimento do braço para a postura ereta de alerta
  moverSuave(servoBase, posBase, 90, 12);
  moverSuave(servoOmbro, posOmbro, 90, 12);
  moverSuave(servoCotovelo, posCotovelo, 90, 12);

  // 3. Fecha a garra por último
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 10);

  ultimoMovimentoTs = millis();
}

void posturaDescanso() {
  garantirServosAtivos();
  expressaoAtual = FACE_SONO;
  atualizarDisplay();

  // 1. Abre a garra primeiro
  moverSuave(servoGarra, posGarra, GARRA_ABERTA, 10);

  // 2. Faz o movimento do braço para recolhimento seguro
  moverSuave(servoBase, posBase, 90, 12);
  moverSuave(servoCotovelo, posCotovelo, 45, 12);
  moverSuave(servoOmbro, posOmbro, 45, 12);

  // 3. Fecha a garra por último
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 10);
  delay(150);

  // 4. Proteção térmica imediata em todos os servos
  desenergizarServos();
}

void rotinaAcenar() {
  garantirServosAtivos();
  expressaoAtual = FACE_FELIZ;
  atualizarDisplay();

  // 1. Ergue o braço para saudar
  moverSuave(servoOmbro, posOmbro, 80, 10);
  moverSuave(servoCotovelo, posCotovelo, 80, 10);

  // 2. Aceno expressivo de um lado para o outro
  for (int j = 0; j < 3; j++) {
    moverSuave(servoBase, posBase, 120, 8);
    moverSuave(servoBase, posBase, 60, 8);
  }
  moverSuave(servoBase, posBase, 90, 8);

  // 3. Abre a garra, mantém aberta por 2 segundos e depois fecha
  moverSuave(servoGarra, posGarra, GARRA_ABERTA, 10);
  delay(2000);
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 10);

  posturaProntidao();
}

void rotinaApontar() {
  garantirServosAtivos();
  expressaoAtual = FACE_FOCADO;
  atualizarDisplay();

  // 1. Estende o braço apontando para a frente
  moverSuave(servoBase, posBase, 90, 10);
  moverSuave(servoOmbro, posOmbro, 120, 10);
  moverSuave(servoCotovelo, posCotovelo, 120, 10);

  // 2. Abre e fecha a garra uma vez
  moverSuave(servoGarra, posGarra, GARRA_ABERTA, 10);
  delay(300);
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 10);
  delay(800);

  posturaProntidao();
}

// ==============================================================================
// 6. SETUP E LOOP PRINCIPAL
// ==============================================================================

void setup() {
  Serial.begin(115200);

  // Pulso de Hardware Reset no D8 para inicialização limpa do controlador SH1107
  pinMode(8, OUTPUT);
  digitalWrite(8, LOW);
  delay(25);
  digitalWrite(8, HIGH);
  delay(50);

  u8g2.begin();
  u8g2.setPowerSave(0);
  u8g2.setContrast(255);

  // Tela de apresentação inicial com a face do robô
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();
  delay(600);

  // Executa diagnóstico dos 4 servos apenas no boot
  rotinaDiagnosticoInicial();

  // Face neutra ativa (pronta e piscando autonomamente)
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();

  // Desenergiza os servos após o diagnóstico: proteção térmica inicial
  desenergizarServos();

  Serial.println("JARVIS_ONLINE_READY");
}

void loop() {
  unsigned long agora = millis();

  // 1. Proteção Térmica Total: se os servos ficarem 1.5s inativos, desliga o sinal PWM de todos eles
  if (servosEnergizados && (agora - ultimoMovimentoTs > 1500)) {
    desenergizarServos();
  }

  // 2. Animação Autônoma da Face Humanoide (Piscar + Micro-sacadas)
  if (expressaoAtual == FACE_NEUTRO) {
    // Piscar a cada 3.8s
    if (!emPiscar && agora - ultimoPiscar > 3800) {
      emPiscar = true;
      tempoInicioPiscar = agora;
      expressaoAtual = FACE_PISCANDO;
      atualizarDisplay();
    } else if (emPiscar && agora - tempoInicioPiscar > 140) {
      emPiscar = false;
      ultimoPiscar = agora;
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
    }

    // Micro-sacada de olhar a cada 7.5s (dá sensação de consciência observando o ambiente)
    if (!emPiscar && agora - ultimoOlhar > 7500) {
      ultimoOlhar = agora;
      static int seqOlhar = 0;
      seqOlhar = (seqOlhar + 1) % 4;
      if (seqOlhar == 1) olharOffset = 2;
      else if (seqOlhar == 3) olharOffset = -2;
      else olharOffset = 0;
      atualizarDisplay();
    }
  }

  // 3. Processamento de Comandos Seriais do Python (J.A.R.V.I.S. Brain)
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "CMD:PING" || comando == "PING") {
      Serial.println("ACK:JARVIS_ARM_PONG");
    } else if (comando == "CMD:WAVE") {
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
    } else if (comando == "CMD:FACE:FOCUS") {
      expressaoAtual = FACE_FOCADO;
      atualizarDisplay();
      Serial.println("ACK:FACE_FOCUS");
    } else if (comando == "CMD:FACE:NEUTRAL") {
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
      Serial.println("ACK:FACE_NEUTRAL");
    } else if (comando == "CMD:GARRA:OPEN") {
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, GARRA_ABERTA);
      Serial.println("ACK:GARRA_OPEN");
    } else if (comando == "CMD:GARRA:CLOSE") {
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, GARRA_FECHADA);
      Serial.println("ACK:GARRA_CLOSE");
    } else if (comando.startsWith("CMD:GARRA:")) {
      int ang = constrain(comando.substring(10).toInt(), 0, 180);
      garantirServosAtivos();
      moverSuave(servoGarra, posGarra, ang);
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
    } else if (comando.startsWith("CMD:PERSONA:")) {
      String p = comando.substring(12);
      p.trim();
      if (p.length() > 0 && p.length() < 16) {
        p.toCharArray(nomePersona, sizeof(nomePersona));
        atualizarDisplay();
        Serial.print("ACK:PERSONA_"); Serial.println(nomePersona);
      }
    } else {
      Serial.println("ERR:UNKNOWN_CMD");
    }
  }
}
