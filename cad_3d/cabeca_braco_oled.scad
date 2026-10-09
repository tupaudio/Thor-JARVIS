// =============================================================================
// J.A.R.V.I.S. - MÓDULO CABEÇA DO BRAÇO ROBÓTICO (OLED 1.5" SPI)
// =============================================================================
// Compatível com: Display OLED 1.5" SPI (128x128) - GME128128-01-SPI
// Montagem: Mecanismo de Pulso / Garra de 4-DOF em Acrílico
// Calibrado com medições reais do paquímetro digital:
//   - Largura PCB: 33.8 mm | Comprimento PCB: 47.2 mm
//   - Furação M2: 28.7 mm x 41.5 mm
//   - Encaixe Pulso Braço: 17.2 mm | Entre-furos Garra: 14.8 mm
// =============================================================================

$fn = 40; // Qualidade de curvatura

// --- PARÂMETROS GERAIS ---
folga = 0.5;             // Tolerância de impressão FDM (+0.5mm)
espessura_parede = 2.5;  // Espessura estrutural reforçada

// --- DIMENSÕES DO DISPLAY OLED (CORRIGIDAS COM MARGEM DE ERRO) ---
// Placa real: 34 x 47 mm (com margem de 1mm = 35 x 48 mm)
oled_pcb_w = 35.0;          // Largura interna do berço
oled_pcb_l = 48.0;          // Comprimento interno do berço
oled_pcb_h = 4.0;           // Altura do rebaixo da placa (com vidro)
furos_oled_dx = 28.7;       // Entre-furos largura
furos_oled_dy = 41.5;       // Entre-furos comprimento

// Vidro visível da tela: 34 x 34 mm
janela_oled_w = 34.0;       // Janela visível do display
janela_oled_l = 34.0;

// --- DIMENSÕES DA CAIXA EXTERNA ---
caixa_w = oled_pcb_w + (espessura_parede * 2); // 40.0 mm
caixa_l = oled_pcb_l + (espessura_parede * 2); // 53.0 mm
caixa_profundidade = 14.0;

// --- DIMENSÕES DA BASE DE FIXAÇÃO NA GARRA (SOLICITADO 3mm) ---
bracket_w = 23.0;           // Largura da base da garra
bracket_l = 18.0;           // Comprimento da aba de fixação
bracket_h = 3.0;            // ESPESSURA EXATA DE 3.0 mm SOLICITADA
furos_garra_dist = 14.8;    // Distância entre parafusos M2 da garra acrílica

// =============================================================================
// MÓDULOS PRINCIPAIS
// =============================================================================

module cabeca_oled_frontal() {
    difference() {
        // Bloco externo chanfrado (Design estilo armadura Stark)
        hull() {
            translate([-caixa_w/2 + 2, -caixa_l/2 + 2, 0])
                cylinder(r=2, h=caixa_profundidade);
            translate([caixa_w/2 - 2, -caixa_l/2 + 2, 0])
                cylinder(r=2, h=caixa_profundidade);
            translate([-caixa_w/2 + 2, caixa_l/2 - 2, 0])
                cylinder(r=2, h=caixa_profundidade);
            translate([caixa_w/2 - 2, caixa_l/2 - 2, 0])
                cylinder(r=2, h=caixa_profundidade);
        }

        // Cavidade interna para alojar a PCB e fiação
        translate([-oled_pcb_w/2, -oled_pcb_l/2, espessura_parede])
            cube([oled_pcb_w, oled_pcb_l, caixa_profundidade + 1]);

        // Janela do Display frontal chanfrada (Bezel ergonômico)
        translate([0, 2.0, -0.1]) {
            // Abertura passante
            translate([-janela_oled_w/2, -janela_oled_l/2, 0])
                cube([janela_oled_w, janela_oled_l, espessura_parede + 0.2]);
            
            // Chanfro frontal estético
            translate([0, 0, 0.6])
                rotate([0, 0, 0])
                cylinder(r1=janela_oled_w/2 + 1.2, r2=janela_oled_w/2 - 0.5, h=1.0);
        }

        // 4 Furos de fixação para parafusos M2 da PCB
        for (dx = [-furos_oled_dx/2, furos_oled_dx/2]) {
            for (dy = [-furos_oled_dy/2, furos_oled_dy/2]) {
                translate([dx, dy, -0.5])
                    cylinder(d=2.4, h=espessura_parede + 2); // Furo passante M2
            }
        }

        // Canal inferior para saída do cabo flat/fios SPI
        translate([-8, -caixa_l/2 - 1, espessura_parede + 2])
            cube([16, espessura_parede + 2, 6]);
    }
}

