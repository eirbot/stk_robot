// Pilotage : événements reçus de la base (état du robot).
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

// =======================================================
// 6. ÉVÉNEMENTS WEBSOCKET & TÉLÉMÉTRIE
// =======================================================
function initWebSocketEvents() {
    if (!window.socket) return;

    // Statut de connexion
    const connBadge = document.getElementById('conn-badge');

    setInterval(() => {
        if (window.socket.ws && window.socket.ws.readyState === WebSocket.OPEN) {
            if (connBadge) {
                setText(connBadge, "CONNECTÉ (20Hz)");
                setClass(connBadge, "badge-conn connected");
            }
        } else {
            if (connBadge) {
                setText(connBadge, "DÉCONNECTÉ");
                setClass(connBadge, "badge-conn disconnected");
            }
        }
    }, 1000);

    // Mise à jour de la position
    window.socket.on('robot_position', (pos) => {
        if (!pos) return;
        const elX = document.getElementById('pos-x');
        const elY = document.getElementById('pos-y');
        const elTheta = document.getElementById('pos-theta');

        if (elX && pos.x !== undefined) setText(elX, `${pos.x.toFixed(1)} mm`);
        if (elY && pos.y !== undefined) setText(elY, `${pos.y.toFixed(1)} mm`);
        if (elTheta && pos.theta !== undefined) setText(elTheta, `${pos.theta.toFixed(1)}°`);
    });

    // Mise à jour de l'état global et du LiDAR
    window.socket.on('state_update', (state) => {
        if (!state) return;

        // Statut LiDAR
        const badgeLidar = document.getElementById('lidar-status-badge');
        if (badgeLidar) {
            const obsType = state.obstacle_type !== undefined ? state.obstacle_type : (state.telemetry?.obstacle_type || 0);
            const obsDet = state.obstacle_detected || (obsType > 0);

            if (obsType === 1) {
                setIconText(badgeLidar, "circle-stop", "ARRÊT CRITIQUE");
                setClass(badgeLidar, "badge-status status-stop");
            } else if (obsType === 2) {
                setIconText(badgeLidar, "triangle-alert", "OBSTACLE AVANT");
                setClass(badgeLidar, "badge-status status-alert");
            } else if (obsType === 3) {
                setIconText(badgeLidar, "triangle-alert", "OBSTACLE ARRIÈRE");
                setClass(badgeLidar, "badge-status status-alert");
            } else if (obsDet) {
                setIconText(badgeLidar, "triangle-alert", "ATTENTION");
                setClass(badgeLidar, "badge-status status-alert");
            } else {
                setIconText(badgeLidar, null, "LIBRE");
                setClass(badgeLidar, "badge-status status-free");
            }
        }

        // Équipe
        if (state.team) {
            setClass(document.body, `mode-${state.team}`);
        }
    });
}
