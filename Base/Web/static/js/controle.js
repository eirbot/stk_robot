// =======================================================
// EIRBOT 2026 - CONTROLE JOYSTICK SCRIPT
// =======================================================

let linearMax = 500;   // mm/s
let angularMax = 90;   // deg/s
let invertY = false;

let currentVx = 0.0;
let currentVtheta = 0.0;

let isDragging = false;
let joystickCenter = { x: 0, y: 0 };
let maxRadius = 90;

const ecartRoues = 345.0; // mm

// État du clavier
const keysDown = {
    up: false,
    down: false,
    left: false,
    right: false
};

// Variable pour gérer l'envoi périodique (20 Hz = 50 ms)
let sendInterval = null;
let lastSentVx = null;
let lastSentVtheta = null;
let zeroSendCount = 0;

document.addEventListener('DOMContentLoaded', () => {
    initJoystick();
    initKeyboard();
    initWebSocketEvents();
    initSettings();

    // Démarrage de la boucle de transmission à 20 Hz (50 ms)
    sendInterval = setInterval(tickTransmission, 50);
});

// =======================================================
// 1. INITIALISATION JOYSTICK TACTILE / SOURIS
// =======================================================
function initJoystick() {
    const zone = document.getElementById('joystick-zone');
    const knob = document.getElementById('joystick-knob');
    if (!zone || !knob) return;

    function updateMaxRadius() {
        const zoneRect = zone.getBoundingClientRect();
        const knobRect = knob.getBoundingClientRect();
        maxRadius = (zoneRect.width - knobRect.width) / 2;
    }
    updateMaxRadius();
    window.addEventListener('resize', updateMaxRadius);

    zone.addEventListener('pointerdown', (e) => {
        isDragging = true;
        zone.setPointerCapture(e.pointerId);
        updateMaxRadius();

        const rect = zone.getBoundingClientRect();
        joystickCenter = {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };

        handlePointerMove(e);
    });

    zone.addEventListener('pointermove', (e) => {
        if (!isDragging) return;
        handlePointerMove(e);
    });

    function onPointerUp(e) {
        if (!isDragging) return;
        isDragging = false;
        try {
            zone.releasePointerCapture(e.pointerId);
        } catch (err) { }

        // Retour élastique au centre
        knob.style.transform = 'translate(0px, 0px)';
        currentVx = 0.0;
        currentVtheta = 0.0;
        updateGauges(0, 0);
        sendCmdVel(0, 0);
    }

    zone.addEventListener('pointerup', onPointerUp);
    zone.addEventListener('pointercancel', onPointerUp);
}

function handlePointerMove(e) {
    const knob = document.getElementById('joystick-knob');
    if (!knob) return;

    let dx = e.clientX - joystickCenter.x;
    let dy = e.clientY - joystickCenter.y;

    const distance = Math.hypot(dx, dy);
    if (distance > maxRadius) {
        dx = (dx / distance) * maxRadius;
        dy = (dy / distance) * maxRadius;
    }

    knob.style.transform = `translate(${dx}px, ${dy}px)`;

    // Normalisation [-1.0, 1.0]
    let normX = dx / maxRadius;
    let normY = -dy / maxRadius; // Vers le haut = positif (avancer)

    // Zone morte de 5%
    const normDist = Math.hypot(normX, normY);
    if (normDist < 0.05) {
        normX = 0;
        normY = 0;
    }

    if (invertY) {
        normY = -normY;
    }

    // Calcul des consignes physiques
    // normY > 0 -> avancer (Vx > 0)
    // normX > 0 (droite) -> tourner vers la droite (Vtheta négatif CW)
    // normX < 0 (gauche) -> tourner vers la gauche (Vtheta positif CCW)
    currentVx = Math.round(normY * linearMax);
    currentVtheta = Math.round(-normX * angularMax);

    updateGauges(currentVx, currentVtheta);
}

