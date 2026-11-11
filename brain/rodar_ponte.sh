#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Disparador da Ponte Direta (Dock -> Braço)
# Encontra automaticamente o Python com pyserial instalado
# ==============================================================================
set -e

DIR_PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${DIR_PROJ}"

echo "🤖 [PONTE JARVIS] Localizando ambiente Python..."

PYTHON_EXEC=""
if [ -f "${HOME}/.platformio/penv/bin/python" ]; then
    PYTHON_EXEC="${HOME}/.platformio/penv/bin/python"
elif [ -f "${DIR_PROJ}/.venv/bin/python3" ]; then
    PYTHON_EXEC="${DIR_PROJ}/.venv/bin/python3"
elif [ -f "${DIR_PROJ}/.venv/bin/python" ]; then
    PYTHON_EXEC="${DIR_PROJ}/.venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "✅ Usando Python: ${PYTHON_EXEC}"

# Executa a ponte direta garantida
exec "${PYTHON_EXEC}" brain/ponte_direta.py
