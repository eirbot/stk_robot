#!/usr/bin/env bash
# ==============================================================================
# STKbtw - Script de Déploiement USB & Partition de Données Persistante
# Coupe de France de Robotique 2026
# ==============================================================================
# Ce script :
#   1. Flashe l'image stkbtw.iso sur une clé USB cible via dd.
#   2. Détecte le type de table de partition (MBR/dos ou GPT).
#   3. Crée la 3ème partition occupant 100% de l'espace libre restant :
#      - Si MBR/dos (standard archiso) : ajout de la partition 3 via sfdisk.
#      - Si GPT : réparation de l'en-tête de secours et ajout via sgdisk.
#   4. Formate cette partition en exFAT avec le label STK_DATA pour montage auto.
# ==============================================================================

set -euo pipefail

# Couleurs pour le terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/out"

echo -e "${BLUE}${BOLD}======================================================${NC}"
echo -e "${BLUE}${BOLD}   STKbtw - Déploiement USB & Partition Persistante   ${NC}"
echo -e "${BLUE}${BOLD}======================================================${NC}"

# 1. Vérification des privilèges root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERREUR] Ce script doit être exécuté avec les privilèges root :${NC}"
    echo -e "         ${YELLOW}sudo $0${NC}"
    exit 1
fi

# 2. Vérification des dépendances système requises
REQUIRED_TOOLS=("dd" "sfdisk" "partprobe" "mkfs.exfat" "lsblk" "udevadm")
MISSING_TOOLS=()

for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "${tool}" &>/dev/null; then
        MISSING_TOOLS+=("${tool}")
    fi
done

