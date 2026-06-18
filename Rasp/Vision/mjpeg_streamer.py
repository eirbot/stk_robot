import time
import cv2
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import ihm.shared as shared

class MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Désactive les logs d'accès HTTP dans la console pour ne pas polluer stdout
        pass

    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            try:
                last_frame_time = 0
                while True:
                    now = time.time()
                    # Limite à 20 FPS pour le traitement et l'affichage
                    if now - last_frame_time < 0.05:
                        time.sleep(0.005)
                        continue

                    if shared.camera and shared.camera.running:
                        success, frame = shared.camera.read()
                        if success and frame is not None:
                            # Redimensionnement à 800px de large (résolution optimale attendue par cam.py)
                            h, w = frame.shape[:2]
                            target_w = 800
                            if w != target_w:
                                ratio = target_w / w
                                dim = (target_w, int(h * ratio))
                                send_frame = cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)
                            else:
                                send_frame = frame

                            # Encodage JPEG avec une qualité confortable pour la vision ArUco (75%)
                            ret, jpeg = cv2.imencode('.jpg', send_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                            if ret:
                                self.wfile.write(b'--frame\r\n')
                                self.send_header('Content-Type', 'image/jpeg')
                                self.send_header('Content-Length', len(jpeg))
                                self.end_headers()
                                self.wfile.write(jpeg.tobytes())
                                self.wfile.write(b'\r\n')
                                last_frame_time = now
                    else:
                        # Si la caméra n'est pas prête, on attend un peu
                        time.sleep(0.1)
            except Exception as e:
                # Connexion fermée par le client (normal lors de l'arrêt du flux)
                pass
        else:
            self.send_response(404)
            self.end_headers()

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
