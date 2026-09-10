"""
Módulo de Simulação de Hardware para o JARVIS.
Permite testar todas as respostas, movimentos do braço mecânico e
o rosto robótico do display OLED 1.5" diretamente no terminal!
"""

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

class HardwareSimulator:
    def __init__(self):
        self.braco_conectado = False
        self.tela_conectada = False
        self.posicao_atual = "REPOUSO"
        self.expressao_face = "NEUTRO"
        print("[HARDWARE SIMULATOR] Simulador virtual do Braço e Face OLED 1.5\" inicializado.")

    def desenhar_rosto_oled(self, expressao: str):
        """
        Emula a tela OLED 1.5" (128x128) do Arduino com expressões robóticas.
        """
        self.expressao_face = expressao.upper()
        faces = {
            "NEUTRO": ("  ┌───────────────┐\n"
                       "  │   ( ● ) ( ● )  │\n"
                       "  │               │\n"
                       "  └───────────────┘"),
            "FELIZ":  ("  ┌───────────────┐\n"
                       "  │   ( ^ ) ( ^ )  │\n"
                       "  │     ╰───╯     │\n"
                       "  └───────────────┘"),
            "OUVINDO":("  ┌───────────────┐\n"
                       "  │   [ ◉ ] [ ◉ ]  │\n"
                       "  │       (o)     │\n"
                       "  └───────────────┘"),
            "PISCANDO":("  ┌───────────────┐\n"
                       "  │   ───   ───   │\n"
                       "  │               │\n"
                       "  └───────────────┘"),
            "SONO":   ("  ┌───────────────┐\n"
                       "  │   ━━━   ━━━   │\n"
                       "  │      z Z Z    │\n"
                       "  └───────────────┘"),
            "FOCADO": ("  ┌───────────────┐\n"
                       "  │   / ● \\ / ● \\  │\n"
                       "  │               │\n"
                       "  └───────────────┘")
        }
        desenho = faces.get(self.expressao_face, faces["NEUTRO"])
        print("\n📺 [ROSTO OLED 1.5\" ARDUINO UNO] Expressão: " + self.expressao_face)
        print(desenho)

    def mover_braco(self, acao: str, detalhes: str = ""):
        """
        Simula os movimentos do braço mecânico no terminal sincronizado com a face.
        """
        acao = acao.lower().strip()
        print("\n" + "="*50)
        print(f"🦾 [BRAÇO ROBÓTICO] Executando movimento: {acao.upper()}")
        if detalhes:
            print(f"ℹ️ Detalhe: {detalhes}")
        
        if "aceno" in acao or "acenar" in acao or "wave" in acao:
            self.desenhar_rosto_oled("FELIZ")
            print("   [Base: 90° -> 115° -> 65° -> 115° -> 90°] Acenando suavemente...")
            self.posicao_atual = "ACENANDO"
        elif "apontar" in acao or "point" in acao:
            self.desenhar_rosto_oled("FOCADO")
            print("   [Ombro: 120°, Cotovelo: 120°, Garra: Fechada com ponteiro] Apontando...")
            self.posicao_atual = "APONTANDO"
        elif "positivo" in acao or "confirmar" in acao:
            self.desenhar_rosto_oled("FELIZ")
            print("   [Cotovelo: 110°, Garra: Aberta 2x] Gesto afirmativo...")
            self.posicao_atual = "POSITIVO"
        elif "repouso" in acao or "rest" in acao or "dormir" in acao:
            self.desenhar_rosto_oled("SONO")
            print("   [Todos os servos retornando à posição recolhida: 45°]")
            self.posicao_atual = "REPOUSO"
        else:
            self.desenhar_rosto_oled("NEUTRO")
            print(f"   [Movimento: {acao}]")
            self.posicao_atual = acao.upper()
            
        print(f"✅ [BRAÇO] Concluído. Estado: {self.posicao_atual}")
        print("="*50 + "\n")
        return f"Movimento '{acao}' executado com sucesso."

    def atualizar_tela(self, titulo: str, subtitulo: str, icone: str = "🤖"):
        """
        Simula o card da tela.
        """
        print("\n" + "┌" + "─"*46 + "┐")
        print(f"│  📺 [PAINEL INFORMATIVO] {icone:<26}│")
        print("├" + "─"*46 + "┤")
        print(f"│  TÍTULO: {titulo[:35]:<36}│")
        print(f"│  STATUS: {subtitulo[:35]:<36}│")
        print("└" + "─"*46 + "┘\n")
        return "Tela atualizada."

hardware = HardwareSimulator()
