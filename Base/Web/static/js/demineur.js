// Démineur (comme celui de Windows 95) : premier clic jamais sur une mine, drapeaux au clic droit
// ou à l'appui long (téléphone), clic sur un chiffre entouré d'assez de drapeaux = découvrir autour.
// Meilleurs temps par niveau gardés dans le navigateur.

const MINE_LEVELS = {
    debutant: { label: 'Débutant', rows: 9, cols: 9, mines: 10 },
    intermediaire: { label: 'Intermédiaire', rows: 16, cols: 16, mines: 40 },
    expert: { label: 'Expert', rows: 16, cols: 30, mines: 99 },
};
const MINE_BEST_KEY = 'stk-demineur-best';
const MINE_LEVEL_KEY = 'stk-demineur-level';
const LONG_PRESS_MS = 400;

const mine = {
    level: 'debutant', rows: 9, cols: 9, mines: 10,
    cells: [], opened: 0, flags: 0, started: false, over: false,
    t0: 0, timer: null, flagMode: false,
};

const W95 = (name) => `<svg class="mine-ico" aria-hidden="true"><use href="/static/icons/win95.svg?v=7#w95-${name}"></use></svg>`;

// Visages du bouton : normal, « oh » pendant un clic, lunettes de soleil (gagné), mort (perdu)
const FACES = {
    smile: '<path d="M7 12q4 4 8 0" fill="none" stroke="#000" stroke-width="1.4"/><rect x="7" y="7" width="2" height="2"/><rect x="13" y="7" width="2" height="2"/>',
    oh: '<circle cx="11" cy="13.5" r="2" fill="none" stroke="#000" stroke-width="1.4"/><rect x="7" y="7" width="2" height="2"/><rect x="13" y="7" width="2" height="2"/>',
    cool: '<path d="M7 13q4 3 8 0" fill="none" stroke="#000" stroke-width="1.4"/><path d="M4 7h14v1h-1l-1 2h-3l-1-2h-2l-1 2H6L5 8H4z"/>',
    dead: '<path d="M7 14q4-3 8 0" fill="none" stroke="#000" stroke-width="1.4"/><path d="M6.5 6.5l3 3m0-3l-3 3M12.5 6.5l3 3m0-3l-3 3" stroke="#000" stroke-width="1.2"/>',
};

function setFace(kind) {
    document.getElementById('mine-face').innerHTML =
        `<svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="9" fill="#ffff00" stroke="#000" stroke-width="1.2"/>${FACES[kind]}</svg>`;
}

const led = (n) => (n < 0 ? '-' + String(Math.min(99, -n)).padStart(2, '0') : String(Math.min(999, n)).padStart(3, '0'));

function store(key, value) {
    try {
        if (value === undefined) return localStorage.getItem(key);
        localStorage.setItem(key, value);
    } catch (e) { /* stockage bloqué */ }
    return null;
}

function bestTimes() {
    try { return JSON.parse(store(MINE_BEST_KEY) || '{}'); } catch (e) { return {}; }
}

// --- Partie ---

function mineNew(level) {
    if (level && MINE_LEVELS[level]) {
        mine.level = level;
        store(MINE_LEVEL_KEY, level);
    }
    const L = MINE_LEVELS[mine.level];
    Object.assign(mine, { rows: L.rows, cols: L.cols, mines: L.mines, opened: 0, flags: 0, started: false, over: false });
    mine.cells = Array.from({ length: L.rows * L.cols }, () => ({ mine: false, n: 0, open: false, flag: false }));
    clearInterval(mine.timer);
    mine.timer = null;

    const grid = document.getElementById('mine-grid');
    grid.style.setProperty('--cols', L.cols);
    grid.innerHTML = mine.cells.map((_, i) => `<div class="mine-cell" role="gridcell" data-i="${i}"></div>`).join('');
    document.querySelectorAll('#mine-levels [data-level]').forEach(b => b.classList.toggle('btn-primary', b.dataset.level === mine.level));
    setFace('smile');
    updateCounters();
}

const neighbors = (i) => {
    const r = Math.floor(i / mine.cols), c = i % mine.cols, out = [];
    for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
            const rr = r + dr, cc = c + dc;
            if ((dr || dc) && rr >= 0 && rr < mine.rows && cc >= 0 && cc < mine.cols) out.push(rr * mine.cols + cc);
        }
    }
    return out;
};

// Mines placées au premier clic, ni sur la case ni autour (première ouverture toujours utile)
function placeMines(safe) {
    const forbidden = new Set([safe, ...neighbors(safe)]);
    const free = mine.cells.map((_, i) => i).filter(i => !forbidden.has(i));
    for (let k = 0; k < mine.mines; k++) {
        const j = k + Math.floor(Math.random() * (free.length - k));
        [free[k], free[j]] = [free[j], free[k]];
        mine.cells[free[k]].mine = true;
    }
    mine.cells.forEach((c, i) => { c.n = neighbors(i).filter(j => mine.cells[j].mine).length; });
}

function startClock() {
    mine.started = true;
    mine.t0 = Date.now();
    mine.timer = setInterval(updateCounters, 250);
}

const elapsed = () => (mine.started ? Math.min(999, Math.floor((Date.now() - mine.t0) / 1000) + 1) : 0);

function updateCounters() {
    document.getElementById('mine-left').textContent = led(mine.mines - mine.flags);
    document.getElementById('mine-time').textContent = led(elapsed());
}

function cellEl(i) {
    return document.querySelector(`#mine-grid [data-i="${i}"]`);
}

