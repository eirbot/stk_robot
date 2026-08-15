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
    
    // Mise à jour visuelle immédiate (Optimistic UI)
    const btnCam = document.getElementById('btn-toggle-cam');
    if (btnCam) {
        if (nextState) {
            btnCam.innerText = "📷 Caméra Active";
            btnCam.className = "btn-toggle-active state-on";
        } else {
            btnCam.innerText = "📷 Caméra Inactive";
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
            btnLidar.innerText = `🚨 LiDAR Actif (${nextMode})`;
            btnLidar.className = "btn-toggle-active state-on";
        } else {
            btnLidar.innerText = "🚨 LiDAR Inactif";
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

async function runDiagnosticTest() {
    const btn = document.getElementById('btn-run-speedtest');
    const progressContainer = document.getElementById('test-progress-container');
    const progressBar = document.getElementById('test-progress-bar');
    const statusMsg = document.getElementById('test-status-msg');
    
    // Reset values in UI
    document.getElementById('test-latency').innerHTML = '-- <span>ms</span>';
    document.getElementById('test-latency-status').innerText = '-';
    document.getElementById('test-latency-status').className = 'test-stat-status';
    document.getElementById('test-download').innerHTML = '-- <span>Mbps</span>';
    document.getElementById('test-download-status').innerText = '-';
    document.getElementById('test-download-status').className = 'test-stat-status';
    document.getElementById('test-upload').innerHTML = '-- <span>Mbps</span>';
    document.getElementById('test-upload-status').innerText = '-';
    document.getElementById('test-upload-status').className = 'test-stat-status';

    btn.disabled = true;
    btn.innerText = "TEST EN COURS...";
    btn.style.filter = "brightness(0.7)";
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    statusMsg.style.color = '#888';

    try {
        // --- 1. LATENCE ---
        statusMsg.innerText = "Mesure de la latence (ping) en cours...";
        let latencies = [];
        const numPings = 15;
        for (let i = 0; i < numPings; i++) {
            const start = performance.now();
            // Cache-busting parameter
            await fetch(`/api/ping?t=${Date.now()}`);
            const end = performance.now();
            latencies.push(end - start);
            progressBar.style.width = `${((i + 1) / numPings) * 20}%`; // Ping takes up 20%
            await new Promise(r => setTimeout(r, 30)); // small delay
        }
        
        // Trier pour exclure les valeurs aberrantes (les 2 plus élevées et les 2 plus basses)
        const sorted = [...latencies].sort((a, b) => a - b);
        const filtered = sorted.slice(2, -2);
        const avgLatency = filtered.reduce((a, b) => a + b, 0) / filtered.length;
        const minLatency = Math.min(...latencies);
        
        const latencyEl = document.getElementById('test-latency');
        const latencyStatusEl = document.getElementById('test-latency-status');
        
        latencyEl.innerHTML = `${avgLatency.toFixed(1)} <span>ms</span>`;
        if (avgLatency < 5) {
            latencyStatusEl.innerText = `Excellent (min: ${minLatency.toFixed(0)}ms)`;
            latencyStatusEl.className = 'test-stat-status status-text-excellent';
        } else if (avgLatency < 20) {
            latencyStatusEl.innerText = `Bon (min: ${minLatency.toFixed(0)}ms)`;
            latencyStatusEl.className = 'test-stat-status status-text-good';
        } else if (avgLatency < 50) {
            latencyStatusEl.innerText = `Moyen (min: ${minLatency.toFixed(0)}ms)`;
            latencyStatusEl.className = 'test-stat-status status-text-fair';
        } else {
            latencyStatusEl.innerText = `Mauvais (min: ${minLatency.toFixed(0)}ms)`;
            latencyStatusEl.className = 'test-stat-status status-text-poor';
        }

        // --- 2. DEBIT DESCENDANT (DOWNLOAD) ---
        statusMsg.innerText = "Test de débit descendant (téléchargement) en cours...";
        
        const dlStartTime = performance.now();
        let bytesRead = 0;
        
        const controller = new AbortController();
        const signal = controller.signal;
        const timeoutId = setTimeout(() => controller.abort(), 2000); // Test durant 2 secondes
        
        // Progress bar smooth animation during download
        const dlProgInterval = setInterval(() => {
            const elapsed = performance.now() - dlStartTime;
            const progressPercent = 20 + Math.min(40, (elapsed / 2000) * 40);
            progressBar.style.width = `${progressPercent}%`;
        }, 100);

        try {
            const dlResp = await fetch(`/api/speedtest/download?t=${Date.now()}`, { signal });
            const reader = dlResp.body.getReader();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                bytesRead += value.length;
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                throw err;
            }
        } finally {
            clearTimeout(timeoutId);
            clearInterval(dlProgInterval);
        }
        
        const dlEndTime = performance.now();
        progressBar.style.width = '60%'; // Fin de l'étape download
        
        const dlDurationSec = (dlEndTime - dlStartTime) / 1000;
        const dlSpeedMbps = (bytesRead * 8 / dlDurationSec) / (1000 * 1000);
        
        const downloadEl = document.getElementById('test-download');
        const downloadStatusEl = document.getElementById('test-download-status');
        
        downloadEl.innerHTML = `${dlSpeedMbps.toFixed(1)} <span>Mbps</span>`;
        if (dlSpeedMbps > 250) {
            downloadStatusEl.innerText = 'Excellent';
            downloadStatusEl.className = 'test-stat-status status-text-excellent';
        } else if (dlSpeedMbps > 80) {
            downloadStatusEl.innerText = 'Bon';
            downloadStatusEl.className = 'test-stat-status status-text-good';
        } else if (dlSpeedMbps > 20) {
            downloadStatusEl.innerText = 'Moyen';
            downloadStatusEl.className = 'test-stat-status status-text-fair';
        } else {
            downloadStatusEl.innerText = 'Faible';
            downloadStatusEl.className = 'test-stat-status status-text-poor';
        }

        // --- 3. DEBIT MONTANT (UPLOAD) ---
        statusMsg.innerText = "Test de débit montant (téléversement) en cours...";
        
        // Generate 2MB of random bytes in Javascript for high-speed upload precision
        const uploadSize = 2 * 1024 * 1024; // 2 MB
        const uploadBuffer = new Uint8Array(uploadSize);
        // Fill buffer with random values to make it incompressible
        for (let i = 0; i < uploadSize; i += 65536) {
            const chunk = uploadBuffer.subarray(i, i + 65536);
            crypto.getRandomValues(chunk);
        }
        
        const ulStartTime = performance.now();
        let bytesUploaded = 0;
        const testDuration = 2000; // 2 seconds
        
        while (performance.now() - ulStartTime < testDuration) {
            const response = await fetch('/api/speedtest/upload', {
                method: 'POST',
                body: uploadBuffer
            });
            await response.json();
            bytesUploaded += uploadSize;
            
            const elapsed = performance.now() - ulStartTime;
            const progressPercent = 60 + Math.min(40, (elapsed / testDuration) * 40);
            progressBar.style.width = `${progressPercent}%`;
        }
        
        const ulEndTime = performance.now();
        progressBar.style.width = '100%';
        
        const ulDurationSec = (ulEndTime - ulStartTime) / 1000;
        const ulSpeedMbps = (bytesUploaded * 8 / ulDurationSec) / (1000 * 1000);
        
        const uploadEl = document.getElementById('test-upload');
        const uploadStatusEl = document.getElementById('test-upload-status');
        
        uploadEl.innerHTML = `${ulSpeedMbps.toFixed(1)} <span>Mbps</span>`;
        if (ulSpeedMbps > 250) {
            uploadStatusEl.innerText = 'Excellent';
            uploadStatusEl.className = 'test-stat-status status-text-excellent';
        } else if (ulSpeedMbps > 80) {
            uploadStatusEl.innerText = 'Bon';
            uploadStatusEl.className = 'test-stat-status status-text-good';
        } else if (ulSpeedMbps > 20) {
            uploadStatusEl.innerText = 'Moyen';
            uploadStatusEl.className = 'test-stat-status status-text-fair';
        } else {
            uploadStatusEl.innerText = 'Faible';
            uploadStatusEl.className = 'test-stat-status status-text-poor';
        }

        statusMsg.innerText = "Diagnostic terminé avec succès !";
        
    } catch (err) {
        console.error("Erreur durant le test de diagnostic:", err);
        statusMsg.innerText = "Erreur de connexion durant le test.";
        statusMsg.style.color = '#f44336';
    } finally {
        btn.disabled = false;
        btn.innerText = "Lancer le test de connexion";
        btn.style.filter = "none";
        setTimeout(() => {
            progressContainer.style.display = 'none';
        }, 3000);
    }
}
