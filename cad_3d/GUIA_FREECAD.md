# 📐 Guia Completo de Modelagem Paramétrica no FreeCAD (J.A.R.V.I.S.)

Este guia ensina o passo a passo exato para modelar, editar e parametrizar as peças do J.A.R.V.I.S. no **FreeCAD** (versão 0.21, 1.0 ou superior), utilizando as melhores práticas da bancada **PartDesign** e **Sketcher**.

---

## 🛠️ Regra de Ouro do FreeCAD: A Bancada Spreadsheet (Planilha)

Antes de desenhar qualquer linha, a melhor prática no FreeCAD é criar uma **Spreadsheet** com as medidas do paquímetro. Se você precisar ajustar uma folga de impressão depois, basta alterar um número na planilha e a peça inteira se atualiza automaticamente!

1. Abra o FreeCAD e mude para a bancada **Spreadsheet**.
2. Clique em **Criar nova planilha** (ícone verde de planilha).
3. Renomeie a planilha para `Params`.
4. Preencha as células com as medidas reais e defina os *Aliases* (botão direito na célula da direita > Propriedades > Alias):

| Nome | Valor | Alias | Descrição |
| :--- | :--- | :--- | :--- |
| `folga_fdm` | `0.4 mm` | `folga` | Tolerância de dilatação do plástico |
| `oled_w` | `33.8 mm` | `oled_w` | Largura da placa OLED |
| `oled_l` | `47.2 mm` | `oled_l` | Comprimento da placa OLED |
| `oled_furo_x` | `28.7 mm` | `oled_fx` | Entre-furos largura M2 |
| `oled_furo_y` | `41.5 mm` | `oled_fy` | Entre-furos comprimento M2 |
| `garra_furos` | `14.8 mm` | `garra_f` | Distância parafusos da garra |
| `garra_largura` | `23.0 mm` | `garra_w` | Largura da base do servo da garra |
| `tft_vidro_x` | `93.4 mm` | `tft_vx` | Vidro do TFT 4.0 |
| `tft_vidro_y` | `60.8 mm` | `tft_vy` | Altura do vidro TFT 4.0 |
| `tft_furo_x` | `101.5 mm` | `tft_fx` | Furação M3 comprimento TFT |
| `tft_furo_y` | `54.0 mm` | `tft_fy` | Furação M3 largura TFT |
| `falante_w` | `27.8 mm` | `fal_w` | Largura do alto-falante 4Ω 3W |
| `falante_l` | `36.7 mm` | `fal_l` | Comprimento do alto-falante |
| `mic_diam` | `13.6 mm` | `mic_d` | Diâmetro do microfone INMP441 |
| `caneta_diam` | `4.8 mm` | `pen_d` | Diâmetro do corpo da Stylus |

---

## 🤖 MODELO 1: Cabeça Articulada (OLED 1.5" sobre a Garra)

Bancada: **PartDesign**

### Passo 1: Criar o Corpo e o Bloco Principal
1. Clique em **Criar Corpo (Create Body)** e depois **Criar Esboço (Create Sketch)** no plano **XY**.
2. Desenhe um retângulo centrado na origem:
   - Largura: `= Params.oled_w + 5 mm` (~`38.8 mm`).
   - Altura: `= Params.oled_l + 5 mm` (~`52.2 mm`).
3. Feche o esboço e aplique **Pad (Extrusão)** de `14.0 mm`.

### Passo 2: Cavidade Interna (Alojamento da Placa)
1. Crie um novo esboço na face traseira do bloco.
2. Desenhe um retângulo centrado:
   - Largura: `= Params.oled_w + Params.folga` (`34.2 mm`).
   - Altura: `= Params.oled_l + Params.folga` (`47.6 mm`).
3. Aplique **Pocket (Cavidade)** com profundidade de `11.6 mm` (deixando `2.4 mm` de parede frontal).

### Passo 3: Janela Frontal do Display (Visor)
1. Crie um esboço na face frontal (ou plano XY).
2. Desenhe um quadrado centrado de `28.5 mm × 28.5 mm`.
3. Aplique **Pocket (Cavidade)** através de todos (**Through All**).
4. *(Opcional)* Selecione as 4 bordas da janela e aplique **Chamfer (Chanfro)** de `1.0 mm` para o efeito biselado estilo armadura.

### Passo 4: Furação M2 da Placa
1. Crie um esboço na face interna onde a placa apoia.
2. Insira 4 pontos de esboço (Sketch Points) simétricos em relação aos eixos:
   - Distância horizontal: `= Params.oled_fx` (`28.7 mm`).
   - Distância vertical: `= Params.oled_fy` (`41.5 mm`).
3. Use a ferramenta **Hole (Furo)**:
   - Diâmetro: `2.4 mm` (tamanho ideal para parafuso M2 abrir rosca direta).
   - Profundidade: passante ou `6.0 mm`.

