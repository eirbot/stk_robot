// map.js — Carte Temps Réel en 3D (Three.js) pour Eurobot 2026
//
// -----------------------------------------------------------------------------
// GESTION DU REPÈRE DE COORDONNÉES (ORIGINE EN HAUT À GAUCHE) :
// -----------------------------------------------------------------------------
// Repère Eurobot physique (Monde) :
// - Axe X (Longueur) : -1500 à 1500 mm (de gauche à droite, center=0).
// - Axe Y (Largeur) : 0 à 2000 mm (du haut vers le bas).
// - Theta (Orientation) : Angle en radians.
//   - 0 = vers l'est/X+ (droite).
//   - PI/2 = vers le sud/Y+ (bas, car Y croît vers le bas).
//
// Repère Three.js :
// - La table de 3000x2000 mm est centrée à l'origine (0, 0, 0) de la scène 3D.
// - La surface supérieure de la table correspond au plan Z = 0 (axe Z vertical).
// - L'axe X de Three.js correspond à la Longueur (de -1500 à +1500 mm).
// - L'axe Y de Three.js correspond à la Largeur (de -1000 à +1000 mm, où +1000 est le haut et -1000 est le bas).
//
// Formules de conversion (Robot -> Scène 3D) :
// - X_three = X_robot
// - Y_three = 1000 - Y_robot  (car Y=0 est en haut à +1000, et Y=2000 est en bas à -1000)
// - Z_three = 0
// - Rotation Z_three = -Theta_robot (signe négatif car l'inversion de l'axe Y inverse le sens trigonométrique)
// -----------------------------------------------------------------------------

const TABLE_L_MM = 3000; // Longueur de la table (axe X Three.js)
const TABLE_W_MM = 2000; // Largeur de la table (axe Y Three.js)

let scene, camera, renderer, controls;
let robotGroup, lidarGroup;
let robotMaterial, lidarMaterial;
let beacons = [];
let targetSphere = null;

let robotPos = { x: 0, y: 1000, theta: 0 };
let lidarPos = null;
let currentTeam = "BLEUE";
let isTopDown = false;

// -----------------------------------------------------------------------------
// INITIALISATION DE LA SCÈNE 3D
// -----------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    console.log("[MAP 3D] Initialisation de la scène Three.js...");
    init3D();
    loadBeacons();
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

// -----------------------------------------------------------------------------
// CONSTRUCTION DES OBJETS DE LA SCÈNE
// -----------------------------------------------------------------------------
function createTable() {
    // Plateau principal (boîte de 3000 x 2000 x 20 mm)
    const tableGeo = new THREE.BoxGeometry(TABLE_L_MM, TABLE_W_MM, 20);
    const tableMat = new THREE.MeshStandardMaterial({
        color: 0x181d26,
        roughness: 0.8,
        metalness: 0.1
    });
    const tableMesh = new THREE.Mesh(tableGeo, tableMat);
    // Table centrée en (0,0) - Sa surface supérieure est à Z=0
    tableMesh.position.set(0, 0, -10);
    tableMesh.receiveShadow = true;
    scene.add(tableMesh);

    // Bordures de la table (tasseaux protecteurs de 70 mm de haut)
    const borderMat = new THREE.MeshStandardMaterial({ color: 0x090a0d, roughness: 0.9 });
    const borderGeoLong = new THREE.BoxGeometry(TABLE_L_MM + 20, 10, 70);
    const borderGeoWide = new THREE.BoxGeometry(10, TABLE_W_MM, 70);

    const borderSouth = new THREE.Mesh(borderGeoLong, borderMat);
    borderSouth.position.set(0, -TABLE_W_MM / 2 - 5, 15);
    scene.add(borderSouth);

    const borderNorth = new THREE.Mesh(borderGeoLong, borderMat);
    borderNorth.position.set(0, TABLE_W_MM / 2 + 5, 15);
    scene.add(borderNorth);

    const borderWest = new THREE.Mesh(borderGeoWide, borderMat);
    borderWest.position.set(-TABLE_L_MM / 2 - 5, 0, 15);
    scene.add(borderWest);

    const borderEast = new THREE.Mesh(borderGeoWide, borderMat);
    borderEast.position.set(TABLE_L_MM / 2 + 5, 0, 15);
    scene.add(borderEast);

    // Quadrillage décoratif tous les 100 mm
    const gridColor = 0x2e3846;
    const gridGroup = new THREE.Group();

    // Lignes verticales (axe Y de Three.js)
    for (let x = -TABLE_L_MM / 2; x <= TABLE_L_MM / 2; x += 100) {
        const points = [
            new THREE.Vector3(x, -TABLE_W_MM / 2, 0.5),
            new THREE.Vector3(x, TABLE_W_MM / 2, 0.5)
        ];
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: gridColor }));
        gridGroup.add(line);
    }
    // Lignes horizontales (axe X de Three.js)
    for (let y = -TABLE_W_MM / 2; y <= TABLE_W_MM / 2; y += 100) {
        const points = [
            new THREE.Vector3(-TABLE_L_MM / 2, y, 0.5),
            new THREE.Vector3(TABLE_L_MM / 2, y, 0.5)
        ];
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: gridColor }));
        gridGroup.add(line);
    }
    scene.add(gridGroup);
}

