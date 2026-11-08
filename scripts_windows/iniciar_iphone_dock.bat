@echo off
title J.A.R.V.I.S. - Stark Dock HUD (iPhone 11)
chcp 65001 > nul
cd /d "%~dp0brain"
if exist "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" (
    "%~dp0..\.virtualenvs\jarvis\Scripts\python.exe" iphone_dock_server.py
) else if exist "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" (
    "%USERPROFILE%\.virtualenvs\jarvis\Scripts\python.exe" iphone_dock_server.py
) else (
    python iphone_dock_server.py
)
pause
