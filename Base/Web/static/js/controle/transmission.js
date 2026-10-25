// Pilotage : envoi des consignes de vitesse (cmd_vel) et arrêt d'urgence.
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

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

// Envoi immédiat dès que la consigne change (plafonné à ~60 Hz) au lieu d'attendre
// le prochain tick de 50 ms ; tickTransmission reste le maintien en vie (watchdog ESP 500 ms)
let lastImmediateSendTs = 0;
function maybeSendNow() {
    if (currentTarget !== 'robot') return;
    if (currentVx === lastSentVx && currentVtheta === lastSentVtheta) return;
    const t = performance.now();
    if (t - lastImmediateSendTs < 15) return;
    lastImmediateSendTs = t;
    sendCmdVel(currentVx, currentVtheta);
    if (currentVx !== 0 || currentVtheta !== 0) zeroSendCount = 0;
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

// Badge avec icône du thème (window.icon de theme.js) : réécrit seulement si le contenu change
function setIconText(el, name, text) {
    if (!el) return;
    const key = (name || '') + '|' + text;
    if (el.dataset.content === key) return;
    el.dataset.content = key;
    el.innerHTML = (name && window.icon ? window.icon(name) + ' ' : '') + text;
}

function triggerEmergencyStop() {
    console.warn("ARRÊT D'URGENCE MANUEL DÉCLENCHÉ");
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