function createRobots() {
    // --- ROBOT PRINCIPAL ---
    robotGroup = new THREE.Group();

    // Couleur d'équipe (Bleue par défaut)
    robotMaterial = new THREE.MeshStandardMaterial({
        color: 0x007bff,
        roughness: 0.4,
        metalness: 0.2
    });

    // Corps géométrique simple (Box de 300x300x250 mm) reposant sur Z=0
    const bodyGeo = new THREE.BoxGeometry(300, 300, 250);
    const bodyMesh = new THREE.Mesh(bodyGeo, robotMaterial);
    bodyMesh.position.z = 125;
    bodyMesh.castShadow = true;
    bodyMesh.receiveShadow = true;
    robotGroup.add(bodyMesh);

    // Nez indiquant l'avant (Cône rouge pointant vers le +X local, car 0 rad = vers X+)
    const noseGeo = new THREE.ConeGeometry(50, 100, 4);
    const noseMat = new THREE.MeshStandardMaterial({ color: 0xff3333, roughness: 0.5 });
    const noseMesh = new THREE.Mesh(noseGeo, noseMat);
    noseMesh.rotation.z = -Math.PI / 2; // Oriente le cône vers X+ local
    noseMesh.position.set(150, 0, 125);
    noseMesh.castShadow = true;
    robotGroup.add(noseMesh);

    // Roues (Cylindres noirs sur l'axe Y local, permettant de rouler vers X)
    const wheelGeo = new THREE.CylinderGeometry(60, 60, 30, 16);
    const wheelMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.9 });

    const leftWheel = new THREE.Mesh(wheelGeo, wheelMat);
    leftWheel.position.set(0, 165, 60);
    leftWheel.castShadow = true;
    robotGroup.add(leftWheel);

    const rightWheel = new THREE.Mesh(wheelGeo, wheelMat);
    rightWheel.position.set(0, -165, 60);
    rightWheel.castShadow = true;
    robotGroup.add(rightWheel);

    scene.add(robotGroup);

    // -------------------------------------------------------------------------
    // CODE DE CHARGEMENT D'UN MODÈLE 3D EXTERNE (.GLTF / .GLB)
    // -------------------------------------------------------------------------
    /*
    const loader = new THREE.GLTFLoader();
    loader.load('/static/models/robot.glb', (gltf) => {
        const model = gltf.scene;
        model.scale.set(1, 1, 1);
        model.traverse(child => {
            if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
            }
        });
        
        robotGroup.remove(bodyMesh);
        robotGroup.remove(noseMesh);
        robotGroup.remove(leftWheel);
        robotGroup.remove(rightWheel);
        robotGroup.add(model);
        console.log("[MAP 3D] Modèle 3D GLTF chargé.");
    });
    */

    // --- ROBOT GHOST (LIDAR / ESTIMATION) ---
    // Représente la position estimée par le LiDAR, dessinée de manière semi-transparente
    lidarGroup = new THREE.Group();
    lidarMaterial = new THREE.MeshBasicMaterial({
        color: 0x00e676, // Vert fluo
        transparent: true,
        opacity: 0.35
    });

    const ghostMesh = new THREE.Mesh(bodyGeo, lidarMaterial);
    ghostMesh.position.z = 125;
    lidarGroup.add(ghostMesh);

    const ghostNose = new THREE.Mesh(noseGeo, new THREE.MeshBasicMaterial({
        color: 0x00e676,
        transparent: true,
        opacity: 0.5
    }));
    ghostNose.rotation.z = -Math.PI / 2;
    ghostNose.position.set(150, 0, 125);
    lidarGroup.add(ghostNose);

    lidarGroup.visible = false; // Caché par défaut
    scene.add(lidarGroup);
}

