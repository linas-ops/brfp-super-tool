"""Regressões da camisa no mapa distribuído, sem os modelos 3D ou um kit base."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "motor"))
from conversor import converter_texturas


class MapaCamisaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Kit de 1024 px com um emblema circular e faixas contínuas no tronco e nas duas mangas.
        kit = np.full((1024, 1024, 3), (205, 200, 89), np.uint8)
        for inicio in (463, 478, 493):
            kit[inicio:inicio + 8] = 20
            kit[inicio - 280:inicio - 272] = 20  # mesma faixa na ilha da manga longa do PES
        y, x = np.ogrid[:1024, :1024]
        kit[(x - 512)**2 + (y - 660)**2 <= 35**2] = (200, 0, 200)
        kit[750:880, 351:360] = 20  # estampa na lateral, junto à borda do tronco do PES
        cls.camisa = converter_texturas(kit)["jersey"]

    def test_tres_faixas_coincidem_nas_duas_cavas(self):
        def bordas(x, deslocamento):
            perfil = self.camisa[940 - deslocamento:1110 - deslocamento, x, 0] < 90
            return np.flatnonzero(np.diff(perfil, prepend=False))

        for tronco, manga in ((744, 726), (1303, 1321)):
            esperado = bordas(tronco, 0)
            self.assertEqual(esperado.size, 6)
            for deslocamento in (0, 662):  # manga longa encosta no tronco, curta fica acima
                np.testing.assert_allclose(bordas(manga, deslocamento), esperado, atol=1)

    def test_proporcao_do_emblema(self):
        peito = self.camisa[1240:1500, 850:1200]
        # Peso do pigmento magenta, incluindo os pixels de borda parcialmente cobertos.
        peso = np.clip((peito[..., 2] - 89) / (200 - 89), 0, 1)
        self.assertGreater(peso.sum(), 14000)
        y, x = np.indices(peso.shape)
        dx = x - np.average(x, weights=peso)
        dy = y - np.average(y, weights=peso)
        largura = np.sqrt(np.average(dx**2, weights=peso))
        altura = np.sqrt(np.average(dy**2, weights=peso))
        self.assertAlmostEqual(largura / altura, 1, delta=0.01)
        self.assertLess(abs(np.average(dx*dy, weights=peso)) / (largura * altura), 0.01)

    def test_fundo_longe_das_ilhas(self):
        fundo = self.camisa[1600:1900:16, :120:16]
        self.assertLessEqual(np.abs(fundo - (205, 200, 89)).max(), 1)


if __name__ == "__main__":
    unittest.main()
