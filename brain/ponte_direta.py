#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Ponte Serial Direta e À Prova de Falhas (Dock -> Braço)
"""

import os
import sys
import time
import json
import subprocess

print("\n" + "=" * 60, flush=True)
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
ser_arm = None
try:
    ser_arm = serial.Serial(PORTA_ARM, BAUD, timeout=0.5, write_timeout=1.0)
    print("⏳ Aguardando 2.5s para o Arduino Uno concluir o boot...", flush=True)
    time.sleep(2.5) # Aguarda o bootloader Optiboot do Arduino
    
    # Limpa buffer do boot do Arduino
    ser_arm.reset_input_buffer()
    print("✅ [2/3] Arduino Uno conectado e pronto!", flush=True)
    
    # Dispara o aceno de teste no braço
    print("👋 [TESTE] Movimentando o braço robótico (ACENAR)...", flush=True)
    ser_arm.write(b"CMD:WAVE\n")
    ser_arm.flush()
    time.sleep(1.0)
except Exception as e:
    ser_arm = None
    print(f"❌ [2/3] Falha ao abrir Arduino: {e}", flush=True)

# 3. Conecta ao ESP32-S3 Dock (sem usar in_waiting para evitar Errno 5 no cdc_acm)
print(f"🔌 [3/3] Conectando ao ESP32-S3 Dock ({PORTA_DOCK})...", flush=True)
ser_dock = None
try:
    ser_dock = serial.Serial(PORTA_DOCK, BAUD, timeout=0.1, write_timeout=1.0)
    ser_dock.dtr = True
    ser_dock.rts = True
    time.sleep(0.5)
    print("✅ [3/3] ESP32-S3 Dock conectado com sucesso!", flush=True)
    
    # Atualiza persona no dock
    ser_dock.write(b'{"persona":"J.A.R.V.I.S."}\n')
    ser_dock.flush()
except Exception as e:
    ser_dock = None
    print(f"❌ [3/3] Falha ao abrir Dock: {e}", flush=True)

print("\n" + "=" * 60, flush=True)
print("🎯 [SISTEMA PRONTO] TOQUE EM QUALQUER BOTAO NA TELA DE 4 POLEGADAS!", flush=True)
print("=" * 60 + "\n", flush=True)

while True:
    try:
        if ser_dock and ser_dock.is_open:
            # Lê linha direto com timeout sem chamar in_waiting (evita Errno 5 no Linux)
            linha = ser_dock.readline().decode("utf-8", errors="ignore").strip()
            if linha:
                if "{" in linha and "}" in linha:
                    try:
                        d = json.loads(linha)
                        if d.get("type") == "arm_cmd":
                            acao = d.get("action", "").upper()
                            print(f"\n👆 [TOQUE RECEBIDO]: Comando {acao}!", flush=True)
                            
                            cmd = f"CMD:{acao}\n".encode("utf-8")
                            if ser_arm and ser_arm.is_open:
                                print(f"🚀 [ENVIANDO AO ARDUINO]: {cmd.strip().decode()}", flush=True)
                                ser_arm.write(cmd)
                                ser_arm.flush()
                                
                                # Lê resposta do Arduino
                                time.sleep(0.1)
                                resp = ser_arm.read(64).decode("utf-8", errors="ignore").strip()
                                if resp:
                                    print(f"✅ [RESPOSTA ARDUINO]: {resp}", flush=True)
                            else:
                                print("⚠️ Arduino não conectado.", flush=True)
                    except json.JSONDecodeError:
                        pass
                elif "TOUCH" in linha:
                    print(f"  [TOUCH]: {linha}", flush=True)

        time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Encerrando ponte.", flush=True)
        break
    except Exception as e:
        # Se houver erro passageiro na serial do dock, tenta reconectar suavemente
        time.sleep(0.5)

if ser_arm: ser_arm.close()
if ser_dock: ser_dock.close()
