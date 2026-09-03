#!/usr/bin/env bash
# ==============================================================================
# STKbtw - Script de construction de l'ISO Live USB Arch Linux
# Usage: sudo ./build.sh [-c|--clean] [-h|--help]
# ==============================================================================

set -euo pipefail

# Couleurs pour le terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Répertoires clés
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AIROOTFS_BASE="${SCRIPT_DIR}/airootfs/opt/eirbot/Base"
WORK_DIR="/tmp/archiso-tmp"
OUT_DIR="${SCRIPT_DIR}/out"

# Affichage de l'aide
show_help() {
    echo -e "${BOLD}STKbtw Build Script - Coupe de France de Robotique 2026${NC}"
    echo ""
    echo -e "${BOLD}Usage:${NC}"
    echo -e "    sudo $0 [options]"
    echo ""
    echo -e "${BOLD}Options:${NC}"
    echo -e "    -c, --clean    Supprime le dossier temporaire (${WORK_DIR}) avant le build"
    echo -e "    -h, --help     Affiche cette aide et quitte"
    echo ""
    echo -e "${BOLD}Exemple:${NC}"
    echo -e "    sudo ./build.sh --clean"
}

# Parsing des options
CLEAN_BUILD=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--clean)
            CLEAN_BUILD=1
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}[!] Option inconnue : $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}   STKbtw - Préparation et Compilation de l'ISO       ${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"

# 1. Vérification des privilèges root (obligatoire pour mkarchiso / pacstrap / mounts)
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERREUR] Ce script doit être exécuté avec les droits root :${NC}"
    echo -e "         ${YELLOW}sudo $0${NC}"
    exit 1
fi

# 2. Vérification de la présence de mkarchiso
if ! command -v mkarchiso &>/dev/null; then
    echo -e "${RED}[ERREUR] 'mkarchiso' est introuvable. Installez-le avec :${NC}"
    echo -e "         ${YELLOW}pacman -S --needed archiso${NC}"
    exit 1
fi

# 3. Nettoyage éventuel du répertoire temporaire si demandé
if [[ $CLEAN_BUILD -eq 1 ]]; then
    echo -e "${YELLOW}[*] Nettoyage du répertoire temporaire : ${WORK_DIR}${NC}"
    rm -rf "${WORK_DIR}"
fi

# 4. Préparation de l'arborescence airootfs cible
echo -e "${BLUE}[*] Création de l'arborescence dans airootfs : ${AIROOTFS_BASE}${NC}"
mkdir -p "${AIROOTFS_BASE}"
mkdir -p "${SCRIPT_DIR}/airootfs/home/stk/Base_Data"
mkdir -p "${OUT_DIR}"

# 5. Synchronisation des dossiers Vision/ et Web/
echo -e "${BLUE}[*] Synchronisation de '../Vision/' et '../Web/' vers '/opt/eirbot/Base/'...${NC}"

if [[ -d "${BASE_DIR}/Vision" ]]; then
    rsync -av --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git*' \
        "${BASE_DIR}/Vision/" "${AIROOTFS_BASE}/Vision/"
    echo -e "${GREEN}[OK] Vision synchronisé.${NC}"
else
    echo -e "${YELLOW}[AVERTISSEMENT] Dossier '${BASE_DIR}/Vision' introuvable, étape ignorée.${NC}"
fi

if [[ -d "${BASE_DIR}/Web" ]]; then
    rsync -av --delete \
        --exclude='.git*' \
        "${BASE_DIR}/Web/" "${AIROOTFS_BASE}/Web/"
    echo -e "${GREEN}[OK] Web synchronisé.${NC}"
else
    echo -e "${YELLOW}[AVERTISSEMENT] Dossier '${BASE_DIR}/Web' introuvable, étape ignorée.${NC}"
fi

# 6. S'assurer des permissions d'exécution sur les scripts et binaires airootfs
echo -e "${BLUE}[*] Application des droits d'exécution sur les scripts internes...${NC}"
chmod +x "${SCRIPT_DIR}/airootfs/usr/local/bin/"* 2>/dev/null || true
if [[ -f "${AIROOTFS_BASE}/Web/base_stk" ]]; then
    chmod +x "${AIROOTFS_BASE}/Web/base_stk"
fi

# 7. Vérification du fichier pacman.conf local
if [[ ! -f "${SCRIPT_DIR}/pacman.conf" ]]; then
    echo -e "${YELLOW}[*] Copie du pacman.conf système par défaut...${NC}"
    cp /etc/pacman.conf "${SCRIPT_DIR}/pacman.conf"
fi

# 8. Lancement de mkarchiso
echo -e "${BLUE}${BOLD}[*] Lancement de mkarchiso...${NC}"
echo -e "    - Profil : ${SCRIPT_DIR}"
echo -e "    - Workdir: ${WORK_DIR} (évite de polluer le repo Git)"
echo -e "    - Output : ${OUT_DIR}"

mkdir -p "${WORK_DIR}"

mkarchiso -v \
    -w "${WORK_DIR}" \
    -o "${OUT_DIR}" \
    "${SCRIPT_DIR}"

echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e "${GREEN}${BOLD}   Build terminé avec succès !                        ${NC}"
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e "L'image ISO générée se trouve dans : ${BOLD}${OUT_DIR}${NC}"
ls -lh "${OUT_DIR}"/*.iso 2>/dev/null || true

echo -e "\n${BLUE}Pour flasher l'ISO sur clé USB :${NC}"
echo -e "  ${YELLOW}sudo dd if=${OUT_DIR}/stkbtw-*.iso of=/dev/sdX bs=4M status=progress oflag=sync${NC}"
echo -e "${BLUE}Pour créer la partition persistante sur la même clé USB :${NC}"
echo -e "  Créez une seconde partition formatée en ext4 avec le label : ${BOLD}STK_DATA${NC}"
echo -e "  ${YELLOW}sudo e2label /dev/sdX2 STK_DATA${NC}"
