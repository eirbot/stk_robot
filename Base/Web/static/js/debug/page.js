// Page Debug : initialisation, état du robot reçu par WebSocket (cases, menus, voyants).
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

let currentChart = null;

// Au chargement de la page debug, initialisation du graphique et chargement des stratégies Blockly

document.addEventListener("DOMContentLoaded", () => {
    initDebugPage();
    loadBlocklyStrats('strat-select'); // Charge la liste pour le mode Statique

    // EventListener pour le bouton de calibration de la vision zénithale
    const btnCalibrate = document.getElementById('btn-calibrate-vision');
    if (btnCalibrate) {
        btnCalibrate.addEventListener('click', () => {
            console.log("Demande de calibration vision zénithale envoyée...");
            if (window.socket && window.socket.ws && window.socket.ws.readyState === WebSocket.OPEN) {
                window.socket.ws.send(JSON.stringify({ type: "action", payload: "calibrate_vision" }));
            } else {
                console.warn("WebSocket non ouvert. Impossible d'envoyer la demande de calibration.");
            }
        });
    }

    // Gestion du flux Caméra Zénithale USB & Plein Écran
    initZenithaleVision();
});

function initDebugPage() {
    const canvas = document.getElementById('currentChart');
    if (!canvas) return; // Sécurité si le canvas n'existe pas

    // Couleurs du thème courant (common.css)
    const cs = getComputedStyle(document.documentElement);
    const themeColor = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
    const lineColor = themeColor('--timer', '#FFCB6B');
    const gridColor = themeColor('--border', '#333');
    const tickColor = themeColor('--text-muted', '#8b949e');

    const ctx = canvas.getContext('2d');
    currentChart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Courant (A)', data: [], borderColor: lineColor, borderWidth: 2, tension: 0.3, pointRadius: 0 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: tickColor } } },
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10, color: tickColor }, grid: { color: gridColor } },
                y: { beginAtZero: true, ticks: { color: tickColor }, grid: { color: gridColor } }
            }
        }
    });
}

// Icône du sprite + libellé dans un bouton ; n'écrit que si le libellé change
// (state_update arrive à 10 Hz, comme setText de common.js)
function setIconLabel(el, name, label) {
    if (!el) return;
    if (el.textContent.trim() !== label) el.innerHTML = icon(name) + ' ' + label;
}

// Mise à jour Config via l'événement state_update
window.socket.on('state_update', (state) => {
    const btnCam = document.getElementById('btn-toggle-cam');
    if (btnCam) {
        // La config n'est pas dans tous les messages (~1 sur 15) : sans elle, garder la dernière reçue
        // (common.js), sinon caméra, LiDAR et mode de stratégie repassaient aux valeurs par défaut
        const c = state.config || window.localConfig || {};
        
        // 1. État caméra
        let camEnabled = (typeof c.camera === 'object') ? c.camera.enabled : c.camera;
        if (camEnabled) {
            setIconLabel(btnCam, 'camera', "Caméra Active");
            setClass(btnCam, "btn-toggle-active state-on");
        } else {
            setIconLabel(btnCam, 'camera', "Caméra Inactive");
            setClass(btnCam, "btn-toggle-active state-off");
        }
        window.currentCameraEnabled = !!camEnabled;

        // 2. État LiDAR
        const btnLidar = document.getElementById('btn-toggle-lidar');
        const selectLidarMode = document.getElementById('lidar-mode');
        const lidarMode = c.lidar_mode || "OFF";
        
        if (selectLidarMode) {
            selectLidarMode.value = lidarMode;
        }

        if (lidarMode !== "OFF") {
            window.lastActiveLidarMode = lidarMode;
        }

        if (btnLidar) {
            if (lidarMode !== "OFF") {
                setIconLabel(btnLidar, 'radar', `LiDAR Actif (${lidarMode})`);
                setClass(btnLidar, "btn-toggle-active state-on");
            } else {
                setIconLabel(btnLidar, 'radar', "LiDAR Inactif");
                setClass(btnLidar, "btn-toggle-active state-off");
            }
            window.currentLidarMode = lidarMode;
        }

        // Mode test
        const testModeBox = document.getElementById('test-mode');
        if (testModeBox) testModeBox.checked = !!c.test_mode;

        // Gestion Mode Stratégie
        const stratMode = c.strat_mode || "DYNAMIC";
        const modeSel = document.getElementById('strat-mode');
        syncSelect(modeSel, stratMode);

        const box = document.getElementById('static-strat-box');
        if (box && modeSel) box.style.display = (modeSel.value === 'STATIC') ? 'block' : 'none';

        syncSelect(document.getElementById('strat-select'), c.static_strat || null);
    }

    // Mise à jour de la télémétrie odonométrique en direct
    if (state.telemetry) {
        const livePosX = document.getElementById('live-pos-x');
        const livePosY = document.getElementById('live-pos-y');
        const livePosTheta = document.getElementById('live-pos-theta');
        if (livePosX && state.telemetry.x != null) setText(livePosX, Math.round(state.telemetry.x));
        if (livePosY && state.telemetry.y != null) setText(livePosY, Math.round(state.telemetry.y));
        if (livePosTheta && state.telemetry.theta != null) {
            let deg = state.telemetry.theta;
            if (Math.abs(deg) <= Math.PI * 2.1) {
                deg = deg * 180 / Math.PI;
            }
            setText(livePosTheta, Number(deg).toFixed(1));
        }
    }
});
