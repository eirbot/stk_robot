// map.js — Carte Temps Réel
// Repère Table : X vers le bas, Y vers la gauche (physique)
// Vue écran (face à face) : Y+ physique (gauche robot) → DROITE écran

const TABLE_W_MM = 3000; // Dimension Y (horizontal sur écran)
const TABLE_H_MM = 2000; // Dimension X (vertical sur écran)

let ctxMap = null;
let imgTable = new Image();
let imgRobot = new Image();

let robotPos = { x: 0, y: 0, theta: 0 };  // Coordonnées ESP32
let lidarPos = null;                         // Coordonnées LiDAR calculées
let beacons = [];                           // Positions des balises

// --- État clic/drag pour GoTo ---
let mouseDown = false;
let clickWorld = null;   // Point cliqué (world)
let dragTheta = null;   // Angle calculé par le drag

// -----------------------------------------------
// INIT
// -----------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    console.log("[MAP] Initialisation...");
    initMapPage();
    loadBeacons();
});

function initMapPage() {
    const canvas = document.getElementById('mapCanvas');
    if (!canvas) return;
    ctxMap = canvas.getContext('2d');

    imgTable.src = '/static/img/table_coupe_2026.png';
    imgRobot.src = '/static/img/robot.png';
    imgTable.onload = () => { console.log("[MAP] Image Table chargée"); drawMap(); };
    imgRobot.onload = () => { drawMap(); };

    window.socket.emit('map_connect');

    // --- Interactions Goto ---
    canvas.addEventListener('mousedown', onMapMouseDown);
    canvas.addEventListener('mousemove', onMapMouseMove);
    canvas.addEventListener('mouseup', onMapMouseUp);
    canvas.addEventListener('mouseleave', onMapMouseLeave);
    canvas.addEventListener('contextmenu', e => e.preventDefault());

    // Curseur
    canvas.style.cursor = 'crosshair';
}

// -----------------------------------------------
// CONVERSION Monde <-> Écran
// Vue face-à-face : Y+ (gauche physique) → droite écran
// -----------------------------------------------
function getScales() {
    const canvas = document.getElementById('mapCanvas');
    return {
        scaleY: canvas.width / TABLE_W_MM,
        scaleX: canvas.height / TABLE_H_MM,
        w: canvas.width,
        h: canvas.height
    };
}

function worldToScreen(wx, wy) {
    const { scaleX, scaleY, w } = getScales();
    return {
        px: (w / 2) + (wy * scaleY),   // Y+ → droite écran
        py: wx * scaleX                 // X+ → bas écran
    };
}

function screenToWorld(sx, sy) {
    const { scaleX, scaleY, w } = getScales();
    return {
        x: sy / scaleX,
        y: (sx - w / 2) / scaleY
    };
}

function getCanvasPos(canvas, e) {
    const rect = canvas.getBoundingClientRect();
    return {
        sx: (e.clientX - rect.left) * (canvas.width / rect.width),
        sy: (e.clientY - rect.top) * (canvas.height / rect.height)
    };
}

// -----------------------------------------------
// INTERACTIONS GOTO (Clic = X,Y ; Drag = Theta)
// -----------------------------------------------
function onMapMouseDown(e) {
    if (e.button !== 0) return;
    mouseDown = true;
    const { sx, sy } = getCanvasPos(e.target, e);
    clickWorld = screenToWorld(sx, sy);
    dragTheta = robotPos.theta; // Angle par défaut = angle actuel
    drawMap();
}

function onMapMouseMove(e) {
    if (!mouseDown || !clickWorld) return;
    const { sx, sy } = getCanvasPos(e.target, e);
    const cur = screenToWorld(sx, sy);

    // Vecteur de drag depuis le point cliqué
    const { scaleX, scaleY, w } = getScales();
    const clickScreen = worldToScreen(clickWorld.x, clickWorld.y);
    const dsx = sx - clickScreen.px;
    const dsy = sy - clickScreen.py;
    const dist = Math.sqrt(dsx * dsx + dsy * dsy);

    if (dist > 20) { // Seuil de drag minimal (pixels)
        // Convertir direction écran → angle monde (trigo)
        // Drag droit (dsx>0) → Y+ → theta=90°
        // Drag bas   (dsy>0) → X+ → theta=0°
        dragTheta = Math.atan2(dsx / scaleY, dsy / scaleX) * 180 / Math.PI;
    }
    drawMap();
}

function onMapMouseUp(e) {
    if (!mouseDown || !clickWorld) return;
    mouseDown = false;
    const theta = dragTheta !== null ? dragTheta : robotPos.theta;
    sendGoto(clickWorld.x, clickWorld.y, theta);
    clickWorld = null;
    dragTheta = null;
    drawMap();
}

function onMapMouseLeave() {
    if (mouseDown) {
        mouseDown = false;
        clickWorld = null;
        dragTheta = null;
        drawMap();
    }
}

async function sendGoto(x, y, theta) {
    console.log(`[MAP] GOTO -> X=${x.toFixed(0)} Y=${y.toFixed(0)} θ=${theta.toFixed(1)}°`);
    await fetch('/api/goto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y, theta })
    });
}

