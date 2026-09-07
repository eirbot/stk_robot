#!/usr/bin/env bash
# shellcheck disable=SC2034
# ==============================================================================
# STKbtw - Profil archiso pour PC embarqué (Coupe de France de Robotique 2026)
# ==============================================================================

iso_name="stkbtw"
iso_label="STKBTW_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="Eirbot - STK Robot Team <https://eirbot.github.io>"
iso_application="STKbtw Live OS (RAM copytoram) - Base Deporte"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=(
    'bios.syslinux'
    'uefi.systemd-boot'
)
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
# Compression xz avec dictionnaire 1M pour compacité et rapidité de chargement en RAM
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')

# Permissions strictes sans nécessiter de chmod manuel dans Git
# Note: Un slash final '/' applique la récursion (chown -R / chmod -R)
declare -A file_permissions=(
    ["/etc/shadow"]="0:0:400"
    ["/etc/gshadow"]="0:0:400"
    ["/etc/sudoers.d/"]="0:0:750"
    ["/etc/sudoers.d/stk"]="0:0:440"
    ["/root/"]="0:0:750"
    ["/etc/skel/"]="0:0:755"
    ["/etc/skel/.bash_profile"]="0:0:644"
    ["/home/stk/"]="1000:1000:755"
    ["/home/stk/.bash_profile"]="1000:1000:644"
    ["/home/stk/Base_Data/"]="1000:1000:755"
    ["/opt/eirbot/"]="1000:1000:755"
    ["/opt/eirbot/Base/Web/base_stk"]="1000:1000:755"
    ["/usr/local/bin/"]="0:0:755"
    ["/usr/local/bin/stk-dashboard"]="0:0:755"
)