// =============================================================================
// BRACKET ELEVADO (OPÇÃO 2: MONTADO SOBRE A GARRA)
// =============================================================================
// Cria uma ponte que eleva a cabeça OLED 8mm acima da garra, permitindo que
// os dedos e as engrenagens de acrílico se movimentem sem colisão.
// Fixação: 2 parafusos M2 na distância de 14.8 mm + encaixe na base de 23.0 mm.
// =============================================================================

altura_ponte_elevacao = 8.5; // Vão livre para as engrenagens da garra

module bracket_articulacao() {
    difference() {
        union() {
            // Pilares de elevação que descem até a base da garra
            translate([-furos_garra_dist/2 - 3, -caixa_l/2 - 12, -altura_ponte_elevacao])
                cube([furos_garra_dist + 6, 12, altura_ponte_elevacao + bracket_h]);

            // Base de fixação traseira que apoia sobre o suporte do servo (23.0 mm)
            translate([-23.0/2, -caixa_l/2 - 14, -altura_ponte_elevacao])
                cube([23.0, 4.0, altura_ponte_elevacao + bracket_h]);

            // Trilho superior de engate rápido para Câmera / Sensor frontal
            translate([-10, caixa_l/2 - 3, 0])
                cube([20, 6, 4]);
        }

        // Furo dos 2 parafusos M2 da garra (14.8 mm centro a centro)
        translate([-furos_garra_dist/2, -caixa_l/2 - 6, -altura_ponte_elevacao - 1])
            cylinder(d=2.4, h=altura_ponte_elevacao + bracket_h + 2);
        translate([furos_garra_dist/2, -caixa_l/2 - 6, -altura_ponte_elevacao - 1])
            cylinder(d=2.4, h=altura_ponte_elevacao + bracket_h + 2);

        // Vão em túnel para a engrenagem e os dedos da garra girarem livres
        translate([-furos_garra_dist/2 + 1, -caixa_l/2 - 14, -altura_ponte_elevacao - 0.5])
            cube([furos_garra_dist - 2, 16, altura_ponte_elevacao - 1.5]);

        // Canal passa-cabo para o chicote de fios do OLED (7 vias)
        translate([-4, -caixa_l/2 - 15, 0])
            cube([8, 16, bracket_h + 2]);
    }
}

// Tampa traseira com ventilação e clipe de pressão
module tampa_traseira_cabeca() {
    tampa_w = oled_pcb_w - 0.2;
    tampa_l = oled_pcb_l - 0.2;
    tampa_h = 2.0;

    difference() {
        cube([tampa_w, tampa_l, tampa_h], center=true);

        // Fendas de ventilação futuristas
        for (i = [-3 : 3]) {
            translate([0, i * 5, 0])
                cube([tampa_w - 10, 2.0, tampa_h + 1], center=true);
        }

        // Furos M2 para parafusar a tampa na traseira
        for (dx = [-furos_oled_dx/2, furos_oled_dx/2]) {
            for (dy = [-furos_oled_dy/2, furos_oled_dy/2]) {
                translate([dx, dy, 0])
                    cylinder(d=2.6, h=tampa_h + 1, center=true);
            }
        }
    }
}

// =============================================================================
// MONTAGEM FINAL
// =============================================================================

// Peça Principal: Moldura + Bracket Integrado
union() {
    cabeca_oled_frontal();
    bracket_articulacao();
}

// Para visualizar a tampa traseira, descomente a linha abaixo:
// translate([caixa_w + 10, 0, 1]) tampa_traseira_cabeca();
