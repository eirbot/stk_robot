// Pilotage : joystick tactile / souris.
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

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
    maybeSendNow();
}
