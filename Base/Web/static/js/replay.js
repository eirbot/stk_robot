// Replay d'un match : boîte noire du robot (Rasp/utils/telemetry_logger.py), lue par ssh (Base/Web/media.go).
// match_*.jsonl : trames 10 Hz (pose, caméra, adversaires, LiDAR, évitement) + événements de stratégie
// (goto, plan, retour, tag...) ; anciens blackbox_*.csv : pose et batterie seulement.
// Toile 3000 x 2000 = la table vue comme la carte 3D (frames.js) : Y vers la droite, X vers le bas.

let logData = [];        // trames {t, x, y, th, fsm, v, i, obs, sig, cam, adv, lidar}
let logEvents = [];      // {t, k, ...}
let isPlaying = false;
let playbackIndex = 0;
let playbackSpeed = 5;
let animationFrameId;

const selectLogs = document.getElementById('log-select');
const btnPlay = document.getElementById('btn-play');
const slider = document.getElementById('time-slider');
const timeDisplay = document.getElementById('time-display');
const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');
const selectSpeed = document.getElementById('speed-select');

// Encombrement du robot autour de son point de référence (core/frames.py)
const ROBOT_AVANT = 245.5, ROBOT_ARRIERE = 102.0, ROBOT_DEMI_LARGEUR = 188.2;
const OBS_COULEURS = ['#2fbf4a', '#ff3b3b', '#ff9300', '#ff9300'];   // CLEAR, STOP, FRONT, BACK
const OBS_NOMS = ['libre', 'STOP', 'avant bloqué', 'arrière bloqué'];

let vChart, cChart;

// (la page ne charge pas common.js : pas de WebSocket ici)
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

window.onload = function () {
    fetchLogs();
    setupCharts();
};

selectSpeed.onchange = () => playbackSpeed = parseInt(selectSpeed.value);

slider.oninput = function () {
    playbackIndex = parseInt(this.value);
    updateFrame(playbackIndex);
};

function fetchLogs() {
    fetch('/api/logs/list')
        .then(r => r.json())
        .then(files => {
            selectLogs.innerHTML = '';
            if (!files.length) {
                selectLogs.innerHTML = '<option>Aucun journal (robot hors ligne ?)</option>';
                return;
            }
            files.forEach(f => {
                const o = document.createElement('option');
                o.value = f;
                o.textContent = f;
                selectLogs.appendChild(o);
            });
        });
}

function loadLog() {
    const filename = selectLogs.value;
    if (!filename) return;
    fetch(`/api/logs/${filename}`)
        .then(r => r.text())
        .then(text => {
            if (filename.endsWith('.jsonl')) parseJSONL(text); else parseCSV(text);
            slider.max = Math.max(0, logData.length - 1);
            updateChartsTotal();
            renderEvents();
            resetPlayer();
        });
}

function parseJSONL(text) {
    logData = [];
    logEvents = [];
    for (const line of text.split('\n')) {
        if (!line.trim()) continue;
        let o;
        try { o = JSON.parse(line); } catch (e) { continue; }
        if (o.type === 'f') logData.push(o);
        else if (o.type === 'e') logEvents.push(o);
    }
}

function parseCSV(text) {
    // timestamp,match_time,x,y,theta,match_running,fsm_state,voltage,current,cpu_temp
    logData = [];
    logEvents = [];
    const lines = text.trim().split('\n');
    for (let i = 1; i < lines.length; i++) {
        const p = lines[i].split(',');
        if (p.length < 9) continue;
        logData.push({
            t: parseFloat(p[1]), x: parseFloat(p[2]), y: parseFloat(p[3]), th: parseFloat(p[4]),
            fsm: p[6], v: parseFloat(String(p[7]).replace('V', '')), i: parseFloat(p[8]), obs: 0
        });
    }
}

function resetPlayer() {
    isPlaying = false;
    playbackIndex = 0;
    slider.value = 0;
    btnPlay.innerHTML = icon('play') + " PLAY";
    updateFrame(0);
}

function togglePlay() {
    if (isPlaying) {
        isPlaying = false;
        btnPlay.innerHTML = icon('play') + " PLAY";
        cancelAnimationFrame(animationFrameId);
    } else {
        isPlaying = true;
        btnPlay.innerHTML = "PAUSE";
        lastLoopTime = Date.now();
        loop();
    }
}

