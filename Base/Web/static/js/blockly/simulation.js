// Strat Studio : moteur de dessin de la simulation (canvas, table, robot, trajets).
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 2. MOTEUR GRAPHIQUE (CANVAS)
// ============================================================

const canvas = document.getElementById('simCanvas');
const ctx = canvas.getContext('2d');
const imgTable = document.getElementById('imgTable');
const consoleDiv = document.getElementById('simConsole');

// Création de l'infobulle (Tooltip) pour la souris
const coordTooltip = document.createElement('div');
coordTooltip.style.position = 'absolute';
coordTooltip.style.background = 'var(--chip-bg)';
coordTooltip.style.color = 'var(--text)';
coordTooltip.style.border = '2px solid var(--line)';
coordTooltip.style.padding = '4px 8px';
coordTooltip.style.borderRadius = 'var(--radius-sm)';
coordTooltip.style.pointerEvents = 'none'; // Click-through
coordTooltip.style.display = 'none';
coordTooltip.style.fontSize = '12px';
coordTooltip.style.fontFamily = 'var(--font-mono)';
coordTooltip.style.zIndex = '1000';
document.body.appendChild(coordTooltip);

// État du Robot
let robot = {
    x: DEFAULT_START_X,
    y: DEFAULT_START_Y,
    theta: DEFAULT_START_THETA,
    currentIcon: null,
    bezier: null,
    isMoving: false
};

let actionQueue = [];
let previewPath = [];

// --- FONCTIONS DE CONVERSION ---

// Convertit Millimètres vers Pixels Écran (Nouveau Repère)
function worldToScreen(x_mm, y_mm) {
    const scaleX = canvas.width / TABLE_WIDTH; // 3000 -> correspond à Y
    const scaleY = canvas.height / TABLE_HEIGHT; // 2000 -> correspond à X
    return {
        x: (canvas.width / 2) + (y_mm * scaleX),
        y: x_mm * scaleY
    };
}

// Convertit Pixels Écran vers Millimètres (Pour la souris)
function screenToWorld(px, py) {
    const scaleX = canvas.width / TABLE_WIDTH;
    const scaleY = canvas.height / TABLE_HEIGHT;
    return {
        x: Math.round(py / scaleY),
        y: Math.round((px - (canvas.width / 2)) / scaleX)
    };
}

// Calcul Point Segment (t entre 0 et 1)
function getSegmentPoint(t, p0, p3) {
    return {
        x: p0.x + t * (p3.x - p0.x),
        y: p0.y + t * (p3.y - p0.y)
    };
}

// Vérifie si un point est hors de la table
function isOutOfBounds(p) {
    // X : 0 à 2000, Y : -1500 à 1500
    return p.x < 0 || p.x > TABLE_HEIGHT || p.y < -1500 || p.y > 1500;
}

// --- ERREURS & BLOCKLY ---
function clearBlockWarnings() {
    workspace.getAllBlocks().forEach(b => b.setWarningText(null));
    workspace.highlightBlock(null);
    canvas.classList.remove("collision-alert");
}

function markBlockError(blockId, msg) {
    if (!blockId) return;
    let block = workspace.getBlockById(blockId);
    if (block) block.setWarningText(msg);
    canvas.classList.add("collision-alert");
}

// --- FONCTIONS DE DESSIN ---

function drawGrid() {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.15)"; // Gris foncé transparent
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";    // Texte gris foncé
    ctx.lineWidth = 1;
    ctx.font = "10px Arial";
    ctx.textAlign = "center";

    // Lignes pour Y (gauche à droite)
    for (let y = -1500; y <= 1500; y += GRID_STEP) {
        let p = worldToScreen(0, y);
        ctx.beginPath(); ctx.moveTo(p.x, 0); ctx.lineTo(p.x, canvas.height); ctx.stroke();
        if (y % 500 === 0) ctx.fillText(y, p.x, 10);
    }
    // Lignes pour X (haut en bas)
    ctx.textAlign = "left";
    for (let x = 0; x <= 2000; x += GRID_STEP) {
        let p = worldToScreen(x, 0);
        ctx.beginPath(); ctx.moveTo(0, p.y); ctx.lineTo(canvas.width, p.y); ctx.stroke();
        if (x % 500 === 0 && x > 0) ctx.fillText(x, 5, p.y - 2);
    }
}

