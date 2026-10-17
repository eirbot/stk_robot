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

function robotToThree(x, y) {
    return { x: y, y: 1000 - x };
}

function threeToRobot(pt) {
    return { x: 1000 - pt.y, y: pt.x };
}

let scene, camera, renderer, controls;
let robotGroup, visionGroup, lidarScanGroup;
let robotMaterial, visionMaterial;
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

    // --- ROBOT GHOST (VISION ZENITHALE) ---
    // Représente la position détectée par la caméra zénithale en cyan semi-transparent
    visionGroup = new THREE.Group();
    visionMaterial = new THREE.MeshBasicMaterial({
        color: 0x00d2ff, // Cyan zénithal
        transparent: true,
        opacity: 0.35
    });

    const vMesh = new THREE.Mesh(bodyGeo, visionMaterial);
    vMesh.position.z = 125;
    visionGroup.add(vMesh);

    const vNose = new THREE.Mesh(noseGeo, new THREE.MeshBasicMaterial({
        color: 0x00d2ff,
        transparent: true,
        opacity: 0.5
    }));
    vNose.rotation.z = -Math.PI / 2;
    vNose.position.set(150, 0, 125);
    visionGroup.add(vNose);

    visionGroup.visible = false;
    scene.add(visionGroup);
}

// -----------------------------------------------------------------------------
// CONNEXION WEBSOCKET ET RÉCEPTION DE LA TÉLÉMÉTRIE
// -----------------------------------------------------------------------------
function setupWebSocket() {
    // Réutilisation du socket partagé de common.js pour éviter une double connexion réseau
    if (window.socket) {
        console.log("[MAP 3D] Utilisation du WebSocket partagé (window.socket)");
        window.socket.on('state_update', (state) => {
            if (!state) return;
            if (state.team && state.team !== currentTeam) {
                currentTeam = state.team;
                updateTeamColor();
            }
            if (state.obstacle_detected !== undefined) {
                obstacleDetected = state.obstacle_detected;
                obstacleType = state.obstacle_type;
            }
            if (state.telemetry) {
                robotPos = {
                    x: state.telemetry.x,
                    y: state.telemetry.y,
                    theta: state.telemetry.theta // Télémétrie odométrie roues en degrés
                };
                updateRobotMeshPosition(robotGroup, robotPos);
                updateUI();
            }
            if (state.vision_pose && state.vision_pose.detected !== undefined) {
                visionPos = {
                    x: state.vision_pose.x,
                    y: state.vision_pose.y,
                    theta: state.vision_pose.theta,
                    detected: state.vision_pose.detected
                };
                if (visionGroup) {
                    visionGroup.visible = visionPos.detected;
                    if (visionPos.detected) {
                        updateRobotMeshPosition(visionGroup, visionPos);
                    }
                }
                updateUI();
            }
        });

        window.socket.on('vision_update', (data) => {
            if (!data) return;
            visionPos = {
                x: data.x,
                y: data.y,
                theta: data.theta, // Caméra zénithale en degrés
                detected: data.detected
            };
            if (visionGroup) {
                visionGroup.visible = data.detected;
                if (data.detected) {
                    updateRobotMeshPosition(visionGroup, visionPos);
                }
            }
            updateUI();
        });

        window.socket.on('lidar_frame', (data) => {
            if (data) updateLidarFrame(data);
        });
        return;
    }

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

                // Détection d'obstacle par le LiDAR
                if (state.obstacle_detected !== undefined) {
                    obstacleDetected = state.obstacle_detected;
                    obstacleType = state.obstacle_type;
                }

                // Télémétrie odométrique
                if (state.telemetry) {
                    robotPos = {
                        x: state.telemetry.x,
                        y: state.telemetry.y,
                        theta: state.telemetry.theta // en degrés
                    };

                    updateRobotMeshPosition(robotGroup, robotPos);
                    updateUI();
                }

                if (state.vision_pose && state.vision_pose.detected !== undefined) {
                    visionPos = {
                        x: state.vision_pose.x,
                        y: state.vision_pose.y,
                        theta: state.vision_pose.theta,
                        detected: state.vision_pose.detected
                    };
                    if (visionGroup) {
                        visionGroup.visible = visionPos.detected;
                        if (visionPos.detected) {
                            updateRobotMeshPosition(visionGroup, visionPos);
                        }
                    }
                    updateUI();
                }
            }
            
            // 2. Traitement de la position Vision Zénithale
            if (msg.type === "vision_update" && msg.data) {
                visionPos = {
                    x: msg.data.x,
                    y: msg.data.y,
                    theta: msg.data.theta, // en degrés
                    detected: msg.data.detected
                };
                if (visionGroup) {
                    visionGroup.visible = msg.data.detected;
                    if (msg.data.detected) {
                        updateRobotMeshPosition(visionGroup, visionPos);
                    }
                }
                updateUI();
            }

            // 3. Traitement de la trame LiDAR brute (obstacle le plus proche)
            if (msg.type === "lidar_frame" && msg.data) {
                updateLidarFrame(msg.data);
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
    if (!group || !pos) return;

    const p = robotToThree(pos.x, pos.y);
    group.position.x = p.x;
    group.position.y = p.y;

    // pos.theta est en DEGRÉS, Three.js attend des RADIANS
    // theta = 0 (X robot) pointe vers -Y_three, d'où le décalage de -90°
    const thetaRad = ((pos.theta || 0) * Math.PI) / 180;
    group.rotation.z = thetaRad - Math.PI / 2;
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
    
    // Affichage utilisateur (Longueur X et Largeur Y physique du robot, orientation en degrés)
    const thetaDeg = robotPos ? (robotPos.theta || 0) : 0;
    let txt = `ROBOT | X: ${robotPos.x.toFixed(0)} mm | Y: ${robotPos.y.toFixed(0)} mm | θ: ${thetaDeg.toFixed(1)}°`;
    
    if (visionPos && visionPos.detected) {
        txt += `  ·  VISION | X: ${visionPos.x.toFixed(0)} | Y: ${visionPos.y.toFixed(0)} | θ: ${(visionPos.theta || 0).toFixed(1)}°`;
    }

    if (obstacleDetected) {
        let typeStr = "360°";
        if (obstacleType === 2) typeStr = "AVANT";
        else if (obstacleType === 3) typeStr = "ARRIÈRE";
        txt += `  ·  🛑 OBSTACLE DÉTECTÉ (${typeStr})`;
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
            const { x: targetX, y: targetY } = threeToRobot(pt);
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
            const { x: targetX, y: targetY } = threeToRobot(pt);

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

    // Effet visuel clignotant rouge si un obstacle est détecté
    if (robotMaterial) {
        if (obstacleDetected) {
            const time = Date.now() * 0.005;
            const pulse = 0.5 + 0.5 * Math.sin(time); // Pulse de 0 à 1
            const baseColor = (currentTeam === 'JAUNE') ? 0xffa600 : 0x007bff;
            const targetColor = 0xff3333; // Rouge vif
            
            // Interpolation linéaire entre la couleur d'équipe et le rouge
            robotMaterial.color.setHex(baseColor).lerp(new THREE.Color(targetColor), pulse);
        } else {
            // Rétablir la couleur normale de l'équipe
            const teamColor = (currentTeam === 'JAUNE') ? 0xffa600 : 0x007bff;
            robotMaterial.color.setHex(teamColor);
        }
    }

    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}

// -----------------------------------------------------------------------------
// AFFICHAGE DE L'OBSTACLE LIDAR LE PLUS PROCHE
// -----------------------------------------------------------------------------
function updateLidarFrame(data) {
    if (!lidarScanGroup) return;

    // Nettoyer les anciens tracés de la trame LiDAR précédente
    while (lidarScanGroup.children.length > 0) {
        const obj = lidarScanGroup.children[0];
        lidarScanGroup.remove(obj);
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
            if (Array.isArray(obj.material)) {
                obj.material.forEach(m => m.dispose());
            } else {
                obj.material.dispose();
            }
        }
    }

    const currentRobotPos = robotPos;
    if (!currentRobotPos) return;

    // Fonction d'aide pour transformer la position relative (polaire) en coordonnées mondiales Three.js
    function getGlobalCoords(relAngleDeg, relDistMm) {
        // Angle relatif en radians
        const relAngleRad = (relAngleDeg * Math.PI) / 180;
        // Angle absolu dans le repère de la carte (currentRobotPos.theta est en degrés)
        const robotThetaRad = ((currentRobotPos.theta || 0) * Math.PI) / 180;
        const globalAngleRad = robotThetaRad + relAngleRad;
        
        const globalX = currentRobotPos.x + relDistMm * Math.cos(globalAngleRad);
        const globalY = currentRobotPos.y + relDistMm * Math.sin(globalAngleRad);
        
        return robotToThree(globalX, globalY);
    }

    // 1. Tracer l'obstacle le plus proche
    if (data.obstacle && data.obstacle.distance > 0 && data.obstacle.distance < 90000) {
        const pt = getGlobalCoords(data.obstacle.angle, data.obstacle.distance);
        
        // Sphère rouge brillante pour l'obstacle
        const obsGeo = new THREE.SphereGeometry(20, 16, 16);
        const obsMat = new THREE.MeshBasicMaterial({ color: 0xff3333, transparent: true, opacity: 0.8 });
        const obsMesh = new THREE.Mesh(obsGeo, obsMat);
        obsMesh.position.set(pt.x, pt.y, 15);
        lidarScanGroup.add(obsMesh);

        // Anneau d'avertissement autour de l'obstacle
        const ringGeo = new THREE.RingGeometry(30, 35, 32);
        const ringMat = new THREE.MeshBasicMaterial({ color: 0xff3333, side: THREE.DoubleSide, transparent: true, opacity: 0.5 });
        const ringMesh = new THREE.Mesh(ringGeo, ringMat);
        ringMesh.position.set(pt.x, pt.y, 2);
        lidarScanGroup.add(ringMesh);
    }
}
