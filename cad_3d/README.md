# 🤖 J.A.R.V.I.S. - Módulos de Engenharia e Impressão 3D

Este diretório contém os projetos em **OpenSCAD** e arquivos **STL** calibrados diretamente a partir das medições do paquímetro digital dos componentes físicos do projeto.

---

## 📂 Arquivos Disponíveis

| Arquivo | Descrição | Componentes Alojados |
| :--- | :--- | :--- |
| [`cabeca_braco_oled.scad`](file:///d:/Jarvis/cad_3d/cabeca_braco_oled.scad) | Cabeça elevada sobre a garra do braço 4-DOF | Display OLED 1.5" SPI, trilho superior para câmera, vão livre de 8.5mm para as engrenagens |
| [`console_satelite_tft.scad`](file:///d:/Jarvis/cad_3d/console_satelite_tft.scad) | Console Satélite de Mesa (Layout Oficial) | **Esq:** Alto-falante 4Ω 3W c/ câmara selada<br>**Centro:** TFT 4.0" Touch<br>**Topo:** Mic INMP441 centralizado<br>**Dir:** Coldre Stylus (87mm) |
| [`tampa_inferior_satelite.scad`](file:///d:/Jarvis/cad_3d/tampa_inferior_satelite.scad) | Base inferior (160 x 105 mm) | Fechamento M3, grelha de fluxo térmico, pés de silicone |
| [`stls/`](file:///d:/Jarvis/cad_3d/stls) | Pasta com arquivos `.stl` prontos para fatiar | Modelos prontos para Cura, PrusaSlicer, OrcaSlicer, Bambu Studio |

---

## 📐 Dimensões Críticas Cadastradas (Paquímetro)

- **Display OLED 1.5":**
  - PCB: `33.8 mm × 47.2 mm`
  - Furação M2: `28.7 mm × 41.5 mm`
  - Área ativa do display: `28.0 mm × 28.0 mm`
- **Display TFT 4.0" Touch:**
  - Vidro / Painel: `93.4 mm × 60.8 mm`
  - Furação M3/M2.5: `101.5 mm × 54.0 mm`
- **Alto-falante 4Ω 3W:**
  - Corpo: `27.8 mm × 36.7 mm`
- **Microfone INMP441:**
  - Diâmetro PCB: `13.6 mm` (cápsula MEMS central)
- **Caneta Touch (Stylus):**
  - Comprimento: `87.0 mm` | Diâmetro: `4.8 mm` | Presilha: `7.8 mm`
- **Articulação da Garra do Braço:**
  - Vão do pulso: `17.2 mm` | Entre-furos garra: `14.8 mm` | Base do servo: `23.0 mm`

---

## 🖨️ Recomendações de Impressão FDM

- **Material recomendado:** PLA ou PETG (PETG oferece maior resistência mecânica para o braço robótico).
- **Altura de Camada (Layer Height):** `0.20 mm` (ou `0.16 mm` para acabamento refinado nas grelhas).
- **Paredes / Perímetros (Walls):** `3` a `4` voltas de parede (mínimo `1.2 mm` para aceitar rosca de parafuso com firmeza).
- **Preenchimento (Infill):**
  - Cabeça do Braço: `25%` Gyroid ou Grid (leve e rígida para não sobrecarregar os servos SG90).
  - Console Satélite: `15%` a `20%` Gyroid.
- **Suportes:**
  - **Cabeça OLED:** Imprimir com a face da janela do display voltada para a mesa (não requer suportes).
  - **Console Satélite:** Imprimir apoiado pela base inferior (suportes mínimos necessários apenas no vão inclinado da tela).

---

## 🔧 Dicas de Montagem & Acústica

1. **Vedação da Câmara Acústica:**
   - O alto-falante deve ser colado ou parafusado firmemente na sua câmara interna.
   - Aplique uma pequena fita de espuma ou silicone na borda para evitar vibração e vazamento de ar, garantindo graves nítidos e a voz do J.A.R.V.I.S. encorpada.
2. **Isolamento do Microfone:**
   - O microfone INMP441 fica em um compartimento separado da câmara do falante para evitar realimentação de áudio (eco).
   - Use um pedacinho de fita isolante ou espuma ao redor da cápsula contra o orifício frontal de 2.5 mm.
3. **Cabeça no Braço:**
   - Fixe a aba do suporte na furação de `14.8 mm` da garra usando 2 parafusos M2 com arruela plástica, ou diretamente no braço do servo do pulso (`17.2 mm`).
