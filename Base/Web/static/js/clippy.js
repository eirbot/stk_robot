// Clippy : trombone moqueur du thème Windows 95 (blagues, piques, sons rigolos).
// Actif seulement en thème win95, jamais sur l'écran 7" du robot.
// Sons synthétisés en Web Audio (aucun fichier son de Windows).
(function () {
    'use strict';

    const MUTE_KEY = 'stk-clippy-off';   // sessionStorage : « Ferme-la » vaut pour l'onglet
    const FIRST_DELAY = 8000;
    const MIN_GAP = 60000, MAX_GAP = 120000;
    const BUBBLE_MS = 14000;

    const JOKES = [
        "On dirait que vous essayez de gagner la Coupe de France de robotique. Voulez-vous de l'aide ?",
        "Que dit un robot à un autre robot ? Rien : ils se parlent en ZMQ.",
        "Pourquoi l'ESP32 est-il toujours calme ? Il a un watchdog qui le surveille.",
        "100 secondes de match, 6 mois de code. Rentable.",
        "Le LiDAR voit tout. Sauf vos erreurs de stratégie.",
        "Il semblerait que vous ayez écrit une stratégie. Voulez-vous la tester avant la finale, pour changer ?",
        "C'est moi ou l'odométrie dérive encore ?",
        "Combien d'ingénieurs Eirbot faut-il pour changer une ampoule ? Aucun : on la remplace par 60 LEDs RGB et 3 semaines de firmware.",
        "Je tiens des feuilles ensemble. Vous, vous tenez à peine le robot ensemble.",
        "Voulez-vous défragmenter votre stratégie ?",
        "Conseil du jour : la tirette, c'est le truc qu'on oublie toujours.",
        "Pourquoi le robot a-t-il traversé la table ? Parce que l'évitement était désactivé.",
        "Un robot qui ne bouge pas ne prend jamais de pénalité. Réfléchissez-y.",
        "Erreur 404 : points introuvables.",
        "J'ai calculé vos chances de victoire. Je préfère ne pas en parler.",
        "Astuce : Ctrl+Z ne fonctionne pas sur un robot qui tombe de la table.",
        "Saviez-vous que l'équipe jaune, c'est juste l'équipe bleue avec y → -y ? Moi aussi je suis symétrique.",
        "Le robot n'a pas de bug. Il a des fonctionnalités imprévues.",
    ];

    const PAGE_JOKES = {
        '/': "Bienvenue dans C:\\EIRBOT ! Ne supprimez pas System32, s'il vous plaît.",
        '/media': "On dirait que vous écoutez de la musique. Voulez-vous que je chante ? ♪ Daisy, Daisy…",
        '/controle': "Pilotage manuel détecté. J'ai prévenu les bordures.",
        '/map': "Le robot est ici. Enfin, d'après l'odométrie.",
        '/debug': "Vous déboguez ? Avez-vous essayé de l'éteindre et de le rallumer ?",
        '/blockly': "Une stratégie en blocs ? Comme au CP, mais en plus stressant.",
        '/led_studio': "Plus de LEDs = plus de points. C'est la règle. (Ce n'est pas la règle.)",
        '/replay': "Revoir le match ? Courage.",
    };

    const ERROR_TAUNTS = [
        "Oups ! Voulez-vous de l'aide pour ignorer cette erreur ?",
        "Une erreur ? Je n'ai rien vu. Enfin si, mais je ne dirai rien.",
        "Ça, c'est pas moi. C'est le Go.",
    ];

    // --- Sons ---
    let ctx = null;
    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }

    // Note simple : type d'onde, fréquence (ou [début, fin]), départ, durée, volume
    function note(type, freq, at, dur, vol) {
        const a = audio();
        if (!a) return;
        const t = a.currentTime + at;
        const o = a.createOscillator();
        const g = a.createGain();
        o.type = type;
        if (Array.isArray(freq)) {
            o.frequency.setValueAtTime(freq[0], t);
            o.frequency.exponentialRampToValueAtTime(freq[1], t + dur);
        } else {
            o.frequency.setValueAtTime(freq, t);
        }
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        o.connect(g).connect(a.destination);
        o.start(t);
        o.stop(t + dur + 0.05);
    }

    const SOUNDS = {
        ding: () => { note('sine', 1318, 0, 0.6, 0.25); note('sine', 1976, 0, 0.4, 0.08); },
        chord: () => [523, 659, 784, 1046].forEach(f => note('triangle', f, 0, 1.0, 0.12)),
        tada: () => [523, 659, 784, 1046].forEach((f, i) => note('square', f, i * 0.09, i === 3 ? 0.7 : 0.12, 0.06)),
        boing: () => { note('sine', [180, 720], 0, 0.15, 0.3); note('sine', [720, 140], 0.15, 0.35, 0.3); },
        error: () => { note('square', 220, 0, 0.12, 0.08); note('square', 165, 0.14, 0.3, 0.08); },
        pouet: () => { note('sawtooth', [330, 110], 0, 0.45, 0.08); },
    };
    const FUNNY = ['ding', 'chord', 'tada', 'boing', 'pouet'];

    function play(name) {
        try { SOUNDS[name](); } catch (e) { /* audio indisponible */ }
    }

    // --- Personnage ---
    const SVG = `
<svg viewBox="0 0 80 120" aria-hidden="true">
  <path d="M30 112 V30 a14 14 0 0 1 28 0 V96 a9 9 0 0 1 -18 0 V40 a4 4 0 0 1 8 0 V90"
        fill="none" stroke="#5a5a5a" stroke-width="7" stroke-linecap="round"/>
  <path d="M30 112 V30 a14 14 0 0 1 28 0 V96 a9 9 0 0 1 -18 0 V40 a4 4 0 0 1 8 0 V90"
        fill="none" stroke="#d8d8d8" stroke-width="3.5" stroke-linecap="round"/>
  <g class="clippy-eyes">
    <ellipse cx="30" cy="44" rx="10" ry="11" fill="#fff" stroke="#000" stroke-width="1.5"/>
    <ellipse cx="54" cy="44" rx="10" ry="11" fill="#fff" stroke="#000" stroke-width="1.5"/>
    <circle class="clippy-pupil" cx="33" cy="46" r="3.5"/>
    <circle class="clippy-pupil" cx="57" cy="46" r="3.5"/>
  </g>
  <path class="clippy-brows" d="M20 28 q10 -8 18 0 M46 28 q10 -8 18 0" fill="none" stroke="#000" stroke-width="2.5" stroke-linecap="round"/>
</svg>`;

    let root = null, bubble = null, textEl = null, timer = null, hideTimer = null;
    let lastJoke = -1, greeted = false;

    function active() {
        return document.documentElement.getAttribute('data-theme') === 'win95'
            && !document.body.classList.contains('robot-screen')
            && new URLSearchParams(location.search).get('mode') !== 'robot'
            && !muted();
    }

    function muted() {
        try { return sessionStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; }
    }

    function build() {
        root = document.createElement('div');
        root.className = 'clippy';
        root.innerHTML = `
<div class="clippy-bubble" role="status">
  <p class="clippy-text"></p>
  <div class="clippy-actions">
    <button type="button" class="clippy-more">Encore !</button>
    <button type="button" class="clippy-shut">Ferme-la</button>
  </div>
</div>
<button type="button" class="clippy-body" title="Clippy">${SVG}</button>`;
        document.body.appendChild(root);
        bubble = root.querySelector('.clippy-bubble');
        textEl = root.querySelector('.clippy-text');
        root.querySelector('.clippy-body').onclick = () => say(randomJoke(), 'boing');
        root.querySelector('.clippy-more').onclick = () => say(randomJoke());
        root.querySelector('.clippy-shut').onclick = () => {
            say("Très bien. Je boude.", 'error');
            try { sessionStorage.setItem(MUTE_KEY, '1'); } catch (e) { /* stockage bloqué */ }
            setTimeout(sync, 1800);
        };
    }

    function randomJoke() {
        let i;
        do { i = Math.floor(Math.random() * JOKES.length); } while (i === lastJoke && JOKES.length > 1);
        lastJoke = i;
        return JOKES[i];
    }

    function say(text, sound) {
        if (!root) return;
        textEl.textContent = text;
        bubble.classList.add('is-open');
        root.classList.remove('is-wiggle');
        void root.offsetWidth; // relance l'animation
        root.classList.add('is-wiggle');
        play(sound || FUNNY[Math.floor(Math.random() * FUNNY.length)]);
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => bubble.classList.remove('is-open'), BUBBLE_MS);
    }

    function schedule(delay) {
        clearTimeout(timer);
        timer = setTimeout(() => {
            if (!active()) return;
            if (!greeted) {
                greeted = true;
                const path = location.pathname.replace(/\/$/, '') || '/';
                say(PAGE_JOKES[path] || randomJoke(), 'ding');
            } else {
                say(randomJoke());
            }
            schedule(MIN_GAP + Math.random() * (MAX_GAP - MIN_GAP));
        }, delay);
    }

    // Affiche ou retire Clippy selon le thème courant
    function sync() {
        if (active()) {
            if (!root) build();
            root.hidden = false;
            if (!timer) schedule(FIRST_DELAY);
        } else {
            if (root) root.hidden = true;
            clearTimeout(timer);
            timer = null;
        }
    }

    // Pique sur les erreurs (toast() de common.js, boîtes d'erreur Win95)
    function hookErrors() {
        document.addEventListener('stk:error', () => {
            if (active() && root) {
                setTimeout(() => say(ERROR_TAUNTS[Math.floor(Math.random() * ERROR_TAUNTS.length)]), 900);
            }
        });
    }

    // Sons partagés avec les boîtes de dialogue Win95 (win95.js)
    window.w95Sound = play;

    function init() {
        hookErrors();
        sync();
        new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        // Les navigateurs bloquent le son avant une première interaction
        document.addEventListener('pointerdown', () => { if (active()) audio(); }, { once: true });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