let lastLoopTime = 0;
let accumulated = 0;
function loop() {
    if (!isPlaying) return;
    const now = Date.now();
    accumulated += (now - lastLoopTime) / 1000 * 10 * playbackSpeed;   // 10 trames par seconde de match
    lastLoopTime = now;
    if (accumulated >= 1) {
        playbackIndex += Math.floor(accumulated);
        accumulated -= Math.floor(accumulated);
        if (playbackIndex >= logData.length) {
            playbackIndex = logData.length - 1;
            isPlaying = false;
            btnPlay.innerHTML = icon('play') + " PLAY";
        }
        slider.value = playbackIndex;
        updateFrame(playbackIndex);
    }
    animationFrameId = requestAnimationFrame(loop);
}

function setText(id, txt) {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
}

function updateFrame(idx) {
    const d = logData[idx];
    if (!d) return;
    timeDisplay.innerText = d.t.toFixed(2) + "s";
    setText('val-batt', isFinite(d.v) ? d.v.toFixed(2) + " V" : '--');
    setText('val-curr', isFinite(d.i) ? Number(d.i).toFixed(2) + " A" : '--');
    setText('val-state', d.fsm || '--');
    setText('val-obs', OBS_NOMS[d.obs || 0] || String(d.obs));
    setText('val-sig', d.sig !== undefined ? d.sig.toFixed(0) + ' mm' : '--');
    drawMap(idx);
    highlightEvents(d.t);
}

// --- Dessin ------------------------------------------------------------------------------
// Repère table -> toile : Y (-1500..1500) vers la droite, X (0..2000) vers le bas
const px = (x, y) => [y + 1500, x];

function drawTable() {
    const css = getComputedStyle(document.documentElement);
    ctx.fillStyle = '#1d5c2e';
    ctx.fillRect(0, 0, 3000, 2000);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 2;
    for (let v = 0; v <= 3000; v += 250) { ctx.beginPath(); ctx.moveTo(v, 0); ctx.lineTo(v, 2000); ctx.stroke(); }
    for (let v = 0; v <= 2000; v += 250) { ctx.beginPath(); ctx.moveTo(0, v); ctx.lineTo(3000, v); ctx.stroke(); }
    ctx.fillStyle = css.getPropertyValue('--blue').trim() || '#2f8cff';
    ctx.fillRect(0, 0, 20, 2000);           // côté Y-
    ctx.fillStyle = css.getPropertyValue('--yellow').trim() || '#ffd23f';
    ctx.fillRect(2980, 0, 20, 2000);        // côté Y+
}

function drawRobot(x, y, th, couleur, contour, alpha) {
    const [cx, cy] = px(x, y);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(cx, cy);
    // cap 0 = X+ = vers le bas de la toile ; cap 90 = Y+ = vers la droite
    ctx.rotate(Math.PI / 2 - th * Math.PI / 180);
    ctx.fillStyle = couleur;
    ctx.strokeStyle = contour;
    ctx.lineWidth = 10;
    ctx.beginPath();
    ctx.rect(-ROBOT_DEMI_LARGEUR, -ROBOT_ARRIERE, 2 * ROBOT_DEMI_LARGEUR, ROBOT_AVANT + ROBOT_ARRIERE);
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, ROBOT_AVANT + 60);
    ctx.strokeStyle = '#ff3b3b';
    ctx.lineWidth = 12;
    ctx.stroke();
    ctx.restore();
}

function lastEventBefore(t, kind) {
    let e = null;
    for (const ev of logEvents) {
        if (ev.t > t) break;
        if (ev.k === kind) e = ev;
    }
    return e;
}

