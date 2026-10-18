@echo off
title J.A.R.V.I.S. - Assistente de Instalacao e Configuracao de Motor
chcp 65001 > nul
cd /d "%~dp0brain"
echo ============================================================
echo   J.A.R.V.I.S. - ASSISTENTE DE SELECAO DE MOTOR E SETUP
echo ============================================================
echo.
if exist "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" (
    "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" setup_jarvis.py
) else if exist "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" (
    "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" setup_jarvis.py
) else (
    python setup_jarvis.py
)
echo.
pause
