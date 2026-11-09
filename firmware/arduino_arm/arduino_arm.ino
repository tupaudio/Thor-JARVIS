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

#define U8G2_SEMICIRCLE_UPPER (U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_UPPER_LEFT)
#define U8G2_SEMICIRCLE_LOWER (U8G2_DRAW_LOWER_RIGHT | U8G2_DRAW_LOWER_LEFT)

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
// Rotação: U8G2_R2 inverte 180 graus conforme solicitado pelo usuário para acomodar os cabos.
U8G2_SH1107_PIMORONI_128X128_1_4W_HW_SPI u8g2(U8G2_R2, /* cs=*/ 10, /* dc=*/ 9, /* reset=*/ 8);

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
const int PIN_BASE_D6  = 6; // Giro Inferior Espelhado (D6) - caso o pino D2 da shield esteja danificado
const int PIN_OMBRO    = 3; // Elevação Primária / Ombro (D3)
#endif
const int PIN_COTOVELO = 4; // Elevação Secundária / Cotovelo (D4)
const int PIN_GARRA    = 5; // Garra (D5)

Servo servoBase;
Servo servoBase6;
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
// 3. FUNÇÕES DE DESENHO DO ROSTO ROBÓTICO REALISTA (128x128 SH1107 PIMORONI)
// ==============================================================================

void desenharMolduraHUD() {
  // Cantos cibernéticos estilo Stark Tech HUD
  u8g2.drawLine(4, 4, 16, 4);
  u8g2.drawLine(4, 4, 4, 16);
  u8g2.drawLine(111, 4, 123, 4);
  u8g2.drawLine(123, 4, 123, 16);
  u8g2.drawLine(4, 123, 16, 123);
  u8g2.drawLine(4, 123, 4, 111);
  u8g2.drawLine(111, 123, 123, 123);
  u8g2.drawLine(123, 123, 123, 111);
  
  // Badge de identificação no topo
  u8g2.setFont(u8g2_font_4x6_tf);
  u8g2.drawStr(43, 11, "J.A.R.V.I.S.");
}

void desenharNariz() {
  // Sensor óptico central facial
  u8g2.drawLine(64, 69, 61, 75);
  u8g2.drawLine(61, 75, 67, 75);
  u8g2.drawLine(67, 75, 64, 69);
}

