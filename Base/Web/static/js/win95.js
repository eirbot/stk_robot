// Barre des tâches Windows 95 : menu Démarrer (pages), boutons de fenêtres, zone de
// notification (infos système + horloge). Active seulement en thème win95, jamais sur
// l'écran 7" du robot (qui a sa propre barre des boutons physiques).
//
// Fenêtres : si la page a des <section data-task="Nom" data-icon="icone">, chaque section
// devient une fenêtre et la barre passe de l'une à l'autre (une seule affichée, pas de
// défilement de page). Sinon, un seul bouton : la page courante.
(function () {
    'use strict';

    const PAGES = [
        { href: '/', label: 'Accueil', icon: 'home' },
        { href: '/controle', label: 'Contrôle', icon: 'joystick' },
        { href: '/map', label: 'Carte', icon: 'map' },
        { href: '/debug', label: 'Debug', icon: 'bug' },
        { href: '/blockly', label: 'Strat Studio', icon: 'puzzle' },
        { href: '/led_studio', label: 'LED Studio', icon: 'bulb' },
        { href: '/media', label: 'Sons', icon: 'sound' },
        { href: '/replay', label: 'Replay', icon: 'film' },
    ];

    let bar = null, menu = null, tray = null, clock = null, sysInfoHome = null;
    let clockTimer = null;

    function active() {
        return document.documentElement.getAttribute('data-theme') === 'win95'
            && new URLSearchParams(location.search).get('mode') !== 'robot'
            && !document.body.classList.contains('robot-screen');
    }

    // Icônes pixel art 16x16 (static/icons/win95.svg, généré par tools/win95_icons.py)
    const ico = (name) => `<svg class="w95-ico" aria-hidden="true"><use href="/static/icons/win95.svg?v=4#w95-${name}"></use></svg>`;
    const path = () => location.pathname.replace(/\/$/, '') || '/';

    // Icône de la barre de titre d'une fenêtre, d'après son titre (sinon celle de la page)
    const TITLE_ICONS = [
        [/strat/i, 'puzzle'],
        [/position|carte|simulation/i, 'map'],
        [/ms-dos|console/i, 'dos'],
        [/caméra|vidéo/i, 'camera'],
        [/consommation|logs?\b/i, 'chart'],
        [/réseau|diagnostic|eirbot/i, 'home'],
        [/système|outils|réglages|limites/i, 'gear'],
        [/vitesse|tactile|manette|actionneur|bras/i, 'joystick'],
        [/lecteur|audio|assignation|son/i, 'sound'],
        [/led|bandeau|palette|animation/i, 'bulb'],
        [/séquenceur|replay/i, 'film'],
        [/pin/i, 'power'],
        [/périph|robot|télémétrie|état/i, 'robot'],
    ];

    function titleIcon(text) {
        const hit = TITLE_ICONS.find(([re]) => re.test(text));
        if (hit) return hit[1];
        const page = PAGES.find(p => p.href === path());
        return page ? page.icon : 'home';
    }

    function decorate(root) {
        const page = PAGES.find(p => p.href === path());
        root.querySelectorAll('.card-title, .header .page-title, .header .brand').forEach(el => {
            if (el.querySelector(':scope > .w95-title-ico')) return;
            const name = el.matches('.card-title') ? titleIcon(el.textContent) : (page ? page.icon : 'home');
            el.insertAdjacentHTML('afterbegin', ico(name).replace('class="w95-ico"', 'class="w95-ico w95-title-ico"'));
        });
    }

    // Icônes au trait du thème (sprite.svg) -> icône Win95 colorée, ou rien (boutons Win95 surtout
    // textuels). Un bouton qui n'a qu'une icône la garde, pour ne pas devenir vide.
    const SWAP = {
        'play': 'play', 'square': 'stop', 'circle-stop': 'stop', 'save': 'save', 'folder-open': 'folder',
        'trash-2': 'trash', 'refresh-cw': 'refresh', 'rotate-ccw': 'refresh', 'zap': 'zap', 'radar': 'radar',
        'crosshair': 'target', 'triangle-alert': 'warning', 'camera': 'camera', 'video': 'camera',
        'map': 'map', 'route': 'map', 'music': 'sound', 'volume-2': 'sound', 'lightbulb': 'bulb',
        'paintbrush': 'palette', 'joystick': 'joystick', 'gamepad-2': 'joystick', 'wrench': 'gear',
        'puzzle': 'puzzle', 'power': 'power', 'house': 'home', 'bot': 'robot',
    };

    function swapIcons(root) {
        root.querySelectorAll('svg.icon:not([data-w95])').forEach(svg => {
            svg.setAttribute('data-w95', '');
            if (svg.closest('.tile-icon, .card-title')) return;  // déjà gérés
            const use = svg.querySelector('use');
            const m = use && /#i-([a-z0-9-]+)/.exec(use.getAttribute('href') || '');
            const target = m && SWAP[m[1]];
            if (target) {
                svg.insertAdjacentHTML('afterend', ico(target).replace('class="w95-ico"', 'class="w95-ico w95-swap"'));
            } else if (svg.parentElement && !svg.parentElement.textContent.trim()) {
                svg.classList.add('w95-keep');
            }
        });
    }

    // Win95 n'écrit pas en capitales : « CONSIGNE DE VITESSE » -> « Consigne de vitesse »
    // (titres, cadres, boutons, onglets ; le texte d'origine est rendu en quittant le thème)
    const ACRONYMS = { led: 'LED', leds: 'LED', esp: 'ESP', lidar: 'LiDAR', ip: 'IP', usb: 'USB', rasp: 'Rasp',
                       zmq: 'ZMQ', fsm: 'FSM', init: 'Init', pc: 'PC', eirbot: 'EIRBOT' };
    const capsOriginal = new Map();  // nœud texte -> texte d'origine
    const CAPS_TARGETS = '.page-title, .card-title, .btn, button, .tab-btn, .w95-task, .field-label, .test-stat-title';

    function sentenceCase(text) {
        let first = true;
        return text.toLowerCase().replace(/[\p{L}]+/gu, (w) => {
            if (ACRONYMS[w]) { first = false; return ACRONYMS[w]; }
            if (first) { first = false; return w.charAt(0).toUpperCase() + w.slice(1); }
            return w;
        });
    }

    function fixCaps(root) {
        const els = root.matches && root.matches(CAPS_TARGETS) ? [root] : [];
        root.querySelectorAll(CAPS_TARGETS).forEach(e => els.push(e));
        els.forEach(el => {
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            for (let n = walker.nextNode(); n; n = walker.nextNode()) {
                const t = n.nodeValue;
                const letters = t.replace(/[^\p{L}]/gu, '');
                if (letters.length < 3 || letters !== letters.toUpperCase()) continue;
                if (!capsOriginal.has(n)) capsOriginal.set(n, t);
                n.nodeValue = sentenceCase(t);
            }
        });
    }

    function restoreCaps() {
        capsOriginal.forEach((t, n) => { if (n.isConnected) n.nodeValue = t; });
        capsOriginal.clear();
    }

    // --- Boîtes de dialogue (MessageBox) ---
    // icône : error | warning | info | question ; boutons : libellés, Entrée = défaut, Échap = annuler.
    // Renvoie une Promise résolue avec l'indice du bouton (ou cancelIndex si fermée).
    const BOX_SOUND = { error: 'chord', warning: 'ding', info: 'ding', question: 'ding' };
    let boxCount = 0;

    function appTitle() {
        const page = PAGES.find(p => p.href === path());
        if (path() === '/blockly') return 'Strat Studio';
        return page ? (page.href === '/' ? 'EIRBOT' : page.label) : 'EIRBOT';
    }

    function messageBox(opts) {
        const o = Object.assign({ title: appTitle(), icon: 'info', buttons: ['OK'], defaultIndex: 0 }, opts);
        const cancelIndex = o.cancelIndex !== undefined ? o.cancelIndex : o.buttons.length - 1;
        return new Promise(resolve => {
            const win = document.createElement('div');
            win.className = 'w95-msgbox';
            win.setAttribute('role', 'alertdialog');
            win.setAttribute('aria-modal', 'true');
            win.innerHTML = `
<div class="w95-msgbox-title"><span>${escape(o.title)}</span><button type="button" class="w95-msgbox-close" aria-label="Fermer"></button></div>
<div class="w95-msgbox-body">${ico(o.icon).replace('class="w95-ico"', 'class="w95-ico w95-msgbox-ico"')}<p></p></div>
<div class="w95-msgbox-buttons">${o.buttons.map((b, i) => `<button type="button" data-i="${i}"${i === o.defaultIndex ? ' class="is-default"' : ''}>${escape(b)}</button>`).join('')}</div>`;
            win.querySelector('p').textContent = String(o.text);

            // Fond transparent qui bloque les clics (Windows 95 n'assombrit pas l'écran)
            const shield = document.createElement('div');
            shield.className = 'w95-msgbox-shield';
            shield.appendChild(win);
            document.body.appendChild(shield);

            // Fenêtres empilées en cascade
            const off = 18 * (boxCount++ % 6);
            win.style.left = `calc(50% - ${win.offsetWidth / 2}px + ${off}px)`;
            win.style.top = `calc(40% - ${win.offsetHeight / 2}px + ${off}px)`;

            const close = (i) => {
                boxCount = Math.max(0, boxCount - 1);
                shield.remove();
                document.removeEventListener('keydown', onKey, true);
                resolve(i);
            };
            const onKey = (e) => {
                if (e.key === 'Escape') { e.preventDefault(); close(cancelIndex); }
                else if (e.key === 'Enter') {
                    e.preventDefault();
                    const f = document.activeElement;
                    close(f && f.dataset && f.dataset.i !== undefined && win.contains(f) ? +f.dataset.i : o.defaultIndex);
                }
            };
            document.addEventListener('keydown', onKey, true);
            win.querySelectorAll('.w95-msgbox-buttons button').forEach(b => b.addEventListener('click', () => close(+b.dataset.i)));
            win.querySelector('.w95-msgbox-close').addEventListener('click', () => close(cancelIndex));
            // Clic hors de la boîte : bip, comme sous Windows
            shield.addEventListener('mousedown', (e) => {
                if (e.target === shield && window.w95Sound) window.w95Sound('ding');
            });
            dragByTitle(win);

            win.querySelectorAll('.w95-msgbox-buttons button')[o.defaultIndex].focus();
            if (window.w95Sound) window.w95Sound(BOX_SOUND[o.icon] || 'ding');
        });
    }

    // Déplacer une fenêtre par sa barre de titre
    function dragByTitle(win) {
        const bar = win.querySelector('.w95-msgbox-title');
        bar.addEventListener('pointerdown', (e) => {
            if (e.target.closest('button')) return;
            const r = win.getBoundingClientRect();
            const dx = e.clientX - r.left, dy = e.clientY - r.top;
            bar.setPointerCapture(e.pointerId);
            const move = (ev) => {
                win.style.left = Math.max(0, Math.min(innerWidth - 40, ev.clientX - dx)) + 'px';
                win.style.top = Math.max(0, Math.min(innerHeight - 30, ev.clientY - dy)) + 'px';
            };
            const up = () => { bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up); };
            bar.addEventListener('pointermove', move);
            bar.addEventListener('pointerup', up);
        });
    }

    // Icône d'après le texte, pour les alert() existants
    function guessIcon(text) {
        if (/erreur|échec|impossible|invalide|introuvable|refus/i.test(text)) return 'error';
        if (/sauvegardé|succès|réussi|terminé|redémarré/i.test(text)) return 'info';
        return 'warning';
    }

    const nativeAlert = window.alert.bind(window);
    window.w95MessageBox = (opts) => (active() ? messageBox(opts) : null);
    // toast(…, 'err') de common.js : true = affiché ici
    window.w95Alert = (text, icon) => {
        if (!active()) return false;
        messageBox({ text, icon: icon || guessIcon(text) });
        return true;
    };
    // askConfirm() de common.js
    window.w95Confirm = (text) => (active()
        ? messageBox({ text, icon: 'question', buttons: ['Oui', 'Non'], cancelIndex: 1 }).then(i => i === 0)
        : null);

    // --- Construction ---
    function build() {
        bar = document.createElement('div');
        bar.className = 'w95-taskbar';
        bar.innerHTML = `
<button type="button" class="w95-start" aria-haspopup="menu" aria-expanded="false">
  <span class="w95-flag" aria-hidden="true"><i></i><i></i><i></i><i></i></span><b>Démarrer</b>
</button>
<div class="w95-tasks" role="tablist"></div>
<div class="w95-tray"><span class="w95-clock"></span></div>`;

        menu = document.createElement('div');
        menu.className = 'w95-menu';
        menu.setAttribute('role', 'menu');
        menu.hidden = true;
        const current = path();
        menu.innerHTML = `
<div class="w95-menu-banner"><b>EIRBOT</b>95</div>
<div class="w95-menu-items">
  ${PAGES.map(p => `<a role="menuitem" href="${p.href}"${p.href === current ? ' class="is-current"' : ''}>${ico(p.icon)}<span>${p.label}</span></a>`).join('')}
  <hr>
  <div class="w95-sub">
    <button type="button" role="menuitem" aria-haspopup="menu">${ico('palette')}<span>Thèmes</span><i class="w95-arrow">▸</i></button>
    <div class="w95-submenu" role="menu">
      ${Object.entries(window.EIRBOT_THEMES || {}).map(([k, v]) => `<button type="button" role="menuitemradio" data-theme="${k}"${k === 'win95' ? ' class="is-current"' : ''}>${escape(v)}</button>`).join('')}
    </div>
  </div>
  <button type="button" role="menuitem" data-action="shutdown">${ico('power')}<span>Arrêter Windows…</span></button>
</div>`;

        document.body.appendChild(menu);
        document.body.appendChild(bar);
        tray = bar.querySelector('.w95-tray');
        clock = bar.querySelector('.w95-clock');

        const start = bar.querySelector('.w95-start');
        start.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleMenu(menu.hidden);
        });
        document.addEventListener('click', (e) => {
            if (!menu.hidden && !menu.contains(e.target)) toggleMenu(false);
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') toggleMenu(false);
        });
        const sub = menu.querySelector('.w95-sub');
        sub.querySelector('[aria-haspopup]').addEventListener('click', (e) => {
            e.stopPropagation();
            sub.classList.toggle('is-open');  // tactile : pas de survol
        });
        menu.querySelectorAll('[data-theme]').forEach(b => b.addEventListener('click', () => {
            toggleMenu(false);
            if (window.setTheme) window.setTheme(b.dataset.theme);
        }));
        menu.querySelector('[data-action="shutdown"]').addEventListener('click', () => {
            toggleMenu(false);
            shutdown();
        });

        buildApp();
        buildTasks();
    }

    function toggleMenu(open) {
        if (!menu) return;
        menu.hidden = !open;
        if (!open) menu.querySelectorAll('.w95-sub').forEach(s => s.classList.remove('is-open'));
        bar.querySelector('.w95-start').setAttribute('aria-expanded', open ? 'true' : 'false');
        bar.querySelector('.w95-start').classList.toggle('is-pressed', open);
    }

    // « Il est maintenant possible d'éteindre votre ordinateur » -> retour au thème par défaut
    function shutdown() {
        const screen = document.createElement('div');
        screen.className = 'w95-shutdown';
        screen.innerHTML = '<p>Il est maintenant possible d\'éteindre<br>votre ordinateur en toute sécurité.</p>';
        document.body.appendChild(screen);
        setTimeout(() => {
            screen.remove();
            if (window.setTheme) window.setTheme('stk');
        }, 2500);
    }

    // Un seul bouton dans la barre des tâches : l'application de la page
    function buildTasks() {
        const box = bar.querySelector('.w95-tasks');
        const page = PAGES.find(p => p.href === path());
        const pt = document.querySelector('.page-title');
        const title = (APPS[path()] && APPS[path()].title) || (pt && (pt.innerText || pt.textContent)) || (page && page.label) || document.title;
        box.innerHTML = `<button type="button" class="w95-task is-active" role="tab" aria-selected="true">${ico(page ? page.icon : 'home')}<span>${escape(title.trim())}</span></button>`;
    }

    // --- Applications : barre de menus, barre d'état, cadres de groupe, onglets ---
    const call = (name, ...args) => () => {
        const fn = window[name];
        if (typeof fn === 'function') fn(...args);
    };
    const click = (sel) => () => { const el = document.querySelector(sel); if (el) el.click(); };
    const ABOUT = { label: 'À propos de EIRBOT', run: () => messageBox({
        title: 'À propos de EIRBOT', icon: 'info',
        text: 'EIRBOT pour Windows 95\nEirbot — Coupe de France de robotique\n\nCe logiciel est fourni « tel quel ». Le robot aussi.' }) };
    const CLOSE = { label: 'Fermer', run: () => { location.href = '/'; } };

    // Par page : titre de la fenêtre, menus (items : label + run, ou '-' pour un séparateur),
    // champs de la barre d'état ({ mirror: sélecteur, fmt: 'Texte : %' } recopie un élément de la page)
    const APPS = {
        '/': {
            menus: [
                ['&Match', [
                    { label: 'Démarrer le match', run: call('sendAction', 'start') },
                    { label: 'Arrêt d\'urgence', run: call('sendAction', 'stop') },
                    { label: 'Réinitialiser', run: call('sendAction', 'reset') },
                    '-',
                    { label: 'Changer d\'équipe', run: call('sendAction', 'team') },
                    '-',
                    { label: 'Arrêter Windows…', run: () => shutdown() },
                ]],
                ['A&ffichage', PAGES.filter(p => p.href !== '/').map(p => ({ label: p.label, run: () => { location.href = p.href; } }))],
                ['&?', [ABOUT]],
            ],
            status: [{ mirror: '#fsm-display', fmt: 'État : %' }, { mirror: '#tirette-status', fmt: 'Tirette : %' },
                     { mirror: '#timer', fmt: 'Chrono : % s' }],
        },
        '/controle': {
            title: 'Pilotage du robot',
            menus: [
                ['&Fichier', [CLOSE]],
                ['&Robot', [
                    { label: 'Arrêt d\'urgence', run: click('#btn-emergency-stop') },
                    { label: 'Vitesse à zéro', run: click('#btn-zero-speed') },
                    '-',
                    { label: 'Initialiser les actionneurs', run: call('sendActuatorCmd', 'init_robot') },
                ]],
                ['&Poses', [
                    { label: 'Match', run: call('sendActuatorCmd', 'pose_match') },
                    { label: 'Ranger', run: call('sendActuatorCmd', 'pose_ranger') },
                    { label: 'Caméra', run: call('sendActuatorCmd', 'pose_camera') },
                    { label: 'Déployer', run: call('sendActuatorCmd', 'pose_deploy') },
                    { label: 'Saisir', run: call('sendActuatorCmd', 'pose_grab') },
                    { label: 'Poser', run: call('sendActuatorCmd', 'pose_poser') },
                ]],
                ['&?', [{ label: 'Aide manette', run: click('#btn-gamepad-help') }, '-', ABOUT]],
            ],
            status: [{ mirror: '#conn-badge', fmt: 'Liaison : %' }, { mirror: '#gamepad-status-text', fmt: 'Manette : %' }],
        },
        '/map': {
            title: 'Carte du match',
            menus: [['&Fichier', [CLOSE]], ['&Affichage', [{ label: 'Vue 2D / 3D', run: click('#btn-view-toggle') }]], ['&?', [ABOUT]]],
            status: [{ mirror: '#pos-text', fmt: '%' }],
        },
        '/debug': {
            title: 'Propriétés de EIRBOT',
            menus: [
                ['&Fichier', [CLOSE]],
                ['&Outils', [
                    { label: 'Flasher l\'ESP moteurs…', run: call('flashESP', 'motors') },
                    { label: 'Flasher l\'ESP bras…', run: call('flashESP', 'arms') },
                    { label: 'Mettre à jour le code de la Rasp…', run: call('updateRasp') },
                    '-',
                    { label: 'Diagnostic réseau', run: () => { showTab(tabSections().findIndex(s => s.dataset.task === 'Réseau')); call('runDiagnosticTest')(); } },
                ]],
                ['&?', [ABOUT]],
            ],
        },
        '/led_studio': {
            title: 'LED Studio',
            menus: [
                ['&Fichier', [
                    { label: 'Nouvelle animation', run: click('#btnNew') },
                    { label: 'Enregistrer', run: click('#btnSave') },
                    { label: 'Supprimer', run: click('#btnDelete') },
                    '-', CLOSE,
                ]],
                ['&Séquence', [
                    { label: 'Ajouter une étape', run: click('#btnAddStep') },
                    '-',
                    { label: 'Lire', run: click('#btnPlay') },
                    { label: 'Arrêter', run: click('#btnStop') },
                ]],
                ['&?', [ABOUT]],
            ],
        },
        '/media': {
            title: 'Sons et lumières',
            menus: [
                ['&Fichier', [CLOSE]],
                ['&Lecture', [
                    { label: 'Lire', run: call('wmpPlay') },
                    { label: 'Arrêter', run: call('wmpStop') },
                    { label: 'Précédent', run: call('playPrev') },
                    { label: 'Suivant', run: call('playNext') },
                    '-',
                    { label: 'Tester sur le robot', run: call('playOnRobot') },
                    { label: 'Couper le son du robot', run: call('stopAudio') },
                ]],
                ['&Affichage', [
                    { label: 'Studio audio', run: call('switchTab', 'audio') },
                    { label: 'Studio LED', run: call('switchTab', 'leds') },
                ]],
                ['&?', [ABOUT]],
            ],
        },
        '/replay': {
            title: 'Replay',
            menus: [
                ['&Fichier', [{ label: 'Ouvrir l\'enregistrement choisi', run: call('loadLog') }, '-', CLOSE]],
                ['&Lecture', [{ label: 'Lire / Pause', run: call('togglePlay') }]],
                ['&?', [ABOUT]],
            ],
            status: [{ mirror: '#time-display', fmt: 'Temps : %' }, { mirror: '#val-state', fmt: 'État : %' }],
        },
    };

    // « &Fichier » -> F souligné
    const accel = (label) => escape(label).replace(/&amp;(.)/, '<u>$1</u>');

    function buildMenubar(header, menus) {
        const nav = document.createElement('nav');
        nav.className = 'w95-menubar w95-only';
        menus.forEach(([title, items]) => {
            const item = document.createElement('div');
            item.className = 'w95-mb-item';
            item.innerHTML = `<button type="button">${accel(title)}</button><div class="w95-mb-menu"></div>`;
            const list = item.querySelector('.w95-mb-menu');
            items.forEach(it => {
                if (it === '-') { list.appendChild(document.createElement('hr')); return; }
                const b = document.createElement('button');
                b.type = 'button';
                b.textContent = it.label;
                b.addEventListener('click', () => { closeMenus(nav); it.run(); });
                list.appendChild(b);
            });
            const head = item.querySelector('button');
            head.addEventListener('click', (e) => {
                e.stopPropagation();
                const open = item.classList.contains('is-open');
                closeMenus(nav);
                if (!open) item.classList.add('is-open');
            });
            // Un menu ouvert : survoler un autre titre l'ouvre, comme sous Windows
            head.addEventListener('mouseenter', () => {
                if (nav.querySelector('.w95-mb-item.is-open')) { closeMenus(nav); item.classList.add('is-open'); }
            });
            nav.appendChild(item);
        });
        document.addEventListener('click', () => closeMenus(nav));
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenus(nav); });
        header.insertAdjacentElement('afterend', nav);
    }

    function closeMenus(nav) {
        nav.querySelectorAll('.w95-mb-item.is-open').forEach(i => i.classList.remove('is-open'));
    }

    function buildStatusbar(frame, fields) {
        const sb = document.createElement('div');
        sb.className = 'w95-statusbar w95-only';
        const main = document.createElement('span');
        main.className = 'w95-sb-main';
        main.textContent = 'Prêt';
        sb.appendChild(main);
        (fields || []).forEach(f => {
            const span = document.createElement('span');
            const src = document.querySelector(f.mirror);
            if (!src) return;
            const copy = () => {
                let t = (src.innerText || src.textContent || '').trim() || '—';
                if (/\p{L}{3}/u.test(t) && t === t.toUpperCase()) t = sentenceCase(t);
                span.textContent = f.fmt.replace('%', t);
            };
            copy();
            new MutationObserver(copy).observe(src, { childList: true, subtree: true, characterData: true });
            sb.appendChild(span);
        });
        frame.appendChild(sb);
    }

    // Debug : sections data-task -> onglets d'une feuille de propriétés (OK / Annuler / Appliquer)
    const TAB_KEY = 'stk-win95-tab:' + location.pathname;
    const tabSections = () => Array.from(document.querySelectorAll('section[data-task]'));

    function buildTabs() {
        const secs = tabSections();
        if (!secs.length) return;
        const strip = document.createElement('div');
        strip.className = 'w95-tabs w95-only';
        strip.setAttribute('role', 'tablist');
        strip.innerHTML = secs.map((s, i) => `<button type="button" class="w95-tab" role="tab" data-i="${i}">${escape(s.dataset.task)}</button>`).join('');
        strip.querySelectorAll('.w95-tab').forEach(b => b.addEventListener('click', () => showTab(+b.dataset.i)));
        secs[0].parentElement.insertBefore(strip, secs[0]);
        secs.forEach(s => s.classList.add('w95-tabpanel'));

        const buttons = document.createElement('div');
        buttons.className = 'w95-propsheet-buttons w95-only';
        buttons.innerHTML = '<button type="button" data-b="ok">OK</button><button type="button" data-b="cancel">Annuler</button><button type="button" disabled>Appliquer</button>';
        buttons.querySelectorAll('[data-b]').forEach(b => b.addEventListener('click', () => { location.href = '/'; }));
        secs[secs.length - 1].insertAdjacentElement('afterend', buttons);

        let saved = 0;
        try { saved = parseInt(sessionStorage.getItem(TAB_KEY), 10) || 0; } catch (e) { /* stockage bloqué */ }
        showTab(Math.min(saved, secs.length - 1));
    }

    function showTab(i) {
        if (i < 0) return;
        tabSections().forEach((s, k) => s.classList.toggle('w95-tab-hidden', k !== i));
        document.querySelectorAll('.w95-tab').forEach((b, k) => {
            b.classList.toggle('is-active', k === i);
            b.setAttribute('aria-selected', k === i ? 'true' : 'false');
        });
        try { sessionStorage.setItem(TAB_KEY, String(i)); } catch (e) { /* stockage bloqué */ }
        window.dispatchEvent(new Event('resize'));  // graphiques mesurés à l'affichage
    }

    function buildApp() {
        const header = document.querySelector('.header');
        if (!header) return;
        const app = APPS[path()] || {};
        const frame = header.parentElement;
        frame.classList.add('w95-appframe');
        // Titre de la fenêtre propre au thème (l'original reste pour les autres thèmes)
        const pt = header.querySelector('.page-title');
        if (app.title && pt) {
            pt.innerHTML = `<span class="w95-hide">${pt.innerHTML}</span><span class="w95-only">${escape(app.title)}</span>`;
        }
        if (app.menus && !document.getElementById('w95Menubar')) buildMenubar(header, app.menus);
        if (!frame.querySelector('.w95-statusbar')) buildStatusbar(frame, app.status);
        buildTabs();
    }

    function escape(s) {
        return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    }

    function tick() {
        if (!clock) return;
        const d = new Date();
        clock.textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    }

    // --- Activation / désactivation selon le thème ---
    function sync() {
        const sysInfo = document.getElementById('sys-info');
        if (active()) {
            if (!bar) {
                build();
                decorate(document);
                swapIcons(document);
                fixCaps(document.body);
                // Fenêtres et boutons créés plus tard (code PIN, listes, etc.)
                new MutationObserver(muts => muts.forEach(m => m.addedNodes.forEach(n => {
                    if (n.nodeType !== 1) return;
                    if (n.matches('.card-title') || n.querySelector('.card-title')) decorate(n.parentNode || n);
                    if (n.matches('svg.icon') || n.querySelector('svg.icon')) swapIcons(n.parentNode || n);
                    if (active()) fixCaps(n.parentElement || n);
                }))).observe(document.body, { childList: true, subtree: true });
            }
            bar.hidden = false;
            if (!capsOriginal.size) fixCaps(document.body);
            document.body.classList.add('w95-has-taskbar', 'w95-app');
            // Les infos système (IP, robot, batterie) vont dans la zone de notification
            window.alert = (text) => {
                const icon = guessIcon(String(text));
                if (icon === 'error') document.dispatchEvent(new CustomEvent('stk:error', { detail: text }));
                messageBox({ text, icon });
            };
            if (sysInfo && sysInfo.parentNode !== tray) {
                sysInfoHome = { parent: sysInfo.parentNode, next: sysInfo.nextSibling };
                tray.insertBefore(sysInfo, clock);
            }
            tick();
            if (!clockTimer) clockTimer = setInterval(tick, 10000);
        } else {
            if (bar) bar.hidden = true;
            restoreCaps();
            if (menu) menu.hidden = true;
            document.body.classList.remove('w95-has-taskbar', 'w95-app');
            window.alert = nativeAlert;
            if (sysInfo && sysInfoHome && sysInfo.parentNode === tray) {
                sysInfoHome.parent.insertBefore(sysInfo, sysInfoHome.next);
            }
            clearInterval(clockTimer);
            clockTimer = null;
        }
    }

    function init() {
        sync();
        new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
