#!/bin/bash
# Compile le serveur web de la base (Base/Web) en Base/base_stk.
# À lancer sur la machine qui exécutera le binaire (cgo + libzmq => dépend de la glibc locale).
# Usage : ./build.sh [--run | --restart]
#   --run     : lance le binaire au premier plan (depuis Base/)
#   --restart : redémarre le service systemd base_stk s'il est installé (cf. install_service.sh)
set -e

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
WEB_DIR="$BASE_DIR/Web"
OUT="$BASE_DIR/base_stk"

command -v go >/dev/null || { echo "go introuvable (sudo apt install golang-go)"; exit 1; }
pkg-config --exists libzmq 2>/dev/null || echo "Attention : libzmq non trouvée par pkg-config (sudo apt install libzmq3-dev)"

echo "[1/2] go mod download..."
cd "$WEB_DIR"
go mod download

# Version injectée dans le binaire (route /api/version) : commit court, -dirty si modifs locales, date
VERSION="inconnu"
if git -C "$BASE_DIR" rev-parse --short HEAD >/dev/null 2>&1; then
    VERSION="$(git -C "$BASE_DIR" rev-parse --short HEAD)"
    [ -n "$(git -C "$BASE_DIR/.." status --porcelain 2>/dev/null)" ] && VERSION="$VERSION-dirty"
fi
VERSION="$VERSION $(date -Iseconds)"

echo "[2/2] Compilation -> $OUT (version : $VERSION)"
CGO_ENABLED=1 go build -trimpath -ldflags "-s -w -X 'main.buildVersion=$VERSION'" -o "$OUT" .

echo "OK : $(du -h "$OUT" | cut -f1) $OUT"

if [ "${1:-}" = "--restart" ]; then
    if systemctl cat base_stk.service >/dev/null 2>&1; then
        echo "Redémarrage du service base_stk..."
        sudo systemctl restart base_stk
        systemctl --no-pager --lines=0 status base_stk || true
        exit 0
    fi
    echo "Service base_stk non installé (sudo ./install_service.sh) : rien à redémarrer."
    echo "Relancer à la main le base_stk qui tourne dans son terminal (ou ./build.sh --run)."
    exit 0
fi

if [ "${1:-}" = "--run" ]; then
    # Le binaire cherche ../Rasp, ../Vision et ../Web : on le lance depuis Base/
    cd "$BASE_DIR"
    exec ./base_stk
fi
