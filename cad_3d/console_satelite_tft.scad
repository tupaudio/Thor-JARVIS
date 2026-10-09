// =============================================================================
// J.A.R.V.I.S. - CONSOLE SATÉLITE DE MESA (LAYOUT DEFINITIVO & SIMPLIFICADO)
// =============================================================================
// Configuração Oficial:
//   - LADO ESQUERDO: Alto-falante 4Ω 3W (27.8 x 36.7 mm) c/ câmara selada e grelha
//   - CENTRO: Display TFT 4.0" Touch (Vidro: 93.4 x 60.8 mm | Furos: 101.5 x 54.0 mm)
//   - TOPO CENTRALIZADO: Microfone MEMS INMP441 (13.6 mm) c/ porta acústica frontal
//   - LADO DIREITO: Coldre integrado para a Stylus / Caneta Touch (87.0 x 4.8 mm)
//   - INTERIOR: Berço para ESP32-S3 DevKit e 1x Amplificador MAX98357A (Mono)
// =============================================================================

$fn = 35;

// --- FOLGAS E TOLERÂNCIAS FDM ---
folga = 0.5;
parede = 2.6;
angulo_tela = 55; // Inclinação ergonômica da tela (55°)

// --- DIMENSÕES DOS COMPONENTES (MEDIDAS REAIS) ---
tft_furo_x = 101.5;
tft_furo_y = 54.0;
tft_vidro_x = 93.4 + folga;
tft_vidro_y = 60.8 + folga;

falante_w = 27.8 + folga;
falante_l = 36.7 + folga;
falante_prof = 10.0;

mic_d = 13.6 + folga;
caneta_d = 5.2;
caneta_comp = 82.0;

// --- DIMENSÕES DO GABINETE ---
console_w = 160.0; // Largura total (Falante na esquerda + Tela no centro/direita)
console_d = 105.0; // Profundidade na mesa
console_h = 75.0;  // Altura traseira

// Posição da Tela no Console (Centralizada para a direita)
tela_pos_x = 95.0; 
tela_pos_y = 45.0;
tela_pos_z = console_h/2 - 2;

// =============================================================================
// GABINETE PRINCIPAL DO SATÉLITE
// =============================================================================

module console_satelite_simplificado() {
    difference() {
        // Bloco aerodinâmico externo chanfrado
        hull() {
            // Base inferior
            translate([4, 4, 0]) cylinder(r=4, h=2);
            translate([console_w - 4, 4, 0]) cylinder(r=4, h=2);
            translate([console_w - 4, console_d - 4, 0]) cylinder(r=4, h=2);
            translate([4, console_d - 4, 0]) cylinder(r=4, h=2);

            // Perfil superior inclinado
            translate([6, 8, 16]) cylinder(r=4, h=2);
            translate([console_w - 6, 8, 16]) cylinder(r=4, h=2);
            translate([console_w - 6, console_d - 6, console_h - 2]) cylinder(r=4, h=2);
            translate([6, console_d - 6, console_h - 2]) cylinder(r=4, h=2);

            // Torre/Cúpula superior centralizada para o Microfone
            translate([console_w/2 - 12, console_d - 14, console_h])
                cube([24, 8, 6]);
        }

        // Cavidade interna geral (ESP32-S3, MAX98357A, fiação)
        translate([parede, parede, parede])
            cube([console_w - (parede*2), console_d - (parede*2), console_h + 12]);

        // 1. ABERTURA E BEZEL DO DISPLAY TFT 4.0" TOUCH
        translate([tela_pos_x, tela_pos_y, tela_pos_z])
            rotate([angulo_tela - 90, 0, 0]) {
                // Janela visível do vidro
                cube([tft_vidro_x, tft_vidro_y, 25], center=true);

                // Furação M3 (101.5 x 54.0 mm)
                for (dx = [-tft_furo_x/2, tft_furo_x/2]) {
                    for (dy = [-tft_furo_y/2, tft_furo_y/2]) {
                        translate([dx, dy, -15])
                            cylinder(d=3.2, h=30);
                    }
                }
            }

        // 2. LADO ESQUERDO: GRELHA DO ALTO-FALANTE 4Ω 3W
        translate([24, 40, 32])
            rotate([angulo_tela - 90, 0, 0]) {
                // Abertura acústica e grelha futurista
                for (slot = [-4 : 4]) {
                    translate([0, slot * 4.2, 0])
                        cube([24.0, 2.0, 16], center=true);
                }
            }

        // 3. TOPO CENTRALIZADO: PÓRTICO ACÚSTICO DO MICROFONE INMP441
        translate([console_w/2, console_d - 10, console_h + 3])
            rotate([30, 0, 0])
                cylinder(d=2.6, h=16, center=true); // Orifício frontal de 2.6mm

        // 4. LADO DIREITO: COLDRE DA CANETA STYLUS TOUCH
        translate([console_w - 5, console_d/2, 28])
            rotate([0, 90 - angulo_tela, 0]) {
                cylinder(d=caneta_d, h=caneta_comp + 5);
                translate([-3, 0, caneta_comp - 15])
                    cube([6, 8.5, 20]);
            }

        // 5. TRASEIRA: SAÍDA USB-C
        translate([console_w/2, console_d - 1, 10])
            cube([14, parede + 2, 8], center=true);
    }
}

// Câmara acústica selada para o Alto-falante no lado esquerdo
module camara_acustica_esquerda() {
    translate([8, 20, parede]) {
        difference() {
            cube([falante_w + 6, falante_l + 6, 22]);
            translate([3, 3, 2])
                cube([falante_w, falante_l, 24]);
        }
    }
}

// Berço isolado para a PCB do Microfone INMP441 no topo central
module berco_microfone_topo() {
    translate([console_w/2 - 9, console_d - 20, console_h - 12]) {
        difference() {
            cube([18, 18, 14]);
            translate([9, 9, 2])
                cylinder(d=mic_d, h=16);
        }
    }
}

// Trilhos de apoio para ESP32-S3 e MAX98357A na base
module berco_eletronica_base() {
    // Guias do ESP32-S3
    translate([console_w/2 - 15, 30, parede]) {
        cube([48, 3, 4]);
        translate([0, 28, 0]) cube([48, 3, 4]);
    }

    // Trilho do amplificador MAX98357A
    translate([45, 25, parede]) {
        difference() {
            cube([22, 21, 6]);
            translate([2, 2, 2])
                cube([18.5, 19.5, 6]);
        }
    }
}

// =============================================================================
// MONTAGEM FINAL DO CONSOLE
// =============================================================================
union() {
    console_satelite_simplificado();
    camara_acustica_esquerda();
    berco_microfone_topo();
    berco_eletronica_base();
}
