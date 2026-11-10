#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Gravador de Firmware para Dock ESP32-S3 + ILI9488 4.0" Touch
# Executa no Servidor Debian 13 (Dell OptiPlex)
# ==============================================================================
set -e

DIR_PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR_PROJ}"

echo "🤖 [JARVIS DOCK] Iniciando processo de gravação do ESP32-S3..."

# 1. Localizar PlatformIO Core (pio)
PIO_CMD="pio"
if ! command -v pio &>/dev/null; then
    if [ -f "${HOME}/.platformio/penv/bin/pio" ]; then
        PIO_CMD="${HOME}/.platformio/penv/bin/pio"
    elif [ -f "${HOME}/.local/bin/pio" ]; then
        PIO_CMD="${HOME}/.local/bin/pio"
    elif [ -f "/usr/local/bin/pio" ]; then
        PIO_CMD="/usr/local/bin/pio"
    else
        echo "📦 PlatformIO não encontrado. Instalando localmente no usuário..."
        pip install --upgrade platformio || pip3 install --user platformio
        PIO_CMD="${HOME}/.local/bin/pio"
    fi
fi

# 2. Identificar a porta USB do ESP32-S3 (Protegendo /dev/ttyUSB0 e /dev/ttyUSB1)
PORTA_ALVO="${1:-}"

if [ -z "${PORTA_ALVO}" ]; then
    # Busca especificamente por dispositivos CDC (ttyACM*) ou identificadores Espressif
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

echo "✅ Porta selecionada para o Dock: ${PORTA_ALVO}"

# 3. Compilação e Gravação via PlatformIO
echo "🔨 Compilando firmware com LovyanGFX e DMA..."
${PIO_CMD} run -e esp32-s3-supermini

echo "🚀 Enviando firmware para o ESP32-S3..."
${PIO_CMD} run -e esp32-s3-supermini --target upload --upload-port "${PORTA_ALVO}"

echo "🎉 [SUCESSO] Firmware do Dock gravado com sucesso no ESP32-S3!"
echo "📡 Abrindo monitor serial por 10 segundos..."
timeout 10 ${PIO_CMD} device monitor -p "${PORTA_ALVO}" -b 115200 || true