function drawStraightPath(bz, color, width, showFootprint = false) {
    let p0_scr = worldToScreen(bz.p0.x, bz.p0.y);
    let p3_scr = worldToScreen(bz.p3.x, bz.p3.y);

    ctx.beginPath();
    ctx.moveTo(p0_scr.x, p0_scr.y);
    ctx.lineTo(p3_scr.x, p3_scr.y);
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();

    if (showFootprint) {
        // --- TRACÉ DE L'ENCOMBREMENT (TUNNEL) ---
        let dx = bz.p3.x - bz.p0.x;
        let dy = bz.p3.y - bz.p0.y;
        let dist = Math.sqrt(dx * dx + dy * dy);

        if (dist > 0) {
            let nx = dx / dist;
            let ny = dy / dist;
            let offsetX = -ny * ROBOT.HALF_WIDTH_MM;
            let offsetY = nx * ROBOT.HALF_WIDTH_MM;

            // Points des bords
            let p0L = worldToScreen(bz.p0.x + offsetX, bz.p0.y + offsetY);
            let p0R = worldToScreen(bz.p0.x - offsetX, bz.p0.y - offsetY);
            let p3L = worldToScreen(bz.p3.x + offsetX, bz.p3.y + offsetY);
            let p3R = worldToScreen(bz.p3.x - offsetX, bz.p3.y - offsetY);

            ctx.beginPath();
            ctx.moveTo(p0L.x, p0L.y); ctx.lineTo(p3L.x, p3L.y);
            ctx.moveTo(p0R.x, p0R.y); ctx.lineTo(p3R.x, p3R.y);
            ctx.strokeStyle = "rgba(255, 0, 0, 0.4)";
            ctx.setLineDash([5, 5]); // Lignes pointillées pour le tunnel
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.setLineDash([]); // Reset

            // Remplissage léger du tunnel
            ctx.beginPath();
            ctx.moveTo(p0L.x, p0L.y); ctx.lineTo(p3L.x, p3L.y);
            ctx.lineTo(p3R.x, p3R.y); ctx.lineTo(p0R.x, p0R.y);
            ctx.closePath();
            ctx.fillStyle = "rgba(255, 0, 0, 0.1)";
            ctx.fill();
        }
    }
}

// Polygone en coordonnées table (mm) -> tracé à l'écran
function tracePolygon(points) {
    ctx.beginPath();
    points.forEach((p, i) => {
        const sp = worldToScreen(p.x, p.y);
        if (i === 0) ctx.moveTo(sp.x, sp.y); else ctx.lineTo(sp.x, sp.y);
    });
    ctx.closePath();
}

// Point du repère robot (fx vers l'avant, fy vers la gauche) -> repère table
function robotPoint(fx, fy) {
    const t = robot.theta * Math.PI / 180, c = Math.cos(t), s = Math.sin(t);
    return { x: robot.x + fx * c - fy * s, y: robot.y + fx * s + fy * c };
}

// Robot à l'échelle : encombrement réel (l'axe des roues n'est pas au centre), roues, flèche avant
// Vue de dessus du vrai robot (modèle MuJoCo, tools/rendu_robot_dessus.py) : cadrée sur son encombrement,
// avant vers la droite de l'image, gauche du robot vers le haut
const robotImage = new Image();
robotImage.src = '/static/img/robot_dessus.png?v=1';

// Image posée sur l'encombrement : les coins haut-gauche, haut-droit et bas-gauche de l'image vont sur
// l'arrière gauche, l'avant gauche et l'arrière droit du robot (transformation affine)
function drawRobotImage() {
    const p0 = robotPoint(-ROBOT.BACK_MM, ROBOT.HALF_WIDTH_MM);
    const p1 = robotPoint(ROBOT.FRONT_MM, ROBOT.HALF_WIDTH_MM);
    const p2 = robotPoint(-ROBOT.BACK_MM, -ROBOT.HALF_WIDTH_MM);
    const s0 = worldToScreen(p0.x, p0.y), s1 = worldToScreen(p1.x, p1.y), s2 = worldToScreen(p2.x, p2.y);
    const w = robotImage.naturalWidth, h = robotImage.naturalHeight;
    ctx.save();
    ctx.transform((s1.x - s0.x) / w, (s1.y - s0.y) / w, (s2.x - s0.x) / h, (s2.y - s0.y) / h, s0.x, s0.y);
    ctx.drawImage(robotImage, 0, 0);
    ctx.restore();
}