// -----------------------------------------------------------------------------
// CHARGEMENT DES BALISES
// -----------------------------------------------------------------------------
async function loadBeacons() {
    try {
        const resp = await fetch('/api/beacons');
        if (!resp.ok) return;
        beacons = await resp.json();

        const beaconGeo = new THREE.CylinderGeometry(25, 25, 120, 16);
        const beaconMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, roughness: 0.5, metalness: 0.1 });
        const capGeo = new THREE.CylinderGeometry(30, 30, 20, 16);
        const capMat = new THREE.MeshStandardMaterial({ color: 0xcc2222 });

        beacons.forEach(([bx, by]) => {
            const beaconGroup = new THREE.Group();

            const pillar = new THREE.Mesh(beaconGeo, beaconMat);
            pillar.position.z = 60;
            pillar.castShadow = true;
            beaconGroup.add(pillar);

            const cap = new THREE.Mesh(capGeo, capMat);
            cap.position.z = 130;
            cap.castShadow = true;
            beaconGroup.add(cap);

            // Conversion Repère :
            // Dans l'API, les coordonnées des balises sont :
            // - bx = Largeur robot (0 à 2000) -> Y_three = 1000 - bx
            // - by = Longueur robot (-1500 à 1500) -> X_three = by
            beaconGroup.position.set(by, 1000 - bx, 0);
            scene.add(beaconGroup);
        });
    } catch (e) {
        console.warn("[MAP 3D] Impossible de charger les balises fixes :", e);
    }
}

// -----------------------------------------------------------------------------
// CONNEXION WEBSOCKET ET RÉCEPTION DE LA TÉLÉMÉTRIE
// -----------------------------------------------------------------------------
function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    console.log(`[MAP 3D] Connexion au WebSocket : ${wsUrl}`);
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("[MAP 3D] Connexion WebSocket ouverte");
    };

    socket.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            
            // 1. Traitement de la télémétrie principale
            if (msg.type === "state_update" && msg.data) {
                const state = msg.data;

                // Couleur d'équipe
                if (state.team && state.team !== currentTeam) {
                    currentTeam = state.team;
                    updateTeamColor();
                }

                // Télémétrie odométrique
                if (state.telemetry) {
                    robotPos = {
                        x: state.telemetry.x, // Longueur (-1500 à 1500)
                        y: state.telemetry.y, // Largeur (0 à 2000)
                        theta: state.telemetry.theta // en radians
                    };

                    updateRobotMeshPosition(robotGroup, robotPos);
                    updateUI();
                }
            }
            
            // 2. Traitement de la position LiDAR (Ghost semi-transparent)
            if (msg.type === "lidar_pos" && msg.data) {
                lidarPos = {
                    x: msg.data.x, // Longueur (-1500 à 1500)
                    y: msg.data.y, // Largeur (0 à 2000)
                    theta: msg.data.theta * Math.PI / 180, // Télémétrie en degrés -> converti en radians
                    err: msg.data.err
                };
                
                lidarGroup.visible = true;
                updateRobotMeshPosition(lidarGroup, lidarPos);
                updateUI();
            }

        } catch (err) {
            console.error("[MAP 3D] Erreur lors de l'interprétation du message :", err);
        }
    };

    socket.onclose = () => {
        console.warn("[MAP 3D] WebSocket clos. Reconnexion dans 2 secondes...");
        setTimeout(setupWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.error("[MAP 3D] Problème réseau WebSocket :", err);
    };
}