void desenharFaceRealista(Expressao exp) {
  desenharMolduraHUD();
  desenharNariz();

  switch (exp) {
    case FACE_NEUTRO:
      // Sobrancelhas inteligentes
      u8g2.drawLine(24, 34, 52, 33);
      u8g2.drawLine(24, 35, 52, 34);
      u8g2.drawLine(76, 33, 104, 34);
      u8g2.drawLine(76, 34, 104, 35);
      
      // Contorno dos Olhos com acabamento arredondado
      u8g2.drawRFrame(20, 43, 36, 24, 6);
      u8g2.drawRFrame(72, 43, 36, 24, 6);
      
      // Íris com ponto de reflexo de luz natural
      u8g2.drawDisc(38, 55, 8);
      u8g2.drawDisc(90, 55, 8);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(36, 53, 2);
      u8g2.drawDisc(88, 53, 2);
      u8g2.setDrawColor(1);
      
      // Modulador vocal cibernético (boca inteligente)
      u8g2.drawRBox(46, 94, 36, 4, 2);
      u8g2.drawLine(40, 96, 43, 96);
      u8g2.drawLine(85, 96, 88, 96);
      break;

    case FACE_PISCANDO:
      // Sobrancelhas relaxadas
      u8g2.drawLine(24, 35, 52, 34);
      u8g2.drawLine(76, 34, 104, 35);
      
      // Pálpebras fechadas
      u8g2.drawRBox(20, 54, 36, 4, 2);
      u8g2.drawRBox(72, 54, 36, 4, 2);
      
      // Boca neutra
      u8g2.drawRBox(46, 94, 36, 4, 2);
      break;

    case FACE_OUVINDO:
      // Sobrancelhas arqueadas com atenção
      u8g2.drawLine(24, 30, 52, 31);
      u8g2.drawLine(76, 31, 104, 30);
      
      // Olhos alertas e abertos
      u8g2.drawRFrame(18, 41, 40, 28, 7);
      u8g2.drawRFrame(70, 41, 40, 28, 7);
      u8g2.drawDisc(38, 55, 10);
      u8g2.drawDisc(90, 55, 10);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(35, 52, 3);
      u8g2.drawDisc(87, 52, 3);
      u8g2.setDrawColor(1);
      
      // Equalizador de onda de voz ativo (pulsando com a audição)
      u8g2.drawBox(40, 94, 3, 7);
      u8g2.drawBox(48, 90, 3, 15);
      u8g2.drawBox(56, 85, 3, 23);
      u8g2.drawBox(64, 82, 3, 28);
      u8g2.drawBox(72, 85, 3, 23);
      u8g2.drawBox(80, 90, 3, 15);
      u8g2.drawBox(88, 94, 3, 7);
      break;

    case FACE_FELIZ:
      // Sobrancelhas sorridentes
      u8g2.drawLine(24, 33, 38, 27);
      u8g2.drawLine(38, 27, 52, 32);
      u8g2.drawLine(76, 32, 90, 27);
      u8g2.drawLine(90, 27, 104, 33);
      
      // Olhos em arco expressivo sorridente (^)
      u8g2.drawCircle(38, 56, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(38, 55, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(90, 56, 14, U8G2_SEMICIRCLE_UPPER);
      u8g2.drawCircle(90, 55, 14, U8G2_SEMICIRCLE_UPPER);
      
      // Sorriso suave
      u8g2.drawCircle(64, 86, 18, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(64, 85, 18, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawLine(44, 94, 47, 92);
      u8g2.drawLine(84, 94, 81, 92);
      break;

    case FACE_FOCADO:
      // Sobrancelhas anguladas em foco analítico
      u8g2.drawLine(24, 28, 52, 36);
      u8g2.drawLine(24, 29, 52, 37);
      u8g2.drawLine(76, 36, 104, 28);
      u8g2.drawLine(76, 37, 104, 29);
      
      // Olhos focados e atentos
      u8g2.drawRFrame(22, 47, 34, 18, 4);
      u8g2.drawRFrame(72, 47, 34, 18, 4);
      u8g2.drawDisc(39, 56, 6);
      u8g2.drawDisc(89, 56, 6);
      u8g2.setDrawColor(0);
      u8g2.drawDisc(38, 55, 1);
      u8g2.drawDisc(88, 55, 1);
      u8g2.setDrawColor(1);
      
      // Boca concentrada
      u8g2.drawBox(50, 95, 28, 3);
      break;

    case FACE_SONO:
      // Sobrancelhas neutras baixas
      u8g2.drawLine(26, 37, 50, 37);
      u8g2.drawLine(78, 37, 102, 37);
      
      // Olhos cerrados em descanso
      u8g2.drawCircle(38, 56, 14, U8G2_SEMICIRCLE_LOWER);
      u8g2.drawCircle(90, 56, 14, U8G2_SEMICIRCLE_LOWER);
      
      // Boca serena e efeito 'Z z z'
      u8g2.drawBox(54, 96, 20, 2);
      u8g2.setFont(u8g2_font_4x6_tf);
      u8g2.drawStr(104, 24, "Z");
      u8g2.drawStr(110, 19, "z");
      u8g2.drawStr(116, 14, "z");
      break;
  }
}

void atualizarDisplay() {
  u8g2.firstPage();
  do {
    desenharFaceRealista(expressaoAtual);
  } while (u8g2.nextPage());
}

// ==============================================================================
// 4. CONTROLE SUAVE DOS SERVOMOTORES
// ==============================================================================

void garantirServosAtivos() {
  if (!servoBase.attached())     servoBase.attach(PIN_BASE);
#ifndef SERVOS_EM_D0_D1
  if (!servoBase6.attached())    servoBase6.attach(PIN_BASE_D6);
#endif
  if (!servoOmbro.attached())    servoOmbro.attach(PIN_OMBRO);
  if (!servoCotovelo.attached()) servoCotovelo.attach(PIN_COTOVELO);
  if (!servoGarra.attached())    servoGarra.attach(PIN_GARRA);
}

void desenergizarServos() {
  servoBase.detach();
#ifndef SERVOS_EM_D0_D1
  servoBase6.detach();
#endif
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
}

void posturaProntidao() {
  garantirServosAtivos();
  expressaoAtual = FACE_NEUTRO;
  atualizarDisplay();

  // 1. Diagnóstico da Garra: abre e fecha
  moverSuave(servoGarra, posGarra, 40, 12);
  moverSuave(servoGarra, posGarra, GARRA_FECHADA, 12);
  relaxarGarra(); // Corta corrente da garra: zero aquecimento!

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
