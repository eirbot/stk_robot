// Carte 3D : souris (coordonnées sous le curseur, double-clic = GoTo, marqueur de cible).
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

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
