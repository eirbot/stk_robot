// Page Mises à jour (« Windows Update ») : état du dépôt de la base, des versions déployées
// (serveur de la base, code du robot) et installation avec journal en direct (cf. winupdate.go).

let wuStatus = null;
let wuSince = 0;
let wuPoll = null;

const $ = (id) => document.getElementById(id);
const short = (v) => (v || '').split(' ')[0] || 'inconnue';

function fmtDate(iso) {
    if (!iso || iso.startsWith('0001')) return 'jamais';
    const d = new Date(iso);
    return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

// Une ligne de la liste : case à cocher, titre, importance, description
function item(target, title, level, desc, checked) {
    return `<label class="wu-item">
        <input type="checkbox" data-target="${target}"${checked ? ' checked' : ''}>
        <span class="wu-item-body">
            <span class="wu-item-title">${escapeHtml(title)} <span class="wu-level wu-level-${level}">${level === 'critique' ? 'Critique' : 'Recommandée'}</span></span>
            <span class="wu-item-desc">${escapeHtml(desc)}</span>
        </span>
    </label>`;
}

function render(st) {
    wuStatus = st;
    setText($('wu-branch'), st.upstream ? `${st.branch} → ${st.upstream}` : (st.branch || '?'));
    setText($('wu-head'), st.head + (st.dirty ? ' (modifié)' : ''));
    setText($('wu-base'), short(st.base_version) + (st.base_outdated ? ' — en retard' : ''));
    setText($('wu-robot'), st.robot_commit ? st.robot_commit + (st.robot_outdated ? ' — en retard' : '') : 'inconnu (robot hors ligne ?)');
    setText($('wu-checked'), fmtDate(st.checked_at) + (st.checked_at && !st.online ? ' (échec)' : ''));

    const notes = [];
    if (st.fetch_error) notes.push(['warn', `GitHub injoignable : ${st.fetch_error.split('\n').pop()}. Les versions déployées sont quand même comparées au dépôt de la base.`]);
    if (!st.upstream) notes.push(['warn', 'La branche de la base ne suit aucune branche distante : impossible de chercher des mises à jour.']);
    if (st.dirty) notes.push(['warn', 'Fichiers modifiés à la main sur la base : git pull risque d\'échouer.']);
    if (st.ahead > 0) notes.push(['info', `La base a ${st.ahead} commit(s) qui ne sont pas sur GitHub.`]);
    if (st.touches_esp) notes.push(['info', 'Le firmware des ESP a changé : à flasher ensuite depuis Debug (menu Outils).']);
    $('wu-notes').innerHTML = notes.map(([k, t]) => `<div class="wu-note wu-note-${k}">${escapeHtml(t)}</div>`).join('');

    const items = [];
    const n = st.behind;
    if (st.touches_base || st.base_outdated) {
        items.push(item('base', 'Serveur de la base', 'critique', st.touches_base
            ? `${n} commit(s) à récupérer modifient Base/ : téléchargement, compilation puis redémarrage de la base (l'interface se coupe quelques secondes).`
            : `Le serveur tourne en ${short(st.base_version)}, le dépôt est en ${st.head} : recompilation puis redémarrage.`, true));
    }
    if (st.touches_robot || st.robot_outdated) {
        items.push(item('robot', 'Code du robot', 'recommandee', st.touches_robot
            ? `${n} commit(s) à récupérer modifient Rasp/ : copie vers le robot et redémarrage de son programme.`
            : `Le robot tourne en ${st.robot_commit}, le dépôt est en ${st.head} : copie vers le robot.`, true));
    }
    if (n > 0 && !items.length) {
        items.push(item('depot', 'Fichiers du dépôt', 'recommandee', `${n} commit(s) sans effet sur la base ni le robot (docs, outils) : simple téléchargement.`, true));
    }
    $('wu-list').innerHTML = items.length ? items.join('')
        : `<p class="wu-uptodate">${st.online || !st.checked_at ? 'Votre ordinateur est à jour.' : 'Rien à installer avec ce que la base connaît.'}</p>`;

    const commits = st.commits || [];
    $('wu-commits').hidden = !commits.length;
    setText($('wu-commits-title'), `Détails des modifications (${commits.length} commit${commits.length > 1 ? 's' : ''})`);
    $('wu-commits-body').innerHTML = commits.map(c => `<tr><td><code>${escapeHtml(c.hash)}</code></td><td>${escapeHtml(c.author)}</td><td>${escapeHtml(fmtDate(c.date))}</td><td>${escapeHtml(c.subject)}</td></tr>`).join('');
    updateSelection();
}

function selectedTargets() {
    return Array.from(document.querySelectorAll('#wu-list input[type=checkbox]:checked')).map(c => c.dataset.target);
}

function updateSelection() {
    const t = selectedTargets();
    const busy = wuPoll !== null;
    $('wu-install').disabled = busy || !t.length;
    setText($('wu-selection'), t.length ? `${t.length} mise(s) à jour sélectionnée(s)` : '');
}

async function loadStatus(fetchRemote) {
    const btn = $('wu-check');
    if (fetchRemote) {
        btn.disabled = true;
        $('wu-list').innerHTML = '<p class="wu-searching">Recherche de mises à jour disponibles…</p>';
    }
    try {
        const r = await fetch(fetchRemote ? '/api/update/check' : '/api/update/status');
        const b = await r.json();
        if (!r.ok) throw new Error(b.msg || ('Erreur ' + r.status));
        render(b);
    } catch (e) {
        toast(e.message || 'Base injoignable', 'err');
        if (wuStatus) render(wuStatus);
    } finally {
        btn.disabled = false;
    }
}

// --- Installation ---

function showProgress(label) {
    $('wu-progress').hidden = false;
    setText($('wu-progress-label'), label);
}

function appendLog(lines) {
    if (!lines || !lines.length) return;
    const log = $('wu-log');
    log.textContent += lines.join('\n') + '\n';
    log.scrollTop = log.scrollHeight;
}

async function install() {
    const targets = selectedTargets();
    if (!targets.length) return;
    const names = { base: 'le serveur de la base', robot: 'le code du robot', depot: 'les fichiers du dépôt' };
    const what = targets.map(t => names[t]).join(' et ');
    const warn = targets.includes('base') ? '\n\nLa base va redémarrer : l\'interface sera coupée quelques secondes.' : '';
    if (!await askConfirm(`Installer ${what} ?${warn}`)) return;

    const r = await fetch('/api/update/install', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets })
    });
    const b = await r.json().catch(() => ({}));
    if (!r.ok) { alert(b.msg || ('Erreur ' + r.status)); return; }
    $('wu-log').textContent = '';
    wuSince = 0;
    startPolling();
}

