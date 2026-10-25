// Barre de menus et barre d'état de chaque page en thème Windows 95 (une entrée par page).
// win95.js appelle EirbotWin95Apps(outils) avec ses fonctions internes ; chargé AVANT win95.js.
window.EirbotWin95Apps = function ({ ABOUT, CLOSE, PAGES, call, click, messageBox, showTab, shutdown, tabSections }) {
    return {
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
        '/regles': {
            title: 'Règlement Eurobot 2027 - Microsoft Internet Explorer',
            menus: [
                ['&Fichier', [{ label: 'Imprimer…', run: call('iePrint') }, '-', CLOSE]],
                ['&Édition', [{ label: 'Tout sélectionner', run: () => {
                    const doc = document.querySelector('.ie-doc:not([hidden])');
                    if (doc) getSelection().selectAllChildren(doc);
                } }]],
                ['&Affichage', [
                    { label: 'Actualiser', run: call('ieRefresh') },
                    { label: 'Arrêter', run: call('ieStop') },
                ]],
                ['A&ller à', [
                    { label: 'Précédente', run: call('ieBack') },
                    { label: 'Suivante', run: call('ieForward') },
                    '-',
                    { label: 'Page de démarrage', run: call('ieGo', 'accueil') },
                ]],
                ['F&avoris', [
                    { label: 'Règlement 2027', run: call('ieGo', 'jeu') },
                    { label: 'Barème des points', run: call('ieGo', 'jeu/points') },
                    { label: 'Plan de la table', run: call('ieGo', 'jeu/plan') },
                    { label: 'Règles générales', run: call('ieGo', 'general') },
                    { label: 'Pénalités', run: call('ieGo', 'general/penalites') },
                    { label: 'Calculateur de score', run: call('ieGo', 'score') },
                    '-',
                    { label: 'Afficher le volet Favoris', run: call('ieFavorites') },
                ]],
                ['&?', [{ label: 'À propos d\'Internet Explorer', run: () => messageBox({
                    title: 'À propos d\'Internet Explorer', icon: 'info',
                    text: 'Internet Explorer pour EIRBOT\nVersion 2027 (règlement 1.0)\n\nNe se connecte qu\'à l\'intranet du robot. C\'est mieux comme ça.' }) }, ABOUT]],
            ],
            status: [{ mirror: '#ie-zone', fmt: '%' }],
        },
        '/demineur': {
            title: 'Démineur',
            menus: [
                ['&Partie', [
                    { label: 'Nouvelle partie (F2)', run: call('mineNew') },
                    '-',
                    { label: 'Débutant', run: call('mineNew', 'debutant') },
                    { label: 'Intermédiaire', run: call('mineNew', 'intermediaire') },
                    { label: 'Expert', run: call('mineNew', 'expert') },
                    '-',
                    { label: 'Meilleurs temps…', run: call('mineBest') },
                    '-', CLOSE,
                ]],
                ['&?', [{ label: 'À propos du Démineur', run: () => messageBox({
                    title: 'À propos du Démineur', icon: 'info',
                    text: 'Démineur pour EIRBOT\n\nAucune mine n\'a été posée sur la table de jeu. En principe.' }) }, ABOUT]],
            ],
        },
        '/update': {
            title: 'Windows Update',
            menus: [
                ['&Fichier', [CLOSE]],
                ['&Outils', [
                    { label: 'Rechercher les mises à jour', run: click('#wu-check') },
                    { label: 'Installer', run: click('#wu-install') },
                ]],
                ['&?', [ABOUT]],
            ],
            status: [{ mirror: '#wu-head', fmt: 'Dépôt : %' }, { mirror: '#wu-checked', fmt: 'Vérifié : %' }],
        },
    };
};
