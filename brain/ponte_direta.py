#!/usr/bin/env python3
"""
J.A.R.V.I.S. - Ponte Serial Direta com Auto-Descoberta (Dock ESP32-S3 -> Braço Arduino Uno)
Detecta automaticamente as portas seriais corretas mesmo se os números tty mudarem.
"""

import os
import sys
import time
import json
import glob
import subprocess
import serial
import serial.tools.list_ports

print("\n" + "=" * 60, flush=True)
print("🚀 [J.A.R.V.I.S.] INICIANDO PONTE DIRETA BANCADA", flush=True)
print("=" * 60, flush=True)

# 1. Varredura e Diagnóstico das Portas Conectadas
print("\n🔍 [1/3] Varrendo portas seriais conectadas ao servidor...", flush=True)
portas_detectadas = list(serial.tools.list_ports.comports())

if not portas_detectadas:
    print("⚠️ Nenhuma porta serial USB detectada pelo sistema!", flush=True)
    print("  Dica: Verifique se os cabos USB do ESP32-S3 e do Arduino Uno estão plugados.", flush=True)
else:
    for p in portas_detectadas:
        print(f"  • Dispositivo: {p.device} | Descrição: {p.description} | HWID: {p.hwid}", flush=True)

# Links persistentes em /dev/serial/by-id/
links_by_id = glob.glob("/dev/serial/by-id/*")
if links_by_id:
    print("\n📌 Identificadores persistentes (/dev/serial/by-id/):", flush=True)
    for l in links_by_id:
        alvo = os.path.realpath(l)
        print(f"  • {os.path.basename(l)} -> {alvo}", flush=True)

# 2. Resolução da Porta do ESP32-S3 Dock
porta_dock = None

# Tenta por ID
for l in links_by_id:
    base = os.path.basename(l).lower()
    if "espressif" in base or "esp32" in base or "jtag" in base:
        porta_dock = os.path.realpath(l)
        break

# Tenta por comports
if not porta_dock:
    for p in portas_detectadas:
        info = f"{p.device} {p.description} {p.hwid}".lower()
        if "esp32" in info or "espressif" in info or "jtag" in info or "acm" in info:
            porta_dock = p.device
            break

# Fallback por caminho comum
if not porta_dock:
    for cand in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2"]:
        if os.path.exists(cand):
            porta_dock = cand
            break

# 3. Resolução da Porta do Arduino Uno (Braço)
porta_arm = None

# Tenta por ID
for l in links_by_id:
    base = os.path.basename(l).lower()
    if ("arduino" in base or "uno" in base or "ch340" in base or "ftdi" in base or "1a86" in base) and os.path.realpath(l) != porta_dock:
        porta_arm = os.path.realpath(l)
        break

# Tenta por comports
if not porta_arm:
    for p in portas_detectadas:
        if p.device == porta_dock:
            continue
        info = f"{p.device} {p.description} {p.hwid}".lower()
        if "arduino" in info or "uno" in info or "ch340" in info or "usb-serial" in info or "cp210" in info or "ftdi" in info:
            porta_arm = p.device
            break

# Fallback por caminho comum excluindo dock
if not porta_arm:
    for cand in ["/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB0"]:
        if os.path.exists(cand) and cand != porta_dock:
            porta_arm = cand
            break

print(f"\n🎯 [MAPEAMENTO AUTOMÁTICO]:")
print(f"  -> ESP32-S3 Dock : {porta_dock or 'NÃO ENCONTRADO'}", flush=True)
print(f"  -> Arduino Braço : {porta_arm or 'NÃO ENCONTRADO'}", flush=True)

# Libera as portas seriais de processos concorrentes
if porta_dock or porta_arm:
    alvos = f"{porta_dock or ''} {porta_arm or ''}".strip()
    subprocess.run(f"fuser -k {alvos} 2>/dev/null || true", shell=True)
    time.sleep(0.5)

BAUD = 115200

