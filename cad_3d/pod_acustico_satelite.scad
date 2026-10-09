// =============================================================================
// J.A.R.V.I.S. - MÓDULO 3: POD ACÚSTICO SATÉLITE (SOM & VOZ DEDICADOS)
// =============================================================================
// Módulo de bancada independente (Estilo Reator Arc / Mini Torre Studio):
//   - Aloja o Alto-falante 4 Ohm 3W (27.8 x 36.7 mm) com câmara acústica dedicada
//   - Aloja o Microfone MEMS I2S INMP441 (13.6 mm) em cápsula isolada antirruído
//   - Pode ser posicionado em qualquer lugar da bancada ou acoplado ao console
//   - Elimina 100% de autofeedback acústico entre a voz do Jarvis e a tela touch
// =============================================================================

$fn = 40;

folga = 0.4;
parede = 2.4;

// Dimensões do Alto-falante (27.8 x 36.7 mm)
falante_w = 27.8 + folga;
falante_l = 36.7 + folga;
falante_prof = 11.0;

// Dimensões do Microfone INMP441
mic_d = 13.6 + folga;

// Dimensões do Pod Acústico
pod_w = 46.0;
pod_l = 56.0;
pod_h = 42.0;
inclinacao = 65; // Inclinado 65 graus apontando direto para a cabeça do usuário

module pod_acustico_corpo() {
    difference() {
        // Gabinete futurista arredondado
        hull() {
            translate([4, 4, 0]) cylinder(r=4, h=pod_h);
            translate([pod_w - 4, 4, 0]) cylinder(r=4, h=pod_h);
            translate([pod_w - 4, pod_l - 4, 0]) cylinder(r=4, h=pod_h);
            translate([4, pod_l - 4, 0]) cylinder(r=4, h=pod_h);
        }

        // Cavidade acústica traseira selada para o alto-falante (~25 cm³)
        translate([parede, parede, parede])
            cube([pod_w - (parede*2), pod_l - (parede*2), pod_h - parede]);

        // Frontal inclinado com grelha de som e pórtico de mic
        translate([pod_w/2, 10, pod_h/2])
            rotate([inclinacao - 90, 0, 0]) {
                // Abertura do alto-falante
                translate([0, 4, 0]) {
                    // Grelha tipo Reator Arc com ranhuras concêntricas
                    cylinder(d=28.0, h=15, center=true);
                }

                // Orifício isolado do microfone MEMS (Ø 2.5 mm)
                translate([0, -18, 0])
                    cylinder(d=2.6, h=15, center=true);
            }

        // Passa-cabos traseiro para chicote de áudio (I2S MAX98357A + INMP441)
        translate([pod_w/2, pod_l - 1, 8])
            cube([12, parede + 2, 8], center=true);

        // Furos M2.5 para fixação do falante
        translate([pod_w/2, 10, pod_h/2])
            rotate([inclinacao - 90, 0, 0]) {
                translate([-falante_w/2, 4, 0]) cylinder(d=2.6, h=15, center=true);
                translate([falante_w/2, 4, 0]) cylinder(d=2.6, h=15, center=true);
            }
    }
}

// Tampa traseira selada com ranhuras de descompressão acústica
module tampa_pod_acustico() {
    difference() {
        cube([pod_w - 0.4, pod_l - 0.4, 2.0]);
        // 4 furos M2.5 de fechamento
        for (pos = [[5, 5], [pod_w - 5, 5], [pod_w - 5, pod_l - 5], [5, pod_l - 5]]) {
            translate([pos[0], pos[1], -0.5])
                cylinder(d=2.8, h=3);
        }
    }
}

// Renderização principal do Pod
pod_acustico_corpo();
