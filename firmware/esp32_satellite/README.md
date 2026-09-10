# 🛰️ J.A.R.V.I.S. - Satélite de Mesa & Gateway Wi-Fi (ESP32-S3)

Este documento contém o guia completo de montagem, pinagem na protoboard e configuração do **Satélite de Mesa ESP32-S3**.

O ESP32-S3 atua como **dois módulos em um**:
1. **Satélite Interativo de Mesa:** Controla o Display Touch TFT de 4.0" (480x320 ILI9488) com a interface HUD estilo Stark, além do amplificador de áudio I2S (MAX98357A) com alto-falante de 4Ω 3W.
2. **Ponte Sem Fio (Gateway Wi-Fi):** Recebe comandos do JARVIS (Python no PC) via rede local Wi-Fi (HTTP REST) e transmite imediatamente para o **Arduino UNO** via comunicação serial UART (115200 baud).

---

## 🔌 Esquema Completo de Pinagem & Fiação

### 1. 📺 Display TFT 4.0" SPI ILI9488 (com Touch XPT2046)
| Pino no Módulo TFT | Conexão no ESP32-S3 | Observação |
| :--- | :--- | :--- |
| **VCC** | **3.3V** ou **5V** | Verifique se a placa possui regulador LDO de 3.3V no verso |
| **GND** | **GND** | Linha negativa da protoboard |
| **CS** | **GPIO 10** | Chip Select do Display |
| **RESET / RST** | **GPIO 5** | Reinicialização de hardware |
| **DC / RS** | **GPIO 4** | Seleção Data / Command |
| **MOSI / SDI** | **GPIO 11** | SPI Master Out Slave In |
| **SCK / SCLK** | **GPIO 12** | SPI Serial Clock |
| **LED / BL** | **3.3V** ou **GPIO 6** | Luz de fundo (Backlight) |
| **MISO / SDO** | **GPIO 13** | SPI Master In Slave Out |
| **T_CS** | **GPIO 9** | Chip Select do Touch XPT2046 |
| **T_CLK** | **GPIO 12** | Compartilha linha de Clock com display |
| **T_DIN** | **GPIO 11** | Compartilha linha MOSI com display |
| **T_DO** | **GPIO 13** | Compartilha linha MISO com display |

---

### 2. 🔊 Amplificador I2S MAX98357A & Alto-falante 4Ω 3W
| Pino no MAX98357A | Conexão no ESP32-S3 | Observação |
| :--- | :--- | :--- |
| **Vin / VDD** | **5V** | Use 5V para atingir os 3W máximos de saída de áudio |
| **GND** | **GND** | Linha de terra comum |
| **BCLK** | **GPIO 15** | Bit Clock do protocolo I2S |
| **LRC / WS** | **GPIO 16** | Word Select (Left/Right Clock) |
| **DIN** | **GPIO 17** | Data Input de áudio digital |
| **GAIN** | *Desconectado* | Deixe livre para ganho padrão de +12dB |
| **SD / MODE** | *Desconectado* | Deixe livre para som estéreo misturado em mono |
| **Saídas +/-** | **Alto-falante** | Fios direto no alto-falante de 4Ω 3W |

---

### 3. ⚡ Conexão Serial com o Arduino UNO (Ponte de Comandos)
| Pino no ESP32-S3 | Conexão no Arduino UNO | Segurança Elétrica |
| :--- | :--- | :--- |
| **GND** | **GND** | **OBRIGATÓRIO:** GND de ambos deve ser interligado! |
| **GPIO 18 (TX)** | **Pino 0 (RX)** | Direto (3.3V do ESP32 é aceito com segurança pelo Arduino) |
| **GPIO 8 (RX)** | **Pino 1 (TX)** | **ATENÇÃO:** Requer Divisor de Tensão! (Veja abaixo) |

#### ⚠️ Divisor de Tensão de Proteção (5V do Arduino -> 3.3V do ESP32):
O Arduino UNO envia sinais em 5V, mas o ESP32-S3 só suporta 3.3V. 
Na protoboard, faça esta ligação simples com 2 resistores:
```
Pino 1 (TX) do Arduino [5V] ───[ Resistor 1kΩ ]───┬───> GPIO 8 (RX) do ESP32-S3 [~3.3V]
                                                  │
                                          [ Resistor 2kΩ ]
                                                  │
                                                 GND
```

---

## 🛠️ Como Gravar no ESP32-S3 (Arduino IDE)

1. **Placa no Menu da Arduino IDE:**
   - Ferramentas -> Placa -> ESP32 Arduino -> **ESP32S3 Dev Module**
2. **Bibliotecas Necessárias (Instalar pelo Gerenciador de Bibliotecas):**
   - `Adafruit GFX Library`
   - `Adafruit ILI9488` (ou `LovyanGFX` / `TFT_eSPI`)
   - `ArduinoJson` (por Benoit Blanchon)
3. **Credenciais Wi-Fi:**
   - Abra o arquivo [`esp32_satellite.ino`](esp32_satellite.ino) e altere as linhas 47 e 48:
     ```cpp
     const char* WIFI_SSID     = "SEU_WIFI";
     const char* WIFI_PASSWORD = "SUA_SENHA";
     ```
4. **Clique em Carregar (Upload).**

Ao iniciar, o ESP32-S3 exibirá o seu IP na tela TFT de 4.0", tocará o chime de inicialização no alto-falante e entrará em prontidão!
