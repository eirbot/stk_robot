#!/bin/bash
# Déploiement Eirbot : base déportée (serveur web), robot (code Python de Rasp/) et ESP (moteurs / bras).
# Lancé depuis le PC de dev (ou depuis la base pour `robot`). Voir ./deploy.sh -h
set -euo pipefail

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"

# --- Réglages (surchargeables par variables d'environnement) ---
BASE_HOST="${BASE_HOST:-base}"                     # Hôte ssh de la base (alias ~/.ssh/config ou IP)
BASE_USER="${BASE_USER:-based}"
BASE_REPO="${BASE_REPO:-Documents/stk_robot}"      # Relatif au $HOME de la base
ROBOT_HOST="${ROBOT_HOST:-192.168.10.89}"          # Ou robot.eirbot (DNS de la base)
ROBOT_USER="${ROBOT_USER:-eirbot}"
ROBOT_KEY="${ROBOT_KEY-$HOME/.ssh/id_robot}"       # Vide = clé ssh par défaut (cas de la base)
ROBOT_DIR="${ROBOT_DIR:-Documents/robot_stk}"      # Relatif au $HOME du robot
ROBOT_ESPTOOL="${ROBOT_ESPTOOL:-esptool/esptool.py}" # Relatif au $HOME du robot
PIO="${PIO:-pio}"
PIO_HOME="${PIO_HOME:-$HOME/.platformio}"
ESPTOOL_PY="${ESPTOOL_PY:-$PIO_HOME/packages/tool-esptoolpy/esptool.py}"
BOOT_APP0="${BOOT_APP0:-$PIO_HOME/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin}"
SSH_TIMEOUT="${SSH_TIMEOUT:-5}"

DRY_RUN=0
FROM_BASE=0

usage() {
    cat <<EOF
Usage : tools/deploy.sh [options] <commande>

Commandes :
  base          Sur la base : git pull --ff-only --no-rebase, ./Base/build.sh, redémarrage du service base_stk
  robot         rsync de Rasp/ vers le robot, écriture de VERSION, redémarrage de robot_launcher
  esp motors    Compile (pio -e Motor), fusionne et flashe l'ESP moteurs (/dev/esp_motors) via la Rasp
  esp arms      Idem pour l'ESP actionneurs (pio -e Actionneurs, /dev/esp_action)
  status        Versions déployées (base, robot) et état des services
  all           base puis robot

Options :
  -n, --dry-run   Affiche les commandes sans les exécuter
  --from-base     (robot, all) pousse le code depuis la base (après git pull) au lieu du PC local
  -h, --help      Cette aide

Variables d'environnement (valeur actuelle) :
  BASE_HOST=$BASE_HOST BASE_USER=$BASE_USER BASE_REPO=$BASE_REPO
  ROBOT_HOST=$ROBOT_HOST ROBOT_USER=$ROBOT_USER ROBOT_KEY=$ROBOT_KEY
  ROBOT_DIR=$ROBOT_DIR ROBOT_ESPTOOL=$ROBOT_ESPTOOL
  PIO=$PIO PIO_HOME=$PIO_HOME SSH_TIMEOUT=$SSH_TIMEOUT

Exemples :
  tools/deploy.sh robot
  tools/deploy.sh --dry-run esp motors
  ROBOT_HOST=robot.eirbot tools/deploy.sh --from-base robot
EOF
}

log() { echo -e "\033[1;34m[DEPLOY]\033[0m $*"; }
die() { echo -e "\033[1;31m[DEPLOY] $*\033[0m" >&2; exit 1; }

# Exécute une commande, ou l'affiche seulement en --dry-run
run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  \$ $(printf '%q ' "$@")"
    else
        "$@"
    fi
}

# Idem avec un contenu envoyé sur l'entrée standard
run_stdin() {
    local input="$1"; shift
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "  \$ $(printf '%q ' "$@") <<< $(printf '%q' "$input")"
    else
        printf '%s' "$input" | "$@"
    fi
}

