#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador de Firmware para Dock ESP32-S3 + ILI9488 4.0" Touch
# Executa no Servidor Debian 13 (Dell OptiPlex)
# ==============================================================================
set -e

DIR_PROJ="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "${DIR_PROJ}"

echo "🤖 [JARVIS DOCK] Iniciando processo de gravação do ESP32-S3..."

# 1. Localizar PlatformIO Core
PIO_CMD=""
if command -v pio &>/dev/null; then
    PIO_CMD="pio"
elif [ -f "${HOME}/.platformio/penv/bin/pio" ]; then
    PIO_CMD="${HOME}/.platformio/penv/bin/pio"
elif [ -f "${HOME}/.local/bin/pio" ]; then
    PIO_CMD="${HOME}/.local/bin/pio"
elif [ -f "/usr/local/bin/pio" ]; then
    PIO_CMD="/usr/local/bin/pio"
fi

if [ -z "${PIO_CMD}" ] || [ ! -x "${PIO_CMD}" ]; then
    echo "❌ Erro: Não foi possível configurar o executável do PlatformIO."
    exit 1
fi

echo "✅ PlatformIO pronto: ${PIO_CMD}"

# 2. Identificar a porta USB do ESP32-S3 (Protegendo /dev/ttyUSB0 e /dev/ttyUSB1)
PORTA_ALVO="${1:-}"

if [ -z "${PORTA_ALVO}" ]; then
    for dev in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2; do
        if [ -e "${dev}" ]; then
            PORTA_ALVO="${dev}"
            break
        fi
    done
fi

if [ -z "${PORTA_ALVO}" ]; then
    echo "⚠️  Nenhuma porta /dev/ttyACM* detectada automaticamente."
    read -rp "Digite a porta USB do ESP32-S3 (ex: /dev/ttyACM0): " PORTA_ALVO
fi

PORTA_ALVO=$(readlink -f "${PORTA_ALVO}" 2>/dev/null || echo "${PORTA_ALVO}")
echo "✅ Porta selecionada para o Dock: ${PORTA_ALVO}"

# Libera a porta caso algum processo tenha ficado preso nela
fuser -k "${PORTA_ALVO}" 2>/dev/null || true
pkill -f "pio.*device.*monitor" 2>/dev/null || true
sleep 1

# 3. Compilação e Gravação via PlatformIO
echo "🔨 Compilando firmware..."
${PIO_CMD} run -e esp32-s3-supermini

echo "🚀 Enviando firmware para o ESP32-S3 na porta ${PORTA_ALVO}..."
${PIO_CMD} run -e esp32-s3-supermini --target upload --upload-port "${PORTA_ALVO}"

echo "🎉 [SUCESSO] Firmware do Dock gravado com sucesso no ESP32-S3!"
echo "⏳ Aguardando 1 segundo..."
sleep 1

# Leitor limpo via Python (não trava com timeout no stdin)
python3 -c "
import serial, time
try:
    s = serial.Serial('${PORTA_ALVO}', 115200, timeout=1)
    print('📡 Monitorando porta serial por 5 segundos...')
    t_end = time.time() + 5
    while time.time() < t_end:
        line = s.readline().decode('utf-8', errors='ignore').strip()
        if line:
            print('  ->', line)
    s.close()
except Exception as e:
    pass
" 2>/dev/null || true

echo "✅ Concluído!"
