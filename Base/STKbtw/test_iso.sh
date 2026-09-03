#!/usr/bin/env bash
# ==============================================================================
# STKbtw - Test de l'image Live USB en machine virtuelle via run_archiso
# Allocation mémoire : 32 Go de RAM (Simulation PC Framework cible)
# Usage: ./test_iso.sh [chemin_vers_iso]
# ==============================================================================

set -euo pipefail

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/out"

# Détection de l'ISO à tester (soit passée en paramètre, soit la plus récente dans out/)
ISO_IMAGE="${1:-}"
if [[ -z "${ISO_IMAGE}" && -d "${OUT_DIR}" ]]; then
    ISO_IMAGE="$(find "${OUT_DIR}" -maxdepth 1 -name "stkbtw-*.iso" -printf "%T@ %p\n" 2>/dev/null | sort -nr | head -n 1 | cut -d" " -f2-)"
fi

if [[ -z "${ISO_IMAGE}" || ! -f "${ISO_IMAGE}" ]]; then
    echo -e "${RED}[ERREUR] Aucune image ISO trouvée dans : ${OUT_DIR}${NC}"
    echo -e "Compilez d'abord l'ISO avec : ${YELLOW}sudo ./build.sh${NC}"
    echo -e "Ou spécifiez explicitement le fichier : ${YELLOW}$0 /chemin/vers/image.iso${NC}"
    exit 1
fi

# Vérification des outils nécessaires
if ! command -v run_archiso &>/dev/null; then
    echo -e "${RED}[ERREUR] 'run_archiso' est introuvable.${NC}"
    echo -e "Installez le paquet archiso : ${YELLOW}sudo pacman -S --needed archiso${NC}"
    exit 1
fi

REAL_QEMU="$(which qemu-system-x86_64 2>/dev/null || true)"
if [[ -z "${REAL_QEMU}" || ! -x "${REAL_QEMU}" ]]; then
    echo -e "${RED}[ERREUR] 'qemu-system-x86_64' est introuvable.${NC}"
    echo -e "Installez QEMU et OVMF : ${YELLOW}sudo pacman -S --needed qemu-desktop edk2-ovmf${NC}"
    exit 1
fi

echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}   STKbtw - Démarrage de la VM de test (run_archiso)  ${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "  - Image ISO    : ${BOLD}${ISO_IMAGE}${NC}"
echo -e "  - Mémoire RAM  : ${GREEN}${BOLD}32 Go (32768 Mo - Profil PC Framework)${NC}"
echo -e "  - Mode Boot    : ${BOLD}UEFI (OVMF)${NC}"
echo -e "  - Redirection  : ${BOLD}SSH guest:22 -> host:60022${NC}"
echo -e "${BLUE}------------------------------------------------------${NC}"

# run_archiso code en dur une valeur de 3072 Mo de RAM.
# Pour allouer précisément 32 Go (32768 Mo), nous interceptons l'argument mémoire
# via un wrapper éphémère prioritaire dans le PATH qui appelle le vrai QEMU.
WRAPPER_DIR="$(mktemp -d /tmp/archiso-qemu-wrapper.XXXXXX)"
trap 'rm -rf "${WRAPPER_DIR}"' EXIT INT TERM

cat << EOF > "${WRAPPER_DIR}/qemu-system-x86_64"
#!/usr/bin/env bash
QEMU_ARGS=()
for arg in "\$@"; do
    if [[ "\$arg" =~ ^size=3072 ]]; then
        # Substitution précise de 3 Go par 32 Go (32768 Mo)
        QEMU_ARGS+=("size=32768,slots=0,maxmem=\$((32768*1024*1024))")
    else
        QEMU_ARGS+=("\$arg")
    fi
done
exec "${REAL_QEMU}" "\${QEMU_ARGS[@]}"
EOF
chmod +x "${WRAPPER_DIR}/qemu-system-x86_64"

# Lancement de run_archiso avec notre wrapper de RAM
PATH="${WRAPPER_DIR}:${PATH}" run_archiso -u -i "${ISO_IMAGE}"
