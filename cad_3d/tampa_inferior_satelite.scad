// =============================================================================
// J.A.R.V.I.S. - TAMPA INFERIOR / BASE DO CONSOLE SATÉLITE (160 x 105 mm)
// =============================================================================
// Fechamento da base com furos M3, ventilação do ESP32-S3 e pés de silicone
// =============================================================================

$fn = 35;

satelite_w = 160.0;
satelite_d = 105.0;
espessura_tampa = 2.4;

difference() {
    // Placa base com cantos arredondados
    hull() {
        translate([4, 4, 0]) cylinder(r=4, h=espessura_tampa);
        translate([satelite_w - 4, 4, 0]) cylinder(r=4, h=espessura_tampa);
        translate([satelite_w - 4, satelite_d - 4, 0]) cylinder(r=4, h=espessura_tampa);
        translate([4, satelite_d - 4, 0]) cylinder(r=4, h=espessura_tampa);
    }

    // 4 Furos escareados para parafusos M3 nos cantos
    for (pos = [[8, 8], [satelite_w - 8, 8], [satelite_w - 8, satelite_d - 8], [8, satelite_d - 8]]) {
        translate([pos[0], pos[1], -0.5]) {
            cylinder(d=3.4, h=espessura_tampa + 1);
            translate([0, 0, espessura_tampa - 1.0])
                cylinder(d1=3.4, d2=6.2, h=1.6);
        }
    }

    // Grelha de ventilação central (Fluxo térmico do ESP32-S3)
    translate([satelite_w/2, satelite_d/2 + 5, 0]) {
        for (i = [-4 : 4]) {
            translate([0, i * 6, espessura_tampa/2])
                cube([55, 2.5, espessura_tampa + 1], center=true);
        }
    }

    // Rebaixos circulares para pés de borracha/silicone (Ø 8mm)
    for (pe = [[14, 14], [satelite_w - 14, 14], [satelite_w - 14, satelite_d - 14], [14, satelite_d - 14]]) {
        translate([pe[0], pe[1], -0.1])
            cylinder(d=8.2, h=0.8);
    }
}