function drawCell(i) {
    const c = mine.cells[i], el = cellEl(i);
    el.className = 'mine-cell';
    el.innerHTML = '';
    if (c.open) {
        el.classList.add('is-open');
        if (c.mine) el.innerHTML = W95('mine');
        else if (c.n) { el.textContent = c.n; el.classList.add('n' + c.n); }
    } else if (c.flag) {
        el.innerHTML = W95('flag');
    }
}

// Découverte en vague à partir d'une case sans mine voisine
function open(i) {
    const stack = [i];
    while (stack.length) {
        const k = stack.pop(), c = mine.cells[k];
        if (c.open || c.flag) continue;
        c.open = true;
        mine.opened++;
        drawCell(k);
        if (c.mine) { lose(k); return; }
        if (c.n === 0) neighbors(k).forEach(j => { if (!mine.cells[j].open) stack.push(j); });
    }
}

function reveal(i) {
    if (mine.over) return;
    const c = mine.cells[i];
    if (!mine.started) { placeMines(i); startClock(); }
    if (c.open) {
        // Clic sur un chiffre : si assez de drapeaux autour, découvrir le reste
        const around = neighbors(i);
        if (c.n && around.filter(j => mine.cells[j].flag).length === c.n) around.forEach(j => { if (!mine.over) open(j); });
    } else if (!c.flag) {
        open(i);
    }
    if (!mine.over && mine.opened === mine.rows * mine.cols - mine.mines) win();
}

function toggleFlag(i) {
    if (mine.over) return;
    const c = mine.cells[i];
    if (c.open) return;
    c.flag = !c.flag;
    mine.flags += c.flag ? 1 : -1;
    drawCell(i);
    updateCounters();
}

function lose(hit) {
    mine.over = true;
    clearInterval(mine.timer);
    mine.cells.forEach((c, i) => {
        if (c.mine && !c.flag) { c.open = true; drawCell(i); }
        else if (!c.mine && c.flag) { const el = cellEl(i); el.classList.add('is-wrong'); }
    });
    cellEl(hit).classList.add('is-hit');
    setFace('dead');
    document.dispatchEvent(new CustomEvent('stk:error', { detail: 'Démineur : perdu' }));  // Clippy et Tux ont leur mot à dire
}

async function win() {
    mine.over = true;
    clearInterval(mine.timer);
    const t = elapsed();
    mine.cells.forEach((c, i) => { if (c.mine && !c.flag) { c.flag = true; drawCell(i); } });
    mine.flags = mine.mines;
    updateCounters();
    setFace('cool');
    const best = bestTimes();
    if (!best[mine.level] || t < best[mine.level]) {
        best[mine.level] = t;
        store(MINE_BEST_KEY, JSON.stringify(best));
        alertInfo(`Bravo ! Meilleur temps pour le niveau ${MINE_LEVELS[mine.level].label} : ${t} s.`);
    } else {
        toast(`Gagné en ${t} s`, 'ok');
    }
}

function alertInfo(text) {
    if (window.w95MessageBox && document.body.classList.contains('w95-app')) window.w95MessageBox({ title: 'Démineur', icon: 'info', text });
    else toast(text, 'ok');
}

function mineBest() {
    const best = bestTimes();
    const lines = Object.entries(MINE_LEVELS).map(([k, L]) => `${L.label} : ${best[k] ? best[k] + ' s' : '—'}`);
    alertInfo('Meilleurs temps\n\n' + lines.join('\n'));
}

function setFlagMode(on) {
    mine.flagMode = on;
    const b = document.getElementById('mine-flag-mode');
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.classList.toggle('btn-primary', on);
    b.textContent = `Mode drapeau : ${on ? 'oui' : 'non'}`;
}

// --- Souris et doigt ---

document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('mine-grid');
    let press = null;  // { i, timer, long }

    grid.addEventListener('contextmenu', (e) => e.preventDefault());

    grid.addEventListener('pointerdown', (e) => {
        const el = e.target.closest('.mine-cell');
        if (!el || mine.over) return;
        const i = +el.dataset.i;
        if (e.button === 2) { toggleFlag(i); return; }
        if (e.button !== 0) return;
        setFace('oh');
        press = { i, long: false, timer: setTimeout(() => {
            if (!press) return;
            press.long = true;
            toggleFlag(press.i);
            if (navigator.vibrate) navigator.vibrate(30);
            setFace('smile');
        }, LONG_PRESS_MS) };
    });

    const release = (e) => {
        if (!press) return;
        clearTimeout(press.timer);
        const p = press;
        press = null;
        if (!mine.over) setFace('smile');
        if (p.long || e.type === 'pointercancel') return;
        const el = e.target.closest && e.target.closest('.mine-cell');
        if (!el || +el.dataset.i !== p.i) return;  // relâché ailleurs : rien
        if (mine.flagMode && !mine.cells[p.i].open) toggleFlag(p.i);
        else reveal(p.i);
    };
    grid.addEventListener('pointerup', release);
    grid.addEventListener('pointercancel', release);
    grid.addEventListener('pointerleave', () => { if (press) { clearTimeout(press.timer); press = null; if (!mine.over) setFace('smile'); } });

    document.getElementById('mine-face').addEventListener('click', () => mineNew());
    document.getElementById('mine-levels').addEventListener('click', (e) => {
        const b = e.target.closest('[data-level]');
        if (b) mineNew(b.dataset.level);
    });
    document.getElementById('mine-flag-mode').addEventListener('click', () => setFlagMode(!mine.flagMode));
    document.addEventListener('keydown', (e) => { if (e.key === 'F2') { e.preventDefault(); mineNew(); } });

    const saved = store(MINE_LEVEL_KEY);
    mineNew(MINE_LEVELS[saved] ? saved : 'debutant');
});