// =======================================================
// 2. CONTRÔLE AU CLAVIER (ZQSD & FLÈCHES)
// =======================================================
function initKeyboard() {
    window.addEventListener('keydown', (e) => {
        // Ignorer si l'utilisateur est dans un champ texte
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

        let handled = false;
        switch (e.key) {
            case 'z': case 'Z': case 'ArrowUp':
                keysDown.up = true;
                setKeyVisual('key-up', true);
                handled = true;
                break;
            case 's': case 'S': case 'ArrowDown':
                keysDown.down = true;
                setKeyVisual('key-down', true);
                handled = true;
                break;
            case 'q': case 'Q': case 'ArrowLeft':
                keysDown.left = true;
                setKeyVisual('key-left', true);
                handled = true;
                break;
            case 'd': case 'D': case 'ArrowRight':
                keysDown.right = true;
                setKeyVisual('key-right', true);
                handled = true;
                break;
            case ' ':
                triggerEmergencyStop();
                handled = true;
                break;
        }

        if (handled) {
            e.preventDefault();
            evaluateKeyboardMovement();
        }
    });

    window.addEventListener('keyup', (e) => {
        let handled = false;
        switch (e.key) {
            case 'z': case 'Z': case 'ArrowUp':
                keysDown.up = false;
                setKeyVisual('key-up', false);
                handled = true;
                break;
            case 's': case 'S': case 'ArrowDown':
                keysDown.down = false;
                setKeyVisual('key-down', false);
                handled = true;
                break;
            case 'q': case 'Q': case 'ArrowLeft':
                keysDown.left = false;
                setKeyVisual('key-left', false);
                handled = true;
                break;
            case 'd': case 'D': case 'ArrowRight':
                keysDown.right = false;
                setKeyVisual('key-right', false);
                handled = true;
                break;
        }

        if (handled) {
            e.preventDefault();
            evaluateKeyboardMovement();
        }
    });
}

function setKeyVisual(id, active) {
    const el = document.getElementById(id);
    if (!el) return;
    if (active) el.classList.add('active');
    else el.classList.remove('active');
}

function evaluateKeyboardMovement() {
    if (isDragging) return; // Priorité au toucher si en cours

    let normY = 0;
    let normX = 0;

    if (keysDown.up) normY += 1;
    if (keysDown.down) normY -= 1;
    if (keysDown.left) normX -= 1;
    if (keysDown.right) normX += 1;

    if (invertY) normY = -normY;

    currentVx = Math.round(normY * linearMax);
    currentVtheta = Math.round(-normX * angularMax);

    // Mettre à jour visuellement le stick
    const knob = document.getElementById('joystick-knob');
    if (knob) {
        const visualX = normX * maxRadius * 0.75;
        const visualY = -normY * maxRadius * 0.75;
        knob.style.transform = `translate(${visualX}px, ${visualY}px)`;
    }

    updateGauges(currentVx, currentVtheta);
}

// =======================================================
// 3. ENVOI DES COMMANDES (CADENCE 20 HZ)
// =======================================================
function tickTransmission() {
    // Si la vitesse est non nulle, ou si on a besoin d'envoyer les paquets d'arrêt
    if (currentVx !== 0 || currentVtheta !== 0) {
        sendCmdVel(currentVx, currentVtheta);
        zeroSendCount = 0;
    } else if (zeroSendCount < 3) {
        // Envoie au moins 3 trames à 0 pour être sûr de l'arrêt
        sendCmdVel(0, 0);
        zeroSendCount++;
    }
}

