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

// État de ciblage : 'robot', 'arm_1', 'arm_2', 'arm_3', 'arm_4'
let currentTarget = 'robot';
const armHeights = { 1: 0, 2: 0, 3: 0, 4: 0 };
let lastSentArmHeights = { 1: null, 2: null, 3: null, 4: null };
let armControlDebounceX = false;

// Variable pour gérer l'envoi périodique (20 Hz = 50 ms)
let sendInterval = null;
let lastSentVx = null;
let lastSentVtheta = null;
let zeroSendCount = 0;

document.addEventListener('DOMContentLoaded', () => {
    initJoystick();
    initKeyboard();
    initGamepad();
    initActuators();
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
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
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

        // Raccourcis sélection de cible (1, 2, 3, 4 pour les bras, 0 / Échap pour la base robot)
        if (e.key === '1' || e.key === '&' || e.code === 'Digit1' || e.code === 'Numpad1') {
            setControlTarget(currentTarget === 'arm_1' ? 'robot' : 'arm_1');
            e.preventDefault();
            return;
        } else if (e.key === '2' || e.key === 'é' || e.code === 'Digit2' || e.code === 'Numpad2') {
            setControlTarget(currentTarget === 'arm_2' ? 'robot' : 'arm_2');
            e.preventDefault();
            return;
        } else if (e.key === '3' || e.key === '"' || e.code === 'Digit3' || e.code === 'Numpad3') {
            setControlTarget(currentTarget === 'arm_3' ? 'robot' : 'arm_3');
            e.preventDefault();
            return;
        } else if (e.key === '4' || e.key === "'" || e.code === 'Digit4' || e.code === 'Numpad4') {
            setControlTarget(currentTarget === 'arm_4' ? 'robot' : 'arm_4');
            e.preventDefault();
            return;
        } else if (e.key === '0' || e.key === 'à' || e.code === 'Digit0' || e.code === 'Numpad0' || e.key === 'Escape') {
            setControlTarget('robot');
            e.preventDefault();
            return;
        }

        let handled = false;
        switch (e.key) {
            case 'z': case 'Z': case 'w': case 'W': case 'ArrowUp':
                keysDown.up = true;
                setKeyVisual('key-up', true);
                handled = true;
                break;
            case 's': case 'S': case 'ArrowDown':
                keysDown.down = true;
                setKeyVisual('key-down', true);
                handled = true;
                break;
            case 'q': case 'Q': case 'a': case 'A': case 'ArrowLeft':
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
            case 'z': case 'Z': case 'w': case 'W': case 'ArrowUp':
                keysDown.up = false;
                setKeyVisual('key-up', false);
                handled = true;
                break;
            case 's': case 'S': case 'ArrowDown':
                keysDown.down = false;
                setKeyVisual('key-down', false);
                handled = true;
                break;
            case 'q': case 'Q': case 'a': case 'A': case 'ArrowLeft':
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
    // Sécurité supplémentaire : si la fenêtre perd le focus, relâcher les touches
    window.addEventListener('blur', () => {
        keysDown.up = false;
        keysDown.down = false;
        keysDown.left = false;
        keysDown.right = false;
        setKeyVisual('key-up', false);
        setKeyVisual('key-down', false);
        setKeyVisual('key-left', false);
        setKeyVisual('key-right', false);
        evaluateKeyboardMovement();
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
    updateGamepadInput();

    if (currentTarget === 'robot') {
        // Mode Robot : envoi de la consigne différentielle
        if (currentVx !== 0 || currentVtheta !== 0) {
            sendCmdVel(currentVx, currentVtheta);
            zeroSendCount = 0;
        } else if (zeroSendCount < 3) {
            sendCmdVel(0, 0);
            zeroSendCount++;
        }
    } else {
        // Mode Actionneur : contrôle direct de l'ascenseur et de la pince sur le stick
        const armId = parseInt(currentTarget.split('_')[1], 10);
        handleArmJoystickControl(armId);
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

// =======================================================
// 7. GESTION DE LA MANETTE (GAMEPAD API)
// =======================================================
let gamepadIndex = null;
let lastGamepadButtons = {};
let isGamepadModalOpen = false;

function initGamepad() {
    window.addEventListener("gamepadconnected", (e) => {
        console.log(`🎮 Manette connectée : ${e.gamepad.id} (index ${e.gamepad.index})`);
        gamepadIndex = e.gamepad.index;
        updateGamepadBadge(true, e.gamepad.id);
        showActuatorFeedback(`🎮 Manette détectée : ${e.gamepad.id}`);
    });

    window.addEventListener("gamepaddisconnected", (e) => {
        console.log(`🎮 Manette déconnectée : ${e.gamepad.id}`);
        if (gamepadIndex === e.gamepad.index) {
            gamepadIndex = null;
            updateGamepadBadge(false);
            showActuatorFeedback("🎮 Manette déconnectée");
        }
    });
}

function updateGamepadBadge(connected, name = "") {
    const badge = document.getElementById("gamepad-badge");
    const text = document.getElementById("gamepad-status-text");
    const modalName = document.getElementById("modal-gamepad-name");

    if (badge && text) {
        if (connected) {
            badge.className = "badge-gamepad connected";
            text.innerText = "MANETTE ACTIVE";
            badge.title = name;
        } else {
            badge.className = "badge-gamepad disconnected";
            text.innerText = "AUCUNE MANETTE";
            badge.title = "Cliquer pour afficher l'aide manette";
        }
    }
    if (modalName) {
        modalName.innerText = connected ? name : "Aucune manette détectée";
    }
}

function updateGamepadInput() {
    // Si l'utilisateur est en train de glisser à la souris/tactile, on ignore la manette
    if (isDragging) return;

    const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    let gp = null;
    if (gamepadIndex !== null && gamepads[gamepadIndex]) {
        gp = gamepads[gamepadIndex];
    } else {
        // Recherche automatique de la première manette disponible
        for (let i = 0; i < gamepads.length; i++) {
            if (gamepads[i]) {
                gp = gamepads[i];
                gamepadIndex = i;
                updateGamepadBadge(true, gp.id);
                break;
            }
        }
    }

    if (!gp) {
        return;
    }

    // --- 1. LECTURE DES STICKS (DÉPLACEMENT) ---
    // Axe 0 : Stick G Horizontal (-1 gauche, +1 droite)
    // Axe 1 : Stick G Vertical (-1 haut, +1 bas)
    // Axe 2 : Stick D Horizontal (-1 gauche, +1 droite)
    // Axe 3 : Stick D Vertical (-1 haut, +1 bas)
    let rawY = gp.axes.length > 1 ? gp.axes[1] : 0;
    let rawX = 0;
    // On permet de tourner soit avec le stick droit (axe 2), soit avec le stick gauche (axe 0)
    if (gp.axes.length > 2 && Math.abs(gp.axes[2]) > 0.15) {
        rawX = gp.axes[2];
    } else if (gp.axes.length > 0) {
        rawX = gp.axes[0];
    }

    // Zone morte de 10%
    let normY = Math.abs(rawY) > 0.1 ? -rawY : 0; // Stick vers le haut -> normY positif
    let normX = Math.abs(rawX) > 0.1 ? rawX : 0;

    if (invertY) {
        normY = -normY;
    }

    const isUsingGamepadStick = (normY !== 0 || normX !== 0);
    const isKeyboardActive = (keysDown.up || keysDown.down || keysDown.left || keysDown.right);

    if (isUsingGamepadStick || (!isKeyboardActive && !isDragging && (currentVx !== 0 || currentVtheta !== 0))) {
        currentVx = Math.round(normY * linearMax);
        currentVtheta = Math.round(-normX * angularMax);

        // Mise à jour visuelle du knob
        const knob = document.getElementById('joystick-knob');
        if (knob) {
            const visualX = normX * maxRadius * 0.75;
            const visualY = -normY * maxRadius * 0.75;
            knob.style.transform = `translate(${visualX}px, ${visualY}px)`;
        }
        updateGauges(currentVx, currentVtheta);
    }

    // --- 2. LECTURE DES BOUTONS (ACTIONNEURS & SÉCURITÉ) ---
    const buttons = gp.buttons;
    const isPressed = (index) => {
        if (!buttons || !buttons[index]) return false;
        return typeof buttons[index] === 'object' ? buttons[index].pressed : buttons[index] > 0.5;
    };

    const checkEdge = (btnIndex, action) => {
        const pressed = isPressed(btnIndex);
        if (pressed && !lastGamepadButtons[btnIndex]) {
            action();
        }
        lastGamepadButtons[btnIndex] = pressed;
    };

    // Bouton B (index 1) ou Select (index 8) -> Arrêt d'urgence
    checkEdge(1, () => triggerEmergencyStop());
    checkEdge(8, () => triggerEmergencyStop());

    // Boutons d'action :
    // A (index 0) -> Pose Match ou retour au robot
    checkEdge(0, () => {
        if (currentTarget !== 'robot') {
            setControlTarget('robot');
        } else {
            sendActuatorCmd('pose_match');
        }
    });
    // X (index 2) -> Rotation 9G sur le bras actif ou Tout Ouvrir en mode robot
    checkEdge(2, () => {
        if (currentTarget === 'robot') {
            sendActuatorCmd('release_all');
        } else {
            const armId = parseInt(currentTarget.split('_')[1], 10);
            sendActuatorCmd('tourner', { id: armId });
        }
    });
    // Y (index 3) -> Pose Caméra
    checkEdge(3, () => sendActuatorCmd('pose_camera'));

    // Gâchettes / Bumpers :
    // L1 (index 4) -> Actionneur / Cible précédente
    checkEdge(4, () => cycleControlTarget(-1));
    // R1 (index 5) -> Actionneur / Cible suivante
    checkEdge(5, () => cycleControlTarget(1));

    // LT (index 6) -> Ouvrir pince (du bras actif, ou toutes si robot)
    checkEdge(6, () => {
        if (currentTarget === 'robot') {
            sendActuatorCmd('release_all');
        } else {
            const armId = parseInt(currentTarget.split('_')[1], 10);
            sendActuatorCmd('release', { id: armId });
        }
    });

    // RT (index 7) -> Serrer pince (du bras actif, ou toutes si robot)
    checkEdge(7, () => {
        if (currentTarget === 'robot') {
            sendActuatorCmd('grab_all');
        } else {
            const armId = parseInt(currentTarget.split('_')[1], 10);
            sendActuatorCmd('grab', { id: armId });
        }
    });

    // Start (index 9) -> Homing / Init
    checkEdge(9, () => sendActuatorCmd('init_robot'));

    // Croix D-Pad :
    // D-Pad Haut (index 12) -> Déployer
    checkEdge(12, () => sendActuatorCmd('pose_deploy'));
    // D-Pad Bas (index 13) -> Ranger
    checkEdge(13, () => sendActuatorCmd('pose_ranger'));
    // D-Pad Gauche (index 14) -> Grab All
    checkEdge(14, () => sendActuatorCmd('pose_grab'));
    // D-Pad Droite (index 15) -> Poser All
    checkEdge(15, () => sendActuatorCmd('pose_poser'));

    // Visualiseur modal si ouvert
    if (isGamepadModalOpen) {
        updateGamepadModalVisualizer(normY, normX, buttons);
    }
}

function updateGamepadModalVisualizer(normY, normX, buttons) {
    const elVx = document.getElementById('gp-vis-vx');
    const elVtheta = document.getElementById('gp-vis-vtheta');
    if (elVx) elVx.innerText = `${Math.round(normY * 100)}%`;
    if (elVtheta) elVtheta.innerText = `${Math.round(normX * 100)}%`;

    const btnContainer = document.getElementById('gp-buttons-indicator');
    if (btnContainer && buttons) {
        let html = '';
        for (let i = 0; i < Math.min(buttons.length, 16); i++) {
            const pressed = typeof buttons[i] === 'object' ? buttons[i].pressed : buttons[i] > 0.5;
            if (pressed) {
                html += `<span class="gp-active-key">B${i}</span> `;
            }
        }
        btnContainer.innerHTML = html || '<span class="text-muted">Aucun bouton pressé</span>';
    }
}

function toggleGamepadModal() {
    const modal = document.getElementById('gamepad-modal');
    if (!modal) return;
    isGamepadModalOpen = !isGamepadModalOpen;
    if (isGamepadModalOpen) {
        modal.classList.remove('hidden');
    } else {
        modal.classList.add('hidden');
    }
}

function onModalOverlayClick(e) {
    if (e.target.id === 'gamepad-modal') {
        toggleGamepadModal();
    }
}

// =======================================================
// 8. CONTRÔLE DES ACTIONNEURS
// =======================================================
function initActuators() {
    // Initialisation
}

function sendActuatorCmd(cmd, params = {}) {
    const payload = { cmd: cmd, ...params };

    // Feedback visuel
    showActuatorFeedback(getActuatorActionName(cmd, params));

    if (window.socket && window.socket.ws && window.socket.ws.readyState === WebSocket.OPEN) {
        window.socket.emit('cmd_actuator', payload);
    } else {
        fetch('/api/actuator', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).catch(err => console.error("Erreur envoi actionneur:", err));
    }
}

function showActuatorFeedback(text) {
    const el = document.getElementById('actuator-feedback');
    if (!el) return;
    el.innerText = text;
    el.classList.add('active');
    clearTimeout(el._timeout);
    el._timeout = setTimeout(() => {
        el.classList.remove('active');
    }, 2500);
}

function getActuatorActionName(cmd, params) {
    switch (cmd) {
        case 'pose_match': return '🏁 Pose Match lancée';
        case 'pose_camera': return '📸 Pose Caméra déployée';
        case 'pose_deploy': return '📦 Bras Déployés';
        case 'pose_grab': return '📥 Prise des Kaplas';
        case 'pose_poser': return '📤 Dépose des Kaplas';
        case 'pose_ranger': return '🔒 Bras Rangés';
        case 'init_robot': return '🔄 Homing Initialisation lancé';
        case 'grab_all': return '🤏 Toutes les pinces serrées';
        case 'release_all': return '✋ Toutes les pinces ouvertes';
        case 'grab': return `🤏 Bras #${params.id} : Serrer`;
        case 'release': return `✋ Bras #${params.id} : Ouvrir`;
        case 'pivoter': return `🔄 Bras #${params.id} : Pivot ${params.sens}`;
        case 'tourner': return `🔁 Bras #${params.id} : Rotation 9G`;
        case 'ascenseur': return `⬆️ Bras #${params.id} : Hauteur ${params.hauteur}mm`;
        default: return `Commande ${cmd}`;
    }
}

function onHeightSliderChange(id, val) {
    const intVal = parseInt(val, 10);
    armHeights[id] = intVal;
    const label = document.getElementById(`label-height-${id}`);
    if (label) label.innerText = `${intVal} mm`;
    // Debounce de l'envoi vers l'ESP pour ne pas saturer
    clearTimeout(window[`_sliderTimeout_${id}`]);
    window[`_sliderTimeout_${id}`] = setTimeout(() => {
        lastSentArmHeights[id] = intVal;
        sendActuatorCmd('ascenseur', { id: id, hauteur: intVal });
    }, 150);
}

function setActuatorHeight(id, val) {
    const intVal = parseInt(val, 10);
    armHeights[id] = intVal;
    lastSentArmHeights[id] = intVal;
    const slider = document.getElementById(`slider-height-${id}`);
    const label = document.getElementById(`label-height-${id}`);
    if (slider) slider.value = intVal;
    if (label) label.innerText = `${intVal} mm`;
    sendActuatorCmd('ascenseur', { id: id, hauteur: intVal });
}

// =======================================================
// 9. CIBLAGE ET CONTRÔLE SUR LE JOYSTICK (ROBOT VS BRAS 1-4)
// =======================================================
function setControlTarget(target) {
    currentTarget = target;
    
    // Met à jour les boutons visuels
    const targets = ['robot', 'arm_1', 'arm_2', 'arm_3', 'arm_4'];
    targets.forEach(t => {
        const btn = document.getElementById(`target-btn-${t.replace('_', '-')}`);
        if (btn) {
            if (t === target) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });

    // Met à jour les repères de la boussole sur le joystick
    const markN = document.getElementById('mark-n');
    const markS = document.getElementById('mark-s');
    const markW = document.getElementById('mark-w');
    const markE = document.getElementById('mark-e');

    if (target === 'robot') {
        if (markN) markN.innerText = 'AVANT';
        if (markS) markS.innerText = 'ARRIÈRE';
        if (markW) markW.innerText = 'GAUCHE';
        if (markE) markE.innerText = 'DROITE';
        showActuatorFeedback("🤖 Mode : Base Robot (Déplacement)");
        highlightActuatorCard(null);
    } else {
        const armId = target.split('_')[1];
        if (markN) markN.innerText = '▲ MONTER';
        if (markS) markS.innerText = '▼ DESCENDRE';
        if (markW) markW.innerText = '✋ OUVRIR';
        if (markE) markE.innerText = '🤏 SERRER';
        showActuatorFeedback(`🦾 Mode Joystick : Bras #${armId}`);

        // Met en surbrillance la carte de l'actionneur ciblé
        highlightActuatorCard(armId);
    }

    // Sécurité : couper la vitesse robot immédiatement
    sendCmdVel(0, 0);
}

function cycleControlTarget(direction) {
    const targets = ['robot', 'arm_1', 'arm_2', 'arm_3', 'arm_4'];
    let idx = targets.indexOf(currentTarget);
    if (idx === -1) idx = 0;
    let nextIdx = (idx + direction + targets.length) % targets.length;
    setControlTarget(targets[nextIdx]);
}

function highlightActuatorCard(armId) {
    for (let i = 1; i <= 4; i++) {
        const card = document.getElementById(`act-card-${i}`);
        if (card) {
            if (armId && i.toString() === armId.toString()) {
                card.classList.add('targeted');
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } else {
                card.classList.remove('targeted');
            }
        }
    }
}

function handleArmJoystickControl(armId) {
    // 1. Contrôle vertical : Ascenseur (currentVx = stick Y : positif vers le haut)
    if (Math.abs(currentVx) > 20) {
        // Vitesse d'incrément proportionnelle (~6 mm par tick de 50 ms = 120 mm/s)
        const delta = (currentVx / (linearMax || 500)) * 5;
        armHeights[armId] = Math.min(170, Math.max(0, armHeights[armId] + delta));
        
        const roundedHeight = Math.round(armHeights[armId]);
        
        // Mise à jour de l'UI en direct
        const slider = document.getElementById(`slider-height-${armId}`);
        const label = document.getElementById(`label-height-${armId}`);
        if (slider) slider.value = roundedHeight;
        if (label) label.innerText = `${roundedHeight} mm`;

        // Envoi à l'ESP si la consigne a varié d'au moins 2 mm
        if (lastSentArmHeights[armId] === null || Math.abs(roundedHeight - lastSentArmHeights[armId]) >= 2) {
            lastSentArmHeights[armId] = roundedHeight;
            sendActuatorCmd('ascenseur', { id: armId, hauteur: roundedHeight });
        }
    }

    // 2. Contrôle horizontal : Pince (Stick X : Gauche = Ouvrir, Droite = Serrer)
    if (Math.abs(currentVtheta) > 30) {
        if (!armControlDebounceX) {
            armControlDebounceX = true;
            if (currentVtheta > 30) {
                // Vers la gauche -> Ouvrir pince
                sendActuatorCmd('release', { id: armId });
            } else if (currentVtheta < -30) {
                // Vers la droite -> Serrer pince
                sendActuatorCmd('grab', { id: armId });
            }
        }
    } else {
        armControlDebounceX = false;
    }
}
