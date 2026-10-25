"""Flux vidéo de la caméra embarquée en HTTP (port 8081), lu par la page Debug.

/stream             MJPEG du flux d'affichage, une image encodée par image caméra
/stream?aruco=1     idem, avec les tags ArUco détectés (active la détection tant qu'on regarde)
/snapshot           une image grise pleine résolution (JPEG 95) : calibration, réglages
"""
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

import cv2
import hardware


class MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Désactive les logs d'accès HTTP dans la console pour ne pas polluer stdout
        pass

    def _jpeg(self, img, qualite):
        ok, jpeg = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), qualite])
        return jpeg.tobytes() if ok else None

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/stream':
            self._stream(parse_qs(url.query).get('aruco', ['0'])[0] == '1')
        elif url.path == '/snapshot':
            self._snapshot()
        else:
            self.send_response(404)
            self.end_headers()

    def _snapshot(self):
        cam = hardware.camera
        if cam is None or not cam.running or cam.attendre_image(0, timeout=2.0) is None:
            self.send_response(503)
            self.end_headers()
            return
        _, _, gray = cam.read_gray()
        data = self._jpeg(gray, 95)
        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def _stream(self, aruco):
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()
        dernier = 0
        try:
            while True:
                cam = hardware.camera
                if cam is None or not cam.running:
                    time.sleep(0.2)
                    continue
                fid = cam.attendre_image(dernier, timeout=1.0)
                if fid is None:
                    continue
                dernier = fid
                ok, frame = cam.read()
                if not ok:
                    continue
                vision = hardware.vision
                if aruco and vision is not None:
                    vision.activer(1.0)
                    frame = vision.dessiner(frame)
                data = self._jpeg(frame, 75)
                if data is None:
                    continue
                self.wfile.write(b'--frame\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(data))
                self.end_headers()
                self.wfile.write(data)
                self.wfile.write(b'\r\n')
        except Exception:
            # Connexion fermée par le client (normal lors de l'arrêt du flux)
            pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

class MjpegStreamer(threading.Thread):
    def __init__(self, host='0.0.0.0', port=8081):
        super().__init__()
        self.daemon = True
        self.host = host
        self.port = port
        self.server = None

    def run(self):
        print(f"[MJPEG STREAMER] Serveur vidéo démarré sur http://{self.host}:{self.port}/stream")
        try:
            self.server = ThreadedHTTPServer((self.host, self.port), MJPEGHandler)
            self.server.serve_forever()
        except Exception as e:
            print(f"[MJPEG STREAMER] Erreur : {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
