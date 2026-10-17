#!/bin/bash
# Compile le serveur web de la base (Base/Web) en Base/base_stk.
# À lancer sur la machine qui exécutera le binaire (cgo + libzmq => dépend de la glibc locale).
# Usage : ./build.sh [--run]
set -e

BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
WEB_DIR="$BASE_DIR/Web"
OUT="$BASE_DIR/base_stk"

command -v go >/dev/null || { echo "go introuvable (sudo apt install golang-go)"; exit 1; }
pkg-config --exists libzmq 2>/dev/null || echo "Attention : libzmq non trouvée par pkg-config (sudo apt install libzmq3-dev)"

echo "[1/2] go mod download..."
cd "$WEB_DIR"
go mod download

echo "[2/2] Compilation -> $OUT"
CGO_ENABLED=1 go build -trimpath -ldflags "-s -w" -o "$OUT" .

echo "OK : $(du -h "$OUT" | cut -f1) $OUT"

if [ "$1" = "--run" ]; then
    # Le binaire cherche ../Rasp, ../Vision et ../Web : on le lance depuis Base/
    cd "$BASE_DIR"
    exec ./base_stk
fi
