// Page Debug : test de la liaison base <-> robot (latence, pertes, débit).
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

// --- DIAGNOSTIC RÉSEAU ---
// 1. Base <-> robot : allers-retours ZMQ faits par la base (/api/robot_ping) : le lien des commandes
// 2. Navigateur <-> base : allers-retours HTTP
// 3-4. Débits navigateur <-> base (flux caméra, mises à jour)
// Chaque requête a un délai maximum ; la base refuse les tests pendant un match (409).

class DiagAbort extends Error {}

// fetch avec délai maximum
async function fetchT(url, opts = {}, ms = 2000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
        const r = await fetch(url, { ...opts, signal: ctrl.signal, cache: 'no-store' });
        if (r.status === 409) throw new DiagAbort('Test impossible pendant un match.');
        return r;
    } finally {
        clearTimeout(timer);
    }
}

// Note d'un lien d'après ses pics (p95) et ses pertes : [texte, classe]
function rateLatency(p95, lossPct, seuils) {
    let i = p95 < seuils[0] ? 0 : p95 < seuils[1] ? 1 : p95 < seuils[2] ? 2 : 3;
    if (lossPct > 0) i = Math.max(i, 2);
    if (lossPct > 10) i = 3;
    return [['Excellent', 'excellent'], ['Bon', 'good'], ['Moyen', 'fair'], ['Mauvais', 'poor']][i];
}

function rateSpeed(mbps) {
    // Le flux caméra MJPEG demande quelques Mbps ; au-delà de 20, rien à gagner
    if (mbps >= 20) return ['Excellent', 'excellent'];
    if (mbps >= 8) return ['Bon', 'good'];
    if (mbps >= 3) return ['Moyen', 'fair'];
    return ['Faible', 'poor'];
}

function percentile(values, p) {
    const s = [...values].sort((a, b) => a - b);
    return s[Math.max(0, Math.ceil(p * s.length) - 1)];
}

function setDiagBox(id, value, unit, rating, detail) {
    document.getElementById(id).innerHTML = `${value} <span>${unit}</span>`;
    const st = document.getElementById(id + '-status');
    st.textContent = rating ? rating[0] + (detail ? ` (${detail})` : '') : (detail || '-');
    st.className = 'test-stat-status' + (rating ? ' status-text-' + rating[1] : '');
}

async function runDiagnosticTest() {
    const btn = document.getElementById('btn-run-speedtest');
    const progressContainer = document.getElementById('test-progress-container');
    const progressBar = document.getElementById('test-progress-bar');
    const statusMsg = document.getElementById('test-status-msg');
    const progress = (pct) => { progressBar.style.width = `${pct}%`; };
    const say = (text, err) => {
        statusMsg.textContent = text;
        statusMsg.classList.toggle('test-status-err', !!err);
    };

    for (const [id, unit] of [['test-robot', 'ms'], ['test-latency', 'ms'], ['test-download', 'Mbps'], ['test-upload', 'Mbps']]) {
        setDiagBox(id, '--', unit, null, '-');
    }
    btn.disabled = true;
    btn.textContent = 'Test en cours…';
    progressContainer.style.display = 'block';
    progress(0);

    try {
        // --- 1. BASE <-> ROBOT ---
        say('Lien base ↔ robot (30 allers-retours)…');
        const r = await fetchT('/api/robot_ping?n=30', {}, 20000);
        if (r.status === 503) {
            setDiagBox('test-robot', '--', 'ms', ['Hors ligne', 'poor'], '');
        } else {
            const rp = await r.json();
            if (rp.received === 0) {
                setDiagBox('test-robot', '--', 'ms', ['Aucune réponse', 'poor'], '');
            } else {
                setDiagBox('test-robot', rp.avg_ms.toFixed(1), 'ms', rateLatency(rp.p95_ms, rp.loss_pct, [10, 30, 80]),
                    `pics ${rp.p95_ms.toFixed(0)} ms, max ${rp.max_ms.toFixed(0)} ms, pertes ${rp.loss_pct.toFixed(0)} %`);
            }
        }
        progress(30);

        // --- 2. NAVIGATEUR <-> BASE ---
        say('Lien navigateur ↔ base (20 allers-retours)…');
        const lat = [];
        let lost = 0;
        const n = 20;
        for (let i = 0; i < n; i++) {
            const t0 = performance.now();
            try {
                await fetchT(`/api/ping?t=${Date.now()}`, {}, 1000);
                lat.push(performance.now() - t0);
            } catch (e) {
                if (e instanceof DiagAbort) throw e;
                lost++;
            }
            progress(30 + (i + 1) / n * 20);
            await new Promise(res => setTimeout(res, 30));
        }
        if (lat.length === 0) throw new Error('La base ne répond plus.');
        const avg = lat.reduce((a, b) => a + b, 0) / lat.length;
        const p95 = percentile(lat, 0.95), lossPct = 100 * lost / n;
        setDiagBox('test-latency', avg.toFixed(1), 'ms', rateLatency(p95, lossPct, [15, 40, 100]),
            `pics ${p95.toFixed(0)} ms, pertes ${lossPct.toFixed(0)} %`);

        // --- 3. DÉBIT DESCENDANT (2 s) ---
        say('Débit descendant…');
        let bytesRead = 0;
        const dlStart = performance.now();
        const ctrl = new AbortController();
        const stop = setTimeout(() => ctrl.abort(), 2000);
        try {
            const dl = await fetch(`/api/speedtest/download?t=${Date.now()}`, { signal: ctrl.signal, cache: 'no-store' });
            if (dl.status === 409) throw new DiagAbort('Test impossible pendant un match.');
            const reader = dl.body.getReader();
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                bytesRead += value.length;
                progress(50 + Math.min(25, (performance.now() - dlStart) / 2000 * 25));
            }
        } catch (e) {
            if (e.name !== 'AbortError') throw e;
        } finally {
            clearTimeout(stop);
        }
        const dlMbps = bytesRead * 8 / ((performance.now() - dlStart) / 1000) / 1e6;
        setDiagBox('test-download', dlMbps.toFixed(1), 'Mbps', rateSpeed(dlMbps));

        // --- 4. DÉBIT MONTANT (2 s, blocs de 1 Mo aléatoires : incompressibles) ---
        say('Débit montant…');
        const block = new Uint8Array(1024 * 1024);
        for (let i = 0; i < block.length; i += 65536) crypto.getRandomValues(block.subarray(i, i + 65536));
        let sent = 0;
        const ulStart = performance.now();
        while (performance.now() - ulStart < 2000) {
            const up = await fetchT('/api/speedtest/upload', { method: 'POST', body: block }, 3000);
            await up.json();
            sent += block.length;
            progress(75 + Math.min(25, (performance.now() - ulStart) / 2000 * 25));
        }
        const ulMbps = sent * 8 / ((performance.now() - ulStart) / 1000) / 1e6;
        setDiagBox('test-upload', ulMbps.toFixed(1), 'Mbps', rateSpeed(ulMbps));

        progress(100);
        say('Diagnostic terminé.');
    } catch (err) {
        const msg = err instanceof DiagAbort ? err.message
            : err.name === 'AbortError' ? 'La base ne répond pas (délai dépassé).'
            : `Erreur de connexion : ${err.message}`;
        say(msg, true);
        toast(msg, 'err');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Lancer le test de connexion';
        setTimeout(() => { progressContainer.style.display = 'none'; }, 3000);
    }
}
