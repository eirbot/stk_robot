"""Tags ArUco vus par la caméra embarquée : détection rapide sur Pi 4 + pose dans le repère robot.

Réutilisable d'une année à l'autre : ce qui dépend du règlement est dans la config
(camera.aruco : dictionnaire, tags attendus avec taille, orientation et hauteur). La géométrie
(pose d'un tag à partir de ses coins) est dans core/vision_geom.py, pure et testée sur PC.

Usage (stratégie) :
    import hardware
    tag = hardware.vision.mesurer(ids=[13], n=5)     # médiane de 5 images, robot arrêté
    if tag: print(tag.distance, tag.y, tag.ecart_angle)

Ce qui est fait pour la Pi 4 :
- image grise lue directement dans le plan Y du flux YUV420 (aucune conversion couleur) ;
- recherche sur une image réduite (camera.aruco.echelle), coins ensuite affinés au sous-pixel sur
  l'image pleine résolution, autour des seuls coins trouvés ;
- si des tags ont été vus à l'image précédente : recherche d'abord dans une fenêtre autour d'eux
  (budget de pixels fixe), image entière seulement si rien n'y est trouvé ou toutes les N images ;
- 2 seuillages adaptatifs au lieu de 3, taille minimale de tag, ids filtrés tôt ;
- OpenCV limité à 2 threads (le reste de la Pi sert au LiDAR, à l'IHM, aux ESP) ;
- le thread ne travaille que quand quelqu'un l'a activé (mesurer, activer, flux ?aruco=1).
"""

import statistics
import threading
import time

import cv2
import numpy as np

from core import vision_geom
from core.frames import normalize_deg

DEFAUT_ARUCO = {
    "dictionnaire": "DICT_4X4_50",
    "echelle": 0.5,            # réduction de l'image pour la recherche (1 = pleine résolution)
    "plein_cadre_toutes": 10,  # avec suivi : image entière au moins toutes les N images
    "threads": 2,
    "aruco3": False,           # « ArUco 3 » d'OpenCV : pas plus rapide ici, coins grossiers (5-7 px)
    "err_px_max": 3.0,         # pose rejetée au-delà (coins incohérents avec un tag plat)
    # id -> {taille_mm, orientation ("vertical"/"horizontal"), z (mm, liste de hauteurs, ou null)}
    "tags": {},
}


def _params_detecteur(cfg):
    p = cv2.aruco.DetectorParameters() if hasattr(cv2.aruco, "DetectorParameters") \
        else cv2.aruco.DetectorParameters_create()
    p.adaptiveThreshWinSizeMin = 7
    p.adaptiveThreshWinSizeMax = 23
    p.adaptiveThreshWinSizeStep = 16          # fenêtres 7 et 23 : 2 seuillages
    p.minMarkerPerimeterRate = 0.04            # ~8 px de côté sur 820 px de large
    p.maxMarkerPerimeterRate = 4.0
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE   # affinage fait en pleine résolution
    if cfg.get("aruco3") and hasattr(p, "useAruco3Detection"):
        p.useAruco3Detection = True
        p.minSideLengthCanonicalImg = 16
    return p


