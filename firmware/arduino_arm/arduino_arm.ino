/*
 * ==============================================================================
 * J.A.R.V.I.S. - Firmware Oficial Auditado: Braço 4-DOF + Rosto no OLED 1.5"
 * Placa: Arduino UNO R3 (ATmega328P) + Sensor Shield V5.0
 * 
 * AUDITORIA COMPLETA INTEGRADA (Claude + ChatGPT):
 * 1. Nova Fiação OLED Software SPI (CLK=8, DIN=9, DC=10, CS=11, RST=12)
 * 2. Limites mecânicos individuais por junta (evita stall e superaquecimento)
 * 3. Movimentação isolada sem acionamento cruzado de servos
 * 4. Parser serial protegido contra overflow de buffer
 * 5. Watchdog de 4 segundos contra travamentos de barramento
 * 6. Comandos de teste individual por junta (CMD:TEST:D3/D4/D5/D6)
 * ==============================================================================
 */

#include <Arduino.h>
#include <avr/pgmspace.h>
#include <avr/wdt.h>
#include <U8g2lib.h>
#include <Servo.h>

// ---------------- CONFIGURAÇÃO DO DISPLAY OLED (HARDWARE SPI) ----------------
// Configuração Oficial Comprovada (commit 0bde085):
// - SCL (CLK) -> D13 (SCK - Hardware SPI)
// - SDA (DIN) -> D11 (MOSI - Hardware SPI)
// - CS        -> D10 (Chip Select)
// - DC        -> D9  (Data / Command)
// - RST       -> D8  (Hardware Reset)
U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI u8g2(U8G2_R2, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

#define U8G2_SEMICIRCLE_UPPER (U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT)
#define U8G2_SEMICIRCLE_LOWER (U8G2_DRAW_LOWER_RIGHT | U8G2_DRAW_LOWER_LEFT)

// ---------------- SERVOMOTORES & LIMITES MECÂNICOS SEGUROS ----------------
const uint8_t PIN_BASE     = 6; // Base giratória (D6)
const uint8_t PIN_BASE_D2  = 2; // Reserva isolada
const uint8_t PIN_OMBRO    = 3; // Ombro (D3)
const uint8_t PIN_COTOVELO = 4; // Cotovelo (D4)
const uint8_t PIN_GARRA    = 5; // Garra (D5)

#define BASE_DUPLA_D2    0      // 1 SOMENTE se houver um 2º servo físico no D2
#define DIAG_NO_BOOT     0      // 0 = boot rápido e silencioso (evita flapping do braço por DTR)
#define TEMPO_DETACH_MS  2000UL // Tempo de inatividade (ms) até cortar PWM (proteção térmica)

// Limites angulares calibrados para braço de acrílico (protegem contra stall)
const int BASE_MIN     = 45, BASE_MAX     = 135;
const int OMBRO_MIN    = 45, OMBRO_MAX    = 105;
const int COTOVELO_MIN = 40, COTOVELO_MAX = 70;  // Nunca passar de 70° no cotovelo!
const int GARRA_MIN    = 50, GARRA_MAX    = 100;

// Posições pré-definidas
const int BASE_CENTRO        = 90;
const int OMBRO_PRONTIDAO    = 85;
const int OMBRO_DESCANSO     = 45;
const int COTOVELO_PRONTIDAO = 60;
const int COTOVELO_DESCANSO  = 45;
const int GARRA_ABERTA       = 60;
const int GARRA_FECHADA      = 100;

Servo servoBase, servoOmbro, servoCotovelo, servoGarra;
#if BASE_DUPLA_D2
Servo servoBase2;
#endif

int posBase     = BASE_CENTRO;
int posOmbro    = OMBRO_PRONTIDAO;
int posCotovelo = COTOVELO_PRONTIDAO;
int posGarra    = GARRA_FECHADA;

unsigned long ultimoMovimentoTs = 0;
bool servosEnergizados = false;

enum Expressao { FACE_NEUTRO, FACE_PISCANDO, FACE_OUVINDO, FACE_FELIZ, FACE_FOCADO, FACE_SONO };

Expressao expressaoAtual = FACE_NEUTRO;
unsigned long ultimoPiscar = 0, tempoInicioPiscar = 0, ultimoOlhar = 0;
bool emPiscar = false;
int olharOffset = 0;
char nomePersona[16] = "J.A.R.V.I.S.";

// ---------------- DISPLAY & ROSTO REALISTA HUD ----------------
static void drawStrF(uint8_t x, uint8_t y, const __FlashStringHelper *f) {
  char b[12];
  strncpy_P(b, (PGM_P)f, sizeof(b) - 1);
  b[sizeof(b) - 1] = 0;
  u8g2.drawStr(x, y, b);
}

void desenharMolduraHUD() {
  u8g2.drawLine(2, 2, 14, 2);     u8g2.drawLine(2, 2, 2, 14);
  u8g2.drawLine(113, 2, 125, 2);  u8g2.drawLine(125, 2, 125, 14);
  u8g2.drawLine(2, 125, 14, 125); u8g2.drawLine(2, 125, 2, 113);
  u8g2.drawLine(113, 125, 125, 125); u8g2.drawLine(125, 125, 125, 113);

  u8g2.setFont(u8g2_font_5x8_tr);
  int w = u8g2.getStrWidth(nomePersona);
  int x = (128 - w) / 2;
  u8g2.drawLine(x - 5, 3, x + w + 4, 3);
  u8g2.drawLine(x - 5, 13, x + w + 4, 13);
  u8g2.drawLine(x - 5, 3, x - 5, 13);
  u8g2.drawLine(x + w + 4, 3, x + w + 4, 13);
  u8g2.drawStr(x, 11, nomePersona);

  u8g2.drawDisc(5, 5, 2);
  u8g2.drawDisc(122, 5, 2);
}

void desenharEstruturaHumanoide() {
  u8g2.drawLine(16, 70, 22, 78);  u8g2.drawLine(111, 70, 105, 78);
  u8g2.drawLine(22, 78, 28, 92);  u8g2.drawLine(105, 78, 99, 92);
  u8g2.drawLine(52, 115, 75, 115);
  u8g2.drawLine(52, 115, 46, 109); u8g2.drawLine(75, 115, 81, 109);
  u8g2.drawLine(64, 60, 64, 73);
  u8g2.drawLine(61, 76, 67, 76);
  u8g2.drawLine(61, 76, 64, 73);   u8g2.drawLine(67, 76, 64, 73);
}

void desenharFaceRealista(Expressao exp) {
  desenharMolduraHUD();
  desenharEstruturaHumanoide();
  int ox = olharOffset;

  switch (exp) {
    case FACE_NEUTRO:
      u8g2.drawLine(22, 33, 50, 31); u8g2.drawLine(22, 34, 50, 32);
      u8g2.drawLine(78, 31, 106, 33); u8g2.drawLine(78, 32, 106, 34);
      u8g2.drawRFrame(18, 43, 38, 22, 6);
      u8g2.drawRFrame(72, 43, 38, 22, 6);
      u8g2.drawPixel(56, 54); u8g2.drawPixel(71, 54);
      u8g2.drawDisc(37 + ox, 54, 8);
      u8g2.drawDisc(90 + ox, 54, 8);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(35 + ox, 52, 2);
      u8g2.drawDisc(88 + ox, 52, 2);
      u8g2.drawPixel(39 + ox, 56);
      u8g2.drawPixel(92 + ox, 56);
      u8g2.setDrawColor(1);
      u8g2.drawLine(48, 96, 56, 94); u8g2.drawLine(56, 94, 64, 96);
      u8g2.drawLine(64, 96, 72, 94); u8g2.drawLine(72, 94, 80, 96);
      u8g2.drawLine(46, 97, 82, 97);
      u8g2.drawLine(52, 101, 76, 101);
      u8g2.drawLine(46, 97, 52, 101); u8g2.drawLine(82, 97, 76, 101);
      break;

    case FACE_PISCANDO:
      u8g2.drawLine(22, 34, 50, 33);
      u8g2.drawLine(78, 33, 106, 34);
      u8g2.drawCircle(37, 52, 16, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(90, 52, 16, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(19, 57, 55, 57);
      u8g2.drawLine(73, 57, 109, 57);
      u8g2.drawLine(48, 97, 80, 97);
      u8g2.drawLine(52, 100, 76, 100);
      break;

    case FACE_OUVINDO:
      u8g2.drawLine(20, 29, 50, 31);
      u8g2.drawLine(78, 31, 108, 29);
      u8g2.drawRFrame(16, 41, 42, 26, 7);
      u8g2.drawRFrame(70, 41, 42, 26, 7);
      u8g2.drawDisc(37, 54, 10);
      u8g2.drawDisc(90, 54, 10);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(34, 51, 3);
      u8g2.drawDisc(87, 51, 3);
      u8g2.setDrawColor(1);
      u8g2.drawBox(40, 95, 3, 6);  u8g2.drawBox(47, 91, 3, 14);
      u8g2.drawBox(54, 86, 3, 23); u8g2.drawBox(61, 82, 3, 30);
      u8g2.drawBox(68, 86, 3, 23); u8g2.drawBox(75, 91, 3, 14);
      u8g2.drawBox(82, 95, 3, 6);
      break;

    case FACE_FELIZ:
      u8g2.drawCircle(37, 56, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(90, 56, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(64, 86, 18, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(44, 94, 47, 92);
      u8g2.drawLine(84, 94, 81, 92);
      break;

    case FACE_FOCADO:
      u8g2.drawLine(22, 27, 52, 36);
      u8g2.drawLine(76, 36, 106, 27);
      u8g2.drawRFrame(19, 46, 36, 18, 4);
      u8g2.drawRFrame(73, 46, 36, 18, 4);
      u8g2.drawDisc(37, 55, 6);
      u8g2.drawDisc(90, 55, 6);
      u8g2.drawBox(50, 96, 28, 3);
      break;

    case FACE_SONO:
      u8g2.drawLine(24, 37, 48, 37);
      u8g2.drawLine(80, 37, 104, 37);
      u8g2.drawCircle(37, 56, 14, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(90, 56, 14, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawBox(54, 97, 20, 2);
      u8g2.setFont(u8g2_font_4x6_tr);
      u8g2.drawGlyph(104, 24, 'Z');
      u8g2.drawGlyph(110, 19, 'z');
      u8g2.drawGlyph(116, 14, 'z');
      break;
  }
}

void atualizarDisplay() {
  wdt_reset();
  u8g2.firstPage();
  do {
    desenharFaceRealista(expressaoAtual);
  } while (u8g2.nextPage());
  wdt_reset();
}

void definirFace(Expressao e) {
  expressaoAtual = e;
  emPiscar = false;
  atualizarDisplay();
}

void iniciarDisplay() {
  // Pulso de Reset físico no pino 8
  pinMode(8, OUTPUT);
  digitalWrite(8, HIGH); delay(10);
  digitalWrite(8, LOW);  delay(50);
  digitalWrite(8, HIGH); delay(50);

  // CS (Pino 10) mantido em OUTPUT HIGH
  pinMode(10, OUTPUT);
  digitalWrite(10, HIGH);

  u8g2.setBusClock(1000000);
  u8g2.begin();
  u8g2.setPowerSave(0);
  u8g2.setContrast(255);
}

// ---------------- CONTROLE ISOLADO DE SERVOS ----------------
static void anexarServo(Servo &s, uint8_t pin, int pos) {
  if (!s.attached()) {
    s.attach(pin);
    s.write(pos); // Escreve posição segura antes de ligar PWM
    delay(15);
  }
}

void desenergizarServos() {
  servoBase.detach();
  servoOmbro.detach();
  servoCotovelo.detach();
  servoGarra.detach();
#if BASE_DUPLA_D2
  servoBase2.detach();
#endif
  servosEnergizados = false;
}

// Move unicamente o servo solicitado, sem perturbar os demais
void moverSuave(Servo &servo, uint8_t pin, int &posAtual, int posAlvo, int minAng, int maxAng, uint8_t delayMs = 12) {
  posAlvo = constrain(posAlvo, minAng, maxAng);
  anexarServo(servo, pin, posAtual);
#if BASE_DUPLA_D2
  if (&servo == &servoBase) anexarServo(servoBase2, PIN_BASE_D2, posAtual);
#endif
  servosEnergizados = true;

  const int passo = (posAtual < posAlvo) ? 1 : -1;
  while (posAtual != posAlvo) {
    wdt_reset();
    posAtual += passo;
    servo.write(posAtual);
#if BASE_DUPLA_D2
    if (&servo == &servoBase) servoBase2.write(posAtual);
#endif
    delay(delayMs);
  }
  ultimoMovimentoTs = millis();
}

// ---------------- ROTINAS COREOGRAFADAS DO BRAÇO ----------------
void rotinaDiagnosticoInicial() {
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 10);
  delay(300);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 10);
  delay(150);

  moverSuave(servoBase, PIN_BASE, posBase, 120, BASE_MIN, BASE_MAX, 14);
  moverSuave(servoBase, PIN_BASE, posBase, 60, BASE_MIN, BASE_MAX, 14);
  moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 14);

  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 95, OMBRO_MIN, OMBRO_MAX, 14);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 65, OMBRO_MIN, OMBRO_MAX, 14);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, OMBRO_PRONTIDAO, OMBRO_MIN, OMBRO_MAX, 14);

  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, 65, COTOVELO_MIN, COTOVELO_MAX, 14);
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, 45, COTOVELO_MIN, COTOVELO_MAX, 14);
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, COTOVELO_PRONTIDAO, COTOVELO_MIN, COTOVELO_MAX, 14);
}

