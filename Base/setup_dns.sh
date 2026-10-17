#!/bin/bash
# Noms locaux sur le LAN robot (à lancer une fois sur la base, en root) :
#   http://stk.eirbot    -> interface web de la base (192.168.10.2)
#   robot.eirbot         -> Raspberry du robot (IP fixée par DHCP)
# Usage : sudo ./setup_dns.sh
set -e

[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo"; exit 1; }

CONF=/etc/dnsmasq.conf
BASE_IP=192.168.10.2
ROBOT_MAC=74:19:f8:15:e4:b4
ROBOT_IP=192.168.10.89
MARK="# --- Noms locaux Eirbot (setup_dns.sh) ---"

cp "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"

# Bloc idempotent : on retire l'ancien avant de le réécrire
sed -i "/^$MARK/,/^# --- fin Eirbot ---/d" "$CONF"

# Les clients utilisent la base comme DNS (au lieu de 1.1.1.1 / 8.8.8.8)
sed -i "s/^dhcp-option=6,.*/dhcp-option=6,$BASE_IP/" "$CONF"

cat >> "$CONF" <<EOF
$MARK
# DNS amont pour le reste d'internet
no-resolv
server=1.1.1.1
server=8.8.8.8
# Domaine local : jamais transmis à l'extérieur
local=/eirbot/
address=/stk.eirbot/$BASE_IP
address=/robot.eirbot/$ROBOT_IP
# IP fixe pour le robot, pour que robot.eirbot reste valide
dhcp-host=$ROBOT_MAC,$ROBOT_IP,rasp3a
# --- fin Eirbot ---
EOF

# Autorise base_stk (non root) à écouter sur le port 80 pour la redirection vers :8080
echo "net.ipv4.ip_unprivileged_port_start=80" > /etc/sysctl.d/60-eirbot-port80.conf
sysctl -q --system

dnsmasq --test
systemctl restart dnsmasq
systemctl is-active dnsmasq

echo "OK. Relancer base_stk pour activer le port 80."
echo "Sur chaque appareil : se déconnecter / reconnecter du wifi pour récupérer le nouveau DNS."
