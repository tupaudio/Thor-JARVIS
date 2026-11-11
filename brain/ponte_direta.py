#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Ponte Serial Direta e À Prova de Travamentos (Dock -> Braço)
"""

import os
import sys
import time
import json
import subprocess

print("=" * 60, flush=True)
print("🚀 [J.A.R.V.I.S.] INICIANDO PONTE DIRETA BANCADA", flush=True)
print("=" * 60, flush=True)

# 1. Libera as portas seriais caso algum processo antigo esteja segurando
print("🧹 [1/3] Liberando portas seriais /dev/ttyACM* e /dev/ttyUSB*...", flush=True)
subprocess.run("fuser -k /dev/ttyACM0 /dev/ttyUSB1 2>/dev/null || true", shell=True)
time.sleep(1)

import serial

PORTA_DOCK = "/dev/ttyACM0"
PORTA_ARM  = "/dev/ttyUSB1"
BAUD = 115200

# 2. Conecta ao Arduino Uno do Braço
print(f"🔌 [2/3] Conectando ao Arduino Uno ({PORTA_ARM})...", flush=True)
try:
    ser_arm = serial.Serial(PORTA_ARM, BAUD, timeout=0.5, write_timeout=1.0)
    time.sleep(1.5) # Aguarda bootloader
    print(f"✅ [2/3] Arduino Uno conectado com sucesso!", flush=True)
    
    # Teste rápido: dá um aceno inicial de boas-vindas
    print("👋 [TESTE] Disparando aceno inicial no braço...", flush=True)
    ser_arm.write(b"CMD:WAVE\n")
    ser_arm.flush()
except Exception as e:
    ser_arm = None
    print(f"❌ [2/3] Falha ao abrir Arduino: {e}", flush=True)

# 3. Conecta ao ESP32-S3 Dock
print(f"🔌 [3/3] Conectando ao ESP32-S3 Dock ({PORTA_DOCK})...", flush=True)
try:
    ser_dock = serial.Serial(PORTA_DOCK, BAUD, timeout=0.1, write_timeout=1.0)
    ser_dock.dtr = True
    ser_dock.rts = True
    time.sleep(0.5)
    print(f"✅ [3/3] ESP32-S3 Dock conectado com sucesso!", flush=True)
    
    # Atualiza a persona no dock
    ser_dock.write(b'{"persona":"J.A.R.V.I.S."}\n')
    ser_dock.flush()
except Exception as e:
    ser_dock = None
    print(f"❌ [3/3] Falha ao abrir Dock: {e}", flush=True)

print("\n🎯 [SISTEMA PRONTO] APERTE QUALQUER BOTAO NA TELA DE 4 POLEGADAS!", flush=True)
print("Pressione Ctrl+C para encerrar quando quiser.\n", flush=True)

while True:
    try:
        if ser_dock and ser_dock.in_waiting:
            linha = ser_dock.readline().decode("utf-8", errors="ignore").strip()
            if linha:
                if "{" in linha and "}" in linha:
                    try:
                        d = json.loads(linha)
                        if d.get("type") == "arm_cmd":
                            acao = d.get("action", "").upper()
                            print(f"\n👆 [TOQUE NA TELA RECEBIDO]: {acao}", flush=True)
                            
                            cmd = f"CMD:{acao}\n".encode("utf-8")
                            if ser_arm:
                                print(f"🚀 [ENVIANDO AO ARDUINO]: {cmd.strip().decode()}", flush=True)
                                ser_arm.write(cmd)
                                ser_arm.flush()
                                time.sleep(0.2)
                                resp = ser_arm.read(ser_arm.in_waiting or 128).decode("utf-8", errors="ignore").strip()
                                if resp:
                                    print(f"✅ [RESPOSTA ARDUINO]: {resp}", flush=True)
                    except json.JSONDecodeError:
                        pass
        time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n🛑 Encerrando teste.", flush=True)
        break
    except Exception as e:
        print(f"Aviso: {e}", flush=True)
        time.sleep(0.5)

if ser_arm: ser_arm.close()
if ser_dock: ser_dock.close()
