// Pilotage : manette de jeu (Gamepad API).
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

// =======================================================
// 7. GESTION DE LA MANETTE (GAMEPAD API)
// =======================================================
let gamepadIndex = null;
let lastGamepadButtons = {};
let isGamepadModalOpen = false;

function initGamepad() {
    window.addEventListener("gamepadconnected", (e) => {
        console.log(`Manette connectée : ${e.gamepad.id} (index ${e.gamepad.index})`);
        gamepadIndex = e.gamepad.index;
        updateGamepadBadge(true, e.gamepad.id);
        showActuatorFeedback(`Manette détectée : ${e.gamepad.id}`);
    });

    window.addEventListener("gamepaddisconnected", (e) => {
        console.log(`Manette déconnectée : ${e.gamepad.id}`);
        if (gamepadIndex === e.gamepad.index) {
            gamepadIndex = null;
            updateGamepadBadge(false);
            showActuatorFeedback("Manette déconnectée");
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