// -----------------------------------------------
// CHARGEMENT DES BALISES
// -----------------------------------------------
async function loadBeacons() {
    try {
        const resp = await fetch('/api/beacons');
        beacons = await resp.json();
        console.log("[MAP] Balises chargées:", beacons);
        drawMap();
    } catch (e) { console.warn('[MAP] Impossible de charger les balises', e); }
}

// -----------------------------------------------
// SOCKETS
// -----------------------------------------------
window.socket.on('robot_position', (pos) => {
    robotPos = pos;
    updateInfoPanel();
    drawMap();
});

window.socket.on('lidar_pos', (pos) => {
    console.log("[MAP] Reçu LiDAR Pos:", pos);
    lidarPos = pos;
    updateInfoPanel();
    drawMap();
});

function updateInfoPanel() {
    const el = document.getElementById('pos-text');
    if (!el) return;
    let txt = `ESP32 | X:${robotPos.x.toFixed(0)} Y:${robotPos.y.toFixed(0)} θ:${robotPos.theta.toFixed(1)}°`;
    if (lidarPos) {
        txt += `  ·  LiDAR | X:${lidarPos.x.toFixed(0)} Y:${lidarPos.y.toFixed(0)} θ:${lidarPos.theta.toFixed(1)}° (Δ${lidarPos.err.toFixed(0)}mm)`;
    }
    el.innerText = txt;
}

// -----------------------------------------------
// DESSIN
// -----------------------------------------------
function drawArrow(ctx, px, py, theta_deg, length, color) {
    const { scaleX, scaleY } = getScales();
    const rad = theta_deg * Math.PI / 180;
    // Direction monde → écran : sin(theta) → dx_screen, cos(theta) → dy_screen
    const dx = Math.sin(rad) * length;
    const dy = Math.cos(rad) * length;

    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px + dx, py + dy);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Tête de flèche
    const angle = Math.atan2(dy, dx);
    const arrowSize = 8;
    ctx.beginPath();
    ctx.moveTo(px + dx, py + dy);
    ctx.lineTo(px + dx - arrowSize * Math.cos(angle - 0.4), py + dy - arrowSize * Math.sin(angle - 0.4));
    ctx.lineTo(px + dx - arrowSize * Math.cos(angle + 0.4), py + dy - arrowSize * Math.sin(angle + 0.4));
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
}

function drawMap() {
    if (!ctxMap) return;
    const canvas = document.getElementById('mapCanvas');
    const { w, h, scaleY } = getScales();

    ctxMap.clearRect(0, 0, w, h);

    // Fond / image table
    if (imgTable.complete && imgTable.naturalWidth > 0) {
        ctxMap.drawImage(imgTable, 0, 0, w, h);
    } else {
        ctxMap.fillStyle = '#1a2332';
        ctxMap.fillRect(0, 0, w, h);
    }

    // --- Balises ---
    for (const [bx, by] of beacons) {
        const { px, py } = worldToScreen(bx, by);
        ctxMap.beginPath();
        ctxMap.arc(px, py, 8, 0, 2 * Math.PI);
        ctxMap.fillStyle = 'rgba(255, 200, 0, 0.85)';
        ctxMap.fill();
        ctxMap.strokeStyle = '#fff';
        ctxMap.lineWidth = 1.5;
        ctxMap.stroke();
        ctxMap.fillStyle = '#ffe';
        ctxMap.font = 'bold 11px monospace';
        ctxMap.fillText(`(${bx},${by})`, px + 10, py + 4);
    }

    // --- Position LiDAR (cercle vert) ---
    if (lidarPos) {
        const { px, py } = worldToScreen(lidarPos.x, lidarPos.y);
        ctxMap.beginPath();
        ctxMap.arc(px, py, 14, 0, 2 * Math.PI);
        ctxMap.fillStyle = 'rgba(0, 255, 100, 0.25)';
        ctxMap.fill();
        ctxMap.strokeStyle = '#00e676';
        ctxMap.lineWidth = 2;
        ctxMap.stroke();
        drawArrow(ctxMap, px, py, lidarPos.theta, 35, '#00e676');
    }

    // --- Cible GoTo (pendant le drag) ---
    if (clickWorld) {
        const { px, py } = worldToScreen(clickWorld.x, clickWorld.y);
        ctxMap.beginPath();
        ctxMap.arc(px, py, 10, 0, 2 * Math.PI);
        ctxMap.fillStyle = 'rgba(255, 100, 0, 0.6)';
        ctxMap.fill();
        ctxMap.strokeStyle = 'orange';
        ctxMap.lineWidth = 2;
        ctxMap.stroke();
        if (dragTheta !== null) {
            drawArrow(ctxMap, px, py, dragTheta, 45, 'orange');
        }
    }

    // --- Robot (image) ---
    if (imgRobot.complete && imgRobot.naturalWidth > 0) {
        const { px, py } = worldToScreen(robotPos.x, robotPos.y);
        const size = 370 * scaleY;

        ctxMap.save();
        ctxMap.translate(px, py);
        // robot.png pointe vers le BAS (X+). theta=0 -> rotation 0.
        // Comme on est en vue directe canvas, pour une rotation trigo CCW, on utilise -theta.
        ctxMap.rotate(-robotPos.theta * Math.PI / 180);
        ctxMap.drawImage(imgRobot, -size / 2, -size / 2, size, size);
        ctxMap.restore();
    }
}
