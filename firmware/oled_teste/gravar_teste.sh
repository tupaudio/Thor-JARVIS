#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador do Teste Isolado do OLED 1.5"
# Executa no Dell OptiPlex (Debian GNU/Linux 13)
# ==============================================================================
set -e

DIR_TESTE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FQBN="arduino:avr:uno"

echo "📺 [TESTE OLED] Gravando teste de display no Arduino Uno..."

# 1. Identificar porta USB do Arduino (/dev/ttyUSB1 ou /dev/ttyACM0)
PORTA_ARDUINO=""
for p in /dev/ttyUSB1 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB2; do
    if [ -e "$p" ]; then
        PORTA_ARDUINO="$p"
        break
    fi
done

if [ -z "$PORTA_ARDUINO" ]; then
    echo "⚠️ Nenhuma porta serial padrão encontrada."
    read -rp "Digite a porta USB do Arduino (ex: /dev/ttyUSB1): " PORTA_ARDUINO
fi

echo "✅ Porta selecionada: ${PORTA_ARDUINO}"

# 2. Localizar arduino-cli
ARDUINO_CLI="arduino-cli"
if ! command -v arduino-cli &>/dev/null; then
    if [ -f "${HOME}/bin/arduino-cli" ]; then
        ARDUINO_CLI="${HOME}/bin/arduino-cli"
    elif [ -f "/tmp/arduino-cli" ]; then
        ARDUINO_CLI="/tmp/arduino-cli"
    fi
fi

# 3. Compilar e gravar
echo "🔨 Compilando oled_teste.ino..."
${ARDUINO_CLI} compile --fqbn "${FQBN}" "${DIR_TESTE}"

echo "🚀 Gravando no Arduino..."
${ARDUINO_CLI} upload -p "${PORTA_ARDUINO}" --fqbn "${FQBN}" "${DIR_TESTE}"

echo "🎉 [SUCESSO] Teste do OLED gravado no Arduino!"
echo "Observe a tela: ela deve mostrar 'TESTE OLED', um X com diagonais e dois olhos!"
