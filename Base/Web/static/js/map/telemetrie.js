// Carte 3D : réception de l'état du robot (WebSocket) et mise à jour de la scène.
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

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
    group.rotation.z = EirbotFrames.thetaToThreeRad(pos.theta);
}

function updateTeamColor() {
    if (robotMaterial) {
        const teamColor = (currentTeam === 'JAUNE') ? 0xffa600 : 0x007bff;
        robotMaterial.color.setHex(teamColor);
    }
    if (footprintMaterial) footprintMaterial.color.setHex((currentTeam === 'JAUNE') ? 0xffa600 : 0x007bff);
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
        txt += `  ·  ${icon('triangle-alert')} OBSTACLE DÉTECTÉ (${typeStr})`;
    }
    el.innerHTML = txt; // texte calculé (nombres) + icône éventuelle
}
