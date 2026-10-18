@echo off
title J.A.R.V.I.S. - Assistente Virtual
chcp 65001 > nul
cd /d "%~dp0brain"
if exist "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" (
    "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" main.py
) else if exist "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" (
    "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" main.py
) else (
    python main.py
)
pause
