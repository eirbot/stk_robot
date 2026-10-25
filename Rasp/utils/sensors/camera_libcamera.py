"""Caméra embarquée (Picamera2 sur la Raspberry ; sur PC, webcam OpenCV si camera.webcam = son numéro).

Deux flux YUV420 produits par l'ISP de la Pi, sans conversion logicielle :
- principal (`resolution`, 1640x1232 par défaut = champ complet de l'IMX219 en binning 2x2) :
  seul son plan Y (niveaux de gris) est copié, c'est l'image de la détection ArUco ;
- affichage (`affichage`, plus petit) : converti en BGR seulement quand quelqu'un le demande
  (flux MJPEG), une fois par image.
La rotation de 180° est faite par le capteur (Transform), pas par OpenCV. Pas de file d'images
(queue=False) : on lit toujours la plus récente.

Couleurs : l'ancien code demandait du « BGR888 » puis inversait R et B. Avec YUV420 il n'y a plus
d'ordre de canaux à deviner. Si l'image reste rosée, ce n'est pas une inversion : module sans
filtre IR (NoIR) ou mauvais fichier de réglage -> camera.tuning (ex. "imx219_noir.json").
"""

import threading
import time

import cv2

try:
    from picamera2 import Picamera2, MappedArray
    from libcamera import Transform
except ImportError:
    Picamera2 = None


class LibCamera:
    def __init__(self, resolution=(1640, 1232), framerate=10, affichage=(820, 616),
                 rotation_180=True, tuning=None, controles=None, webcam_id=None):
        self.running = False
        self.resolution = tuple(resolution)
        self.affichage = tuple(affichage)
        self.framerate = framerate
        self.picam2 = None
        self._cap = None
        self.thread = None
        self._cond = threading.Condition()
        self._gray = None          # plan Y pleine résolution (uint8, h x w)
        self._lores = None         # YUV420 du flux d'affichage (ou BGR en mode webcam)
        self._bgr = None           # cache de la conversion couleur de l'image courante
        self._bgr_id = -1
        self.frame_id = 0
        self.t = 0.0

        if Picamera2 is not None:
            self._init_picamera(rotation_180, tuning, controles or {})
        elif webcam_id is not None:
            self._init_webcam(webcam_id, rotation_180)
        else:
            print("[ERREUR CAM] picamera2 absent (sudo apt install python3-picamera2).")

    def _init_picamera(self, rotation_180, tuning, controles):
        try:
            print(f"[CAM] Picamera2 {self.resolution} @ {self.framerate} fps, affichage {self.affichage}")
            self.picam2 = Picamera2(tuning=Picamera2.load_tuning_file(tuning) if tuning else None)
            d = int(1_000_000 / self.framerate)
            config = self.picam2.create_video_configuration(
                main={"size": self.resolution, "format": "YUV420"},
                lores={"size": self.affichage, "format": "YUV420"},
                transform=Transform(hflip=1, vflip=1) if rotation_180 else Transform(),
                buffer_count=4, queue=False,
                controls={"FrameDurationLimits": (d, d), **controles})
            self.picam2.configure(config)
            self.resolution = tuple(self.picam2.camera_config["main"]["size"])
            self.affichage = tuple(self.picam2.camera_config["lores"]["size"])
            self.picam2.start()
            self.running = True
        except Exception as e:
            print(f"[ERREUR CAM] Impossible de démarrer Picamera2 : {e}")
            if self.picam2:
                try:
                    self.picam2.close()
                except Exception:
                    pass
            self.picam2 = None

    def _init_webcam(self, webcam_id, rotation_180):
        self._cap = cv2.VideoCapture(webcam_id)
        if not self._cap.isOpened():
            print(f"[ERREUR CAM] Webcam {webcam_id} introuvable.")
            self._cap = None
            return
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self._rotation_180 = rotation_180
        self.running = True
        print("[CAM] picamera2 absent : webcam OpenCV.")

    def start(self):
        if self.running:
            self.thread = threading.Thread(target=self._boucle, daemon=True, name="camera")
            self.thread.start()
        return self

    # --- capture ---------------------------------------------------------------------------

    def _capture_picamera(self):
        req = self.picam2.capture_request()
        try:
            w, h = self.resolution
            with MappedArray(req, "main") as m:
                gray = m.array[:h, :w].copy()
            lores = req.make_array("lores")
        finally:
            req.release()
        return gray, lores

    def _capture_webcam(self):
        ok, bgr = self._cap.read()
        if not ok:
            return None, None
        if self._rotation_180:
            bgr = cv2.rotate(bgr, cv2.ROTATE_180)
        self.resolution = (bgr.shape[1], bgr.shape[0])
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), bgr

    def _boucle(self):
        while self.running:
            try:
                gray, lores = self._capture_picamera() if self.picam2 else self._capture_webcam()
            except Exception as e:
                print(f"[CAM] Erreur capture : {e}")
                gray = None
            if gray is None:
                time.sleep(0.1)
                continue
            with self._cond:
                self._gray, self._lores = gray, lores
                self.frame_id += 1
                self.t = time.time()
                self._cond.notify_all()

    # --- lecture ---------------------------------------------------------------------------

    def attendre_image(self, dernier_id=0, timeout=1.0):
        """Attend une image plus récente que `dernier_id` ; renvoie son numéro (ou None)."""
        with self._cond:
            if not self._cond.wait_for(lambda: self.frame_id > dernier_id or not self.running, timeout):
                return None
            return self.frame_id if self.running else None

    def read_gray(self):
        """(numéro, instant, image grise pleine résolution) ; l'image ne doit pas être modifiée."""
        with self._cond:
            return self.frame_id, self.t, self._gray

    def read(self):
        """(ok, image BGR du flux d'affichage) ; conversion faite une fois par image."""
        with self._cond:
            lores, fid = self._lores, self.frame_id
            if lores is None:
                return False, None
            if self._bgr_id != fid:
                if self.picam2:
                    w, h = self.affichage
                    self._bgr = cv2.cvtColor(lores, cv2.COLOR_YUV2BGR_I420)[:h, :w]
                else:
                    self._bgr = cv2.resize(lores, self.affichage, interpolation=cv2.INTER_AREA)
                self._bgr_id = fid
            return True, self._bgr

    def stop(self):
        self.running = False
        with self._cond:
            self._cond.notify_all()
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception:
                pass
        if self._cap:
            self._cap.release()
        self.picam2 = self._cap = None
