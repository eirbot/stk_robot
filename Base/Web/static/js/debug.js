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
        const c = state.config || {};
        
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

function appendLog(msg, type = 'info') {
    const box = document.getElementById('logs-box');
    if (!box) return;
    const div = document.createElement('div');
    div.className = 'log-line';
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    let cls = 'log-info';
    if (type === 'warn' || msg.includes('[WARN]')) cls = 'log-warn';
    if (type === 'err' || msg.includes('[ERR]')) cls = 'log-err';
    div.innerHTML = `<span class="log-time">${timeStr}</span> <span class="${cls}">${escapeHtml(msg)}</span>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// Reception des logs
window.socket.on('new_log', (log) => {
    appendLog(log.msg);
});

// Infos système & mise à jour du graphique et des statuts périphériques
window.socket.on('sys_info', (data) => {
    // Le sys_info virtuel (dérivé de la télémétrie à 10 Hz) n'a pas de courant : on l'ignore pour le graphe
    if (currentChart && data.current !== undefined) {
        const now = new Date().toLocaleTimeString();
        currentChart.data.labels.push(now);
        currentChart.data.datasets[0].data.push(parseFloat(data.current));
        // 1200 points max : au-delà, le redessin du graphe rame sur téléphone
        if (currentChart.data.labels.length > 1200) {
            currentChart.data.labels.shift();
            currentChart.data.datasets[0].data.shift();
        }
        currentChart.update('none'); // Sans animation : redessin bien moins coûteux
    }
    if (data.devs && document.getElementById('status-lidar')) {
        updateDevStatus('status-lidar', data.devs.lidar);
        updateDevStatus('status-esp_motors', data.devs.esp_motors);
        updateDevStatus('status-esp_arms', data.devs.esp_arms);
        updateDevStatus('status-camera', data.devs.camera);

        // Mise à jour de la source du flux vidéo caméra (HTTP MJPEG)
        const img = document.getElementById('camera-stream');
        const placeholder = document.getElementById('camera-placeholder');
        const embarqueeBadge = document.getElementById('embarquee-badge');
        if (img && placeholder) {
            if (data.devs.camera && data.ip) {
                const streamUrl = 'http://' + data.ip + ':8081/stream';
                // Évite de réassigner inutilement l'URL pour ne pas interrompre le flux continu
                if (img.src !== streamUrl) {
                    img.src = streamUrl;
                }
                img.style.display = 'block';
                placeholder.style.display = 'none';
                if (embarqueeBadge) {
                    embarqueeBadge.innerText = 'EN DIRECT';
                    embarqueeBadge.className = 'badge-status-pill badge-online';
                }
            } else {
                img.style.display = 'none';
                placeholder.style.display = 'block';
                placeholder.innerHTML = '<div class="placeholder-icon">' + icon('camera', 'icon-lg') + '</div><div id="camera-placeholder-text">Flux caméra inactif ou arrêté.</div>';
                if (embarqueeBadge) {
                    embarqueeBadge.innerText = 'HORS LIGNE';
                    embarqueeBadge.className = 'badge-status-pill badge-offline';
                }
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

async function updateRasp() {
    if (!await askConfirm("Mettre à jour le code de la Rasp (git pull sur la base, copie vers le robot, redémarrage du launcher) ?")) {
        return;
    }

    const btn = document.getElementById('btn-update-rasp');
    const oldText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Mise à jour...";
        btn.style.opacity = "0.7";
    }
    appendLog("[RASP] Mise à jour du code de la Rasp...");

    try {
        const resp = await fetch('/api/update_rasp', { method: 'POST' });
        const data = await resp.json();
        if (data.warning) appendLog(`[RASP] ${data.warning}`, 'err');
        if (data.status === 'ok') {
            appendLog(`[RASP] ${data.msg}`);
            (data.files || []).forEach(f => appendLog(`   • ${f}`));
            alert(`${data.msg}`);
        } else {
            const stepMsg = data.step ? `(Étape: ${data.step}) ` : '';
            appendLog(`[RASP] Erreur ${stepMsg}: ${data.msg}`, 'err');
            if (data.output) {
                appendLog(`[DÉTAILS] ${data.output.split('\n').filter(l => l.trim()).slice(-3).join(' | ')}`, 'err');
            }
            alert(`${data.msg}`);
        }
    } catch (err) {
        appendLog(`[RASP] Erreur réseau : ${err.message}`, 'err');
        alert(`Erreur réseau : ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldText;
            btn.style.opacity = "1";
        }
    }
}

