import zmq
import time
import json

def simuler_robot():
    context = zmq.Context()
    
    # Création du socket "PUSH" (envoi unidirectionnel rapide)
    sender = context.socket(zmq.PUSH)
    
    # La Rasp se connecte au PC (ici localhost pour le test)
    sender.connect("tcp://localhost:5555")
    print("[Fausse Rasp] Connecté au serveur Go...")

    # Fausse position de départ
    x, y, theta = 100, 500, 0.0

    try:
        while True:
            # On simule le robot qui avance
            x += 5
            
            # Plus tard, on utilisera Protobuf. Pour le test, on envoie du JSON.
            telemetrie = {"x": x, "y": y, "theta": theta}
            
            sender.send_string(json.dumps(telemetrie))
            print(f"[Fausse Rasp] Trame envoyée : {telemetrie}")
            
            # Envoi à 10Hz (10 fois par seconde)
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Arrêt de la simulation.")

if __name__ == "__main__":
    simuler_robot()