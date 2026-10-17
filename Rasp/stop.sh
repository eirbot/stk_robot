#!/bin/bash

echo "[STOP] Tentative d'arrêt du service systemd..."
# On arrête le service s'il tourne (nécessite sudo)
if sudo systemctl is-active --quiet robot.service; then
    sudo systemctl stop robot.service
    echo " -> Service robot arrêté."
else
    echo " -> Le service n'était pas actif."
fi

echo "[STOP] Nettoyage des processus Python..."
# On tue tous les processus qui contiennent "main_robot.py"
# Le "|| true" permet d'éviter un message d'erreur si aucun processus n'est trouvé
sudo pkill -f main_robot.py || true
# Et ses fils, s'ils ont survécu (anciennes versions sans PDEATHSIG)
sudo pkill -f utils/led_service.py || true
sudo pkill -x lidar_udp || true

echo "[STOP] Robot éteint."