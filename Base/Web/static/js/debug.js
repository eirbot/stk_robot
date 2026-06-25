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
});

function initDebugPage() {
    const canvas = document.getElementById('currentChart');
    if (!canvas) return; // Sécurité si le canvas n'existe pas

    const ctx = canvas.getContext('2d');
    currentChart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Courant (A)', data: [], borderColor: '#FFCB6B', borderWidth: 2, tension: 0.3 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: { display: true, ticks: { maxTicksLimit: 10 } },
                y: { beginAtZero: true, grid: { color: '#333' } }
            }
        }
    });
}

// Mise à jour Config via l'événement state_update
window.socket.on('state_update', (state) => {
    const btnCam = document.getElementById('btn-toggle-cam');
    if (btnCam) {
        const c = state.config || {};
        
        // 1. État caméra
        let camEnabled = (typeof c.camera === 'object') ? c.camera.enabled : c.camera;
        if (camEnabled) {
            btnCam.innerText = "📷 Caméra Active";
            btnCam.className = "btn-toggle-active state-on";
        } else {
            btnCam.innerText = "📷 Caméra Inactive";
            btnCam.className = "btn-toggle-active state-off";
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
                btnLidar.innerText = `🚨 LiDAR Actif (${lidarMode})`;
                btnLidar.className = "btn-toggle-active state-on";
            } else {
                btnLidar.innerText = "🚨 LiDAR Inactif";
                btnLidar.className = "btn-toggle-active state-off";
            }
            window.currentLidarMode = lidarMode;
        }

        // Gestion Mode Stratégie
        const stratMode = c.strat_mode || "DYNAMIC";
        const modeSel = document.getElementById('strat-mode');
        if (modeSel) modeSel.value = stratMode;

        const box = document.getElementById('static-strat-box');
        if (box) box.style.display = (stratMode === 'STATIC') ? 'block' : 'none';

        const stratSel = document.getElementById('strat-select');
        if (stratSel && c.static_strat) {
            stratSel.value = c.static_strat;
        }
    }
});

// Fonctions de bascule d'état caméra et LiDAR
async function toggleCamera() {
    const nextState = !window.currentCameraEnabled;
    console.log("Toggle caméra ->", nextState);
    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'camera.enabled', val: nextState })
    });
}

async function toggleLidar() {
    const activeMode = window.lastActiveLidarMode || "MATCH";
    const nextMode = (window.currentLidarMode === "OFF") ? activeMode : "OFF";
    console.log("Toggle LiDAR ->", nextMode);
    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'lidar_mode', val: nextMode })
    });
}

// Envoi modifications de la stratégie
// Envoi modifs stratégie + Mise à jour VISUELLE immédiate
async function updateStratConfig() {
    const mode = document.getElementById('strat-mode').value;
    const file = document.getElementById('strat-select').value;

    // --- PARTIE AJOUTÉE : Gestion visuelle locale ---
    // On force l'affichage sans attendre le retour du serveur/socket
    const box = document.getElementById('static-strat-box');
    if (box) {
        box.style.display = (mode === 'STATIC') ? 'block' : 'none';
    }
    // -----------------------------------------------

    // Envoi au serveur (Backend)
    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'strat_mode', val: mode })
    });

    if (mode === 'STATIC' && file) {
        await fetch('/api/config_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'static_strat', val: file })
        });
    }
}

// Reception des logs
window.socket.on('new_log', (log) => {
    const box = document.getElementById('logs-box');
    if (box) {
        const div = document.createElement('div');
        div.className = 'log-line';
        let cls = 'log-info';
        if (log.msg.includes('[WARN]')) cls = 'log-warn';
        if (log.msg.includes('[ERR]')) cls = 'log-err';
        div.innerHTML = `<span class="log-time">${log.time}</span> <span class="${cls}">${log.msg}</span>`;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }
});

// Infos système & mise à jour du graphique et des statuts périphériques
window.socket.on('sys_info', (data) => {
    if (currentChart) {
        const now = new Date().toLocaleTimeString();
        currentChart.data.labels.push(now);
        currentChart.data.datasets[0].data.push(parseFloat(data.current));
        // 10 minutes d'historique à 10Hz = 600 x 10 = 6000 points
        if (currentChart.data.labels.length > 6000) {
            currentChart.data.labels.shift();
            currentChart.data.datasets[0].data.shift();
        }
        currentChart.update();
    }
    if (data.devs && document.getElementById('status-lidar')) {
        updateDevStatus('status-lidar', data.devs.lidar);
        updateDevStatus('status-esp_motors', data.devs.esp_motors);
        updateDevStatus('status-esp_arms', data.devs.esp_arms);
        updateDevStatus('status-camera', data.devs.camera);

        // Mise à jour de la source du flux vidéo caméra (HTTP MJPEG)
        const img = document.getElementById('camera-stream');
        const placeholder = document.getElementById('camera-placeholder');
        if (img && placeholder) {
            if (data.devs.camera && data.ip) {
                const streamUrl = 'http://' + data.ip + ':8081/stream';
                // Évite de réassigner inutilement l'URL pour ne pas interrompre le flux continu
                if (img.src !== streamUrl) {
                    img.src = streamUrl;
                }
                img.style.display = 'block';
                placeholder.style.display = 'none';
            } else {
                img.style.display = 'none';
                placeholder.style.display = 'block';
                placeholder.innerText = '🎥 Flux caméra inactif ou arrêté.';
            }
        }
    }
});

function updateDevStatus(id, isOk) {
    const el = document.getElementById(id);
    if (el) el.className = 'status-dot ' + (isOk ? 'status-ok' : 'status-err');
}

async function toggleConfig(key, checkbox) {
    // AJOUTE CETTE LIGNE
    console.log("CLICK DETECTÉ SUR :", key, "VALEUR :", checkbox.checked);

    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key, val: checkbox.checked })
    });
}

async function updateLidarConfig(key, val) {
    console.log("CHANGEMENT LIDAR :", key, "VALEUR :", val);
    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key, val: val })
    });
}

function flashESP(target) {
    if (confirm("Flasher l'ESP " + target + " ?")) {
        fetch('/api/flash_esp/' + target, { method: 'POST' }).then(r => r.json()).then(d => alert(d.msg));
    }
}

function updateBrightness(val) {
    // Le slider est de 0 à 100
    // On veut que 100% = 0.5 (Max)
    const factor = 0.5;
    const computed = (parseFloat(val) / 100.0) * factor;

    console.log("Brightness set to:", val, "% ->", computed);
    fetch('/api/set_brightness', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: computed })
    });
}
async function setRobotPosition() {
    const x = document.getElementById('pos-x').value;
    const y = document.getElementById('pos-y').value;
    const theta = document.getElementById('pos-theta').value;

    console.log("Force SET_POS:", x, y, theta);
    const resp = await fetch('/api/set_robot_pos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            x: parseFloat(x),
            y: parseFloat(y),
            theta: parseFloat(theta)
        })
    });
    const data = await resp.json();
    if (data.status === 'ok') {
        console.log("Position robot mise à jour avec succès");
    }
}

// Le flux caméra MJPEG est chargé directement par le navigateur via l'URL HTTP de la Raspberry Pi