void posturaProntidao() {
  definirFace(FACE_NEUTRO);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 10);
  moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 12);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, OMBRO_PRONTIDAO, OMBRO_MIN, OMBRO_MAX, 12);
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, COTOVELO_PRONTIDAO, COTOVELO_MIN, COTOVELO_MAX, 12);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 10);
}

void posturaDescanso() {
  definirFace(FACE_SONO);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 10);
  moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 12);
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, COTOVELO_DESCANSO, COTOVELO_MIN, COTOVELO_MAX, 12);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, OMBRO_DESCANSO, OMBRO_MIN, OMBRO_MAX, 12);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 10);
  delay(150);
  desenergizarServos();
}

void rotinaAcenar() {
  definirFace(FACE_FELIZ);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 80, OMBRO_MIN, OMBRO_MAX, 10);
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, COTOVELO_PRONTIDAO, COTOVELO_MIN, COTOVELO_MAX, 10);
  for (uint8_t j = 0; j < 3; j++) {
    moverSuave(servoBase, PIN_BASE, posBase, 120, BASE_MIN, BASE_MAX, 8);
    moverSuave(servoBase, PIN_BASE, posBase, 60, BASE_MIN, BASE_MAX, 8);
  }
  moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 8);

  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 10);
  delay(1200);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 10);

  posturaProntidao();
}

