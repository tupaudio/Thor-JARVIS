"""
J.A.R.V.I.S. - Teste Interativo de Bancada: Dock (ESP32-S3) -> Braço (Arduino Uno)
Liga as duas portas seriais diretamente com logs ao vivo no terminal!
"""

import os
import sys
import time
import json
import serial

sys.stdout.reconfigure(line_buffering=True)

PORTA_DOCK = "/dev/ttyACM0"
PORTA_ARM  = "/dev/ttyUSB1"
BAUD = 115200

print("\n" + "=" * 60)
print("🚀 [J.A.R.V.I.S.] INICIANDO PONTE DIRETA: DOCK -> BRAÇO ROBÓTICO")
print("=" * 60)

# 1. Conecta ao Arduino Uno do Braço
print(f"🔌 [1/2] Conectando ao Arduino Uno em {PORTA_ARM}...")
ser_arm = None
try:
    ser_arm = serial.Serial(PORTA_ARM, BAUD, timeout=1.0)
    time.sleep(1.5) # Aguarda bootloader do Arduino
    print(f"✅ [1/2] Arduino Uno conectado com sucesso em {PORTA_ARM}!")
except Exception as e:
    print(f"❌ [1/2] Falha ao abrir {PORTA_ARM}: {e}")

# 2. Conecta ao ESP32-S3 Dock
print(f"🔌 [2/2] Conectando ao ESP32-S3 Dock em {PORTA_DOCK}...")
ser_dock = None
try:
    ser_dock = serial.Serial(PORTA_DOCK, BAUD, timeout=0.1)
    ser_dock.dtr = True  # CRUCIAL para ESP32-S3 USB CDC!
    ser_dock.rts = True
    time.sleep(0.5)
    print(f"✅ [2/2] ESP32-S3 Dock conectado com sucesso em {PORTA_DOCK}!")
except Exception as e:
    print(f"❌ [2/2] Falha ao abrir {PORTA_DOCK}: {e}")

if not ser_dock or not ser_arm:
    print("\n⚠️ Uma das portas não pôde ser aberta. Verifique se o jarvis.service está rodando.")
    print("Dica: rode 'sudo systemctl stop jarvis' antes de rodar este teste manual.")

print("\n🎯 [PRONTO] TOQUE EM QUALQUER BOTÃO NA TELA DE 4 POLEGADAS!")
print("Pressione Ctrl+C para encerrar quando quiser.\n")

# Sincroniza persona no dock logo ao abrir
if ser_dock and ser_dock.is_open:
    try:
        ser_dock.write(b'{"persona":"J.A.R.V.I.S."}\n')
        ser_dock.flush()
    except Exception:
        pass

while True:
    try:
        if ser_dock and ser_dock.is_open and ser_dock.in_waiting:
            linha = ser_dock.readline().decode("utf-8", errors="ignore").strip()
            if linha:
                if "{" in linha and "}" in linha:
                    try:
                        d = json.loads(linha)
                        if d.get("type") == "arm_cmd":
                            acao = d.get("action", "").upper()
                            print(f"\n👆 [TOQUE NA TELA RECEBIDO]: Ação = {acao}")
                            
                            cmd_arduino = f"CMD:{acao}\n".encode("utf-8")
                            if ser_arm and ser_arm.is_open:
                                print(f"🚀 [ENVIANDO AO ARDUINO]: {cmd_arduino.strip().decode()}")
                                ser_arm.write(cmd_arduino)
                                ser_arm.flush()
                                
                                # Aguarda resposta do Arduino
                                time.sleep(0.1)
                                resp = ser_arm.read(ser_arm.in_waiting or 128).decode("utf-8", errors="ignore").strip()
                                if resp:
                                    print(f"✅ [RESPOSTA DO ARDUINO]: {resp}")
                            else:
                                print("⚠️ Arduino não conectado para receber o comando.")
                    except json.JSONDecodeError:
                        pass
                else:
                    # Imprime outros logs do ESP32 (ex: toques)
                    if "TOUCH" in linha:
                        print(f"  [DOCK LOG]: {linha}")

        time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Encerrando teste da ponte.")
        break
    except Exception as e:
        print(f"Erro no loop: {e}")
        time.sleep(1)

if ser_arm: ser_arm.close()
if ser_dock: ser_dock.close()
