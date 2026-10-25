// Carte 3D : ce que voit le planificateur de trajectoire.
//   « plan » (base : Base/Planif, ou robot en secours) : chemin suivi ;
//   « carte_planif » (base, 2 Hz) : carte de coûts (orange = surcoût, rouge = interdit), trajectoires
//   prédites des adversaires (points de plus en plus pâles, anneau = incertitude) ;
//   vision_update (caméra zénithale, 10 Hz) : robots adverses et pierres, empilées selon la hauteur du
//   tag (nb), avec le nombre au-dessus de la pile.
// Fichiers de la carte chargés dans l'ordre par templates/map.html (portée globale partagée).

let planGroup = null;
let advGroup = null;
let carteGroup = null;
let pierresGroup = null;
let dernieresPierres = '';

function initPlanGroups() {
    if (planGroup || typeof scene === 'undefined' || !scene) return;
    planGroup = new THREE.Group();
    advGroup = new THREE.Group();
    carteGroup = new THREE.Group();
    pierresGroup = new THREE.Group();
    scene.add(pierresGroup);
    scene.add(planGroup);
    scene.add(advGroup);
    scene.add(carteGroup);
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
        planGroup.add(heatMapMesh(data.grille, data.pas_mm));   // plan du robot (secours) : sa carte
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

function updateCartePlanif(data) {
    initPlanGroups();
    if (!carteGroup || !data) return;
    viderGroupe(carteGroup);
    if (Array.isArray(data.grille) && data.grille.length && data.pas_mm) {
        carteGroup.add(heatMapMesh(data.grille, data.pas_mm));
    }
    // Trajectoires prédites (filtre de Kalman de la base) : t, x, y, sigma
    (data.predictions || []).forEach(p => {
        const n = p.trajectoire.length;
        p.trajectoire.forEach(([t, x, y, sig], k) => {
            const q = robotToThree(x, y);
            const a = 0.9 * (1 - k / (n + 1));
            const pt = new THREE.Mesh(new THREE.SphereGeometry(22, 10, 10),
                new THREE.MeshBasicMaterial({ color: 0xff3b3b, transparent: true, opacity: a }));
            pt.position.set(q.x, q.y, 30);
            carteGroup.add(pt);
            if (k % 4 === 0 && sig > 30) {
                const ring = new THREE.Mesh(new THREE.RingGeometry(sig - 6, sig, 40),
                    new THREE.MeshBasicMaterial({ color: 0xff3b3b, transparent: true, opacity: a * 0.5, side: THREE.DoubleSide }));
                ring.position.set(q.x, q.y, 6);
                carteGroup.add(ring);
            }
        });
    });
}

// Pierres : boîtes 320 x 110 x 110 mm posées à plat, theta = axe long ; nb = pierres dans la pile
const HAUTEUR_PIERRE = 110;
const pierreGeo = () => new THREE.BoxGeometry(320, 110, HAUTEUR_PIERRE);
const PIERRE_COULEURS = [0xc8a165, 0xb08850, 0xd9b37a];

function etiquette(texte) {
    const cv = document.createElement('canvas');
    cv.width = 64; cv.height = 64;
    const c = cv.getContext('2d');
    c.fillStyle = 'rgba(0,0,0,0.65)';
    c.beginPath(); c.arc(32, 32, 30, 0, 2 * Math.PI); c.fill();
    c.fillStyle = '#ffffff';
    c.font = 'bold 38px sans-serif';
    c.textAlign = 'center'; c.textBaseline = 'middle';
    c.fillText(texte, 32, 34);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), depthTest: false }));
    sp.scale.set(90, 90, 1);
    return sp;
}

function updatePierres(liste) {
    initPlanGroups();
    if (!pierresGroup) return;
    const cle = JSON.stringify(liste || []);
    if (cle === dernieresPierres) return;          // 10 Hz : on ne reconstruit que si ça change
    dernieresPierres = cle;
    viderGroupe(pierresGroup);
    (liste || []).forEach(p => {
        const q = robotToThree(p.x, p.y);
        const nb = Math.max(1, Math.min(6, p.nb || 1));
        for (let k = 0; k < nb; k++) {
            const m = new THREE.Mesh(pierreGeo(), new THREE.MeshLambertMaterial({ color: PIERRE_COULEURS[k % 3] }));
            m.position.set(q.x, q.y, HAUTEUR_PIERRE * (k + 0.5));
            m.rotation.z = ((p.theta || 0) - 90) * Math.PI / 180;   // même convention que thetaToThreeRad (frames.js)
            pierresGroup.add(m);
        }
        const e = etiquette(String(nb));
        e.position.set(q.x, q.y, HAUTEUR_PIERRE * nb + 70);
        pierresGroup.add(e);
    });
}

window.socket.on('plan', updatePlan);
window.socket.on('carte_planif', updateCartePlanif);
window.socket.on('vision_update', (d) => {
    updateAdversaires(d && d.detected ? d.adversaires : []);
    if (d && d.detected && Array.isArray(d.pierres)) updatePierres(d.pierres);
});
