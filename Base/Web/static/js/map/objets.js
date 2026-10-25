// Carte 3D : table et robots (modèles MuJoCo, boîtes de secours).
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

// -----------------------------------------------------------------------------
// CONSTRUCTION DES OBJETS DE LA SCÈNE
// -----------------------------------------------------------------------------
function createTable() {
    // Table simplifiée (boîtes), remplacée par le modèle MuJoCo dès qu'il est chargé
    const fallback = new THREE.Group();
    scene.add(fallback);

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
    fallback.add(tableMesh);

    // Bordures de la table (tasseaux protecteurs de 70 mm de haut)
    const borderMat = new THREE.MeshStandardMaterial({ color: 0x090a0d, roughness: 0.9 });
    const borderGeoLong = new THREE.BoxGeometry(TABLE_L_MM + 20, 10, 70);
    const borderGeoWide = new THREE.BoxGeometry(10, TABLE_W_MM, 70);

    const borderSouth = new THREE.Mesh(borderGeoLong, borderMat);
    borderSouth.position.set(0, -TABLE_W_MM / 2 - 5, 15);
    fallback.add(borderSouth);

    const borderNorth = new THREE.Mesh(borderGeoLong, borderMat);
    borderNorth.position.set(0, TABLE_W_MM / 2 + 5, 15);
    fallback.add(borderNorth);

    const borderWest = new THREE.Mesh(borderGeoWide, borderMat);
    borderWest.position.set(-TABLE_L_MM / 2 - 5, 0, 15);
    fallback.add(borderWest);

    const borderEast = new THREE.Mesh(borderGeoWide, borderMat);
    borderEast.position.set(TABLE_L_MM / 2 + 5, 0, 15);
    fallback.add(borderEast);

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

    loadMujocoTable(fallback, gridGroup);
}

// Repère des modèles MuJoCo = repère table/robot en mètres (x 0..2, y -1,5..1,5).
// Vers la scène : X_three = Y_robot, Y_three = 1000 - X_robot, soit une rotation de -90°
// autour de Z puis une translation de +1000 en Y (cf. robotToThree).
function loadMujocoTable(fallback, gridGroup) {
    if (!window.EirbotMujoco) return;
    EirbotMujoco.load('/models/table/table.xml', { shadows: true }).then(model => {
        model.scale.setScalar(1000);
        model.rotation.z = -Math.PI / 2;
        model.position.set(0, TABLE_W_MM / 2, 0);
        scene.add(model);
        scene.remove(fallback);
        gridGroup.visible = false;  // le tapis de jeu du modèle remplace le quadrillage
        console.log("[MAP 3D] Table MuJoCo chargée");
    }).catch(e => console.warn("[MAP 3D] Modèle de table indisponible, table simplifiée :", e));
}

// Corps simplifié aux vraies dimensions (EirbotFrames.ROBOT) : l'axe des roues (origine du
// groupe, X local = avant) est à 102 mm de l'arrière et 245,5 mm de l'avant
function robotBox(material, noseMaterial) {
    const R = EirbotFrames.ROBOT;
    const group = new THREE.Group();
    const length = R.FRONT_MM + R.BACK_MM;
    const body = new THREE.Mesh(new THREE.BoxGeometry(length, 2 * R.HALF_WIDTH_MM, 250), material);
    body.position.set((R.FRONT_MM - R.BACK_MM) / 2, 0, 125);
    body.castShadow = body.receiveShadow = true;
    group.add(body);
    // Nez indiquant l'avant (cône pointant vers +X local)
    const nose = new THREE.Mesh(new THREE.ConeGeometry(50, 100, 4), noseMaterial);
    nose.rotation.z = -Math.PI / 2;
    nose.position.set(R.FRONT_MM, 0, 125);
    group.add(nose);
    return group;
}

// Empreinte au sol (couleur d'équipe), visible aussi sous le modèle détaillé
function robotFootprint(material) {
    const R = EirbotFrames.ROBOT;
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(R.FRONT_MM + R.BACK_MM, 2 * R.HALF_WIDTH_MM), material);
    plate.position.set((R.FRONT_MM - R.BACK_MM) / 2, 0, 1.5);
    return plate;
}

function createRobots() {
    // --- ROBOT PRINCIPAL ---
    robotGroup = new THREE.Group();
    robotMaterial = new THREE.MeshStandardMaterial({ color: 0x007bff, roughness: 0.4, metalness: 0.2 });
    const noseMat = new THREE.MeshStandardMaterial({ color: 0xff3333, roughness: 0.5 });
    const simple = robotBox(robotMaterial, noseMat);
    robotGroup.add(simple);
    footprintMaterial = new THREE.MeshBasicMaterial({ color: 0x007bff, transparent: true, opacity: 0.45 });
    robotGroup.add(robotFootprint(footprintMaterial));
    scene.add(robotGroup);

    // Modèle détaillé (31 Mo de maillages) : pas sur l'écran du robot (?mode=robot)
    const robotScreen = new URLSearchParams(window.location.search).get('mode') === 'robot';
    if (window.EirbotMujoco && !robotScreen) {
        EirbotMujoco.load('/models/robot/robot.xml', { shadows: true }).then(model => {
            model.scale.setScalar(1000);  // repère du modèle = repère robot (X avant), en mètres
            robotGroup.add(model);
            robotGroup.remove(simple);
            console.log("[MAP 3D] Robot MuJoCo chargé");
        }).catch(e => console.warn("[MAP 3D] Modèle du robot indisponible, robot simplifié :", e));
    }

    // --- ROBOT FANTÔME (VISION ZÉNITHALE) ---
    // Position vue par la caméra zénithale, en cyan semi-transparent
    visionGroup = new THREE.Group();
    visionMaterial = new THREE.MeshBasicMaterial({ color: 0x00d2ff, transparent: true, opacity: 0.35 });
    visionGroup.add(robotBox(visionMaterial, new THREE.MeshBasicMaterial({ color: 0x00d2ff, transparent: true, opacity: 0.5 })));
    visionGroup.visible = false;
    scene.add(visionGroup);
}