# --- ssh ---
SSH_OPTS=(-o ConnectTimeout="$SSH_TIMEOUT" -o StrictHostKeyChecking=accept-new)
ROBOT_SSH_OPTS=("${SSH_OPTS[@]}")
[ -n "$ROBOT_KEY" ] && ROBOT_SSH_OPTS+=(-i "$ROBOT_KEY")
ROBOT="$ROBOT_USER@$ROBOT_HOST"
BASE="$BASE_USER@$BASE_HOST"

# -t (pseudo-terminal) si on est interactif : sudo peut alors demander un mot de passe
TTY_OPT=()
[ -t 0 ] && TTY_OPT=(-t)

ssh_robot() { run ssh "${ROBOT_SSH_OPTS[@]}" "$ROBOT" "$@"; }
ssh_base() { run ssh "${SSH_OPTS[@]}" "${TTY_OPT[@]}" "$BASE" "$@"; }

# Contenu du fichier VERSION (même format que la route Go /api/update_rasp, cf. Base/Web/settings.go) :
#   commit=<sha court>[-dirty]   (dirty = modifs locales dans Rasp/, config.json exclu car non déployé)
#   date=<date ISO 8601>
#   source=<machine qui a poussé>
version_file() {
    local commit="inconnu"
    if commit="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null)"; then
        if [ -n "$(git -C "$ROOT" status --porcelain -- Rasp ':!Rasp/config.json' 2>/dev/null)" ]; then
            commit="$commit-dirty"
        fi
    else
        commit="inconnu"
    fi
    printf 'commit=%s\ndate=%s\nsource=%s\n' "$commit" "$(date -Iseconds)" "$(hostname)"
}

# --- Sous-commandes ---

cmd_base() {
    log "Base ($BASE) : git pull, compilation, redémarrage de base_stk"
    ssh_base "cd ~/$BASE_REPO && git pull --ff-only --no-rebase && ./Base/build.sh --restart"
}

cmd_robot() {
    if [ "$FROM_BASE" -eq 1 ]; then
        log "Robot depuis la base ($BASE) : git pull puis tools/deploy.sh robot"
        # Depuis la base : clé ssh par défaut (ROBOT_KEY vide)
        local remote
        remote="cd ~/$BASE_REPO && { git pull --ff-only --no-rebase || echo '[DEPLOY] git pull a échoué : déploiement du code présent sur la base'; }"
        remote+=" && ROBOT_HOST=$(printf '%q' "$ROBOT_HOST") ROBOT_USER=$(printf '%q' "$ROBOT_USER")"
        remote+=" ROBOT_DIR=$(printf '%q' "$ROBOT_DIR") ROBOT_KEY= tools/deploy.sh robot"
        ssh_base "$remote"
        return
    fi

    [ -f "$ROOT/Rasp/main_robot.py" ] || die "Rasp/main_robot.py introuvable dans $ROOT"
    local version
    version="$(version_file)"
    log "Robot ($ROBOT:$ROBOT_DIR) : $(echo "$version" | head -n1)"

    # Mêmes exclusions que /api/update_rasp (config.json porte les réglages runtime du robot,
    # LiDAR/lidar_udp est compilé sur la Rasp en aarch64)
    run rsync -rc --out-format=%n \
        --exclude=.venv --exclude=__pycache__ --exclude='*.pyc' --exclude='*.log' --exclude=config.json \
        --exclude=LiDAR/lidar_udp \
        -e "ssh $(printf '%q ' "${ROBOT_SSH_OPTS[@]}")" \
        "$ROOT/Rasp/" "$ROBOT:$ROBOT_DIR/"

    run_stdin "$version"$'\n' ssh "${ROBOT_SSH_OPTS[@]}" "$ROBOT" "cat > $ROBOT_DIR/VERSION"

    log "Redémarrage de robot_launcher"
    ssh_robot "sudo systemctl restart robot_launcher"
}