# 4. Conecta ao Arduino Uno
ser_arm = None
if porta_arm:
    print(f"\n🔌 [2/3] Conectando ao Arduino Uno ({porta_arm})...", flush=True)
    try:
        ser_arm = serial.Serial(porta_arm, BAUD, timeout=0.5, write_timeout=1.0)
        print("⏳ Aguardando 2.5s para o Arduino Uno concluir o boot...", flush=True)
        time.sleep(2.5)
        ser_arm.reset_input_buffer()
        print("✅ [2/3] Arduino Uno conectado e pronto!", flush=True)
        
        print("👋 [TESTE] Disparando movimento de teste (ACENAR)...", flush=True)
        ser_arm.write(b"CMD:WAVE\n")
        ser_arm.flush()
        time.sleep(1.0)
    except Exception as e:
        ser_arm = None
        print(f"❌ [2/3] Falha ao abrir Arduino Uno: {e}", flush=True)
else:
    print("\n⚠️ [2/3] Arduino Uno não detectado. Comandos de toque não poderão mover o braço.", flush=True)

# 5. Conecta ao ESP32-S3 Dock
ser_dock = None
if porta_dock:
    print(f"\n🔌 [3/3] Conectando ao ESP32-S3 Dock ({porta_dock})...", flush=True)
    try:
        ser_dock = serial.Serial(porta_dock, BAUD, timeout=0.1, write_timeout=1.0)
        ser_dock.dtr = True
        ser_dock.rts = True
        time.sleep(0.5)
        print("✅ [3/3] ESP32-S3 Dock conectado com sucesso!", flush=True)
        
        # Envia badge de persona
        ser_dock.write(b'{"persona":"J.A.R.V.I.S."}\n')
        ser_dock.flush()
    except Exception as e:
        ser_dock = None
        print(f"❌ [3/3] Falha ao abrir ESP32-S3 Dock: {e}", flush=True)
else:
    print("\n⚠️ [3/3] ESP32-S3 Dock não detectado. Verifique o cabo USB-C.", flush=True)

print("\n" + "=" * 60, flush=True)
if ser_dock and ser_arm:
    print("🎯 [SISTEMA 100% OPERACIONAL] Toque nos botões na tela de 4 polegadas!", flush=True)
else:
    print("⚠️ [MODO PARCIAL] Aguardando eventos ou reconexão...", flush=True)
print("=" * 60 + "\n", flush=True)

while True:
    try:
        if ser_dock and ser_dock.is_open:
            linha = ser_dock.readline().decode("utf-8", errors="ignore").strip()
            if linha:
                if "{" in linha and "}" in linha:
                    try:
                        d = json.loads(linha)
                        if d.get("type") == "arm_cmd":
                            acao = d.get("action", "").upper()
                            print(f"\n👆 [TOQUE RECEBIDO]: Botão {acao} pressionado!", flush=True)
                            
                            cmd = f"CMD:{acao}\n".encode("utf-8")
                            if ser_arm and ser_arm.is_open:
                                print(f"🚀 [ENVIANDO AO ARDUINO]: {cmd.strip().decode()}", flush=True)
                                ser_arm.write(cmd)
                                ser_arm.flush()
                                
                                time.sleep(0.1)
                                resp = ser_arm.read(64).decode("utf-8", errors="ignore").strip()
                                if resp:
                                    print(f"✅ [RESPOSTA ARDUINO]: {resp}", flush=True)
                            else:
                                print("⚠️ Braço não disponível para execução.", flush=True)
                    except json.JSONDecodeError:
                        pass
                elif "TOUCH" in linha:
                    print(f"  [TOUCH]: {linha}", flush=True)

        time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Encerrando ponte de teste.", flush=True)
        break
    except Exception as e:
        time.sleep(0.5)

if ser_arm and ser_arm.is_open:
    ser_arm.close()
if ser_dock and ser_dock.is_open:
    ser_dock.close()
