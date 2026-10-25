// Pilotage : actionneurs (hauteurs, pinces) et choix de la cible (robot / bras).
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

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
        case 'pose_match': return 'Pose Match lancée';
        case 'pose_camera': return 'Pose Caméra déployée';
        case 'pose_deploy': return 'Bras Déployés';
        case 'pose_grab': return 'Prise des Kaplas';
        case 'pose_poser': return 'Dépose des Kaplas';
        case 'pose_ranger': return 'Bras Rangés';
        case 'init_robot': return 'Homing Initialisation lancé';
        case 'grab_all': return 'Toutes les pinces serrées';
        case 'release_all': return 'Toutes les pinces ouvertes';
        case 'grab': return `Bras #${params.id} : Serrer`;
        case 'release': return `Bras #${params.id} : Ouvrir`;
        case 'pivoter': return `Bras #${params.id} : Pivot ${params.sens}`;
        case 'tourner': return `Bras #${params.id} : Rotation 9G`;
        case 'ascenseur': return `Bras #${params.id} : Hauteur ${params.hauteur}mm`;
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
        showActuatorFeedback("Mode : Base Robot (Déplacement)");
        highlightActuatorCard(null);
    } else {
        const armId = target.split('_')[1];
        if (markN) markN.innerText = 'MONTER';
        if (markS) markS.innerText = 'DESCENDRE';
        if (markW) markW.innerText = 'OUVRIR';
        if (markE) markE.innerText = 'SERRER';
        showActuatorFeedback(`Mode Joystick : Bras #${armId}`);

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