async function flashESP(target) {
    const label = (target === 'motors' || target === 'motor') ? 'MOTEURS' : 'BRAS (Actionneurs)';
    if (!await askConfirm(`Compiler et flasher l'ESP ${label} depuis la base déportée (via la Raspberry Pi) ?`)) {
        return;
    }

    const btn = document.getElementById(target === 'motors' ? 'btn-flash-motors' : 'btn-flash-arms');
    const oldText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Compilation & Flash...";
        btn.style.opacity = "0.7";
    }

    appendLog(`[FLASH] Démarrage de la procédure de flash pour l'ESP ${label}...`);
    appendLog(`[FLASH] Étape 1/3 : Compilation locale PlatformIO en cours...`);

    try {
        const resp = await fetch('/api/flash_esp/' + target, { method: 'POST' });
        const data = await resp.json();

        if (data.status === 'ok') {
            appendLog(`[FLASH] ${data.msg}`);
            alert(`${data.msg}\n\nLe microcontrôleur a été redémarré avec le nouveau firmware.`);
        } else {
            const stepMsg = data.step ? `(Étape: ${data.step}) ` : '';
            appendLog(`[FLASH] Erreur ${stepMsg}: ${data.msg}`, 'err');
            alert(`Erreur lors du flash :\n${data.msg}\n\nConsultez les logs pour plus de détails.`);
            if (data.output) {
                console.error("Détails d'erreur :", data.output);
                appendLog(`[DÉTAILS] ${data.output.split('\n').filter(l => l.trim()).slice(-3).join(' | ')}`, 'err');
            }
        }
    } catch (err) {
        appendLog(`[FLASH] Erreur réseau : ${err.message}`, 'err');
        alert(`Erreur réseau : ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldText;
            btn.style.opacity = "1";
        }
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

// --- DIAGNOSTIC RÉSEAU ---
// 1. Base <-> robot : allers-retours ZMQ faits par la base (/api/robot_ping) : le lien des commandes
// 2. Navigateur <-> base : allers-retours HTTP
// 3-4. Débits navigateur <-> base (flux caméra, mises à jour)
// Chaque requête a un délai maximum ; la base refuse les tests pendant un match (409).

class DiagAbort extends Error {}

// fetch avec délai maximum
async function fetchT(url, opts = {}, ms = 2000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
        const r = await fetch(url, { ...opts, signal: ctrl.signal, cache: 'no-store' });
        if (r.status === 409) throw new DiagAbort('Test impossible pendant un match.');
        return r;
    } finally {
        clearTimeout(timer);
    }
}

// Note d'un lien d'après ses pics (p95) et ses pertes : [texte, classe]
function rateLatency(p95, lossPct, seuils) {
    let i = p95 < seuils[0] ? 0 : p95 < seuils[1] ? 1 : p95 < seuils[2] ? 2 : 3;
    if (lossPct > 0) i = Math.max(i, 2);
    if (lossPct > 10) i = 3;
    return [['Excellent', 'excellent'], ['Bon', 'good'], ['Moyen', 'fair'], ['Mauvais', 'poor']][i];
}

function rateSpeed(mbps) {
    // Le flux caméra MJPEG demande quelques Mbps ; au-delà de 20, rien à gagner
    if (mbps >= 20) return ['Excellent', 'excellent'];
    if (mbps >= 8) return ['Bon', 'good'];
    if (mbps >= 3) return ['Moyen', 'fair'];
    return ['Faible', 'poor'];
}

function percentile(values, p) {
    const s = [...values].sort((a, b) => a - b);
    return s[Math.max(0, Math.ceil(p * s.length) - 1)];
}

function setDiagBox(id, value, unit, rating, detail) {
    document.getElementById(id).innerHTML = `${value} <span>${unit}</span>`;
    const st = document.getElementById(id + '-status');
    st.textContent = rating ? rating[0] + (detail ? ` (${detail})` : '') : (detail || '-');
    st.className = 'test-stat-status' + (rating ? ' status-text-' + rating[1] : '');
}

async function runDiagnosticTest() {
    const btn = document.getElementById('btn-run-speedtest');
    const progressContainer = document.getElementById('test-progress-container');
    const progressBar = document.getElementById('test-progress-bar');
    const statusMsg = document.getElementById('test-status-msg');
    const progress = (pct) => { progressBar.style.width = `${pct}%`; };
    const say = (text, err) => {
        statusMsg.textContent = text;
        statusMsg.classList.toggle('test-status-err', !!err);
    };

    for (const [id, unit] of [['test-robot', 'ms'], ['test-latency', 'ms'], ['test-download', 'Mbps'], ['test-upload', 'Mbps']]) {
        setDiagBox(id, '--', unit, null, '-');
    }
    btn.disabled = true;
    btn.textContent = 'Test en cours…';
    progressContainer.style.display = 'block';
    progress(0);

    try {
        // --- 1. BASE <-> ROBOT ---
        say('Lien base ↔ robot (30 allers-retours)…');
        const r = await fetchT('/api/robot_ping?n=30', {}, 20000);
        if (r.status === 503) {
            setDiagBox('test-robot', '--', 'ms', ['Hors ligne', 'poor'], '');
        } else {
            const rp = await r.json();
            if (rp.received === 0) {
                setDiagBox('test-robot', '--', 'ms', ['Aucune réponse', 'poor'], '');
            } else {
                setDiagBox('test-robot', rp.avg_ms.toFixed(1), 'ms', rateLatency(rp.p95_ms, rp.loss_pct, [10, 30, 80]),
                    `pics ${rp.p95_ms.toFixed(0)} ms, max ${rp.max_ms.toFixed(0)} ms, pertes ${rp.loss_pct.toFixed(0)} %`);
            }
        }
        progress(30);

        // --- 2. NAVIGATEUR <-> BASE ---
        say('Lien navigateur ↔ base (20 allers-retours)…');
        const lat = [];
        let lost = 0;
        const n = 20;
        for (let i = 0; i < n; i++) {
            const t0 = performance.now();
            try {
                await fetchT(`/api/ping?t=${Date.now()}`, {}, 1000);
                lat.push(performance.now() - t0);
            } catch (e) {
                if (e instanceof DiagAbort) throw e;
                lost++;
            }
            progress(30 + (i + 1) / n * 20);
            await new Promise(res => setTimeout(res, 30));
        }
        if (lat.length === 0) throw new Error('La base ne répond plus.');
        const avg = lat.reduce((a, b) => a + b, 0) / lat.length;
        const p95 = percentile(lat, 0.95), lossPct = 100 * lost / n;
        setDiagBox('test-latency', avg.toFixed(1), 'ms', rateLatency(p95, lossPct, [15, 40, 100]),
            `pics ${p95.toFixed(0)} ms, pertes ${lossPct.toFixed(0)} %`);

        // --- 3. DÉBIT DESCENDANT (2 s) ---
        say('Débit descendant…');
        let bytesRead = 0;
        const dlStart = performance.now();
        const ctrl = new AbortController();
        const stop = setTimeout(() => ctrl.abort(), 2000);
        try {
            const dl = await fetch(`/api/speedtest/download?t=${Date.now()}`, { signal: ctrl.signal, cache: 'no-store' });
            if (dl.status === 409) throw new DiagAbort('Test impossible pendant un match.');
            const reader = dl.body.getReader();
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                bytesRead += value.length;
                progress(50 + Math.min(25, (performance.now() - dlStart) / 2000 * 25));
            }
        } catch (e) {
            if (e.name !== 'AbortError') throw e;
        } finally {
            clearTimeout(stop);
        }
        const dlMbps = bytesRead * 8 / ((performance.now() - dlStart) / 1000) / 1e6;
        setDiagBox('test-download', dlMbps.toFixed(1), 'Mbps', rateSpeed(dlMbps));

        // --- 4. DÉBIT MONTANT (2 s, blocs de 1 Mo aléatoires : incompressibles) ---
        say('Débit montant…');
        const block = new Uint8Array(1024 * 1024);
        for (let i = 0; i < block.length; i += 65536) crypto.getRandomValues(block.subarray(i, i + 65536));
        let sent = 0;
        const ulStart = performance.now();
        while (performance.now() - ulStart < 2000) {
            const up = await fetchT('/api/speedtest/upload', { method: 'POST', body: block }, 3000);
            await up.json();
            sent += block.length;
            progress(75 + Math.min(25, (performance.now() - ulStart) / 2000 * 25));
        }
        const ulMbps = sent * 8 / ((performance.now() - ulStart) / 1000) / 1e6;
        setDiagBox('test-upload', ulMbps.toFixed(1), 'Mbps', rateSpeed(ulMbps));

        progress(100);
        say('Diagnostic terminé.');
    } catch (err) {
        const msg = err instanceof DiagAbort ? err.message
            : err.name === 'AbortError' ? 'La base ne répond pas (délai dépassé).'
            : `Erreur de connexion : ${err.message}`;
        say(msg, true);
        toast(msg, 'err');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Lancer le test de connexion';
        setTimeout(() => { progressContainer.style.display = 'none'; }, 3000);
    }
}

/* ==========================================================================
   GESTION DU FLUX CAMÉRA ZÉNITHALE USB & PLEIN ÉCRAN
   ========================================================================== */

let isArucoActive = true;
let currentCamResolution = "4K";
let zenithaleStatusTimer = null;
let isZenithaleStreamConnected = false;

function initZenithaleVision() {
    // S'assurer que les boutons quitter plein écran sont strictement masqués au démarrage
    document.querySelectorAll('.fullscreen-close-btn').forEach(btn => {
        btn.style.setProperty('display', 'none', 'important');
    });

    // Initialisation de la surveillance du statut zénithale
    checkZenithaleStatus();
    if (!zenithaleStatusTimer) {
        zenithaleStatusTimer = setInterval(checkZenithaleStatus, 1000);
    }

    // Écouteur pour le mode plein écran
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' || e.key === 'Esc') {
            exitFullscreen();
        }
    });
}

/**
 * Bascule la résolution de la caméra USB (4K @ 30fps <-> 1080p @ 60fps)
 */
async function toggleCameraResolution() {
    const btn = document.getElementById('btn-toggle-resolution');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
    }

    try {
        const host = window.location.hostname || 'localhost';
        const resp = await fetch(`http://${host}:8082/api/toggle_resolution`);
        if (resp.ok) {
            const data = await resp.json();
            currentCamResolution = data.requested || (currentCamResolution === '4K' ? '1080P' : '4K');
            updateResolutionButtonUI(currentCamResolution);
        } else {
            // Fallback via Go backend
            const resp2 = await fetch('/api/vision/resolution', { method: 'POST' });
            if (resp2.ok) {
                const data2 = await resp2.json();
                currentCamResolution = data2.requested || (currentCamResolution === '4K' ? '1080P' : '4K');
                updateResolutionButtonUI(currentCamResolution);
            }
        }
    } catch (e) {
        console.error("Erreur toggleCameraResolution:", e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
        setTimeout(checkZenithaleStatus, 600);
    }
}

function updateResolutionButtonUI(resKey) {
    const btn = document.getElementById('btn-toggle-resolution');
    if (!btn) return;
    const cleanKey = (resKey || '4K').toUpperCase();
    if (cleanKey === '1080P') {
        btn.innerHTML = icon('zap') + ' 1080p @ 60fps';
        btn.className = 'btn-video-action btn-resolution-toggle mode-60fps';
        btn.title = 'Actuellement 1080p @ 60fps (Cliquer pour basculer en 4K @ 30fps)';
    } else if (cleanKey === '2K') {
        btn.innerHTML = icon('zap') + ' 2K @ 60fps';
        btn.className = 'btn-video-action btn-resolution-toggle mode-60fps';
        btn.title = 'Actuellement 2K @ 60fps (Cliquer pour basculer en 4K @ 30fps)';
    } else {
        btn.innerHTML = icon('video') + ' 4K @ 30fps';
        btn.className = 'btn-video-action btn-resolution-toggle';
        btn.title = 'Actuellement 4K @ 30fps (Cliquer pour basculer en 1080p @ 60fps)';
    }
}

/**
 * Bascule l'incrustation ArUco dans le flux vidéo
 */
function toggleArucoOverlay() {
    isArucoActive = !isArucoActive;
    console.log("Toggle ArUco Overlay ->", isArucoActive);

    const btn = document.getElementById('btn-toggle-aruco');
    if (btn) {
        if (isArucoActive) {
            btn.innerHTML = icon('scan') + ' ArUco : ON';
            btn.className = 'btn-video-action btn-aruco-active';
        } else {
            btn.innerHTML = icon('scan') + ' ArUco : OFF';
            btn.className = 'btn-video-action btn-aruco-inactive';
        }
    }

    // Mise à jour immédiate du flux avec la nouvelle requête
    const img = document.getElementById('zenithale-stream');
    if (img && img.style.display !== 'none') {
        const host = window.location.hostname || 'localhost';
        img.src = `http://${host}:8082/stream?aruco=${isArucoActive ? 1 : 0}&t=${Date.now()}`;
    }

    // Notifier le serveur vision en arrière-plan
    try {
        const host = window.location.hostname || 'localhost';
        fetch(`http://${host}:8082/api/toggle_aruco?state=${isArucoActive ? 1 : 0}`, { mode: 'no-cors' }).catch(() => {});
    } catch (e) {}
}

/**
 * Vérifie l'état de la caméra zénithale et met à jour l'interface
 */
async function checkZenithaleStatus() {
    const img = document.getElementById('zenithale-stream');
    const placeholder = document.getElementById('zenithale-placeholder');
    const badge = document.getElementById('zenithale-badge');
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    const host = window.location.hostname || 'localhost';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1200);
        const resp = await fetch(`http://${host}:8082/api/status`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (resp.ok) {
            const data = await resp.json();
            isZenithaleStreamConnected = true;

            if (img && placeholder) {
                const streamUrl = `http://${host}:8082/stream?aruco=${isArucoActive ? 1 : 0}`;
                if (!img.src || !img.src.includes(':8082/stream') || img.style.display === 'none') {
                    img.src = streamUrl;
                }
                img.style.display = 'block';
                placeholder.style.display = 'none';
            }

            if (badge) {
                if (data.robot_detected) {
                    badge.innerText = `ROBOT VU (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                } else if (data.homography_ready) {
                    badge.innerText = `TABLE CALIBRÉE (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                } else {
                    badge.innerText = `EN DIRECT (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                }
            }

            if (data.resolution) {
                currentCamResolution = data.resolution;
                updateResolutionButtonUI(data.resolution);
            }

            if (pwrBtn) {
                pwrBtn.innerHTML = icon('circle-stop') + ' Arrêter';
                pwrBtn.className = 'btn-video-action btn-vision-power running';
            }

            // Mise à jour des coordonnées et statuts du panneau télémétrie zénithale
            updateZenithaleTelemetryUI(data);
            return;
        }
    } catch (err) {
        // En cas d'erreur de communication avec le port 8082
        isZenithaleStreamConnected = false;
    }

    // Si le port 8082 ne répond pas, vérification via le backend Go
    try {
        const resp = await fetch('/api/vision/status');
        if (resp.ok) {
            const data = await resp.json();
            if (pwrBtn) {
                if (data.running) {
                    pwrBtn.innerHTML = icon('circle-stop') + ' Arrêter';
                    pwrBtn.className = 'btn-video-action btn-vision-power running';
                } else {
                    pwrBtn.innerHTML = icon('play') + ' Démarrer';
                    pwrBtn.className = 'btn-video-action btn-vision-power';
                }
            }
        }
    } catch (e) {}

    // Affichage de l'état déconnecté
    if (img && placeholder) {
        img.style.display = 'none';
        placeholder.style.display = 'flex';
    }
    if (badge) {
        badge.innerText = 'HORS LIGNE';
        badge.className = 'badge-status-pill badge-offline';
    }

    // Réinitialisation du panneau télémétrie zénithale
    updateZenithaleTelemetryUI(null);
}

/**
 * Met à jour le bandeau d'affichage de la télémétrie zénithale (X, Y, Theta, Robot, Table)
 */
function updateZenithaleTelemetryUI(data) {
    const zenRobotStatus = document.getElementById('zen-robot-status');
    const zenPosX = document.getElementById('zen-pos-x');
    const zenPosY = document.getElementById('zen-pos-y');
    const zenPosTheta = document.getElementById('zen-pos-theta');
    const zenTableStatus = document.getElementById('zen-table-status');
    const zenTagsList = document.getElementById('zen-tags-list');
    const livePosX = document.getElementById('live-pos-x');
    const livePosY = document.getElementById('live-pos-y');
    const livePosTheta = document.getElementById('live-pos-theta');

    if (!data) {
        if (zenRobotStatus) {
            zenRobotStatus.innerText = 'HORS LIGNE';
            zenRobotStatus.className = 'telemetry-badge-status not-detected';
        }
        if (zenPosX) zenPosX.innerText = '--';
        if (zenPosY) zenPosY.innerText = '--';
        if (zenPosTheta) zenPosTheta.innerText = '--';
        if (zenTableStatus) {
            zenTableStatus.innerText = 'HORS LIGNE';
            zenTableStatus.className = 'telemetry-subval';
        }
        if (zenTagsList) zenTagsList.innerText = '--';
        return;
    }

    window.lastVisionData = data;

    if (zenRobotStatus) {
        const tagLabel = data.robot_tag_id ? `TAG #${data.robot_tag_id}` : 'TAG #2';
        if (data.robot_detected) {
            zenRobotStatus.innerText = `DÉTECTÉ (${tagLabel})`;
            zenRobotStatus.className = 'telemetry-badge-status detected';
        } else {
            zenRobotStatus.innerText = `NON DÉTECTÉ (${tagLabel})`;
            zenRobotStatus.className = 'telemetry-badge-status not-detected';
        }
    }

    if (zenPosX && zenPosY && zenPosTheta) {
        if (data.robot_detected) {
            zenPosX.innerText = Math.round(data.robot_x);
            zenPosY.innerText = Math.round(data.robot_y);
            zenPosTheta.innerText = Number(data.robot_theta_deg).toFixed(1);
        } else {
            zenPosX.innerText = '--';
            zenPosY.innerText = '--';
            zenPosTheta.innerText = '--';
        }
    }

    if (zenTableStatus) {
        if (data.homography_ready) {
            zenTableStatus.innerText = 'CALIBRÉE (4/4)';
            zenTableStatus.className = 'telemetry-subval ready';
        } else {
            const tableTags = [10, 11, 12, 13];
            const nbTags = (data.detected_ids || []).filter(id => tableTags.includes(id)).length;
            zenTableStatus.innerText = `ATTENTE (${nbTags}/4)`;
            zenTableStatus.className = 'telemetry-subval';
        }
    }

    if (zenTagsList) {
        if (data.detected_ids && data.detected_ids.length > 0) {
            zenTagsList.innerText = '[' + data.detected_ids.join(', ') + ']';
        } else {
            zenTagsList.innerText = 'Aucun';
        }
    }

    // Mise à jour de la carte odométrie avec la vision en temps réel si détecté
    if (data.robot_detected) {
        if (livePosX) livePosX.innerText = Math.round(data.robot_x);
        if (livePosY) livePosY.innerText = Math.round(data.robot_y);
        if (livePosTheta) livePosTheta.innerText = Number(data.robot_theta_deg).toFixed(1);
    }
}

/**
 * Copie les coordonnées détectées par la caméra zénithale directement dans les champs d'entrée d'odométrie
 */
function copyVisionToInputs() {
    if (!window.lastVisionData || !window.lastVisionData.robot_detected) {
        alert("Le robot n'est pas encore détecté par la caméra zénithale.");
        return;
    }
    const inputX = document.getElementById('pos-x');
    const inputY = document.getElementById('pos-y');
    const inputTheta = document.getElementById('pos-theta');
    if (inputX) inputX.value = Math.round(window.lastVisionData.robot_x);
    if (inputY) inputY.value = Math.round(window.lastVisionData.robot_y);
    if (inputTheta) inputTheta.value = Math.round(window.lastVisionData.robot_theta_deg);

    showNotification("Coordonnées Vision copiées dans les entrées odométriques !");
}

/**
 * Démarre le sous-processus vision_worker
 */
async function startVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn) pwrBtn.innerText = 'Démarrage...';
    try {
        await fetch('/api/vision/start', { method: 'POST' });
    } catch (e) {
        console.error("Erreur startVisionWorker:", e);
    }
    setTimeout(checkZenithaleStatus, 800);
}

/**
 * Arrête le sous-processus vision_worker
 */
async function stopVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn) pwrBtn.innerText = 'Arrêt...';
    try {
        await fetch('/api/vision/stop', { method: 'POST' });
    } catch (e) {
        console.error("Erreur stopVisionWorker:", e);
    }
    setTimeout(checkZenithaleStatus, 400);
}

