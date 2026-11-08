@echo off
title J.A.R.V.I.S. - Conectar Spotify
chcp 65001 > nul
cd /d "%~dp0brain"
echo ============================================================
echo        J.A.R.V.I.S. - AUTENTICACAO SPOTIFY
echo ============================================================
echo.
echo Abrindo navegador para autorizacao do Spotify...
echo Se o navegador nao abrir, copie e cole o link que aparecer abaixo.
echo.
if exist "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" (
    "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" test_spotify.py
) else if exist "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" (
    "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" test_spotify.py
) else (
    python test_spotify.py
)
echo.
pause