if [[ ${#MISSING_TOOLS[@]} -gt 0 ]]; then
    echo -e "${RED}[ERREUR] Outil(s) manquant(s) sur le système hôte : ${MISSING_TOOLS[*]}${NC}"
    echo -e "         Installez-les via votre gestionnaire de paquets :"
    echo -e "         - Arch Linux : ${YELLOW}pacman -S --needed util-linux parted exfatprogs coreutils${NC}"
    echo -e "         - Debian/Ubuntu: ${YELLOW}apt install fdisk parted exfatprogs util-linux coreutils${NC}"
    exit 1
fi

# 3. Détection ou sélection de l'image ISO
ISO_PATH="${1:-}"

if [[ -z "${ISO_PATH}" ]]; then
    # Recherche automatique de la dernière ISO compilée dans out/
    if [[ -d "${OUT_DIR}" ]]; then
        ISO_PATH=$(find "${OUT_DIR}" -maxdepth 1 -type f -name "stkbtw-*.iso" 2>/dev/null | sort -r | head -n 1)
    fi
fi

if [[ -z "${ISO_PATH}" || ! -f "${ISO_PATH}" ]]; then
    echo -e "${YELLOW}[?] Veuillez renseigner le chemin vers l'image ISO stkbtw :${NC}"
    read -r -p "    Chemin de l'ISO: " ISO_PATH
fi

if [[ ! -f "${ISO_PATH}" ]]; then
    echo -e "${RED}[ERREUR] Fichier ISO introuvable : ${ISO_PATH}${NC}"
    exit 1
fi

ISO_SIZE_MB=$(du -m "${ISO_PATH}" | cut -f1)
echo -e "${GREEN}[OK] Image ISO sélectionnée : ${BOLD}${ISO_PATH}${NC} (${ISO_SIZE_MB} Mo)"

# 4. Identification et sélection du disque USB cible
echo -e "\n${BLUE}${BOLD}[*] Périphériques de stockage connectés :${NC}"
lsblk -d -o NAME,MODEL,SIZE,TRAN,FSTYPE,LABEL,MOUNTPOINTS | grep -E "NAME|usb|sd|nvme|mmc" || lsblk

echo -e "\n${YELLOW}${BOLD}[ATTENTION] Le disque sélectionné sera INTÉGRALEMENT ÉCRASÉ !${NC}"
echo -e "Indiquez le disque entier (ex: /dev/sdb ou /dev/sdc), ${RED}JAMAIS une partition (/dev/sdb1)${NC}."

TARGET_DISK=""
while [[ -z "${TARGET_DISK}" ]]; do
    read -r -p "Entrez le périphérique cible (ex: /dev/sdb) : " TARGET_DISK
    # Ajouter /dev/ si omis par l'utilisateur (ex: 'sda' -> '/dev/sda')
    if [[ ! "${TARGET_DISK}" =~ ^/dev/ ]]; then
        TARGET_DISK="/dev/${TARGET_DISK}"
    fi

    if [[ ! -b "${TARGET_DISK}" ]]; then
        echo -e "${RED}[ERREUR] '${TARGET_DISK}' n'est pas un périphérique bloc valide.${NC}"
        TARGET_DISK=""
    fi
done

# Vérification que ce n'est pas une partition (ex: sdb1)
if [[ "${TARGET_DISK}" =~ [0-9]$ && ! "${TARGET_DISK}" =~ (nvme|mmcblk|loop) ]]; then
    echo -e "${RED}[ERREUR] Vous avez sélectionné une partition (${TARGET_DISK}) et non le disque entier.${NC}"
    echo -e "         Veuillez spécifier la racine du disque (ex: ${TARGET_DISK%[0-9]*})."
    exit 1
fi

# Sécurité absolue : Vérifier qu'aucune partition du disque cible n'héberge le système hôte
if lsblk -ln -o MOUNTPOINT "${TARGET_DISK}" | grep -E "^/($|boot|home|usr)" >/dev/null; then
    echo -e "${RED}${BOLD}[SÉCURITÉ CRITIQUE] LE DISQUE SÉLECTIONNÉ CONTIENT UNE PARTITION SYSTÈME ACTIVE !${NC}"
    echo -e "Action immédiatement interrompue pour éviter la destruction de votre machine hôte."
    exit 1
fi

# Affichage du récapitulatif
DISK_MODEL=$(lsblk -dn -o MODEL "${TARGET_DISK}" 2>/dev/null || echo "Inconnu")
DISK_SIZE=$(lsblk -dn -o SIZE "${TARGET_DISK}" 2>/dev/null || echo "Inconnu")
DISK_TRAN=$(lsblk -dn -o TRAN "${TARGET_DISK}" 2>/dev/null || echo "Inconnu")

echo -e "\n${BLUE}------------------------------------------------------${NC}"
echo -e "  Disque Cible : ${BOLD}${TARGET_DISK}${NC}"
echo -e "  Modèle       : ${DISK_MODEL}"
echo -e "  Taille       : ${DISK_SIZE}"
echo -e "  Transport    : ${DISK_TRAN}"
echo -e "  ISO Source   : ${ISO_PATH}"
echo -e "${BLUE}------------------------------------------------------${NC}"

# Demande de confirmation stricte
read -r -p "$(echo -e "${RED}${BOLD}Êtes-vous certain de vouloir détruire et réécrire ${TARGET_DISK} ? (Tapez 'OUI' en majuscules) : ${NC}")" CONFIRMATION
if [[ "${CONFIRMATION}" != "OUI" ]]; then
    echo -e "${YELLOW}[ANNULATION] Opération annulée par l'utilisateur.${NC}"
    exit 0
fi

# 5. Démontage de toutes les partitions existantes du disque cible
echo -e "\n${BLUE}[1/4] Démontage des partitions existantes sur ${TARGET_DISK}...${NC}"
for part in $(lsblk -ln -o PATH "${TARGET_DISK}" | tail -n +2); do
    if mountpoint -q "${part}" 2>/dev/null || grep -qs "^${part} " /proc/mounts; then
        echo -e "      Démontage de ${part}..."
        umount "${part}" || umount -l "${part}" || true
    fi
done

# 6. Écriture de l'ISO sur la clé USB avec dd
echo -e "\n${BLUE}[2/4] Écriture de l'ISO sur ${TARGET_DISK} (dd)...${NC}"
dd if="${ISO_PATH}" of="${TARGET_DISK}" bs=4M status=progress conv=fsync oflag=direct
sync
echo -e "${GREEN}[OK] Image ISO écrite avec succès.${NC}"

# Détection du type de table de partitions écrite par l'image
sleep 1
partprobe "${TARGET_DISK}" || true
udevadm settle

DISK_LABEL=$(sfdisk -d "${TARGET_DISK}" 2>/dev/null | grep "^label:" | awk '{print $2}' || echo "dos")
echo -e "${BLUE}[*] Type de table de partitions détecté : ${BOLD}${DISK_LABEL}${NC}"

# 7. Création de la 3ème partition persistante dans l'espace restant
echo -e "\n${BLUE}[3/4] Création de la 3ème partition sur l'espace restant...${NC}"

if [[ "${DISK_LABEL}" == "gpt" ]]; then
    # Cas GPT : déplacer l'en-tête secondaire à la fin du disque, puis créer part 3
    if command -v sgdisk &>/dev/null; then
        sgdisk -e "${TARGET_DISK}"
        partprobe "${TARGET_DISK}"
        udevadm settle
        sgdisk -n 0:0:0 -t 0:0700 -c 0:"STK_DATA" "${TARGET_DISK}"
    else
        echo -e "${RED}[ERREUR] Table GPT mais 'sgdisk' n'est pas installé.${NC}"
        exit 1
    fi
else
    # Cas MBR/dos (standard généré par mkarchiso / xorriso) :
    # Ajouter la partition 3 de type 07 (HPFS/NTFS/exFAT) occupant tout l'espace libre
    echo ",,07" | sfdisk --append "${TARGET_DISK}"
fi

partprobe "${TARGET_DISK}"
udevadm settle
sleep 1

# Détermination du nom de device de la partition 3
if [[ "${TARGET_DISK}" =~ [0-9]$ ]]; then
    NEW_PART="${TARGET_DISK}p3"
else
    NEW_PART="${TARGET_DISK}3"
fi

if [[ ! -b "${NEW_PART}" ]]; then
    echo -e "${RED}[ERREUR] Le périphérique de partition '${NEW_PART}' n'apparaît pas.${NC}"
    echo -e "         Vérifiez la table avec 'fdisk -l ${TARGET_DISK}'."
    exit 1
fi
echo -e "${GREEN}[OK] Partition créée : ${BOLD}${NEW_PART}${NC}"

# 8. Formatage en exFAT avec le label STK_DATA
echo -e "\n${BLUE}[4/4] Formatage de ${NEW_PART} en exFAT (Label: STK_DATA)...${NC}"
wipefs -a -f "${NEW_PART}" 2>/dev/null || true
mkfs.exfat -F -L "STK_DATA" "${NEW_PART}"
sync
udevadm settle

echo -e "\n${GREEN}${BOLD}======================================================${NC}"
echo -e "${GREEN}${BOLD}   DÉPLOIEMENT TERMINÉ AVEC SUCCÈS !                  ${NC}"
echo -e "${GREEN}${BOLD}======================================================${NC}"
echo -e "Structure finale du disque ${TARGET_DISK} :"
lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTLABEL,MOUNTPOINTS "${TARGET_DISK}"

echo -e "\n${BLUE}Résumé du fonctionnement :${NC}"
echo -e "  1. Partitions 1 & 2 : Système Live Arch Linux (boot UEFI/BIOS, copytoram)."
echo -e "  2. Partition 3 (STK_DATA, exFAT) : Montée automatiquement au démarrage du Live OS"
echo -e "     dans ${BOLD}/home/stk/Base_Data${NC} via fstab."
echo -e "  3. Compatible Windows, macOS et Linux pour brancher la clé et récupérer les données."