function startPolling() {
    showProgress('Installation des mises à jour…');
    $('wu-bar').classList.add('is-busy');
    clearInterval(wuPoll);
    wuPoll = setInterval(pollJob, 700);
    updateSelection();
    pollJob();
}

function stopPolling() {
    clearInterval(wuPoll);
    wuPoll = null;
    $('wu-bar').classList.remove('is-busy');
    updateSelection();
}

async function pollJob() {
    let b;
    try {
        b = await (await fetch('/api/update/job?since=' + wuSince)).json();
    } catch (e) {
        return; // base en train de redémarrer : on réessaie
    }
    const j = b.job;
    if (!j) { stopPolling(); return; }
    appendLog(j.lines);
    wuSince = b.next;
    if (j.running) return;
    stopPolling();
    if (j.restarting) { waitRestart(); return; }
    if (j.ok) {
        showProgress('Installation terminée.');
        toast('Mises à jour installées', 'ok');
    } else {
        showProgress('L\'installation a échoué.');
        alert(`Erreur : ${j.error}`);
    }
    loadStatus(false);
}

// La base redémarre : attendre qu'elle réponde avec une autre version, puis recharger
async function waitRestart() {
    const before = wuStatus ? wuStatus.base_version : '';
    showProgress('Redémarrage de la base… Ne pas éteindre l\'ordinateur.');
    $('wu-bar').classList.add('is-busy');
    const t0 = Date.now();
    const tick = async () => {
        try {
            const v = await (await fetch('/api/version', { cache: 'no-store' })).json();
            if (v.base && v.base !== before) {
                showProgress(`Base redémarrée en ${short(v.base)}.`);
                setTimeout(() => location.reload(), 1200);
                return;
            }
        } catch (e) { /* pas encore revenue */ }
        if (Date.now() - t0 > 180000) {
            $('wu-bar').classList.remove('is-busy');
            showProgress('La base ne répond pas après 3 minutes : vérifier le service base_stk.');
            return;
        }
        setTimeout(tick, 1500);
    };
    setTimeout(tick, 2500);
}

document.addEventListener('DOMContentLoaded', async () => {
    $('wu-check').addEventListener('click', () => loadStatus(true));
    $('wu-install').addEventListener('click', install);
    $('wu-list').addEventListener('change', updateSelection);
    await loadStatus(false);
    // Une installation lancée depuis un autre appareil est peut-être en cours
    try {
        const b = await (await fetch('/api/update/job?since=0')).json();
        if (b.job && b.job.running) startPolling();
    } catch (e) { /* rien */ }
});
