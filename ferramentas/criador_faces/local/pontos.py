"""Pontos do rosto (478) e segmentação (pele, cabelo, fundo) com o MediaPipe (Apache 2.0), rodando no computador.

Os modelos (face_landmarker.task e selfie_multiclass_256x256.tflite) são baixados à parte para runtime/modelos.
"""
import os
import sys
import types

import numpy as np

from . import MODELOS, PASTA_MODELOS, Erro

CLASSES = ("fundo", "cabelo", "pele_corpo", "pele_rosto", "roupa", "outros")
OPCIONAIS = ("matplotlib", "sounddevice", "certifi", "absl", "flatbuffers")   # o pacote importa, mas não usa aqui
_det = _seg = _mp = None


def modelos_faltando():
    return [n for n, m in MODELOS.items() if not os.path.isfile(os.path.join(PASTA_MODELOS, n)) or
            os.path.getsize(os.path.join(PASTA_MODELOS, n)) != m["tamanho"]]


def mediapipe():
    """importa o mediapipe; módulos que ele só usa para desenhar ou gravar áudio viram módulos vazios se faltarem"""
    global _mp
    if _mp is not None:
        return _mp
    for _ in range(12):
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision  # noqa: F401
            from mediapipe.tasks.python.core.base_options import BaseOptions  # noqa: F401
            _mp = mp
            return mp
        except ModuleNotFoundError as ex:
            nome = ex.name or ""
            if nome.split(".")[0] not in OPCIONAIS:
                raise Erro("Falta o MediaPipe (ou um pacote dele: %s). Instale os componentes do criador próprio." % nome) from ex
            partes = nome.split(".")
            for i in range(1, len(partes) + 1):
                n = ".".join(partes[:i])
                if n not in sys.modules:
                    mod = types.ModuleType(n)
                    mod.__path__ = []
                    sys.modules[n] = mod
            for k in [k for k in sys.modules if k == "mediapipe" or k.startswith("mediapipe.")]:
                del sys.modules[k]
    raise Erro("Não consegui carregar o MediaPipe.")


def _modelo(nome):
    c = os.path.join(PASTA_MODELOS, nome)
    if not os.path.isfile(c):
        raise Erro("Falta o modelo %s do MediaPipe. Instale os componentes do criador próprio." % nome)
    return c


def _opcoes_base(nome):
    from mediapipe.tasks.python.core.base_options import BaseOptions
    # o caminho pode ter acentos: o modelo vai pela memória
    with open(_modelo(nome), "rb") as f:
        return BaseOptions(model_asset_buffer=f.read())


def detectar(rgb):
    """rgb uint8 H x W x 3 -> pontos 478 x 3 em pixels [x, y, z] ou None"""
    global _det
    mp = mediapipe()
    from mediapipe.tasks.python import vision
    if _det is None:
        opts = vision.FaceLandmarkerOptions(base_options=_opcoes_base("face_landmarker.task"), num_faces=1,
                                            min_face_detection_confidence=0.3, min_face_presence_confidence=0.3)
        _det = vision.FaceLandmarker.create_from_options(opts)
    h, w = rgb.shape[:2]
    res = _det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb, np.uint8)))
    if not res.face_landmarks:
        return None
    return np.array([[q.x * w, q.y * h, q.z * w] for q in res.face_landmarks[0]])


def segmentar(rgb):
    """rgb uint8 -> classes (H x W): 0 fundo, 1 cabelo, 2 pele do corpo, 3 pele do rosto, 4 roupa, 5 outros"""
    global _seg
    mp = mediapipe()
    from mediapipe.tasks.python import vision
    if _seg is None:
        opts = vision.ImageSegmenterOptions(base_options=_opcoes_base("selfie_multiclass_256x256.tflite"),
                                            output_category_mask=True, output_confidence_masks=False)
        _seg = vision.ImageSegmenter.create_from_options(opts)
    res = _seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb, np.uint8)))
    return np.array(res.category_mask.numpy_view()).reshape(rgb.shape[:2]).astype(np.uint8)


def fechar():
    """fecha os modelos antes de o programa sair (evita erro no destrutor do MediaPipe)"""
    global _det, _seg
    for x in (_det, _seg):
        try:
            if x is not None:
                x.close()
        except Exception:  # noqa: BLE001
            pass
    _det = _seg = None


# contornos dos olhos na malha do MediaPipe (para tirar a abertura dos olhos da textura)
OLHO_DIREITO = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246)
OLHO_ESQUERDO = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466)
LABIOS_DENTRO = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191)
N_ROSTO = 468                                   # de 468 em diante são as íris