class DetecteurAruco:
    """Détection seule (pas de géométrie) : image grise -> [(id, coins 4x2 en pixels pleine résolution)]."""

    def __init__(self, cfg_aruco=None):
        self.cfg = {**DEFAUT_ARUCO, **(cfg_aruco or {})}
        cv2.setNumThreads(int(self.cfg["threads"]))
        dico = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, self.cfg["dictionnaire"]))
        params = _params_detecteur(self.cfg)
        if hasattr(cv2.aruco, "ArucoDetector"):
            det = cv2.aruco.ArucoDetector(dico, params)
            self._detect = lambda img: det.detectMarkers(img)
        else:                                   # OpenCV < 4.7
            self._detect = lambda img: cv2.aruco.detectMarkers(img, dico, parameters=params)
        ids = self.cfg.get("tags") or {}
        self.ids_attendus = {int(i) for i in ids} or None
        self._zones = []                        # fenêtres de suivi (x0, y0, x1, y1), pleine résolution
        self._n = 0
        self._critere = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.01)

    def _chercher(self, gray, x0, y0, x1, y1, budget):
        zone = gray[y0:y1, x0:x1]
        h, w = zone.shape
        e = min(1.0, (budget / float(w * h)) ** 0.5)
        img = zone if e >= 0.999 else cv2.resize(zone, (int(w * e), int(h * e)), interpolation=cv2.INTER_AREA)
        coins, ids, _ = self._detect(img)
        if ids is None:
            return []
        out = []
        for c, i in zip(coins, ids.flatten()):
            if self.ids_attendus is not None and int(i) not in self.ids_attendus:
                continue
            pts = c.reshape(4, 2) / e + (x0, y0)
            out.append((int(i), pts.astype(np.float32)))
        return out

    def _affiner(self, gray, pts):
        cote = float(np.max(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1)))
        win = int(max(2, min(7, cote / 12)))
        p = pts.reshape(-1, 1, 2).copy()
        cv2.cornerSubPix(gray, p, (win, win), (-1, -1), self._critere)
        return p.reshape(4, 2)

    def detecter(self, gray):
        H, W = gray.shape
        budget = W * H * float(self.cfg["echelle"]) ** 2
        self._n += 1
        trouves = []
        if self._zones and self._n % int(self.cfg["plein_cadre_toutes"]):
            for x0, y0, x1, y1 in self._zones:
                trouves += self._chercher(gray, x0, y0, x1, y1, budget / len(self._zones))
        if not trouves:
            trouves = self._chercher(gray, 0, 0, W, H, budget)
        # un tag vu dans deux fenêtres qui se chevauchent : on n'en garde qu'un
        uniques = []
        for i, pts in trouves:
            c = pts.mean(axis=0)
            if all(j != i or np.linalg.norm(q.mean(axis=0) - c) > 5 for j, q in uniques):
                uniques.append((i, pts))
        res = [(i, self._affiner(gray, pts)) for i, pts in uniques]
        self._zones = []
        for _, pts in res:                       # fenêtre = boîte du tag agrandie 3x
            (xa, ya), (xb, yb) = pts.min(axis=0), pts.max(axis=0)
            m = max(xb - xa, yb - ya)
            self._zones.append((max(0, int(xa - m)), max(0, int(ya - m)), min(W, int(xb + m)), min(H, int(yb + m))))
        return res