/**
 * Bascule marche/arrêt du vision_worker
 */
async function toggleVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn && pwrBtn.classList.contains('running')) {
        await stopVisionWorker();
    } else {
        await startVisionWorker();
    }
}

/**
 * Met à jour l'affichage d'un conteneur vidéo selon qu'il est en plein écran ou non
 */
function updateContainerFullscreenUI(containerId, isFs) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const isZenithale = (containerId === 'container-zenithale');
    const closeBtn = document.getElementById(isZenithale ? 'fs-close-zenithale' : 'fs-close-embarquee');
    const toggleBtn = document.getElementById(isZenithale ? 'btn-fullscreen-zenithale' : 'btn-fullscreen-embarquee');
    const img = container.querySelector('.video-feed');

    if (isFs) {
        container.classList.add('is-fullscreen');
        if (closeBtn) closeBtn.style.setProperty('display', 'block', 'important');
        if (toggleBtn) toggleBtn.innerHTML = icon('x') + ' Quitter';
        if (img) {
            img.style.setProperty('max-height', '100vh', 'important');
            img.style.setProperty('height', '100vh', 'important');
            img.style.setProperty('width', '100vw', 'important');
            img.style.setProperty('object-fit', 'contain', 'important');
        }
    } else {
        container.classList.remove('is-fullscreen');
        if (closeBtn) closeBtn.style.setProperty('display', 'none', 'important');
        if (toggleBtn) toggleBtn.innerHTML = icon('maximize') + ' Plein écran';
        if (img) {
            img.style.removeProperty('max-height');
            img.style.removeProperty('height');
            img.style.removeProperty('width');
            img.style.removeProperty('object-fit');
        }
    }
}

