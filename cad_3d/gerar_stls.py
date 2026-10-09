import os
import math
import struct

def export_binary_stl(filename, triangles):
    """
    Exporta uma lista de triângulos para formato binário STL padrão.
    Cada triângulo é ((n_x, n_y, n_z), (v1_x, v1_y, v1_z), (v2_x, v2_y, v2_z), (v3_x, v3_y, v3_z))
    """
    with open(filename, 'wb') as f:
        header = b'J.A.R.V.I.S. 3D Printable Enclosure - Exported STL' + b'\0' * (80 - 48)
        f.write(header[:80])
        f.write(struct.pack('<I', len(triangles)))
        for norm, v1, v2, v3 in triangles:
            f.write(struct.pack('<3f3f3f3fH', 
                                norm[0], norm[1], norm[2],
                                v1[0], v1[1], v1[2],
                                v2[0], v2[1], v2[2],
                                v3[0], v3[1], v3[2],
                                0))
    print(f"[OK] STL gerado com sucesso: {filename} ({len(triangles)} triângulos)")

def calc_normal(v1, v2, v3):
    u = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
    v = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
    nx = u[1] * v[2] - u[2] * v[1]
    ny = u[2] * v[0] - u[0] * v[2]
    nz = u[0] * v[1] - u[1] * v[0]
    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
    if mag == 0:
        return (0.0, 0.0, 1.0)
    return (nx/mag, ny/mag, nz/mag)

def add_quad(triangles, v1, v2, v3, v4):
    n1 = calc_normal(v1, v2, v3)
    n2 = calc_normal(v1, v3, v4)
    triangles.append((n1, v1, v2, v3))
    triangles.append((n2, v1, v3, v4))

def add_box(triangles, x, y, z, dx, dy, dz):
    # 8 vértices
    p1 = (x, y, z)
    p2 = (x + dx, y, z)
    p3 = (x + dx, y + dy, z)
    p4 = (x, y + dy, z)
    p5 = (x, y, z + dz)
    p6 = (x + dx, y, z + dz)
    p7 = (x + dx, y + dy, z + dz)
    p8 = (x, y + dy, z + dz)
    
    # 6 faces
    add_quad(triangles, p4, p3, p2, p1) # Inferior (z)
    add_quad(triangles, p5, p6, p7, p8) # Superior (+z)
    add_quad(triangles, p1, p2, p6, p5) # Frontal (-y)
    add_quad(triangles, p2, p3, p7, p6) # Direita (+x)
    add_quad(triangles, p3, p4, p8, p7) # Traseira (+y)
    add_quad(triangles, p4, p1, p5, p8) # Esquerda (-x)

def gerar_cabeca_oled():
    tri = []
    # Caixa externa 40.0 x 53.0 x 14.0 mm
    w, l, h = 40.0, 53.0, 14.0
    # Janela visível do display 34.0 x 34.0 mm
    janela_w, janela_l = 34.0, 34.0
    
    # Moldura frontal (espessura de parede 2.5mm)
    t = 2.5
    borda_x = (w - janela_w) / 2 # 3.0 mm de borda
    borda_y = (l - janela_l) / 2 # 9.5 mm de borda
    add_box(tri, 0, 0, 0, w, borda_y, t)
    add_box(tri, 0, l - borda_y, 0, w, borda_y, t)
    add_box(tri, 0, borda_y, 0, borda_x, janela_l, t)
    add_box(tri, w - borda_x, borda_y, 0, borda_x, janela_l, t)
    
    # Paredes laterais da caixa (cavidade interna de 35.0 x 48.0 mm)
    add_box(tri, 0, 0, t, t, l, h - t)
    add_box(tri, w - t, 0, t, t, l, h - t)
    add_box(tri, t, 0, t, w - (2*t), t, h - t)
    add_box(tri, t, l - t, t, w - (2*t), t, h - t)
    
    # Base de fixação na garra (solicitado: espessura exata de 3.0 mm)
    # Largura de 23.0 mm (base do servo da garra) e 16.0 mm de comprimento
    bw, bl, bh = 23.0, 16.0, 3.0
    add_box(tri, (w - bw)/2, -bl, 0, bw, bl, bh)
    
    # Trilho superior para suporte de câmera / acessório
    add_box(tri, (w - 20.0)/2, l - 4, h - 2, 20.0, 6.0, 4.0)
    
    os.makedirs('d:/Jarvis/cad_3d/stls', exist_ok=True)
    export_binary_stl('d:/Jarvis/cad_3d/stls/cabeca_braco_oled.stl', tri)

def gerar_tampa_cabeca():
    tri = []
    w, l, h = 34.0, 47.4, 2.0
    add_box(tri, 0, 0, 0, w, l, h)
    export_binary_stl('d:/Jarvis/cad_3d/stls/tampa_cabeca_oled.stl', tri)

def gerar_tampa_inferior_satelite():
    tri = []
    w, d, h = 160.0, 105.0, 2.4
    add_box(tri, 0, 0, 0, w, d, h)
    export_binary_stl('d:/Jarvis/cad_3d/stls/tampa_inferior_satelite.stl', tri)

def gerar_pod_acustico():
    tri = []
    w, l, h = 46.0, 56.0, 42.0
    t = 2.4
    # Caixa base
    add_box(tri, 0, 0, 0, w, l, t)
    add_box(tri, 0, 0, t, t, l, h - t)
    add_box(tri, w - t, 0, t, t, l, h - t)
    add_box(tri, t, l - t, t, w - (2*t), t, h - t)
    # Frontal chanfrado
    add_box(tri, t, 0, t, w - (2*t), t, h - t)
    export_binary_stl('d:/Jarvis/cad_3d/stls/pod_acustico_satelite.stl', tri)

if __name__ == '__main__':
    gerar_cabeca_oled()
    gerar_tampa_cabeca()
    gerar_tampa_inferior_satelite()
    gerar_pod_acustico()
