// Page Debug : réglages envoyés au robot (caméra, LiDAR, stratégie, luminosité, position).
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

// Fonctions de bascule d'état caméra et LiDAR
async function toggleCamera() {
    const nextState = !window.currentCameraEnabled;
    console.log("Toggle caméra ->", nextState);
    
    // Mise à jour visuelle immédiate (Optimistic UI)
    const btnCam = document.getElementById('btn-toggle-cam');
    if (btnCam) {
        if (nextState) {
            btnCam.innerHTML = icon('camera') + " Caméra Active";
            btnCam.className = "btn-toggle-active state-on";
        } else {
            btnCam.innerHTML = icon('camera') + " Caméra Inactive";
            btnCam.className = "btn-toggle-active state-off";
        }
    }
    window.currentCameraEnabled = nextState;

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

    // Mise à jour visuelle immédiate (Optimistic UI)
    const btnLidar = document.getElementById('btn-toggle-lidar');
    if (btnLidar) {
        if (nextMode !== "OFF") {
            btnLidar.innerHTML = icon('radar') + ` LiDAR Actif (${nextMode})`;
            btnLidar.className = "btn-toggle-active state-on";
        } else {
            btnLidar.innerHTML = icon('radar') + " LiDAR Inactif";
            btnLidar.className = "btn-toggle-active state-off";
        }
    }
    window.currentLidarMode = nextMode;

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

    // Envoi au robot (le menu garde le choix tant que le robot ne l'a pas confirmé)
    if (!await sendConfigEdit('strat-mode', 'strat_mode', mode)) return;
    if (mode === 'STATIC' && file) {
        await sendConfigEdit('strat-select', 'static_strat', file);
    }
}


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

// Odométrie = caméra : le robot prend la médiane de quelques images de la caméra zénithale
// (robot immobile) comme pose connue (actions.py : recalage_camera(force=True))
async function recalageCamera() {
    await fetch('/api/robot/hardware', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'recalage_camera', data: {} })
    });
    toast('Odométrie recalée sur la caméra (robot immobile)');
}

// Le flux caméra MJPEG est chargé directement par le navigateur via l'URL HTTP de la Raspberry Pi