cmd_esp() {
    local target="${1:-}" env port
    case "$target" in
        motors|motor) env=Motor; port=/dev/esp_motors ;;
        arms|arm|actionneurs) env=Actionneurs; port=/dev/esp_action ;;
        *) die "Cible ESP inconnue : '$target' (motors ou arms)" ;;
    esac

    local build="$ROOT/.pio/build/$env"
    local merged="$build/merged.bin"
    local remote_dir="/tmp/esp_flash/$env"

    log "ESP $env : compilation PlatformIO"
    (cd "$ROOT" && run "$PIO" run -e "$env")

    # Python de PlatformIO (pyserial etc.) si présent, sinon python3
    local py=python3
    [ -x "$PIO_HOME/penv/bin/python" ] && py="$PIO_HOME/penv/bin/python"
    if [ "$DRY_RUN" -eq 0 ]; then
        [ -f "$ESPTOOL_PY" ] || die "esptool introuvable : $ESPTOOL_PY"
        [ -f "$BOOT_APP0" ] || die "boot_app0.bin introuvable : $BOOT_APP0"
    fi

    log "ESP $env : fusion en une image ($merged)"
    run "$py" "$ESPTOOL_PY" --chip esp32 merge_bin -o "$merged" \
        --flash_mode dio --flash_freq 40m --flash_size 4MB --target-offset 0x1000 \
        0x1000 "$build/bootloader.bin" 0x8000 "$build/partitions.bin" \
        0xe000 "$BOOT_APP0" 0x10000 "$build/firmware.bin"

    log "ESP $env : copie vers le robot ($ROBOT:$remote_dir)"
    ssh_robot "mkdir -p $remote_dir"
    run scp "${ROBOT_SSH_OPTS[@]}" "$merged" "$ROBOT:$remote_dir/merged.bin"

    # Arrêt du launcher (et de main_robot qui tient le port série), flash, relance même en cas d'échec
    log "ESP $env : flash sur $port"
    ssh_robot "sudo systemctl stop robot_launcher; sudo fuser -k $port 2>/dev/null; sleep 0.5; " \
        "python3 ~/$ROBOT_ESPTOOL --chip esp32 --port $port --baud 460800 write_flash -z" \
        "--flash_mode dio --flash_freq 40m --flash_size 4MB 0x1000 $remote_dir/merged.bin;" \
        "rc=\$?; sudo systemctl start robot_launcher; exit \$rc"
}

cmd_status() {
    log "Local : $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?') ($(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"

    log "Base ($BASE)"
    ssh_base "cd ~/$BASE_REPO && echo \"  dépôt   : \$(git log -1 --format='%h %cd' --date=iso) (\$(git rev-parse --abbrev-ref HEAD))\";" \
        "echo \"  binaire : \$(curl -s --max-time 2 http://localhost:8080/api/version || echo 'serveur injoignable')\";" \
        "echo \"  service : \$(systemctl is-active base_stk 2>/dev/null || true)\"" \
        || echo "  base injoignable"

    log "Robot ($ROBOT)"
    ssh_robot "echo '  VERSION :'; sed 's/^/    /' $ROBOT_DIR/VERSION 2>/dev/null || echo '    (absent)';" \
        "echo \"  robot_launcher : \$(systemctl is-active robot_launcher 2>/dev/null || true)\";" \
        "echo \"  main_robot     : \$(pgrep -f main_robot.py >/dev/null && echo actif || echo arrêté)\"" \
        || echo "  robot injoignable"
}

# --- Arguments ---
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=1 ;;
        --from-base) FROM_BASE=1 ;;
        -h|--help) usage; exit 0 ;;
        -*) usage >&2; die "Option inconnue : $1" ;;
        *) ARGS+=("$1") ;;
    esac
    shift
done
[ ${#ARGS[@]} -ge 1 ] || { usage >&2; exit 1; }
[ "$DRY_RUN" -eq 1 ] && log "Mode --dry-run : aucune commande n'est exécutée"

case "${ARGS[0]}" in
    base) cmd_base ;;
    robot) cmd_robot ;;
    esp) cmd_esp "${ARGS[1]:-}" ;;
    status) cmd_status ;;
    all) cmd_base; cmd_robot ;;
    *) usage >&2; die "Commande inconnue : ${ARGS[0]}" ;;
esac
