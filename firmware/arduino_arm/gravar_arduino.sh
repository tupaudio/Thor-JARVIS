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
PORTA_ARDUINO="${1:-}"

if [ -z "$PORTA_ARDUINO" ]; then
    echo "🔍 Verificando portas seriais USB conectadas ao servidor:"
    ls -l /dev/serial/by-id/* 2>/dev/null || true
    ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
    echo ""

    # Lê porta configurada no .env caso válida e não seja a impressora 3D
    ENV_FILE="${DIR_FIRMWARE}/../../brain/.env"
    PORTA_ENV=""
    PORTA_OCTO=""
    if [ -f "$ENV_FILE" ]; then
        PORTA_ENV=$(grep -E "^ARDUINO_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "\r\n')
        PORTA_OCTO=$(grep -E "^OCTOPRINT_SERIAL_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' "\r\n')
    fi

    # Candidatas USB válidas (excluindo a porta do OctoPrint)
    CANDIDATAS=()
    for p in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2; do
        if [ -e "$p" ] && [ "$p" != "$PORTA_OCTO" ]; then
            CANDIDATAS+=("$p")
        fi
    done

    if [ -n "$PORTA_ENV" ] && [ -e "$PORTA_ENV" ] && [ "$PORTA_ENV" != "$PORTA_OCTO" ]; then
        PORTA_ARDUINO="$PORTA_ENV"
    elif [ ${#CANDIDATAS[@]} -gt 0 ]; then
        PORTA_ARDUINO="${CANDIDATAS[0]}"
    fi
fi

if [ -z "$PORTA_ARDUINO" ] || [ ! -e "$PORTA_ARDUINO" ]; then
    echo "⚠️  Nenhuma porta serial USB identificada automaticamente."
    read -rp "Digite o caminho da porta USB do Arduino (ex: /dev/ttyUSB2): " PORTA_ARDUINO
fi

# Resolve symlink para o nó de dispositivo real se for /dev/serial/by-*
PORTA_ARDUINO=$(readlink -f "${PORTA_ARDUINO}" 2>/dev/null || echo "${PORTA_ARDUINO}")

echo "✅ Porta selecionada para gravação: ${PORTA_ARDUINO}"

# Sincroniza porta identificada no brain/.env para garantir conexão serial perfeita
ENV_FILE="${DIR_FIRMWARE}/../../brain/.env"
if [ -f "$ENV_FILE" ]; then
    if grep -q "^ARDUINO_PORT=" "$ENV_FILE"; then
        sed -i "s|^ARDUINO_PORT=.*|ARDUINO_PORT=${PORTA_ARDUINO}|" "$ENV_FILE"
        echo "📝 ARDUINO_PORT sincronizada no .env com: ${PORTA_ARDUINO}"
    fi
fi

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

# Libera a porta USB caso o processo do Jarvis esteja em execução (sem travar por senha sudo)
echo "⏸️  Liberando acesso à porta ${PORTA_ARDUINO}..."
fuser -k "${PORTA_ARDUINO}" 2>/dev/null || true
pkill -f "python.*serial_comm" 2>/dev/null || true
pkill -f "python.*iphone_dock_server" 2>/dev/null || true
sudo -n systemctl stop jarvis 2>/dev/null || true
sleep 1

${ARDUINO_CLI} upload -p "${PORTA_ARDUINO}" --fqbn "${FQBN}" "${DIR_FIRMWARE}"

echo "🔄 Reativando serviço jarvis.service se disponível..."
sudo -n systemctl restart jarvis 2>/dev/null || true

echo "🎉 [SUCESSO] Firmware do Braço e Face OLED 1.5\" gravado com sucesso no Arduino!"