function updateRobotMeshPosition(group, pos) {
    if (!group) return;

    // Translation du repère :
    // X_three = Robot X (déjà de -1500 à 1500)
    // Y_three = 1000 - Robot Y (car Y=0 est en haut, Y=2000 est en bas)
    group.position.x = pos.x;
    group.position.y = 1000 - pos.y;

    // Rotation autour de Z (inversée car l'axe Y est inversé)
    group.rotation.z = -pos.theta;
}

function updateTeamColor() {
    if (robotMaterial) {
        const teamColor = (currentTeam === 'JAUNE') ? 0xffa600 : 0x007bff;
        robotMaterial.color.setHex(teamColor);
    }
}

function updateUI() {
    const el = document.getElementById('pos-text');
    if (!el) return;
    
    // Affichage utilisateur (Longueur X et Largeur Y physique du robot)
    const thetaDeg = robotPos.theta * 180 / Math.PI;
    let txt = `ROBOT | X: ${robotPos.x.toFixed(0)} mm | Y: ${robotPos.y.toFixed(0)} mm | θ: ${thetaDeg.toFixed(1)}°`;
    
    if (lidarPos) {
        const lThetaDeg = lidarPos.theta * 180 / Math.PI;
        txt += `  ·  LiDAR | X: ${lidarPos.x.toFixed(0)} | Y: ${lidarPos.y.toFixed(0)} | θ: ${lThetaDeg.toFixed(1)}° (Δ${lidarPos.err.toFixed(0)}mm)`;
    }
    el.innerText = txt;
}

// -----------------------------------------------------------------------------
// BASCULE DE VUE (2D DESSUS / 3D PERSPECTIVE)
// -----------------------------------------------------------------------------
function toggleViewMode() {
    isTopDown = !isTopDown;
    const toggleBtn = document.getElementById('btn-view-toggle');
    
    if (isTopDown) {
        if (toggleBtn) toggleBtn.innerText = "Vue 3D (Orbite)";
        controls.enableRotate = false; // Bloque la rotation pour la vue plan 2D
        
        // Positionne la caméra juste au-dessus du centre (Y très légèrement décalé pour éviter le blocage de cardan)
        animateCamera(new THREE.Vector3(0, -0.01, 2500), new THREE.Vector3(0, 0, 0));
    } else {
        if (toggleBtn) toggleBtn.innerText = "Vue 2D (Dessus)";
        controls.enableRotate = true; // Réactive la rotation libre
        
        // Rétablit l'angle oblique par défaut
        animateCamera(new THREE.Vector3(0, -2200, 1800), new THREE.Vector3(0, 0, 0));
    }
}

function animateCamera(targetPosition, targetLookAt) {
    const duration = 600; // Durée de la transition en ms
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    const startTime = performance.now();
    
    function update(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Easing quadratique (in-out)
        const t = progress < 0.5 ? 2 * progress * progress : -1 + (4 - 2 * progress) * progress;
        
        camera.position.lerpVectors(startPos, targetPosition, t);
        controls.target.lerpVectors(startTarget, targetLookAt, t);
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    requestAnimationFrame(update);
}

// -----------------------------------------------------------------------------
// INTERACTION : DOUBLE-CLIC -> ORDRE GOTO (RAYCASTING)
// -----------------------------------------------------------------------------
function onTableDoubleClick(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);

    const intersects = raycaster.intersectObjects(scene.children, true);

    for (let i = 0; i < intersects.length; i++) {
        // Détecter l'impact sur le plateau de jeu
        if (intersects[i].object.receiveShadow && intersects[i].point.z >= -1) {
            const pt = intersects[i].point;

            // Conversion inverse : Three.js -> Repère Robot
            // pt.x = targetX (Longueur -1500 à 1500)
            // pt.y = 1000 - targetY => targetY = 1000 - pt.y (Largeur 0 à 2000)
            const targetX = pt.x;
            const targetY = 1000 - pt.y;
            const targetTheta = robotPos.theta; // On conserve l'orientation actuelle

            console.log(`[MAP 3D] Clic sur table -> Goto X: ${targetX.toFixed(0)}, Y: ${targetY.toFixed(0)}`);

            // Envoi de l'action vers le serveur Go
            sendGoto(targetX, targetY, targetTheta);

            // Dessin temporaire d'un retour visuel orange 3D
            spawnTargetIndicator(pt.x, pt.y);
            break;
        }
    }
}

