#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador de Firmware para Dock ESP32-S3 + ILI9488 4.0" Touch
# Executa no Servidor Debian 13 (Dell OptiPlex)
# ==============================================================================
set -e

DIR_PROJ="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "${DIR_PROJ}"

echo "🤖 [JARVIS DOCK] Iniciando processo de gravação do ESP32-S3..."

# 1. Localizar ou Instalar PlatformIO Core (respeitando PEP 668 do Debian 13)
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
    echo "🔌 Dispositivos seriais disponíveis no momento:"
    ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
    read -rp "Digite a porta USB do ESP32-S3 (ex: /dev/ttyACM0): " PORTA_ALVO
fi

PORTA_ALVO=$(readlink -f "${PORTA_ALVO}" 2>/dev/null || echo "${PORTA_ALVO}")
echo "✅ Porta selecionada para o Dock: ${PORTA_ALVO}"

# 3. Compilação e Gravação via PlatformIO
echo "🔨 Compilando firmware para Flash 4MB..."
${PIO_CMD} run -e esp32-s3-supermini

echo "🚀 Enviando firmware para o ESP32-S3 na porta ${PORTA_ALVO}..."
${PIO_CMD} run -e esp32-s3-supermini --target upload --upload-port "${PORTA_ALVO}"

echo "🎉 [SUCESSO] Firmware do Dock gravado com sucesso no ESP32-S3!"
echo "⏳ Aguardando 2 segundos para o USB CDC re-enumerar..."
sleep 2

echo "📡 Abrindo monitor serial (pressione Ctrl+C para sair quando quiser)..."
timeout 20 ${PIO_CMD} device monitor -p "${PORTA_ALVO}" -b 115200 || true