// Robot à l'échelle : vue de dessus du robot (ou, en attendant l'image, encombrement + roues),
// contour de l'encombrement (l'axe des roues n'est pas au centre) et flèche avant
function drawRobot() {
    const corners = EirbotFrames.robotCorners(robot.x, robot.y, robot.theta);
    if (robotImage.complete && robotImage.naturalWidth > 0) {
        drawRobotImage();
    } else {
        tracePolygon(corners);
        ctx.fillStyle = "rgba(0, 123, 255, 0.55)";
        ctx.fill();
        ctx.fillStyle = "#111";
        for (const side of [1, -1]) {
            tracePolygon([robotPoint(WHEEL_R_MM, side * (WHEEL_Y_MM + 12)), robotPoint(WHEEL_R_MM, side * (WHEEL_Y_MM - 12)),
                          robotPoint(-WHEEL_R_MM, side * (WHEEL_Y_MM - 12)), robotPoint(-WHEEL_R_MM, side * (WHEEL_Y_MM + 12))]);
            ctx.fill();
        }
    }
    tracePolygon(corners);
    ctx.strokeStyle = "#007bff";
    ctx.lineWidth = 2;
    ctx.stroke();

    tracePolygon([robotPoint(ROBOT.FRONT_MM + 40, 0), robotPoint(ROBOT.FRONT_MM - 30, 55), robotPoint(ROBOT.FRONT_MM - 30, -55)]);
    ctx.fillStyle = "#ff3333";
    ctx.fill();
}

// BOUCLE DE RENDU PRINCIPALE
function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Fond de Table
    if (imgTable.complete && imgTable.naturalHeight !== 0) ctx.drawImage(imgTable, 0, 0, canvas.width, canvas.height);
    else { ctx.fillStyle = "#2e8b57"; ctx.fillRect(0, 0, canvas.width, canvas.height); }

    // 2. Grille
    drawGrid();

    // 3. Prévisualisation (Trait Cyan ou Orange si erreur)
    if (previewPath.length > 0) {
        previewPath.forEach(bz => {
            let mid = getSegmentPoint(0.5, bz.p0, bz.p3);
            if (isOutOfBounds(bz.p3) || isOutOfBounds(mid)) {
                drawStraightPath(bz, "rgba(255, 140, 0, 0.8)", 3, true); // Orange Alerte
            } else {
                drawStraightPath(bz, "rgba(0, 255, 255, 0.6)", 2, true); // Cyan OK
            }
        });
    }

    // 4. Mouvement Actif (Trait Rouge)
    if (robot.isMoving && robot.bezier) {
        robot.bezier.t += 0.02; // Vitesse animation

        if (robot.bezier.t >= 1) {
            // Fin du segment
            robot.x = robot.bezier.p3.x;
            robot.y = robot.bezier.p3.y;
            // On garde l'angle actuel (sera mis à jour par la rotation finale si besoin)
            robot.isMoving = false;
            processNextAction();
        } else {
            // Calcul position courante
            let pos = getSegmentPoint(robot.bezier.t, robot.bezier.p0, robot.bezier.p3);

            // Calcul orientation (Tangente)
            let dx = robot.bezier.p3.x - robot.bezier.p0.x;
            let dy = robot.bezier.p3.y - robot.bezier.p0.y;

            if (dx !== 0 || dy !== 0) {
                let moveAngle = Math.atan2(dy, dx) * (180 / Math.PI);

                // --- GESTION MARCHE ARRIERE ---
                // Si l'angle de mouvement est opposé à l'orientation actuelle (>90°), on ne change pas robot.theta
                // Le robot recule.
                let diff = Math.abs(((moveAngle - robot.theta + 180 + 360) % 360) - 180);
                if (diff < 90) {
                    robot.theta = moveAngle;
                }
            }

            robot.x = pos.x;
            robot.y = pos.y;
            drawStraightPath(robot.bezier, "rgba(255, 0, 0, 0.8)", 4);
        }
    }

    // 4.5 Rotation Active
    if (robot.isRotating && robot.rotateTarget !== undefined) {
        let diff = ((robot.rotateTarget - robot.theta + 180 + 360) % 360) - 180;
        if (Math.abs(diff) < 2) {
            robot.theta = robot.rotateTarget;
            robot.isRotating = false;
            processNextAction();
        } else {
            robot.theta += (diff > 0 ? 2 : -2); // 2 degrés par frame
        }
    }

    // 5. Robot
    let screenPos = worldToScreen(robot.x, robot.y);
    const robotSizePx = (2 * ROBOT.HALF_WIDTH_MM / TABLE_WIDTH) * canvas.width;
    drawRobot();

    // 6. Icone Action
    if (robot.currentIcon) {
        // Étiquette texte contourée (lisible sur la table)
        ctx.font = "bold 16px Arial"; ctx.textAlign = "center";
        ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.fillStyle = "#fff";
        ctx.strokeText(robot.currentIcon, screenPos.x, screenPos.y - robotSizePx / 2 - 10);
        ctx.fillText(robot.currentIcon, screenPos.x, screenPos.y - robotSizePx / 2 - 10);
    }

    requestAnimationFrame(draw);
}