// -----------------------------------------------------------------------------
// SURVOL DE LA TABLE : AFFICHAGE DES COORDONNÉES SOUS LE CURSEUR
// -----------------------------------------------------------------------------
function onTableMouseMove(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1
    );

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);

    const intersects = raycaster.intersectObjects(scene.children, true);
    let found = false;

    for (let i = 0; i < intersects.length; i++) {
        // Détecter l'impact sur le plateau de jeu
        if (intersects[i].object.receiveShadow && intersects[i].point.z >= -1) {
            const pt = intersects[i].point;

            // Conversion inverse : Three.js -> Repère Robot
            const targetX = pt.x;
            const targetY = 1000 - pt.y;

            // Mettre à jour et positionner le tooltip
            const tooltip = document.getElementById('coord-tooltip');
            if (tooltip) {
                tooltip.style.display = 'block';
                tooltip.style.left = `${event.clientX - rect.left}px`;
                tooltip.style.top = `${event.clientY - rect.top}px`;
                tooltip.innerText = `X: ${targetX.toFixed(0)} | Y: ${targetY.toFixed(0)}`;
            }
            found = true;
            break;
        }
    }

    if (!found) {
        onTableMouseLeave();
    }
}

function onTableMouseLeave() {
    const tooltip = document.getElementById('coord-tooltip');
    if (tooltip) {
        tooltip.style.display = 'none';
    }
}

async function sendGoto(x, y, theta) {
    try {
        await fetch('/api/goto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x, y, theta })
        });
    } catch (e) {
        console.error("[MAP 3D] Impossible d'envoyer la commande GoTo :", e);
    }
}

// -----------------------------------------------------------------------------
// MARQUEUR VISUEL DE CIBLE TEMPORAIRE
// -----------------------------------------------------------------------------
function spawnTargetIndicator(x, y) {
    if (targetSphere) {
        scene.remove(targetSphere);
    }

    const sphereGeo = new THREE.SphereGeometry(30, 16, 16);
    const sphereMat = new THREE.MeshBasicMaterial({ color: 0xff5722, transparent: true, opacity: 0.9 });
    targetSphere = new THREE.Mesh(sphereGeo, sphereMat);
    targetSphere.position.set(x, y, 15);
    scene.add(targetSphere);

    const fadeStart = Date.now();
    const fadeDuration = 1000;

    function fade() {
        const elapsed = Date.now() - fadeStart;
        if (elapsed < fadeDuration) {
            if (targetSphere) {
                targetSphere.material.opacity = 0.9 * (1 - (elapsed / fadeDuration));
                targetSphere.scale.setScalar(1 + (elapsed / fadeDuration) * 0.7);
                requestAnimationFrame(fade);
            }
        } else {
            if (targetSphere) {
                scene.remove(targetSphere);
                targetSphere = null;
            }
        }
    }
    fade();
}

// -----------------------------------------------------------------------------
// REDIMENSIONNEMENT & BOUCLE DE RENDU D'ANIMATION
// -----------------------------------------------------------------------------
function onWindowResize() {
    const container = document.getElementById('simu3d-container');
    if (!container) return;

    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}

function animate() {
    requestAnimationFrame(animate);

    if (controls) {
        controls.update(); // Permet l'amorti fluide des contrôles camera
    }

    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}
