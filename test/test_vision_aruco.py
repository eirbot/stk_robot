"""Détection ArUco + pose sur images synthétiques (Rasp/Vision/aruco.py). Demande numpy et OpenCV :
    uv run python -m unittest test.test_vision_aruco      (env uv du dépôt : pyproject.toml)
Sauté si OpenCV est absent (python3 système)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
try:
    import cv2
    import numpy as np
    # importé ici : test_robot_integration remplace ensuite cv2 par un faux module dans sys.modules
    from Vision.aruco import DetecteurAruco, VisionAruco
except ImportError:
    cv2 = None

from core import vision_geom as vg  # noqa: E402
from core.frames import normalize_deg  # noqa: E402

TAILLE = 50.0
CFG_CAMERA = {
    "intrinseques": {"resolution": [1640, 1232], "fx": 1360.0, "fy": 1360.0, "cx": 820.0, "cy": 616.0},
    "montage": {"x": 150.0, "y": 0.0, "z": 150.0, "tangage": 8.0},
    "aruco": {"tags": {"13": {"taille_mm": TAILLE, "orientation": "vertical", "z": None}}},
}


def scene(cam, tags, bruit=4.0, seed=0):
    """Image grise 1640x1232 : fond texturé + tags (id, x, y, z, cap) rendus en perspective."""
    rnd = np.random.default_rng(seed)
    img = np.clip(rnd.normal(110, bruit, (1232, 1640)), 0, 255).astype(np.uint8)
    dico = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for id_tag, x, y, z, cap in tags:
        motif = cv2.aruco.generateImageMarker(dico, id_tag, 240)
        carte = np.full((360, 360), 245, np.uint8)        # tag + marge blanche (moitié d'un côté de chaque côté)
        carte[60:300, 60:300] = motif
        src = np.float32([[0, 0], [360, 0], [360, 360], [0, 360]])
        dst = np.float32(vg.projeter_tag(cam, x, y, z, cap, TAILLE * 1.5))
        h = cv2.getPerspectiveTransform(src, dst)
        rendu = cv2.warpPerspective(carte, h, (1640, 1232), flags=cv2.INTER_LINEAR, borderValue=0)
        masque = cv2.warpPerspective(np.full((360, 360), 255, np.uint8), h, (1640, 1232), flags=cv2.INTER_NEAREST)
        img[masque > 0] = rendu[masque > 0]
    return cv2.GaussianBlur(img, (3, 3), 0.8)


@unittest.skipIf(cv2 is None, "OpenCV absent (uv run python -m unittest test.test_vision_aruco)")
class TestDetectionPose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.DetecteurAruco, cls.VisionAruco = DetecteurAruco, VisionAruco
        cls.cam = vg.Camera.depuis_config(CFG_CAMERA, 1640, 1232)

    def mesurer(self, tags, **cfg):
        det = self.DetecteurAruco({**CFG_CAMERA["aruco"], **cfg})
        img = scene(self.cam, tags)
        res = det.detecter(img)
        poses = [vg.estimer_pose(self.cam, [tuple(map(float, p)) for p in pts], TAILLE, "vertical", id_tag=i)
                 for i, pts in res]
        return det, img, poses

    def test_pose_un_tag(self):
        for x, y, cap in ((450, 0, 180), (600, 80, 160), (500, -60, 195), (900, 30, 170)):
            with self.subTest(x=x, y=y, cap=cap):
                _, _, poses = self.mesurer([(13, x, y, 55, cap)])
                self.assertEqual(len(poses), 1)
                p = poses[0]
                self.assertEqual(p.id, 13)
                self.assertAlmostEqual(p.x, x, delta=0.02 * x)
                self.assertAlmostEqual(p.y, y, delta=5)
                self.assertAlmostEqual(p.z, 55, delta=6)
                self.assertAlmostEqual(normalize_deg(p.cap - cap), 0, delta=3)

    def test_ids_filtres(self):
        _, _, poses = self.mesurer([(13, 500, -80, 55, 180), (7, 500, 80, 55, 180)])
        self.assertEqual([p.id for p in poses], [13])

    def test_suivi(self):
        """2e image : recherche dans la fenêtre du tag précédent, même résultat."""
        det, img, poses = self.mesurer([(13, 600, 50, 55, 170)])
        self.assertEqual(len(det._zones), 1)
        res = det.detecter(img)
        self.assertEqual(len(res), 1)
        p = vg.estimer_pose(self.cam, [tuple(map(float, q)) for q in res[0][1]], TAILLE, "vertical")
        self.assertAlmostEqual(p.x, poses[0].x, delta=1)
        self.assertAlmostEqual(p.cap, poses[0].cap, delta=0.5)

    def test_temps(self):
        """Ordre de grandeur sur PC (la Pi 4 est ~5 à 8 fois plus lente)."""
        det = self.DetecteurAruco(CFG_CAMERA["aruco"])
        img = scene(self.cam, [(13, 600, 50, 55, 170)])
        t0 = time.perf_counter()
        for _ in range(10):
            det.detecter(img)
        ms = (time.perf_counter() - t0) * 100
        print(f"\n  détection 1640x1232 avec suivi : {ms:.1f} ms/image sur ce PC")

    def test_service_mesurer(self):
        """VisionAruco avec une fausse caméra : médiane de plusieurs images."""
        img = scene(self.cam, [(13, 550, 20, 55, 175)])

        class FausseCam:
            running = True
            frame_id = 0
            def attendre_image(self, dernier, timeout=1.0):
                time.sleep(0.01)
                self.frame_id += 1
                return self.frame_id
            def read_gray(self):
                return self.frame_id, time.time(), img

        vision = self.VisionAruco(FausseCam(), CFG_CAMERA)
        try:
            p = vision.mesurer(ids=[13], n=3, timeout=3.0)
        finally:
            vision.stop()
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p.x, 550, delta=12)
        self.assertAlmostEqual(p.y, 20, delta=5)
        self.assertAlmostEqual(p.ecart_angle, -5, delta=3)


if __name__ == "__main__":
    unittest.main()
