"""Criador próprio de faces (sem serviço externo): fotos -> headmorphpreset FBX + textura da face do FC 27.

Tudo o que vem do jogo (cabeça base, estatística das cabeças, peles de base, textura dos olhos) é lido do FC 27 instalado
no computador de quem usa, pelo cache do FIFA Editor Tool, e fica em cache/ (fora do repositório e do pacote).

    jogo.py      leitura do jogo (índice do cache do FET, blends de morph, texturas)
    modelo.py    cabeça base + modelo estatístico (PCA) das cabeças masculinas + olhos de referência + peles de base
    pontos.py    MediaPipe: 478 pontos do rosto e segmentação (pele, cabelo, fundo)
    raster.py    câmera (com perspectiva) e rasterizador
    ajustar.py   ajuste da forma e das câmeras às fotos (pontos + silhueta do perfil)
    olhos.py     globos oculares e UV da íris no padrão do jogo
    textura.py   textura careca: pele das fotos + pele de base do jogo
    saida.py     FBX de saída, prévia .glb e imagens de conferência
    criar.py     a sequência inteira (linha de comando com progresso em JSON)
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FERRAMENTA = os.path.dirname(AQUI)
SUPERTOOL = os.path.dirname(os.path.dirname(FERRAMENTA))
CACHE = os.path.join(FERRAMENTA, "cache")
DADOS = os.path.join(AQUI, "tabelas")      # tabelas próprias (ponto do MediaPipe -> cabeça base); "dados" fica fora do pacote
FACES_MOTOR = os.path.join(SUPERTOOL, "ferramentas", "faces", "motor")
ESTADIOS_FC27 = os.path.join(SUPERTOOL, "ferramentas", "estadios_fc27")
REFERENCIA = os.path.join(FACES_MOTOR, "referencia", "messi_158023_fc27.fbx")
ID_REFERENCIA = "158023"
VERSAO_MOTOR = "2.0"
# modelos do MediaPipe (Apache 2.0), baixados à parte para runtime/modelos/mediapipe
PASTA_MODELOS = os.environ.get("BRFP_MODELOS_MEDIAPIPE") or os.path.join(
    os.environ.get("BRFP_RUNTIME") or os.path.join(SUPERTOOL, "runtime"), "modelos", "mediapipe")
MODELOS = {
    "face_landmarker.task": dict(
        nome="MediaPipe Face Landmarker", versao="1", arquivo="face_landmarker.task", tamanho=3758596,
        url="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        sha256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
    "selfie_multiclass_256x256.tflite": dict(
        nome="MediaPipe Selfie Multiclass", versao="1", arquivo="selfie_multiclass_256x256.tflite", tamanho=16371837,
        url="https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/"
            "selfie_multiclass_256x256.tflite",
        sha256="c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0"),
}


def caminhos():
    """Põe no sys.path os motores vizinhos que este usa (leitor de FBX do Conversor de Faces, leitor do jogo dos
    Estádios FC 27) e a pasta comum."""
    for p in (os.path.join(SUPERTOOL, "comum"), ESTADIOS_FC27, FACES_MOTOR):
        if p not in sys.path:
            sys.path.insert(0, p)


class Erro(Exception):
    """Erro com mensagem para o usuário."""
