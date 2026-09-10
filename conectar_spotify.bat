@echo off
title J.A.R.V.I.S. - Conectar Spotify
chcp 65001 > nul
cd /d d:\Jarvis\brain
echo ============================================================
echo        J.A.R.V.I.S. - AUTENTICACAO SPOTIFY
echo ============================================================
echo.
echo Abrindo navegador para autorizacao do Spotify...
echo Se o navegador nao abrir, copie e cole o link que aparecer abaixo.
echo.
C:\Users\dafnh\.virtualenvs\jarvis\Scripts\python.exe test_spotify.py
echo.
pause
