#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador Automático de Firmware para Arduino Uno no Servidor
# Executa no Dell OptiPlex (Debian GNU/Linux 13)
# ==============================================================================
set -e

DIR_FIRMWARE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INO_FILE="${DIR_FIRMWARE}/arduino_arm.ino"
FQBN="arduino:avr:uno"

echo "🤖 [JARVIS FIRMWARE] Iniciando preparação para gravação do Arduino..."

# 1. Identificar porta USB do Arduino (protegendo a porta /dev/ttyUSB0 da Impressora 3D)
PORTA_ARDUINO=""
for p in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB1 /dev/ttyUSB2; do
    if [ -e "$p" ]; then
        PORTA_ARDUINO="$p"
        break
    fi
done

if [ -z "$PORTA_ARDUINO" ]; then
    echo "⚠️  Nenhuma porta /dev/ttyACM* ou /dev/ttyUSB1 encontrada."
    echo "Portas seriais atualmente conectadas no servidor:"
    ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "Nenhum dispositivo serial detectado."
    echo ""
    read -rp "Digite o caminho da porta USB do Arduino (ex: /dev/ttyACM0): " PORTA_ARDUINO
fi

echo "✅ Porta identificada: ${PORTA_ARDUINO}"

# 2. Verificar ou baixar arduino-cli localmente
ARDUINO_CLI="arduino-cli"
if ! command -v arduino-cli &>/dev/null; then
    if [ -f "${HOME}/bin/arduino-cli" ]; then
        ARDUINO_CLI="${HOME}/bin/arduino-cli"
    elif [ -f "/tmp/arduino-cli" ]; then
        ARDUINO_CLI="/tmp/arduino-cli"
    else
        echo "📥 Baixando arduino-cli oficial para compilação local..."
        curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/tmp sh
        ARDUINO_CLI="/tmp/arduino-cli"
    fi
fi

# 3. Garantir núcleo arduino:avr instalado
echo "📦 Verificando núcleo arduino:avr..."
${ARDUINO_CLI} core update-index
if ! ${ARDUINO_CLI} core list | grep -q "arduino:avr"; then
    ${ARDUINO_CLI} core install arduino:avr
fi

# 4. Garantir biblioteca U8g2 instalada
echo "📦 Verificando biblioteca U8g2..."
${ARDUINO_CLI} lib install U8g2 Servo 2>/dev/null || true

# 5. Compilar o firmware
echo "🔨 Compilando ${INO_FILE} para ${FQBN}..."
${ARDUINO_CLI} compile --fqbn "${FQBN}" "${DIR_FIRMWARE}"

# 6. Gravar (Upload) na placa
echo "🚀 Gravando firmware na porta ${PORTA_ARDUINO}..."
echo "⚠️  Nota: se houver erro de timeout, desligue a fonte externa dos servos durante o upload!"
${ARDUINO_CLI} upload -p "${PORTA_ARDUINO}" --fqbn "${FQBN}" "${DIR_FIRMWARE}"

echo "🎉 [SUCESSO] Firmware do Braço e Face OLED 1.5\" gravado com sucesso no Arduino!"