void rotinaApontar() {
  definirFace(FACE_FOCADO);
  moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 10);
  moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 95, OMBRO_MIN, OMBRO_MAX, 10); // Seguro: 95° em vez de 120°
  moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, 65, COTOVELO_MIN, COTOVELO_MAX, 10); // Seguro: 65° em vez de 120°

  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 10);
  delay(300);
  moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 10);
  delay(600);

  posturaProntidao();
}

// ---------------- PROTOCOLO SERIAL COM PROTEÇÃO DE OVERFLOW ----------------
#define IS(s)     (strcmp_P(cmd, PSTR(s)) == 0)
#define STARTS(s) (strncmp_P(cmd, PSTR(s), sizeof(s) - 1) == 0)

void processarComando(char *cmd) {
  while (*cmd == ' ') cmd++;
  size_t l = strlen(cmd);
  while (l > 0 && cmd[l - 1] == ' ') cmd[--l] = 0;
  if (l == 0) return;

  if (IS("CMD:PING") || IS("PING")) {
    Serial.println(F("ACK:JARVIS_ARM_PONG"));
  } else if (IS("CMD:WHO_ARE_YOU") || IS("WHO_ARE_YOU")) {
    Serial.println(F("DEVICE:JARVIS_ARM:V3"));
  } else if (IS("CMD:WAVE")) {
    rotinaAcenar();
    Serial.println(F("ACK:WAVE_DONE"));
  } else if (IS("CMD:REST")) {
    posturaDescanso();
    Serial.println(F("ACK:REST_DONE"));
  } else if (IS("CMD:READY")) {
    posturaProntidao();
    Serial.println(F("ACK:READY_DONE"));
  } else if (IS("CMD:POINT")) {
    rotinaApontar();
    Serial.println(F("ACK:POINT_DONE"));
  } else if (IS("CMD:DIAG")) {
    rotinaDiagnosticoInicial();
    Serial.println(F("ACK:DIAG_DONE"));
  } 
  // --- TESTES INDIVIDUAIS POR SERVO ---
  else if (IS("CMD:TEST:D6") || IS("CMD:TEST:BASE")) {
    moverSuave(servoBase, PIN_BASE, posBase, 120, BASE_MIN, BASE_MAX, 15);
    moverSuave(servoBase, PIN_BASE, posBase, 60, BASE_MIN, BASE_MAX, 15);
    moverSuave(servoBase, PIN_BASE, posBase, BASE_CENTRO, BASE_MIN, BASE_MAX, 15);
    Serial.println(F("ACK:TEST_BASE_DONE"));
  } else if (IS("CMD:TEST:D3") || IS("CMD:TEST:OMBRO")) {
    moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 95, OMBRO_MIN, OMBRO_MAX, 15);
    moverSuave(servoOmbro, PIN_OMBRO, posOmbro, 65, OMBRO_MIN, OMBRO_MAX, 15);
    moverSuave(servoOmbro, PIN_OMBRO, posOmbro, OMBRO_PRONTIDAO, OMBRO_MIN, OMBRO_MAX, 15);
    Serial.println(F("ACK:TEST_OMBRO_DONE"));
  } else if (IS("CMD:TEST:D4") || IS("CMD:TEST:COTOVELO")) {
    moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, 65, COTOVELO_MIN, COTOVELO_MAX, 15);
    moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, 45, COTOVELO_MIN, COTOVELO_MAX, 15);
    moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, COTOVELO_PRONTIDAO, COTOVELO_MIN, COTOVELO_MAX, 15);
    Serial.println(F("ACK:TEST_COTOVELO_DONE"));
  } else if (IS("CMD:TEST:D5") || IS("CMD:TEST:GARRA")) {
    moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX, 12);
    delay(400);
    moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX, 12);
    Serial.println(F("ACK:TEST_GARRA_DONE"));
  }
  // --- COMANDOS DA GARRA & BASE ---
  else if (IS("CMD:GARRA:OPEN")) {
    moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_ABERTA, GARRA_MIN, GARRA_MAX);
    Serial.println(F("ACK:GARRA_OPEN"));
  } else if (IS("CMD:GARRA:CLOSE")) {
    moverSuave(servoGarra, PIN_GARRA, posGarra, GARRA_FECHADA, GARRA_MIN, GARRA_MAX);
    Serial.println(F("ACK:GARRA_CLOSE"));
  } else if (STARTS("CMD:GARRA:")) {
    int ang = atoi(cmd + 10);
    moverSuave(servoGarra, PIN_GARRA, posGarra, ang, GARRA_MIN, GARRA_MAX);
    Serial.print(F("ACK:GARRA_")); Serial.println(posGarra);
  } else if (STARTS("CMD:BASE:")) {
    int ang = atoi(cmd + 9);
    moverSuave(servoBase, PIN_BASE, posBase, ang, BASE_MIN, BASE_MAX, 15);
    Serial.print(F("ACK:BASE_")); Serial.println(posBase);
  } else if (STARTS("CMD:OMBRO:")) {
    int ang = atoi(cmd + 10);
    moverSuave(servoOmbro, PIN_OMBRO, posOmbro, ang, OMBRO_MIN, OMBRO_MAX, 15);
    Serial.print(F("ACK:OMBRO_")); Serial.println(posOmbro);
  } else if (STARTS("CMD:COTOVELO:")) {
    int ang = atoi(cmd + 13);
    moverSuave(servoCotovelo, PIN_COTOVELO, posCotovelo, ang, COTOVELO_MIN, COTOVELO_MAX, 15);
    Serial.print(F("ACK:COTOVELO_")); Serial.println(posCotovelo);
  }
  // --- FACES NO OLED ---
  else if (IS("CMD:FACE:LISTEN")) {
    definirFace(FACE_OUVINDO);
    Serial.println(F("ACK:FACE_LISTEN"));
  } else if (IS("CMD:FACE:HAPPY")) {
    definirFace(FACE_FELIZ);
    Serial.println(F("ACK:FACE_HAPPY"));
  } else if (IS("CMD:FACE:SLEEP")) {
    definirFace(FACE_SONO);
    Serial.println(F("ACK:FACE_SLEEP"));
  } else if (IS("CMD:FACE:FOCUS")) {
    definirFace(FACE_FOCADO);
    Serial.println(F("ACK:FACE_FOCUS"));
  } else if (IS("CMD:FACE:NEUTRAL")) {
    definirFace(FACE_NEUTRO);
    Serial.println(F("ACK:FACE_NEUTRAL"));
  } else if (IS("CMD:OLED:RESET") || IS("CMD:FACE:RESET")) {
    iniciarDisplay();
    atualizarDisplay();
    Serial.println(F("ACK:OLED_RESET_DONE"));
  } else if (STARTS("CMD:PERSONA:")) {
    char *p = cmd + 12;
    while (*p == ' ') p++;
    size_t n = strlen(p);
    if (n > 0 && n < sizeof(nomePersona)) {
      strcpy(nomePersona, p);
      atualizarDisplay();
      Serial.print(F("ACK:PERSONA_")); Serial.println(nomePersona);
    } else {
      Serial.println(F("ERR:PERSONA_LEN"));
    }
  } else {
    Serial.println(F("ERR:UNKNOWN_CMD"));
  }
}

