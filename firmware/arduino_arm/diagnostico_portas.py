#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Diagnóstico Profundo de Portas Seriais e Hardware
Executa no servidor Debian para identificar exatamente onde está o Arduino e a Impressora 3D,
e se há processos travando ou pulsando o DTR (reset contínuo).
"""

import os
import sys
import time
import glob
import subprocess

def rodar_cmd(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception as e:
        return str(e)

def main():
    print("=" * 65)
    print(" 🔍 J.A.R.V.I.S. - DIAGNÓSTICO PROFUNDO DE HARDWARE & PORTAS")
    print("=" * 65)

    # 1. Verifica status de serviços do sistema
    print("\n[1] STATUS DOS SERVIÇOS NO SERVIDOR:")
    for serv in ["jarvis", "octoprint"]:
        status = rodar_cmd(f"systemctl is-active {serv} 2>/dev/null || true")
        if not status:
            status = "não instalado / inativo"
        print(f"  • {serv}.service: {status.upper()}")

    # 2. Portas identificadas pelo kernel
    print("\n[2] MAPEAMENTO DO SUBSYSTEMA UDEV (/dev/serial/by-id):")
    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    if not by_id:
        print("  ⚠️ Nenhum dispositivo encontrado em /dev/serial/by-id/")
    for path in by_id:
        target = os.path.realpath(path)
        print(f"  • {os.path.basename(path)} -> {target}")

    # 3. Varredura e teste não intrusivo em cada /dev/ttyUSB*
    portas = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    print(f"\n[3] TESTE ATIVO NAS PORTAS FÍSICAS ({len(portas)} encontradas):")

    import serial

    for porta in portas:
        print(f"\n--- Analisando {porta} ---")
        
        # Verifica se algum processo está segurando a porta
        fuser_out = rodar_cmd(f"fuser -v {porta} 2>&1")
        if fuser_out:
            print(f"  ⚠️ Processos acessando {porta}:\n    {fuser_out}")
        else:
            print(f"  ✅ Porta livre de processos externos.")

        # Tenta abrir em 115200 (Arduino Uno)
        try:
            s = serial.Serial(porta, 115200, timeout=1.5)
            time.sleep(0.5)
            
            # Lê banner inicial (se a placa enviou algo ao abrir)
            dados_iniciais = ""
            t_limite = time.time() + 2.0
            while time.time() < t_limite:
                if s.in_waiting > 0:
                    l = s.readline().decode("utf-8", errors="ignore").strip()
                    dados_iniciais += " " + l
                time.sleep(0.05)

            # Envia sondagem
            s.write(b"CMD:PING\n")
            s.flush()
            time.sleep(0.3)
            resp_ping = s.read(s.in_waiting or 64).decode("utf-8", errors="ignore").strip()

            s.write(b"M115\n")
            s.flush()
            time.sleep(0.3)
            resp_marlin = s.read(s.in_waiting or 64).decode("utf-8", errors="ignore").strip()

            s.close()

            print(f"  Dados iniciais recebidos: '{dados_iniciais.strip()}'")
            print(f"  Resposta a CMD:PING:      '{resp_ping}'")
            print(f"  Resposta a M115 (Marlin): '{resp_marlin}'")

            if "JARVIS" in dados_iniciais or "PONG" in resp_ping or "JARVIS" in resp_ping:
                print(f"  👉 [IDENTIFICADO]: ESTA PORTA É O ARDUINO DO BRAÇO ROBÓTICO!")
            elif "Marlin" in resp_marlin or "FIRMWARE" in resp_marlin or "start" in dados_iniciais:
                print(f"  👉 [IDENTIFICADO]: ESTA PORTA É A IMPRESSORA 3D CREALITY (Marlin)!")
            else:
                print(f"  ℹ️ Dispositivo não respondeu aos comandos padrão (pode estar sem firmware ou em bootloader).")

        except Exception as e:
            print(f"  ❌ Erro ao abrir serial em {porta}: {e}")

    print("\n" + "=" * 65)

if __name__ == "__main__":
    main()
