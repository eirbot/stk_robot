// Page Règlement : documents (#accueil, #jeu, #general, #score, #pdf) affichés un par un,
// navigation par l'ancre de l'URL (#jeu/points = section « points » du document « jeu »).
// En thème Windows 95, la page est un Internet Explorer : barres d'outils et d'adresse, logo animé.

const IE_HOME = 'accueil';
let ieTimer = null;

const ieDocs = () => Array.from(document.querySelectorAll('.ie-doc'));
const w95 = () => document.body.classList.contains('w95-app');

function parseHash() {
    const [doc, section] = decodeURIComponent(location.hash.replace(/^#/, '')).split('/');
    return { doc: doc || IE_HOME, section: section || '' };
}

function setStatus(text) {
    const sb = document.querySelector('.w95-sb-main');
    if (sb) sb.textContent = text;
}

// Faux chargement : logo qui tourne et barre d'état « Ouverture de la page… » (Win95 seulement)
function fakeLoad(url, done) {
    clearTimeout(ieTimer);
    const throbber = document.getElementById('ie-throbber');
    if (!w95()) { done(); return; }
    throbber.classList.add('is-busy');
    setStatus(`Ouverture de la page ${url}…`);
    ieTimer = setTimeout(() => {
        throbber.classList.remove('is-busy');
        done();
        setStatus('Terminé');
    }, 250 + Math.random() * 350);
}

function render() {
    const { doc, section } = parseHash();
    const target = document.getElementById('doc-' + doc) || document.getElementById('doc-erreur');
    const url = target.id === 'doc-erreur'
        ? `http://intranet.eirbot/${doc}`
        : target.dataset.url + (section ? '#' + section : '');
    document.getElementById('ie-url').value = url;
    document.querySelectorAll('#regles-tabs a').forEach(a => a.classList.toggle('is-active', a.dataset.doc === doc));
    fakeLoad(url, () => {
        ieDocs().forEach(d => { d.hidden = d !== target; });
        const view = document.getElementById('ie-view');
        const anchor = section && document.getElementById(`${doc}-${section}`);
        if (anchor) anchor.scrollIntoView({ block: 'start' });
        else { view.scrollTop = 0; window.scrollTo(0, 0); }
        if (w95()) document.title = `${target.dataset.title} - Microsoft Internet Explorer`;
    });
}

// --- Boutons d'Internet Explorer (aussi appelés par les menus de win95.js) ---
function ieGo(doc) { location.hash = doc; }
function ieBack() { history.back(); }
function ieForward() { history.forward(); }
function ieRefresh() { render(); }
function iePrint() { window.print(); }

function ieStop() {
    clearTimeout(ieTimer);
    document.getElementById('ie-throbber').classList.remove('is-busy');
    setStatus('Terminé');
}

function ieFavorites() {
    const favs = document.getElementById('ie-favs');
    favs.hidden = !favs.hidden;
    document.getElementById('ie-fav-btn').classList.toggle('is-on', !favs.hidden);
}

// Barre d'adresse : une adresse connue ou un nom de document, sinon « Impossible d'afficher la page »
function onAddress(e) {
    e.preventDefault();
    const raw = document.getElementById('ie-url').value.trim();
    const [base, section] = raw.split('#');
    const hit = ieDocs().find(d => d.dataset.url && d.dataset.url.replace(/\/$/, '') === base.replace(/\/$/, ''));
    let doc = hit ? hit.id.replace('doc-', '') : base.replace(/^(https?:\/\/)?(intranet\.eirbot)?\/?/i, '').replace(/\.htm$/, '');
    if (!doc && !hit) doc = IE_HOME;
    const hash = '#' + (section ? `${doc}/${section}` : doc);
    if (location.hash === hash) render();  // même adresse : pas de hashchange, on recharge
    else location.hash = hash;
}

// --- Calculateur de score (barème 2027) ---
function computeScore() {
    const f = document.getElementById('score-form');
    const num = (name) => Math.max(0, parseInt(f.elements[name].value, 10) || 0);
    const murs = num('murs'), tours = num('tours'), autres = num('pierres');
    const porte = f.elements.porte.checked;
    const niveau = num('niveau');
    // Le Graal ne peut pas sortir du château : un niveau d'élévation implique qu'il y est
    if (niveau > 0) f.elements.graal.checked = true;
    const graal = f.elements.graal.checked;
    const retour = parseInt(f.elements.retour.value, 10) || 0;
    const douves = num('douves'), boulets = num('boulets');
    const attaque = f.elements.attaque.checked;
    const penalite = num('penalite');

    const pierres = murs * 3 + tours + (porte ? 3 : 0) + autres;
    const lines = [
        ['Pierres posées (' + pierres + ')', pierres],
        ['Murs (' + murs + ' × 5)', murs * 5],
        ['Tours (' + tours + ' × 5)', tours * 5],
        ['Porte', porte ? 20 : 0],
        ['Graal dans le château', graal ? 5 : 0],
        ['Graal niveau ' + niveau, niveau * 5],
        ['Retour du roi', retour],
        ['Douves (' + douves + ' × 5)', douves * 5],
        ['Attaque de PAMI', attaque ? 5 : 0],
        ['Boulets', boulets >= 1 ? 5 : 0],
        ['3 boulets ou plus', boulets >= 3 ? 15 : 0],
        ['Pénalité', -penalite],
    ];
    const total = Math.max(0, lines.reduce((s, [, v]) => s + v, 0));
    document.getElementById('score-detail').innerHTML = lines
        .filter(([, v]) => v !== 0)
        .map(([label, v]) => `<tr><td>${escapeHtml(label)}</td><td>${v > 0 ? '+' : ''}${v}</td></tr>`)
        .join('') || '<tr><td>Rien pour l\'instant</td><td>0</td></tr>';
    document.getElementById('score-total').textContent = total;

    document.getElementById('score-warn').textContent =
        pierres > 30 ? `${pierres} pierres : il n'y en a que 30 sur la table.` : '';
}

function resetScore() {
    document.getElementById('score-form').reset();
    computeScore();
}

document.addEventListener('DOMContentLoaded', () => {
    window.addEventListener('hashchange', render);
    document.getElementById('ie-address').addEventListener('submit', onAddress);
    document.getElementById('ie-url').addEventListener('focus', (e) => e.target.select());
    const form = document.getElementById('score-form');
    form.addEventListener('input', computeScore);
    form.addEventListener('change', computeScore);
    document.getElementById('score-reset').addEventListener('click', resetScore);
    // Survol d'un lien : son adresse dans la barre d'état, comme dans IE
    document.getElementById('ie-view').addEventListener('mouseover', (e) => {
        const a = e.target.closest('a[href]');
        if (!a || !w95()) return;
        const href = a.getAttribute('href');
        if (href.startsWith('#')) {
            const [doc] = href.slice(1).split('/');
            const d = document.getElementById('doc-' + doc);
            setStatus(d ? d.dataset.url + (href.includes('/') ? '#' + href.split('/')[1] : '') : href);
        } else setStatus(a.href);
    });
    document.getElementById('ie-view').addEventListener('mouseout', (e) => {
        if (e.target.closest('a[href]') && w95()) setStatus('Terminé');
    });
    computeScore();
    render();
});