function drawMap(idx) {
    const d = logData[idx];
    drawTable();

    // Trajectoire parcourue
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.lineWidth = 6;
    for (let i = 0; i <= idx; i += 2) {
        const [a, b] = px(logData[i].x, logData[i].y);
        if (i === 0) ctx.moveTo(a, b); else ctx.lineTo(a, b);
    }
    ctx.stroke();

    // Dernier chemin planifié et dernière cible
    const plan = lastEventBefore(d.t, 'plan');
    if (plan && plan.points && plan.points.length > 1) {
        ctx.beginPath();
        ctx.setLineDash([30, 20]);
        ctx.strokeStyle = '#00e5ff';
        ctx.lineWidth = 10;
        plan.points.forEach(([x, y], k) => { const [a, b] = px(x, y); if (k) ctx.lineTo(a, b); else ctx.moveTo(a, b); });
        ctx.stroke();
        ctx.setLineDash([]);
    }
    const cible = lastEventBefore(d.t, 'goto');
    if (cible) {
        const [a, b] = px(cible.x, cible.y);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 8;
        ctx.beginPath(); ctx.moveTo(a - 40, b - 40); ctx.lineTo(a + 40, b + 40); ctx.moveTo(a + 40, b - 40); ctx.lineTo(a - 40, b + 40); ctx.stroke();
    }

    // Points LiDAR (dernière trame qui en a)
    let lid = null;
    for (let i = idx; i >= 0 && i > idx - 4; i--) if (logData[i].lidar) { lid = logData[i].lidar; break; }
    if (lid) {
        ctx.fillStyle = '#ff5252';
        lid.forEach(([x, y]) => { const [a, b] = px(x, y); ctx.fillRect(a - 12, b - 12, 24, 24); });
    }

    // Adversaires
    (d.adv || []).forEach(([x, y]) => {
        const [a, b] = px(x, y);
        ctx.beginPath();
        ctx.arc(a, b, 200, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(255, 59, 59, 0.45)';
        ctx.fill();
        ctx.strokeStyle = '#ff3b3b';
        ctx.lineWidth = 8;
        ctx.stroke();
    });

    // Pose caméra zénithale (fantôme) puis pose du robot (fusion), contour = état d'évitement
    if (d.cam) drawRobot(d.cam[0], d.cam[1], d.cam[2], 'rgba(255,255,255,0.15)', '#ffffff', 0.7);
    drawRobot(d.x, d.y, d.th, '#ffd23f', OBS_COULEURS[d.obs || 0] || '#ffffff', 1.0);
}

// --- Événements ----------------------------------------------------------------------------
function eventText(e) {
    const r = (v) => Math.round(v);
    switch (e.k) {
        case 'goto': return `GoTo (${r(e.x)}, ${r(e.y)}, ${e.theta}°)`;
        case 'goto_annule': return `GoTo annulé (obstacle)`;
        case 'plan': return `Chemin : ${e.points.length - 1} segment(s)`;
        case 'aller_echec': return `Aucun chemin vers (${r(e.x)}, ${r(e.y)})`;
        case 'retour': return `Retour fin de match (${e.restant} s restantes)`;
        case 'action_sautee': return `Action de ${e.duree} s sautée (${e.restant} s restantes)`;
        case 'tag': return `Tag ${e.id} : latéral ${e.y} mm, angle ${e.angle}°`;
        case 'tag_non_vu': return `Tag non vu`;
        default: return e.k + ' ' + JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !['type', 't', 'k'].includes(k))));
    }
}

function renderEvents() {
    const box = document.getElementById('events-list');
    if (!box) return;
    if (!logEvents.length) {
        box.innerHTML = '<div class="hint">Pas d\'événements (ancien journal ?)</div>';
        return;
    }
    box.innerHTML = logEvents.map((e, k) =>
        `<div class="replay-event" data-k="${k}" onclick="seekTime(${e.t})"><span class="mono">${e.t.toFixed(1)}s</span> ${esc(eventText(e))}</div>`
    ).join('');
}

function highlightEvents(t) {
    const box = document.getElementById('events-list');
    if (!box || !logEvents.length) return;
    let cur = -1;
    logEvents.forEach((e, k) => { if (e.t <= t) cur = k; });
    box.querySelectorAll('.replay-event').forEach(el => el.classList.toggle('current', parseInt(el.dataset.k) === cur));
    const el = box.querySelector('.replay-event.current');
    if (el && isPlaying) el.scrollIntoView({ block: 'nearest' });
}

function seekTime(t) {
    let k = logData.findIndex(d => d.t >= t);
    if (k < 0) k = logData.length - 1;
    playbackIndex = k;
    slider.value = k;
    updateFrame(k);
}

// --- Graphes -----------------------------------------------------------------------------
function setupCharts() {
    // Textes et grilles des graphes aux couleurs du thème (lisibles sur fond sombre comme sur win95)
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.color = css.getPropertyValue('--text-muted').trim() || Chart.defaults.color;
    Chart.defaults.borderColor = css.getPropertyValue('--border').trim() || Chart.defaults.borderColor;

    vChart = new Chart(document.getElementById('chart-voltage'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Tension (V)', data: [], borderColor: '#4CAF50', pointRadius: 0 }] },
        options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });

    cChart = new Chart(document.getElementById('chart-current'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Courant (A)', data: [], borderColor: '#FF9800', pointRadius: 0 }] },
        options: { responsive: true, animation: false, scales: { x: { display: false } } }
    });
}

function updateChartsTotal() {
    const labels = logData.map(d => d.t);
    vChart.data.labels = labels;
    vChart.data.datasets[0].data = logData.map(d => d.v);
    vChart.update();
    cChart.data.labels = labels;
    cChart.data.datasets[0].data = logData.map(d => d.i);
    cChart.update();
}
