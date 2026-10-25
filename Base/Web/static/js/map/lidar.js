// Carte 3D : obstacle LiDAR le plus proche et points du tour (repère table, hors table retirés).
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

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

    // 2. Points du tour (Rasp/LiDAR/lidar_thread.py, déjà dans le repère table)
    if (Array.isArray(data.points) && data.points.length) {
        const pos = new Float32Array(data.points.length * 3);
        data.points.forEach(([x, y], k) => {
            const p = robotToThree(x, y);
            pos[3 * k] = p.x; pos[3 * k + 1] = p.y; pos[3 * k + 2] = 20;
        });
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        lidarScanGroup.add(new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xff5252, size: 25 })));
    }
}
