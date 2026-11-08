"""
Script de Teste e Validação da Telemetria e Hardware Linux para o J.A.R.V.I.S.
Execute no Debian: python test_telemetry_linux.py
"""

import os
import sys

print("="*65)
print("   J.A.R.V.I.S. - DIAGNÓSTICO DE TELEMETRIA E HARDWARE (LINUX)")
print("="*65)

from system_service import system_service
from ai_router import ai_router
from brain_core import processar_comando

print("\n1. [TESTE DISCO FÍSICO /sys, udev e lsblk]:")
disco = system_service.obter_modelo_disco()
print(f"   -> {disco}")

print("\n2. [TESTE MÁQUINA DMI /sys/class/dmi]:")
maquina = system_service.obter_modelo_maquina()
print(f"   -> {maquina}")

print("\n3. [TESTE PROCESSADOR /proc/cpuinfo]:")
cpu = system_service.obter_modelo_processador()
print(f"   -> {cpu}")

print("\n4. [TESTE TEMPERATURA CPU]:")
temp = system_service.obter_temperatura_cpu()
print(f"   -> {temp}°C" if temp is not None else "   -> Não disponível via hwmon")

print("\n5. [TESTE SERVIÇO OLLAMA LOCAL]:")
st_ollama = system_service.obter_status_ollama_texto()
print(f"   -> {st_ollama}")

print("\n6. [TESTE TELEMETRIA OPERACIONAL COMPLETA]:")
telemetria = system_service.obter_telemetria()
print(telemetria)

print("\n7. [TESTE RELATÓRIO DE HARDWARE]:")
hw = system_service.obter_detalhes_hardware()
print(hw)

print("\n8. [TESTE ROTEAMENTO LOCAL - 'como estão o seu sistema']:")
resp1 = processar_comando("como estão o seu sistema", origem="cli")
print(f"   Resposta:\n{resp1}")

print("\n9. [TESTE ROTEAMENTO LOCAL - 'qual modelo de HD instalado no servidor']:")
resp2 = processar_comando("qual modelo de HD instalado no servidor", origem="cli")
print(f"   Resposta:\n{resp2}")

print("\n" + "="*65)
print(" DIAGNÓSTICO CONCLUÍDO COM SUCESSO!")
print("="*65)
