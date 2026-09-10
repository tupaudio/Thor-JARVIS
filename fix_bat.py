# -*- coding: utf-8 -*-
bat_content = (
    b"@echo off\r\n"
    b"title JARVIS - Ajuste de Rede Telegram\r\n"
    b"echo Verificando permissoes...\r\n"
    b"net session >nul 2>&1\r\n"
    b"if %errorlevel% neq 0 (\r\n"
    b"    echo Solicitando permissao de Administrador...\r\n"
    b"    powershell -Command \"Start-Process cmd.exe -ArgumentList '/c netsh interface ipv4 set subinterface \"\"Wi-Fi\"\" mtu=1240 store=persistent && echo. && echo [SUCESSO] Conexao com Telegram liberada! && echo. && pause' -Verb RunAs\"\r\n"
    b"    exit /b\r\n"
    b")\r\n"
    b"netsh interface ipv4 set subinterface \"Wi-Fi\" mtu=1240 store=persistent\r\n"
    b"echo.\r\n"
    b"echo [SUCESSO] Conexao com Telegram liberada!\r\n"
    b"echo.\r\n"
    b"pause\r\n"
)

with open(r"d:\Jarvis\ajustar_rede_telegram.bat", "wb") as f:
    f.write(bat_content)

print("Batch file generated with binary CRLF!")
