// Carte 3D : chemin planifié par le robot (événement « plan », Rasp/strat/actions.py : aller), carte de
// coûts du planificateur (heat map : orange = surcoût, rouge = interdit) et robots adverses vus par la
// caméra zénithale (vision_update.adversaires).
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

let planGroup = null;
let advGroup = null;

function initPlanGroups() {
    if (planGroup || typeof scene === 'undefined' || !scene) return;
    planGroup = new THREE.Group();
    advGroup = new THREE.Group();
    scene.add(planGroup);
    scene.add(advGroup);
}

function viderGroupe(g) {
    while (g.children.length) {
        const o = g.children[0];
        g.remove(o);
        if (o.geometry) o.geometry.dispose();
        if (o.material) {
            if (o.material.map) o.material.map.dispose();
            o.material.dispose();
        }
    }
}

function heatMapMesh(grille, pas) {
    const nx = grille.length, ny = grille[0].length;   // nx le long de X (lignes), ny le long de Y
    const cv = document.createElement('canvas');
    cv.width = ny;
    cv.height = nx;
    const c = cv.getContext('2d');
    for (let i = 0; i < nx; i++) {
        for (let j = 0; j < ny; j++) {
            const v = grille[i][j];
            if (!v) continue;
            c.fillStyle = v >= 9 ? 'rgba(255,40,40,0.45)' : `rgba(255,150,0,${0.08 + 0.05 * v})`;
            c.fillRect(j, i, 1, 1);   // ligne de la toile = X (vers le bas, comme la carte), colonne = Y
        }
    }
    const tex = new THREE.CanvasTexture(cv);
    tex.magFilter = THREE.NearestFilter;
    tex.minFilter = THREE.NearestFilter;
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(ny * pas, nx * pas),
        new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }));
    const centre = robotToThree(nx * pas / 2, -1500 + ny * pas / 2);
    mesh.position.set(centre.x, centre.y, 4);
    return mesh;
}

function updatePlan(data) {
    initPlanGroups();
    if (!planGroup || !data) return;
    viderGroupe(planGroup);
    if (Array.isArray(data.grille) && data.grille.length && data.pas_mm) {
        planGroup.add(heatMapMesh(data.grille, data.pas_mm));
    }
    if (Array.isArray(data.points) && data.points.length > 1) {
        const pts = data.points.map(([x, y]) => { const p = robotToThree(x, y); return new THREE.Vector3(p.x, p.y, 12); });
        planGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
            new THREE.LineBasicMaterial({ color: 0x00e5ff })));
        pts.slice(1).forEach(p => {
            const m = new THREE.Mesh(new THREE.SphereGeometry(18, 12, 12), new THREE.MeshBasicMaterial({ color: 0x00e5ff }));
            m.position.copy(p);
            planGroup.add(m);
        });
    }
}

function updateAdversaires(liste) {
    initPlanGroups();
    if (!advGroup) return;
    viderGroupe(advGroup);
    (liste || []).forEach(a => {
        const p = robotToThree(a.x, a.y);
        const m = new THREE.Mesh(new THREE.CylinderGeometry(200, 200, 350, 32),
            new THREE.MeshBasicMaterial({ color: 0xff3b3b, transparent: true, opacity: 0.35 }));
        m.rotation.x = Math.PI / 2;   // cylindre vertical (z en haut)
        m.position.set(p.x, p.y, 175);
        advGroup.add(m);
    });
}

window.socket.on('plan', updatePlan);
window.socket.on('vision_update', (d) => updateAdversaires(d && d.detected ? d.adversaires : []));
