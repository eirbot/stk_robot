#
# ~/.bash_profile
# Démarrage automatique de Hyprland sur le tty1 pour STKbtw
#

# Charger ~/.bashrc si présent
[[ -f ~/.bashrc ]] && . ~/.bashrc

# Lancement automatique lors d'un login interactif sur tty1
if [[ -z "${DISPLAY}" && -z "${WAYLAND_DISPLAY}" && "$(tty)" == "/dev/tty1" ]]; then
    # Variables d'environnement standard Wayland
    export XDG_SESSION_TYPE=wayland
    export XDG_CURRENT_DESKTOP=Hyprland
    export XDG_SESSION_DESKTOP=Hyprland

    # Forcer Wayland pour les toolkits majeurs
    export GDK_BACKEND="wayland,x11,*"
    export QT_QPA_PLATFORM="wayland;xcb"
    export SDL_VIDEODRIVER=wayland
    export CLUTTER_BACKEND=wayland
    export ELECTRON_OZONE_PLATFORM_HINT=auto

    # Démarrage avec le wrapper officiel start-hyprland pour initialiser
    # les sessions D-Bus / systemd et supprimer l'avertissement Hyprland
    if command -v start-hyprland &>/dev/null; then
        exec start-hyprland
    else
        exec Hyprland
    fi
fi
