@echo off
title J.A.R.V.I.S. - Telegram Bot Remoto
chcp 65001 > nul
cd /d "%~dp0brain"
if exist "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" (
    "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" telegram_bot.py
) else if exist "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" (
    "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" telegram_bot.py
) else (
    python telegram_bot.py
)
pause