class VisionAruco:
    """Service : thread de détection à la demande + poses des tags dans le repère robot."""

    def __init__(self, camera, cfg_camera):
        self.camera = camera
        self.cfg_camera = cfg_camera
        self.cfg = {**DEFAUT_ARUCO, **(cfg_camera.get("aruco") or {})}
        self.detecteur = DetecteurAruco(self.cfg)
        self._cam_geom = None
        self._lock = threading.Lock()
        self._actif_jusqua = 0.0
        self._demandes = 0
        self.dernieres = []          # [PoseTag] de la dernière image traitée
        self.t_derniere = 0.0
        self.ms_par_image = 0.0
        self.running = True
        self.thread = threading.Thread(target=self._boucle, daemon=True, name="vision_aruco")
        self.thread.start()

    # --- activation ------------------------------------------------------------------------

    def activer(self, duree_s=2.0):
        """Fait tourner la détection pendant duree_s (à rappeler pour prolonger)."""
        self._actif_jusqua = max(self._actif_jusqua, time.time() + duree_s)

    @property
    def actif(self):
        return self._demandes > 0 or time.time() < self._actif_jusqua

    def stop(self):
        self.running = False

    # --- géométrie -------------------------------------------------------------------------

    def _geom(self, w, h):
        g = self._cam_geom
        if g is None or (g.intr.largeur, g.intr.hauteur) != (w, h):
            g = self._cam_geom = vision_geom.Camera.depuis_config(self.cfg_camera, w, h)
            if not g.calibree:
                print("[VISION] Caméra non calibrée (camera.intrinseques) : distances approximatives.")
        return g

    def _pose(self, geom, id_tag, pts, t):
        spec = (self.cfg.get("tags") or {}).get(str(id_tag))
        if not spec:
            return None
        pose = vision_geom.estimer_pose(geom, [tuple(map(float, p)) for p in pts], float(spec["taille_mm"]),
                                        spec.get("orientation", "vertical"), z=spec.get("z"),
                                        quarts=spec.get("quarts"), id_tag=id_tag, t=t)
        if pose is None or pose.err_px > float(self.cfg["err_px_max"]):
            return None
        return pose

    # --- boucle ----------------------------------------------------------------------------

    def _boucle(self):
        dernier = 0
        while self.running:
            if not self.actif or self.camera is None or not self.camera.running:
                time.sleep(0.05)
                continue
            fid = self.camera.attendre_image(dernier, timeout=0.5)
            if fid is None:
                continue
            fid, t, gray = self.camera.read_gray()
            dernier = fid
            t0 = time.perf_counter()
            try:
                dets = self.detecteur.detecter(gray)
                geom = self._geom(gray.shape[1], gray.shape[0])
                poses = [p for p in (self._pose(geom, i, pts, t) for i, pts in dets) if p]
            except Exception as e:
                print(f"[VISION] Erreur détection : {e}")
                continue
            dt = (time.perf_counter() - t0) * 1000
            with self._lock:
                self.dernieres, self.t_derniere = poses, t
                self.ms_par_image = dt if not self.ms_par_image else 0.8 * self.ms_par_image + 0.2 * dt

    def derniere(self, ids=None, age_max_s=0.5):
        """Poses vues sur la dernière image traitée (récente), filtrées par id."""
        with self._lock:
            if time.time() - self.t_derniere > age_max_s:
                return []
            return [p for p in self.dernieres if ids is None or p.id in ids]

    def mesurer(self, ids=None, n=5, timeout=1.5, choix="proche"):
        """Médiane de n mesures du même tag (robot arrêté), ou None si pas assez d'images.

        choix : "proche" (le plus près du robot) ou "centre" (le plus dans l'axe) quand plusieurs
        tags sont vus. La médiane élimine une image ratée ; pour un tag vu en mouvement, utiliser
        derniere() avec l'instant `t` de chaque pose.
        """
        self._demandes += 1
        try:
            mesures, vue, fin = [], 0.0, time.time() + timeout
            while time.time() < fin and len(mesures) < n:
                time.sleep(0.02)
                with self._lock:
                    if self.t_derniere <= vue:
                        continue
                    vue, poses = self.t_derniere, [p for p in self.dernieres if ids is None or p.id in ids]
                if not poses:
                    continue
                cle = (lambda p: p.distance) if choix == "proche" else (lambda p: abs(p.y))
                cible = min(poses, key=cle)
                if mesures:   # même tag que la première mesure (à 40 mm près)
                    ref = mesures[0]
                    if abs(cible.x - ref.x) > 40 or abs(cible.y - ref.y) > 40:
                        continue
                mesures.append(cible)
            if len(mesures) < max(1, (n + 1) // 2):
                return None
            return _mediane(mesures)
        finally:
            self._demandes -= 1

    # --- affichage -------------------------------------------------------------------------

    def dessiner(self, bgr):
        """Dessine les derniers tags sur l'image d'affichage (BGR, à l'échelle du flux)."""
        poses = self.derniere(age_max_s=1.0)
        if not poses or self._cam_geom is None:
            return bgr
        img = bgr.copy()
        e = img.shape[1] / float(self._cam_geom.intr.largeur)
        for p in poses:
            pts = (np.array(p.coins_px) * e).astype(np.int32)
            cv2.polylines(img, [pts], True, (0, 255, 0), 2)
            cv2.circle(img, tuple(pts[0]), 4, (0, 0, 255), -1)
            txt = f"{p.id}: {p.distance:.0f}mm y{p.y:+.0f} a{p.ecart_angle:+.1f}"
            cv2.putText(img, txt, (int(pts[:, 0].min()), int(pts[:, 1].min()) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
        cv2.putText(img, f"{self.ms_par_image:.0f} ms/image", (8, img.shape[0] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        return img


def _mediane(poses):
    """Pose médiane composante par composante (cap : médiane des écarts au premier, sans saut à ±180)."""
    ref = poses[0]
    cap = normalize_deg(ref.cap + statistics.median(normalize_deg(p.cap - ref.cap) for p in poses))
    return vision_geom.PoseTag(
        id=ref.id, x=statistics.median(p.x for p in poses), y=statistics.median(p.y for p in poses),
        z=statistics.median(p.z for p in poses), cap=cap, orientation=ref.orientation,
        taille_mm=ref.taille_mm, err_px=statistics.median(p.err_px for p in poses),
        quart=ref.quart, coins_px=poses[-1].coins_px, t=poses[-1].t)
