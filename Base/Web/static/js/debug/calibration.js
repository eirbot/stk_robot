// Debug > Robot : calibration automatique de la fusion odométrie + caméra (Rasp/strat/calibration.py).
// Le robot fait sa séquence (carrés, rotations, lignes droites), analyse l'enregistrement et renvoie
// un événement « calibration » : progression, puis réglages vision_odom proposés (bouton Appliquer).

let calibProposition = null;

async function calibCommande(cmd) {
    const cote = parseFloat(document.getElementById('calib-cote').value) || 500;
    await fetch('/api/robot/hardware', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'calibration', data: { cmd: cmd, cote_mm: cote } })
    });
    if (cmd === 'start') {
        document.getElementById('calib-etat').textContent = 'Demande envoyée…';
        document.getElementById('calib-resultat').innerHTML = '';
    }
}

async function calibAppliquer() {
    if (!calibProposition) return;
    for (const [k, v] of Object.entries(calibProposition)) {
        await fetch('/api/config_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'vision_odom.' + k, val: v })
        });
    }
    document.getElementById('calib-etat').textContent = 'Réglages appliqués (vision_odom)';
}

function calibFmt(v, unite = '', nd = 1) {
    return (v === null || v === undefined) ? '?' : Number(v).toFixed(nd) + unite;
}

function calibAfficherResultat(r) {
    calibProposition = r.proposition || {};
    const lignes = [
        ['Images caméra / trames odo', `${r.images ?? '?'} / ${r.trames_odo ?? '?'}`],
        ['Latence caméra', calibFmt(r.latence_s, ' s', 3)],
        ['Bruit caméra immobile', r.bruit_camera ? `${calibFmt(r.bruit_camera[0], ' mm')} / ${calibFmt(r.bruit_camera[1], '°', 2)}` : '?'],
        ['Erreur distances (odo)', calibFmt(r.erreur_distance_pct, ' %', 2)],
        ['Erreur rotations (odo)', calibFmt(r.erreur_rotation_pct, ' %', 2)],
    ];
    const rej = (x) => x ? `${x.acceptees ?? '?'} acc. / ${x.rejetees ?? '?'} rej., NIS ${calibFmt(x.nis_moyen, '', 2)}` : '?';
    lignes.push(['Rejeu actuel', rej(r.rejeu_actuel)], ['Rejeu proposé', rej(r.rejeu_propose)]);
    let firmware = '';
    if (Math.abs(r.erreur_distance_pct || 0) > 1 || Math.abs(r.erreur_rotation_pct || 0) > 1) {
        firmware = `<p class="hint">Firmware : diamètre des roues × ${r.facteur_diametre}, entraxe × ${r.facteur_entraxe}, puis refaire une calibration.</p>`;
    }
    const prop = Object.entries(calibProposition).map(([k, v]) => `<code>${escapeHtml(k)} = ${escapeHtml(String(v))}</code>`).join('<br>');
    document.getElementById('calib-resultat').innerHTML =
        `<table class="calib-table">${lignes.map(([a, b]) => `<tr><td>${a}</td><td>${escapeHtml(b)}</td></tr>`).join('')}</table>` +
        firmware +
        (prop ? `<div class="calib-prop">${prop}</div><button class="btn btn-success" onclick="calibAppliquer()">Appliquer ces réglages</button>` : '');
}

window.socket.on('calibration', (d) => {
    if (!d) return;
    const etat = document.getElementById('calib-etat');
    const barre = document.getElementById('calib-progression');
    if (d.progression !== undefined) barre.value = d.progression;
    if (d.etat === 'en_cours') etat.textContent = d.etape ? `En cours : ${d.etape}` : 'En cours…';
    if (d.etat === 'erreur' || d.etat === 'fini') etat.textContent = d.message || d.etat;
    if (d.etat === 'fini' && d.resultat) calibAfficherResultat(d.resultat);
});
