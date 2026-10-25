// Strat Studio : constantes (table, départ par défaut, encombrement du robot).
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 0. CONFIGURATION
// ============================================================

const TABLE_WIDTH = 3000;
const TABLE_HEIGHT = 2000;
const GRID_STEP = 200; // Quadrillage tous les 200mm

// Valeurs par défaut si le bloc "Départ" n'est pas utilisé
const DEFAULT_START_X = 250;
const DEFAULT_START_Y = 0;
const DEFAULT_START_THETA = 0;
// Encombrement réel du robot (modèle MuJoCo) : cf. EirbotFrames.ROBOT dans frames.js
const ROBOT = EirbotFrames.ROBOT;
const WHEEL_Y_MM = 157.2;   // roues à ±157,2 mm de l'axe (modèle MuJoCo)
const WHEEL_R_MM = 36;      // diamètre 72 mm
