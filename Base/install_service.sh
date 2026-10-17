#!/bin/bash
# Installe et active le service systemd base_stk (serveur web de la base déportée).
# À lancer une fois sur la base, depuis n'importe où : sudo ./install_service.sh [--dry-run]
# Le modèle Base/systemd/base_stk.service est adapté au dossier et à l'utilisateur réels.
set -euo pipefail

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
TEMPLATE="$BASE_DIR/systemd/base_stk.service"
DEST=/etc/systemd/system/base_stk.service
# Propriétaire du dépôt (= utilisateur qui fera tourner le serveur), pas root
SVC_USER="${SVC_USER:-$(stat -c %U "$BASE_DIR")}"
SVC_HOME="$(getent passwd "$SVC_USER" | cut -d: -f6)"

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

UNIT="$(sed -e "s|^User=.*|User=$SVC_USER|" \
            -e "s|/home/based/Documents/stk_robot/Base|$BASE_DIR|g" \
            -e "s|/home/based|$SVC_HOME|g" "$TEMPLATE")"

if [ "$DRY" -eq 1 ]; then
    echo "# --- $DEST (à blanc) ---"
    echo "$UNIT"
    exit 0
fi

[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo"; exit 1; }
[ -x "$BASE_DIR/base_stk" ] || echo "Attention : $BASE_DIR/base_stk absent, lancer ./build.sh d'abord"

echo "$UNIT" > "$DEST"
# Redémarrage sans mot de passe (build.sh --restart, tools/deploy.sh base lancé en ssh)
SUDOERS=/etc/sudoers.d/base_stk
SYSTEMCTL="$(command -v systemctl)"
echo "$SVC_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart base_stk, $SYSTEMCTL stop base_stk, $SYSTEMCTL start base_stk" > "$SUDOERS.tmp"
chmod 440 "$SUDOERS.tmp"
if visudo -cf "$SUDOERS.tmp" >/dev/null; then mv "$SUDOERS.tmp" "$SUDOERS"; else rm -f "$SUDOERS.tmp"; echo "Règle sudoers invalide, ignorée"; fi

systemctl daemon-reload
systemctl enable base_stk.service
systemctl restart base_stk.service
echo "Service base_stk installé ($DEST, utilisateur $SVC_USER)."
echo "Logs : journalctl -u base_stk -f   |   Redémarrage : sudo systemctl restart base_stk"
echo "Pensez à arrêter tout base_stk lancé à la main (port 8080 déjà pris sinon)."
