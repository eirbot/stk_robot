// Carte 3D : repères, état partagé, création de la scène Three.js.
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

// map.js — Carte Temps Réel en 3D (Three.js) pour Eurobot 2026
//
// -----------------------------------------------------------------------------
// GESTION DU REPÈRE DE COORDONNÉES (ORIGINE EN HAUT À GAUCHE) :
// -----------------------------------------------------------------------------
// Repère robot (cf. Rasp/strat/actions.py, la symétrie JAUNE se fait sur Y) :
// - Axe X (Largeur) : 0 à 2000 mm (du haut vers le bas).
// - Axe Y (Longueur) : -1500 à 1500 mm (de gauche à droite, center=0).
// - Theta (Orientation) : Angle en degrés.
//   - 0 = X+ (vers le bas).
//   - 90 = Y+ (vers la droite).
//
// Repère Three.js :
// - La table de 3000x2000 mm est centrée à l'origine (0, 0, 0) de la scène 3D.
// - La surface supérieure de la table correspond au plan Z = 0 (axe Z vertical).
// - L'axe X de Three.js correspond à la Longueur (de -1500 à +1500 mm).
// - L'axe Y de Three.js correspond à la Largeur (de -1000 à +1000 mm, où +1000 est le haut et -1000 est le bas).
//
// Formules de conversion (Robot -> Scène 3D), cf. robotToThree / threeToRobot :
// - X_three = Y_robot
// - Y_three = 1000 - X_robot  (car X=0 est en haut à +1000, et X=2000 est en bas à -1000)
// - Z_three = 0
// - Rotation Z_three = Theta_robot - 90° (rotation pure, pas d'inversion de sens)
// -----------------------------------------------------------------------------

const TABLE_L_MM = 3000; // Longueur de la table (axe X Three.js)
const TABLE_W_MM = 2000; // Largeur de la table (axe Y Three.js)

// Conversions de repère : définition unique dans frames.js (cf. Rasp/core/frames.py)
const robotToThree = EirbotFrames.robotToThree;
const threeToRobot = EirbotFrames.threeToRobot;

let scene, camera, renderer, controls;
let robotGroup, visionGroup, lidarScanGroup;
let robotMaterial, visionMaterial, footprintMaterial;
let targetSphere = null;

let robotPos = { x: 1000, y: 0, theta: 0 }; // theta en degrés
let visionPos = null;                        // theta en degrés
let currentTeam = "BLEUE";
let isTopDown = false;
let obstacleDetected = false;
let obstacleType = 0;

// -----------------------------------------------------------------------------
// INITIALISATION DE LA SCÈNE 3D
// -----------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    console.log("[MAP 3D] Initialisation de la scène Three.js...");
    init3D();
    setupWebSocket();
});

function init3D() {
    const container = document.getElementById('simu3d-container');
    if (!container) return;

    // 1. Scène, Caméra et Renderer
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0c10); // Fond sombre / anthracite
    scene.fog = new THREE.FogExp2(0x0a0c10, 0.00015);

    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 10, 20000);
    // Définir l'axe Z comme axe vertical
    camera.up.set(0, 0, 1);
    // Vue de départ oblique surélevée au-dessus de la table
    camera.position.set(0, -2200, 1800);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    // 2. Contrôles orbitaux (OrbitControls)
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; // Effet d'amorti agréable
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.05; // Empêche la caméra de passer sous la table
    controls.minDistance = 300;
    controls.maxDistance = 6000;

    // 3. Lumières (Ambiante + Directionnelle)
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(500, -1000, 1500);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.bias = -0.0005;
    scene.add(dirLight);

    // 4. Création de la Table de jeu
    createTable();

    // 5. Création des Représentations des Robots
    createRobots();

    // Groupe pour l'affichage de la trame LiDAR courante
    lidarScanGroup = new THREE.Group();
    scene.add(lidarScanGroup);

    // 6. Gestion du bouton de bascule de vue (2D / 3D)
    const toggleBtn = document.getElementById('btn-view-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleViewMode);
    }

    // 7. Double-clic pour ordonner un déplacement (Raycasting)
    renderer.domElement.addEventListener('dblclick', onTableDoubleClick);
    renderer.domElement.addEventListener('mousemove', onTableMouseMove);
    renderer.domElement.addEventListener('mouseleave', onTableMouseLeave);

    // 8. Redimensionnement fenêtre
    window.addEventListener('resize', onWindowResize);

    // 9. Démarrage de la boucle d'animation
    animate();
}
