// Carte 3D : bascule 2D / 3D, redimensionnement, boucle de rendu.
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

// -----------------------------------------------------------------------------
// BASCULE DE VUE (2D DESSUS / 3D PERSPECTIVE)
// -----------------------------------------------------------------------------
function toggleViewMode() {
    isTopDown = !isTopDown;
    const toggleBtn = document.getElementById('btn-view-toggle');
    
    if (isTopDown) {
        if (toggleBtn) toggleBtn.innerHTML = icon('rotate-ccw') + " Vue 3D (Orbite)";
        controls.enableRotate = false; // Bloque la rotation pour la vue plan 2D
        
        // Positionne la caméra juste au-dessus du centre (Y très légèrement décalé pour éviter le blocage de cardan)
        animateCamera(new THREE.Vector3(0, -0.01, 2500), new THREE.Vector3(0, 0, 0));
    } else {
        if (toggleBtn) toggleBtn.innerHTML = icon('map') + " Vue 2D (Dessus)";
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
