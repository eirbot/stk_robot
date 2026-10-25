// Pilotage : commande au clavier.
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

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
    maybeSendNow();
}
