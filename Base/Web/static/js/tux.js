// Tux (thème Windows 95 seulement, pas sur l'écran du robot) : une fois par session, au bout de
// quelques minutes ou après une erreur, une fenêtre « Avez-vous essayé Linux ? ».
//   Oui              -> la base et le robot tournent déjà sous Linux ; propose d'« arrêter Windows »
//   Non              -> Tux repassera (session suivante)
//   Ne plus demander -> plus jamais sur cet appareil
// Clippy le prend mal (événement stk:tux, cf. clippy.js).
(function () {
    'use strict';

    const FIRST_MIN = 150 * 1000, FIRST_MAX = 330 * 1000;  // première apparition entre 2 min 30 et 5 min 30
    const ERROR_CHANCE = 0.3;                                // ou sur une erreur, une fois sur 3
    const KEY_SESSION = 'stk-tux-seen';
    const KEY_NEVER = 'stk-tux-never';

    let timer = null, win = null;

    function active() {
        return document.documentElement.getAttribute('data-theme') === 'win95'
            && new URLSearchParams(location.search).get('mode') !== 'robot'
            && !document.body.classList.contains('robot-screen');
    }

    function store(kind, key, value) {
        try {
            const s = kind === 'local' ? localStorage : sessionStorage;
            if (value === undefined) return s.getItem(key);
            s.setItem(key, value);
        } catch (e) { /* stockage bloqué : Tux revient, tant pis */ }
        return null;
    }

    const allowed = () => active() && !win && !store('session', KEY_SESSION) && !store('local', KEY_NEVER);

    // Tux dessiné à la main (formes simples, pas le dessin officiel)
    const TUX = `<svg class="tux-svg" viewBox="0 0 64 78" aria-hidden="true">
  <ellipse class="tux-flipper tux-flipper-l" cx="12" cy="46" rx="6" ry="15" transform="rotate(20 12 46)"/>
  <g class="tux-wave"><ellipse class="tux-flipper" cx="52" cy="46" rx="6" ry="15" transform="rotate(-20 52 46)"/></g>
  <ellipse cx="32" cy="46" rx="21" ry="27" fill="#000"/>
  <ellipse cx="32" cy="50" rx="14" ry="20" fill="#fff"/>
  <ellipse cx="32" cy="20" rx="15" ry="16" fill="#000"/>
  <ellipse cx="26.5" cy="17" rx="4.2" ry="5.5" fill="#fff"/>
  <ellipse cx="37.5" cy="17" rx="4.2" ry="5.5" fill="#fff"/>
  <circle class="tux-pupil" cx="27.5" cy="18.5" r="2.1" fill="#000"/>
  <circle class="tux-pupil" cx="36.5" cy="18.5" r="2.1" fill="#000"/>
  <path d="M23 26 Q32 20 41 26 Q32 34 23 26z" fill="#f5b301" stroke="#a06800" stroke-width=".8"/>
  <ellipse cx="20" cy="73" rx="10" ry="4.5" fill="#f5b301" stroke="#a06800" stroke-width=".8"/>
  <ellipse cx="44" cy="73" rx="10" ry="4.5" fill="#f5b301" stroke="#a06800" stroke-width=".8"/>
</svg>`;

    const LINES = {
        idle: ['Avez-vous essayé Linux ?', 'Gratuit, libre, et il ne plante pas en plein match.'],
        error: ['Encore une erreur ? Avez-vous essayé Linux ?', 'Chez nous, au moins, le message d\'erreur dit pourquoi.'],
    };

    function close() {
        if (!win) return;
        win.classList.add('is-leaving');
        const w = win;
        win = null;
        setTimeout(() => w.remove(), 400);
    }

    function show(reason) {
        if (!allowed()) return;
        store('session', KEY_SESSION, '1');
        const [title, sub] = LINES[reason] || LINES.idle;
        win = document.createElement('div');
        win.className = 'tux-window';
        win.setAttribute('role', 'dialog');
        win.setAttribute('aria-label', 'Message de Linux');
        win.innerHTML = `
<div class="tux-titlebar"><span>Message de Linux</span><button type="button" class="tux-x" aria-label="Fermer">×</button></div>
<div class="tux-body">${TUX}<div class="tux-text"><b>${title}</b><p>${sub}</p></div></div>
<div class="tux-buttons">
  <button type="button" data-a="yes" class="is-default">Oui</button>
  <button type="button" data-a="no">Non</button>
  <button type="button" data-a="never">Ne plus demander</button>
</div>`;
        document.body.appendChild(win);
        win.querySelector('.tux-x').addEventListener('click', close);
        win.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', () => answer(b.dataset.a)));
        if (window.w95Sound) window.w95Sound('ding');
        document.dispatchEvent(new CustomEvent('stk:tux'));
    }

    async function answer(a) {
        const w = win;
        if (a === 'never') {
            store('local', KEY_NEVER, '1');
            close();
            return;
        }
        if (a === 'no') {
            w.classList.add('is-sad');
            w.querySelector('.tux-text').innerHTML = '<b>Dommage.</b><p>Je repasserai. On repasse toujours.</p>';
            w.querySelector('.tux-buttons').remove();
            setTimeout(close, 2200);
            return;
        }
        close();
        const box = window.w95MessageBox;
        if (!box) return;
        const i = await box({
            title: 'Linux', icon: 'info', buttons: ['Oui', 'Non'],
            text: 'Bonne nouvelle : vous l\'utilisez déjà.\nLa base et le robot tournent sous Linux ; Windows 95 n\'est qu\'un thème.\n\nArrêter Windows maintenant ?',
        });
        if (i === 0 && window.w95Shutdown) window.w95Shutdown();
    }

    function sync() {
        if (active()) {
            if (!timer && allowed()) timer = setTimeout(() => show('idle'), FIRST_MIN + Math.random() * (FIRST_MAX - FIRST_MIN));
        } else {
            clearTimeout(timer);
            timer = null;
            if (win) { win.remove(); win = null; }
        }
    }

    function init() {
        sync();
        new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        document.addEventListener('stk:error', () => {
            if (allowed() && Math.random() < ERROR_CHANCE) setTimeout(() => show('error'), 2500);
        });
        // Pour essayer tout de suite : window.tuxShow()
        window.tuxShow = () => { store('session', KEY_SESSION, ''); if (active()) show('idle'); };
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