void lerSerial() {
  static char buf[40];
  static uint8_t n = 0;
  static bool overflow = false;

  while (Serial.available() > 0) {
    wdt_reset();
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (overflow) {
        overflow = false;
        n = 0;
      } else if (n > 0) {
        buf[n] = 0;
        n = 0;
        processarComando(buf);
      }
    } else if (!overflow) {
      if (n < sizeof(buf) - 1) {
        buf[n++] = c;
      } else {
        overflow = true; // Linha excessiva: descarta até o final
        n = 0;
      }
    }
  }
}

// ---------------- SETUP & LOOP PRINCIPAL ----------------
void setup() {
  Serial.begin(115200);
  Serial.println(F("DEVICE:JARVIS_ARM:V3:ONLINE")); // Resposta instantânea de boot

  // Ativa Watchdog de 4 segundos
  wdt_enable(WDTO_4S);

  iniciarDisplay();

  // Teste de acendimento (flash por 150ms para confirmar energização e comunicação)
  u8g2.firstPage();
  do {
    u8g2.drawBox(0, 0, 128, 128);
  } while (u8g2.nextPage());
  delay(150);

  u8g2.firstPage();
  do {
    u8g2.drawFrame(0, 0, 128, 128);
    u8g2.setFont(u8g2_font_helvB10_tr);
    drawStrF(34, 45, F("JARVIS"));
    u8g2.setFont(u8g2_font_6x10_tr);
    drawStrF(42, 65, F("ONLINE"));
    u8g2.drawDisc(64, 95, 10);
    u8g2.drawCircle(64, 95, 14);
  } while (u8g2.nextPage());
  delay(400);

#if DIAG_NO_BOOT
  rotinaDiagnosticoInicial();
  desenergizarServos();
#endif

  definirFace(FACE_NEUTRO);
  Serial.println(F("JARVIS_ONLINE_READY"));
}

