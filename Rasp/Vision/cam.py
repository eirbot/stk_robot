import sys
import cv2
import os
import glob
import math
os.environ['QT_QPA_FONTDIR'] = '/usr/share/fonts/truetype/ubuntu'
    
class cam:
    def __init__(self, image_path=None, use_camera=False):
        self.use_camera = use_camera
        self.largeur_cible = 800 # largeur de l'image en pixels
        self.tolerance_position_x = 30 # pixels
        self.tolerance_position_y = 20 # pixels
        self.tolerance_angle = 13  # degres

        if self.use_camera:
            self.image_reduite = None
            self.dimension = None
        else:
            image = cv2.imread(image_path)
            ratio = self.largeur_cible / image.shape[1]
            self.dimension = (self.largeur_cible, int(image.shape[0] * ratio))
            self.image_reduite = cv2.resize(image, self.dimension, interpolation=cv2.INTER_AREA)

        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        parameters = cv2.aruco.DetectorParameters()
        # Enhance detection parameters
        parameters.adaptiveThreshWinSizeMin = 3
        parameters.adaptiveThreshWinSizeMax = 23
        parameters.adaptiveThreshWinSizeStep = 10
        parameters.minMarkerPerimeterRate = 0.01  # Lower to detect smaller markers
        parameters.maxMarkerPerimeterRate = 4.0
        parameters.polygonalApproxAccuracyRate = 0.03
        parameters.minCornerDistanceRate = 0.05
        parameters.minDistanceToBorder = 0  # Allow markers touching the border
        parameters.minMarkerDistanceRate = 0.05
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX  # Better corner refinement
        self.detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

        # Test d'ouverture pour basculer en simu si besoin
        if self.use_camera:
            import hardware
            # Si on a déjà une caméra partagée qui tourne, c'est OK
            if hardware.camera_running():
                print("[CAM] Utilisation de la caméra partagée détectée.")
            else:
                # Sinon on teste l'ouverture locale (cas hors robot complet)
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    print("⚠️ [CAM] Impossible d'ouvrir la caméra physique. Passage en mode simulation.")
                    self.use_camera = False
                cap.release()

        self.max_angle = None
        self.err_x = None
        self.err_y = None


    def check_aruco_position(self):

        self.everything_in_position = True

        self.allowed_zones = [(250, 274), (350, 274), (460, 274), (560, 274)] # toutes les valeurs sont mesurees pour 800 px de large

        self.angles = []
        self.aruco_center_positions = []

        if self.use_camera:
            image = self.capture_image()
            ratio = self.largeur_cible / image.shape[1]
            self.dimension = (self.largeur_cible, int(image.shape[0] * ratio))
            self.image_reduite = cv2.resize(image, self.dimension, interpolation=cv2.INTER_AREA)
        
        self.corners, self.ids, rejected = self.detector.detectMarkers(self.image_reduite)

        # only keep 47 and 36 ids
        if self.ids is not None:
            mask = (self.ids.flatten() == 47) | (self.ids.flatten() == 36)
            self.ids = self.ids[mask]
            self.corners = [self.corners[i] for i in range(len(self.corners)) if mask[i]]

        if self.ids is not None and len(self.ids) > 0:
            for i in range(len(self.ids)):
                aruco_center_position = (self.corners[i][0][0] + self.corners[i][0][1] + self.corners[i][0][2] + self.corners[i][0][3]) / 4
                self.aruco_center_positions.append(aruco_center_position)
                if not any(abs(aruco_center_position[0] - zone[0]) <= self.tolerance_position_y and abs(aruco_center_position[1] - zone[1]) <= self.tolerance_position_x for zone in self.allowed_zones):
                    self.everything_in_position = False
                pt1 = tuple(map(int, self.corners[i][0][1]))
                pt2 = tuple(map(int, self.corners[i][0][0]))
                angle = cv2.fastAtan2(pt2[0] - pt1[0], pt2[1] - pt1[1])
                if angle > 180:
                    angle -= 360
                if angle > 90:
                    angle -= 180
                elif angle < -90:
                    angle += 180
                self.angles.append(angle)

            self.max_angle = max(self.angles, key=abs)
            if abs(self.max_angle) > self.tolerance_angle:
                self.everything_in_position = False

        else:
            self.everything_in_position = False

        return self.everything_in_position

    def capture_image(self):
        import hardware
        import numpy as np

        # Priorité à la caméra partagée (LibCamera)
        if hardware.camera_running():
            success, frame = hardware.camera.read()
            if success and frame is not None:
                return frame
            print("⚠️ [CAM] Échec lecture hardware.camera, tentative fallback...")

        # Fallback VideoCapture(0)
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("⚠️ [CAM] Erreur d'ouverture VideoCapture(0)")
            return np.zeros((480, 640, 3), dtype=np.uint8)
            
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("⚠️ [CAM] Échec de la capture d'image via VideoCapture(0)")
            return np.zeros((480, 640, 3), dtype=np.uint8)
        return frame
    
    def get_colors(self, is_jaune):
        if self.ids is None or len(self.ids) == 0:
            return []
        self.sorted_ids = [id for _, id in sorted(zip([pos[0] for pos in self.aruco_center_positions], self.ids.flatten()))]
        if is_jaune:
            return [id == 47 for id in self.sorted_ids]
        else:
            return [id == 36 for id in self.sorted_ids]

    def get_colors_pousse(self, is_jaune): 
        if self.ids is None or len(self.ids) == 0:
            return []
        self.sorted_ids = [id for _, id in sorted(zip([pos[1] for pos in self.aruco_center_positions], self.ids.flatten()))]
        if is_jaune:
            return [id == 47 for id in self.sorted_ids]
        else:
            return [id == 36 for id in self.sorted_ids]

    def is_salvagable(self):
        # this function checks if the aruco codes are aligned with each other and that this alignment is roughly perpendicular to the angle of the aruco codes
        if self.ids is None or len(self.ids) < 2:
            return False
        
        sorted_positions = sorted(self.aruco_center_positions, key=lambda pos: pos[0])
        start = sorted_positions[0]
        end   = sorted_positions[-1]
        alignment_angle = cv2.fastAtan2(end[0] - start[0], end[1] - start[1])
        cv2.line(self.image_reduite, (int(start[0]), int(start[1])), (int(end[0]), int(end[1])), (255, 0, 0), 2)
        if abs(abs(alignment_angle - self.max_angle) - 90) > 20:
            return False

        dx = float(end[0] - start[0])
        dy = float(end[1] - start[1])
        line_length = math.hypot(dx, dy)
        for center in sorted_positions[1:-1]:
            px = float(center[0] - start[0])
            py = float(center[1] - start[1])
            distance = abs(dx * py - dy * px) / line_length
            if distance > self.tolerance_position_y:
                return False
            
        max_angle_diff = max(abs(angle1 - angle2) for angle1 in self.angles for angle2 in self.angles if angle1 != angle2)
        print(max_angle_diff)
        if max_angle_diff > self.tolerance_angle:
             return False
        
        return True

    def get_errors(self):
        if self.ids is None or len(self.ids) == 0:
            return None, None, None
        
        main_center_position = (414, 290)
        avg_y = sum([pos[0] for pos in self.aruco_center_positions]) / len(self.aruco_center_positions)
        avg_x = sum([pos[1] for pos in self.aruco_center_positions]) / len(self.aruco_center_positions)
        px_to_mm = 30/56.5 # 56.5 px correspond a 30 mm dans la realite
        self.err_x = -(avg_x-main_center_position[1]) * px_to_mm
        self.err_y = -(avg_y-main_center_position[0]) * px_to_mm
        return self.err_x, self.err_y, self.max_angle
    
    def get_image(self):
        if self.ids is not None and len(self.ids) > 0:
            for i in range(len(self.ids)):
                pt1 = tuple(map(int, self.corners[i][0][0]))
                pt2 = tuple(map(int, self.corners[i][0][1]))
                cv2.line(self.image_reduite, pt1, pt2, (0, 255, 0), 3)
                cv2.circle(self.image_reduite, (int(self.aruco_center_positions[i][0]), int(self.aruco_center_positions[i][1])), 5, (0, 255, 0), -1)
            for zone in self.allowed_zones:
                cv2.rectangle(self.image_reduite, (zone[0] - self.tolerance_position_y, zone[1] - self.tolerance_position_x), (zone[0] + self.tolerance_position_y, zone[1] + self.tolerance_position_x), (0, 255, 255), 2)
        
            cv2.aruco.drawDetectedMarkers(self.image_reduite, self.corners, self.ids)

        if self.everything_in_position:
            cv2.putText(self.image_reduite, 'OK', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
        else:
            cv2.putText(self.image_reduite, 'PAS OK', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

        # writes angle in top left
        if self.max_angle is not None:
            cv2.putText(self.image_reduite, f'Max angle: {self.max_angle:.2f}', (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # writes average x and y position of centers in top left
        # if self.everything_in_position:
        self.get_errors()
        if self.err_x is not None and self.err_y is not None:
            cv2.putText(self.image_reduite, f'Avg err : X {self.err_x:.2f}, Y {self.err_y:.2f}', (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        if self.is_salvagable():
            cv2.putText(self.image_reduite, 'pas bordel', (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 3)
        else:
            cv2.putText(self.image_reduite, 'bordel', (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 3)


        # prints a reference in the bottom right corner, x is an arrow pointing up and y is an arrow pointing left
        cv2.arrowedLine(self.image_reduite, (self.dimension[0] - 20, self.dimension[1] - 20), (self.dimension[0] - 20, self.dimension[1] - 70), (255, 255, 255), 2)
        cv2.arrowedLine(self.image_reduite, (self.dimension[0] - 20, self.dimension[1] - 20), (self.dimension[0] - 70, self.dimension[1] - 20), (255, 255, 255), 2)
        cv2.putText(self.image_reduite, 'X', (self.dimension[0] - 30, self.dimension[1] - 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(self.image_reduite, 'Y', (self.dimension[0] - 80, self.dimension[1] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return self.image_reduite

    def save_debug(self, prefix="debug"):
        import os
        import time
        try:
            # Création du dossier de logs si inexistant
            log_dir = os.path.join(os.getcwd(), "logs", "vision")
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # Récupération de l'image annotée
            img = self.get_image()
            
            # Nom de fichier avec timestamp
            fname = f"{prefix}_{int(time.time())}.jpg"
            fpath = os.path.join(log_dir, fname)
            
            import cv2
            cv2.imwrite(fpath, img)
            print(f"📸 [VISION] Debug sauvegardé : {fpath}")
            return fpath
        except Exception as e:
            print(f"⚠️ [VISION] Erreur sauvegarde debug : {e}")
            return None

if __name__ == '__main__':
    

    cam = cam('logs/oui2.jpg')
    # cam = cam(use_camera=True)

    in_position = cam.check_aruco_position()
    if in_position:
        colors = cam.get_colors("bleu")
        print("Colors in order : ")
        print(colors)
    else:
        # if cam.is_salvagable():
        x_error, y_error, angle_error = cam.get_errors()
        print("X error : ", x_error)
        print("Y error : ", y_error)
        print("Angle error : ", angle_error)

    img = cam.get_image()
    cv2.imshow('Detection ArUco - Format Reduit', img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()