### Passo 5: Ponte de Elevação sobre a Garra
1. Crie um esboço na base inferior traseira:
   - Desenhe o perfil da ponte com pilares laterais de `8.5 mm` de altura (deixando o vão central de `14.8 mm` aberto para os dedos da garra se moverem).
   - Largura total: `= Params.garra_w` (`23.0 mm`).
2. Aplique **Pad (Extrusão)** de `12.0 mm`.
3. Crie os 2 furos M2 na base dos pilares com espaçamento de `= Params.garra_f` (`14.8 mm`) para parafusar na garra existente.

---

## 🖥️ MODELO 2: Console Satélite de Mesa (TFT 4.0" + Som + Mic)

Bancada: **PartDesign**

### Passo 1: Perfil Inclinado do Gabinete
1. Crie um novo **Body** e um **Sketch** no plano **XZ (Vista Lateral)**.
2. Desenhe o trapézio de perfil da lateral do console:
   - Base inferior: `105.0 mm` (horizontal).
   - Altura traseira: `75.0 mm` (vertical).
   - Altura frontal: `16.0 mm` (vertical).
   - Face superior inclinada unindo a frente e a traseira: ângulo de **55°** em relação à base.
3. Feche o esboço e aplique **Pad (Extrusão)** simétrico ao plano com comprimento de `160.0 mm`.

### Passo 2: Oco Interno (Casca do Console)
1. Selecione a face inferior (chão do console).
2. Clique na ferramenta **Thickness (Espessura)** ou faça um **Pocket** a partir do fundo:
   - Deixe espessura de parede de `2.6 mm`.

### Passo 3: Janela do Display TFT 4.0"
1. Crie um **Datum Plane (Plano de Referência)** alinhado à face inclinada de 55°.
2. Crie um esboço nesse Datum Plane:
   - Posicione o retângulo da tela deslocado `15 mm` para a direita do centro.
   - Dimensões: `= Params.tft_vx + Params.folga` (`93.8 mm`) por `= Params.tft_vy + Params.folga` (`61.2 mm`).
   - Adicione 4 pontos nos cantos para os parafusos M3: distância de `= Params.tft_fx` (`101.5 mm`) por `= Params.tft_fy` (`54.0 mm`).
3. Aplique **Pocket (Cavidade)** passante de `10 mm`.
4. Use a ferramenta **Hole** nos 4 pontos com diâmetro `3.2 mm`.

### Passo 4: Grelha do Alto-falante (Lado Esquerdo)
1. No mesmo Datum Plane (face inclinada), à esquerda da tela:
   - Desenhe 7 a 9 ranhuras retangulares de `24.0 mm × 2.0 mm` espaçadas de `4.2 mm`.
2. Aplique **Pocket** passante.
3. No interior do gabinete, modele uma parede de isolamento (caixa fechada de `34 mm × 43 mm × 20 mm`) para selar o fundo do alto-falante.

### Passo 5: Torre Centralizada do Microfone (Topo)
1. No topo superior traseiro do gabinete, crie uma pequena saliência (cúpula) centrada em X.
2. Crie um furo (**Hole**) de `2.6 mm` inclinado para a frente (direcionado para a linha de fala).
3. Na parte interna, crie o rebaixo cilíndrico de `= Params.mic_d + 0.4 mm` (`14.0 mm`) para encaixar a placa do INMP441.

### Passo 6: Coldre da Caneta Stylus (Lado Direito)
1. Na face lateral direita do console, crie um esboço com um círculo de `Ø 5.2 mm`.
2. Aplique **Pocket** com profundidade de `82.0 mm` acompanhando a inclinação do console.
3. Adicione um rasgo de alívio de `8.5 mm` para a trava/presilha da caneta.

---

## 💡 Dicas Profissionais para Evitar Erros no FreeCAD

1. **Evite o Topological Naming Problem (TNP):**
   - Nunca desenhe um esboço diretamente sobre faces que receberam chanfros ou filetes.
   - **Sempre crie Datum Planes (Planos de Referência)** vinculados aos eixos principais (X, Y, Z) e use-os como suporte para os esboços.
2. **Chanfros e Filetes sempre no final:**
   - Faça toda a geometria estrutural primeiro (cortes, furos, cavidades).
   - Só aplique chanfros estéticos e arredondamentos como a última etapa da árvore de modelagem.
3. **Como Importar os Arquivos `.scad` no FreeCAD:**
   - O FreeCAD tem a bancada nativa **OpenSCAD**.
   - Você pode ir em `Arquivo > Abrir`, selecionar `cabeca_braco_oled.scad` ou `console_satelite_tft.scad`.
   - O FreeCAD converte automaticamente o código CSG em sólidos paramétricos editáveis!
4. **Exportar para STL:**
   - Selecione o último item do **Body** na árvore (ex: `Pocket` ou `Fillet` final).
   - Vá em `Arquivo > Exportar` e selecione formato **STL Mesh (*.stl)**.
   - Configure a deflexão de malha em `0.05 mm` nas preferências do FreeCAD para curvas perfeitamente redondas sem facetas visíveis.