void loop() {
  wdt_reset();
  unsigned long agora = millis();

  // 1. Proteção Térmica: corta PWM após inatividade
  if (servosEnergizados && (agora - ultimoMovimentoTs > TEMPO_DETACH_MS)) {
    desenergizarServos();
  }

  // 2. Animação Autônoma dos Olhos (Piscar + Micro-sacadas)
  if (expressaoAtual == FACE_NEUTRO || expressaoAtual == FACE_PISCANDO) {
    if (!emPiscar && expressaoAtual == FACE_NEUTRO && agora - ultimoPiscar > 3800UL) {
      emPiscar = true;
      tempoInicioPiscar = agora;
      expressaoAtual = FACE_PISCANDO;
      atualizarDisplay();
    } else if (emPiscar && agora - tempoInicioPiscar > 140UL) {
      emPiscar = false;
      ultimoPiscar = agora;
      expressaoAtual = FACE_NEUTRO;
      atualizarDisplay();
    }

    if (!emPiscar && expressaoAtual == FACE_NEUTRO && agora - ultimoOlhar > 7500UL) {
      ultimoOlhar = agora;
      static uint8_t seqOlhar = 0;
      seqOlhar = (seqOlhar + 1) % 4;
      olharOffset = (seqOlhar == 1) ? 2 : (seqOlhar == 3) ? -2 : 0;
      atualizarDisplay();
    }
  }

  // 3. Processamento Serial
  lerSerial();
}
