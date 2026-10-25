// Pilotage : état partagé (limites de vitesse, consignes, cible) et démarrage de la page.
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

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

const ecartRoues = 339.3; // mm, comme le firmware (ESP/src/motors/config.h : WHEEL_BASE_MM)

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
