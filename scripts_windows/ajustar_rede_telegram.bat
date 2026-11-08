@echo off
title JARVIS - Ajuste de Rede Telegram
echo Verificando permissoes...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permissao de Administrador...
    powershell -Command "Start-Process cmd.exe -ArgumentList '/c netsh interface ipv4 set subinterface ""Wi-Fi"" mtu=1240 store=persistent && echo. && echo [SUCESSO] Conexao com Telegram liberada! && echo. && pause' -Verb RunAs"
    exit /b
)
netsh interface ipv4 set subinterface "Wi-Fi" mtu=1240 store=persistent
echo.
echo [SUCESSO] Conexao com Telegram liberada!
echo.
pause