function sendCmdVel(vx, vtheta) {
    lastSentVx = vx;
    lastSentVtheta = vtheta;

    const payload = { vx: vx, vtheta: vtheta };

    // Envoi prioritaire via WebSocket
    if (window.socket && window.socket.ws && window.socket.ws.readyState === WebSocket.OPEN) {
        window.socket.emit('cmd_vel', payload);
    } else {
        // Fallback API REST
        fetch('/api/cmd_vel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).catch(() => { });
    }
}

function triggerEmergencyStop() {
    console.warn("🛑 ARRÊT D'URGENCE MANUEL DÉCLENCHÉ");
    currentVx = 0;
    currentVtheta = 0;
    updateGauges(0, 0);

    const knob = document.getElementById('joystick-knob');
    if (knob) knob.style.transform = 'translate(0px, 0px)';

    // Envoi immédiat arrêt vitesse
    sendCmdVel(0, 0);
    // Envoi action arrêt d'urgence globale
    sendAction('stop');
}

function sendZeroSpeed() {
    currentVx = 0;
    currentVtheta = 0;
    updateGauges(0, 0);

    const knob = document.getElementById('joystick-knob');
    if (knob) knob.style.transform = 'translate(0px, 0px)';

    sendCmdVel(0, 0);
}

// =======================================================
// 4. JAUGE & AFFICHAGES EN DIRECT
// =======================================================
function updateGauges(vx, vtheta) {
    const elVx = document.getElementById('val-vx');
    const elVtheta = document.getElementById('val-vtheta');
    const barVx = document.getElementById('bar-vx');
    const barVtheta = document.getElementById('bar-vtheta');

    if (elVx) elVx.innerHTML = `${vx} <small>mm/s</small>`;
    if (elVtheta) elVtheta.innerHTML = `${vtheta} <small>°/s</small>`;

    if (barVx) {
        // -linearMax -> 0%, 0 -> 50%, +linearMax -> 100%
        const pct = 50 + (vx / (linearMax || 1)) * 50;
        barVx.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }

    if (barVtheta) {
        const pct = 50 + (vtheta / (angularMax || 1)) * 50;
        barVtheta.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }

    // Vitesses différentielles gauche/droite estimées
    const omega = (vtheta * Math.PI) / 180.0;
    const vl = Math.round(vx + omega * (ecartRoues / 2.0));
    const vr = Math.round(vx - omega * (ecartRoues / 2.0));

    const elVl = document.getElementById('val-vl');
    const elVr = document.getElementById('val-vr');
    if (elVl) elVl.innerText = `${vl} mm/s`;
    if (elVr) elVr.innerText = `${vr} mm/s`;
}

// =======================================================
// 5. RÉGLAGES & PRESETS
// =======================================================
function initSettings() {
    const toggle = document.getElementById('toggle-invert-y');
    if (toggle) {
        toggle.addEventListener('change', (e) => {
            invertY = e.target.checked;
        });
    }
}

function setLinearMax(val) {
    linearMax = parseInt(val, 10);
    const slider = document.getElementById('slider-linear-max');
    if (slider) slider.value = val;
    const badge = document.getElementById('label-linear-max');
    if (badge) badge.innerText = `${val} mm/s`;

    updateActivePresets('slider-linear-max', val);
    updateGauges(currentVx, currentVtheta);
}

function onLinearSliderChange(val) {
    linearMax = parseInt(val, 10);
    const badge = document.getElementById('label-linear-max');
    if (badge) badge.innerText = `${val} mm/s`;
    updateActivePresets('slider-linear-max', val);
    updateGauges(currentVx, currentVtheta);
}

function setAngularMax(val) {
    angularMax = parseInt(val, 10);
    const slider = document.getElementById('slider-angular-max');
    if (slider) slider.value = val;
    const badge = document.getElementById('label-angular-max');
    if (badge) badge.innerText = `${val} °/s`;

    updateActivePresets('slider-angular-max', val);
    updateGauges(currentVx, currentVtheta);
}

function onAngularSliderChange(val) {
    angularMax = parseInt(val, 10);
    const badge = document.getElementById('label-angular-max');
    if (badge) badge.innerText = `${val} °/s`;
    updateActivePresets('slider-angular-max', val);
    updateGauges(currentVx, currentVtheta);
}

function updateActivePresets(sliderId, val) {
    const parent = document.getElementById(sliderId)?.closest('.setting-group');
    if (!parent) return;
    const buttons = parent.querySelectorAll('.btn-preset');
    buttons.forEach(btn => {
        if (btn.innerText.includes(val.toString())) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

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
                connBadge.innerText = "CONNECTÉ (20Hz)";
                connBadge.className = "badge-conn connected";
            }
        } else {
            if (connBadge) {
                connBadge.innerText = "DÉCONNECTÉ";
                connBadge.className = "badge-conn disconnected";
            }
        }
    }, 1000);

    // Mise à jour de la position
    window.socket.on('robot_position', (pos) => {
        if (!pos) return;
        const elX = document.getElementById('pos-x');
        const elY = document.getElementById('pos-y');
        const elTheta = document.getElementById('pos-theta');

        if (elX && pos.x !== undefined) elX.innerText = `${pos.x.toFixed(1)} mm`;
        if (elY && pos.y !== undefined) elY.innerText = `${pos.y.toFixed(1)} mm`;
        if (elTheta && pos.theta !== undefined) elTheta.innerText = `${pos.theta.toFixed(1)}°`;
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
                badgeLidar.innerText = "🛑 ARRÊT CRITIQUE";
                badgeLidar.className = "badge-status status-stop";
            } else if (obsType === 2) {
                badgeLidar.innerText = "⚠️ OBSTACLE AVANT";
                badgeLidar.className = "badge-status status-alert";
            } else if (obsType === 3) {
                badgeLidar.innerText = "⚠️ OBSTACLE ARRIÈRE";
                badgeLidar.className = "badge-status status-alert";
            } else if (obsDet) {
                badgeLidar.innerText = "⚠️ ATTENTION";
                badgeLidar.className = "badge-status status-alert";
            } else {
                badgeLidar.innerText = "LIBRE";
                badgeLidar.className = "badge-status status-free";
            }
        }

        // Équipe
        if (state.team) {
            document.body.className = `mode-${state.team}`;
        }
    });
}
