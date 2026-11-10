#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador do Teste Isolado de Bancada do OLED 1.5"
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INO_TESTE="${DIR}/teste_oled/teste_oled.ino"
FQBN="arduino:avr:uno"
PORTA="${1:-/dev/ttyUSB1}"

echo "🔬 [TESTE OLED] Gravando sketch de bancada para testar o display..."
echo "🔌 Porta alvo: ${PORTA}"

# 1. Liberar a porta serial (para processos do jarvis)
sudo -n systemctl stop jarvis 2>/dev/null || true
fuser -k "${PORTA}" 2>/dev/null || true
sleep 1

# 2. Localizar arduino-cli
ARDUINO_CLI="arduino-cli"
if ! command -v arduino-cli &>/dev/null; then
    if [ -f "${HOME}/bin/arduino-cli" ]; then
        ARDUINO_CLI="${HOME}/bin/arduino-cli"
    elif [ -f "/tmp/arduino-cli" ]; then
        ARDUINO_CLI="/tmp/arduino-cli"
    fi
fi

# 3. Compilar sketch de teste
echo "🔨 Compilando ${INO_TESTE}..."
${ARDUINO_CLI} compile --fqbn "${FQBN}" "${DIR}/teste_oled"

# 4. Gravar na placa
echo "🚀 Enviando firmware de teste para a placa..."
${ARDUINO_CLI} upload -p "${PORTA}" --fqbn "${FQBN}" "${DIR}/teste_oled"

echo ""
echo "🎉 [SUCESSO] Teste gravado com sucesso no Arduino Uno!"
echo "📡 Abrindo monitor serial por 15 segundos para acompanhar o diagnóstico..."
echo "--------------------------------------------------"
stty -F "${PORTA}" 115200 raw -echo -hupcl
timeout 15 cat "${PORTA}" || true
echo ""
echo "--------------------------------------------------"
echo "💡 Se o display não acender:"
echo "1. Abra 'firmware/arduino_arm/teste_oled/teste_oled.ino'"
echo "2. Mude '#define TESTE_DRIVER 1' para '3' (SSD1327 Waveshare)"
echo "3. Rode este script novamente!"