/**
 * Bascule le plein écran pour un conteneur vidéo donné
 */
async function toggleFullscreen(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    const isCurrentFs = (fsEl === container) || container.classList.contains('is-fullscreen');

    if (isCurrentFs) {
        await exitFullscreen();
    } else {
        // Quitter tout plein écran préexistant d'abord
        if (fsEl || document.querySelector('.video-display-container.is-fullscreen')) {
            await exitFullscreen();
        }

        try {
            if (container.requestFullscreen) {
                await container.requestFullscreen();
            } else if (container.webkitRequestFullscreen) {
                container.webkitRequestFullscreen();
            } else if (container.mozRequestFullScreen) {
                container.mozRequestFullScreen();
            } else if (container.msRequestFullscreen) {
                container.msRequestFullscreen();
            } else {
                updateContainerFullscreenUI(containerId, true);
            }
        } catch (err) {
            console.warn('requestFullscreen a échoué, fallback CSS:', err);
            updateContainerFullscreenUI(containerId, true);
        }
    }
}

/**
 * Quitte le mode plein écran proprement et restaure la page de debug
 */
async function exitFullscreen() {
    // 1. Réinitialiser immédiatement l'état visuel de tous les conteneurs
    updateContainerFullscreenUI('container-zenithale', false);
    updateContainerFullscreenUI('container-embarquee', false);

    // 2. Quitter le plein écran natif du navigateur si actif
    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    if (fsEl) {
        try {
            if (document.exitFullscreen) {
                await document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        } catch (e) {
            console.warn('Erreur lors de exitFullscreen:', e);
        }
    }

    // 3. Forcer une seconde fois la remise à zéro
    updateContainerFullscreenUI('container-zenithale', false);
    updateContainerFullscreenUI('container-embarquee', false);
}

/**
 * Met à jour l'état et l'interface lors des changements d'état plein écran du navigateur
 */
function handleFullscreenChange() {
    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    const isZenithaleFs = Boolean(fsEl && (fsEl.id === 'container-zenithale' || fsEl.contains(document.getElementById('zenithale-stream'))));
    const isEmbarqueeFs = Boolean(fsEl && (fsEl.id === 'container-embarquee' || fsEl.contains(document.getElementById('camera-stream'))));

    updateContainerFullscreenUI('container-zenithale', isZenithaleFs);
    updateContainerFullscreenUI('container-embarquee', isEmbarqueeFs);
}

// --- Versions du code (base : binaire ; robot : fichier VERSION écrit au déploiement) ---
async function refreshCodeVersions() {
    const el = document.getElementById('code-versions');
    if (!el) return;
    try {
        const v = await (await fetch('/api/version')).json();
        const robot = v.robot && v.robot.commit ? `${v.robot.commit}${v.robot.date ? ' (' + v.robot.date.slice(0, 16).replace('T', ' ') + ')' : ''}` : 'inconnue';
        setText(el, `Base : ${v.base || 'inconnue'} · Robot : ${robot}`);
    } catch (e) {
        setText(el, 'Versions indisponibles');
    }
}
refreshCodeVersions();
setInterval(refreshCodeVersions, 10000);
