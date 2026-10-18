/**
 * RASPBERRY PI ROBOT STUDIO
 * Fichier : Rasp/ihm/static/blockly_script.js
 * Version : COMPLÈTE (Bézier, Grid 200mm, Preview, Mouse, Collisions, Start Block)
 */

document.addEventListener("DOMContentLoaded", function () {

    // ============================================================
    // 0. CONFIGURATION
    // ============================================================

    // Orientation Image Robot :
    // 'RIGHT' (->), 'UP' (^), 'LEFT' (<), 'DOWN' (v)
    // Réglé sur 'DOWN' car ton image nécessite une rotation de 180°
    const ROBOT_IMAGE_ORIENTATION = 'DOWN';

    const TABLE_WIDTH = 3000;
    const TABLE_HEIGHT = 2000;
    const GRID_STEP = 200; // Quadrillage tous les 200mm

    // Valeurs par défaut si le bloc "Départ" n'est pas utilisé
    const DEFAULT_START_X = 250;
    const DEFAULT_START_Y = 0;
    const DEFAULT_START_THETA = 0;
    const ROBOT_WIDTH_MM = 320;
    const ROBOT_LENGTH_MM = 370;


    // ============================================================
    // 1. DÉFINITION DES BLOCS BLOCKLY
    // ============================================================

    // --- DATA FETCHING FOR DROPDOWNS ---
    window.BLOCKLY_ANIMATIONS = [["Aucune", ""]];
    window.BLOCKLY_SOUNDS = [["Aucun", ""]];

    function fetchDropdownData() {
        // Animations
        fetch('/api/led_animations')
            .then(r => r.json())
            .then(data => {
                let keys = Object.keys(data);
                if (keys.length > 0) {
                    window.BLOCKLY_ANIMATIONS = keys.map(k => [k, k]);
                }
            });

        // Sounds
        fetch('/api/list_audio_files')
            .then(r => r.json())
            .then(data => {
                if (data.length > 0) {
                    window.BLOCKLY_SOUNDS = data.map(f => [f, f]);
                }
            });
    }
    fetchDropdownData();


    // --- BLOC DÉPART ---
    Blockly.Blocks['robot_start'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Départ Match (Bleu)")
                .appendField("X").appendField(new Blockly.FieldNumber(250), "X")
                .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
                .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA");
            this.setNextStatement(true, null);
            this.setColour(290); // Violet
            this.setTooltip("Définit la position de départ pour la simulation.");
        }
    };

    // --- BLOC GOTO ---
    Blockly.Blocks['robot_goto'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Aller à X").appendField(new Blockly.FieldNumber(1000), "X")
                .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
                .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(230); // Bleu
            this.setTooltip("Déplacement en ligne droite puis rotation finale.");
        }
    };

    // --- ACTIONNEURS ---
    Blockly.Blocks['prendre_kapla'] = { init: function () { this.appendDummyInput().appendField("Prendre Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
    Blockly.Blocks['retourner_kapla'] = { init: function () { this.appendDummyInput().appendField("Retourne Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
    Blockly.Blocks['poser_kapla'] = { init: function () { this.appendDummyInput().appendField("Poser Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
    Blockly.Blocks['pousse_kapla'] = { init: function () { this.appendDummyInput().appendField("Pousse Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
    Blockly.Blocks['robot_stop'] = { init: function () { this.appendDummyInput().appendField("Arrêter le robot"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(0); } };

    Blockly.Blocks['robot_gobase_at'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Retour Base à")
                .appendField(new Blockly.FieldNumber(90), "SECONDS")
                .appendField("secondes");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(0); // Rouge
            this.setTooltip("Attend le temps indiqué puis rentre à la base (coord. départ).");
        }
    };

    Blockly.Blocks['robot_approche_kapla'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Approche Kapla (Vision)");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(40);
            this.setTooltip("Se positionne devant un Kapla détecté par la caméra.");
        }
    };

    Blockly.Blocks['robot_thermometre'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Déployer Thermomètre");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(200); // Bleu-cyan
            this.setTooltip("Déploie le thermomètre selon la couleur de l'équipe.");
        }
    };

    Blockly.Blocks['robot_attendre'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Attendre")
                .appendField(new Blockly.FieldNumber(1, 0, 100, 0.1), "SECONDES")
                .appendField("secondes");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(65);
            this.setTooltip("Attend un nombre de secondes (interruptible par l'arrêt d'urgence).");
        }
    };

    Blockly.Blocks['robot_recalage_camera'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Recaler l'odométrie sur la caméra");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(230);
            this.setTooltip("Robot immobile : corrige la position de l'ESP avec la pose vue par la caméra de la base.");
        }
    };

    Blockly.Blocks['robot_si_approche_reussie'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Si l'approche a réussi");
            this.appendStatementInput("DO")
                .setCheck(null)
                .appendField("Faire");
            this.appendStatementInput("ELSE")
                .setCheck(null)
                .appendField("Sinon");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(40);
            this.setTooltip("Exécute le bloc 'Faire' si approcheKapla() a réussi, 'Sinon' autrement.");
        }
    };

    // --- NOUVEAUX ACTIONNEURS (BAS & HAUT NIVEAU) ---
    Blockly.Blocks['actionneur_unique'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Actionneur")
                .appendField(new Blockly.FieldDropdown([["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"]]), "ID")
                .appendField("Action:")
                .appendField(new Blockly.FieldDropdown([["FLIP (Prendre + Tourne)", "FLIP"], ["nFLIP (Prendre sans tourner)", "nFLIP"], ["DOWN (Poser)", "DOWN"], ["INIT (Match)", "INIT"], ["RESET (Rangé)", "RESET"]]), "CMD");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(120);
            this.setTooltip("Contrôle individuel bas niveau pour un actionneur.");
        }
    };

    Blockly.Blocks['prendre_tous_kaplas'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Prendre 4 Kaplas (Auto Caméra)");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(120);
            this.setTooltip("Analyse via la caméra et définit s'il faut faire FLIP ou nFLIP pour chaque Kapla.");
        }
    };

    // --- SONS & LUMIERES ---
    Blockly.Blocks['play_animation'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Jouer Animation")
                .appendField(new Blockly.FieldDropdown(function () { return window.BLOCKLY_ANIMATIONS; }), "ANIM_NAME");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(300); // Violet foncé
            this.setTooltip("Lance une animation LED.");
        }
    };

    Blockly.Blocks['play_sound'] = {
        init: function () {
            this.appendDummyInput()
                .appendField("Jouer Son")
                .appendField(new Blockly.FieldDropdown(function () { return window.BLOCKLY_SOUNDS; }), "SOUND_NAME");
            this.setPreviousStatement(true, null);
            this.setNextStatement(true, null);
            this.setColour(300);
            this.setTooltip("Joue un fichier audio.");
        }
    };

    // --- GÉNÉRATEURS PYTHON ---
    Blockly.Python.forBlock['robot_start'] = function (block) { return `robot.set_pos(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')})\n`; };
    Blockly.Python.forBlock['robot_goto'] = function (block) { return `robot.goto(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')})\n`; };
    Blockly.Python.forBlock['prendre_kapla'] = function (block) { return `robot.prendreKapla()\n`; };
    Blockly.Python.forBlock['retourner_kapla'] = function (block) { return `robot.retournerKapla()\n`; };
    Blockly.Python.forBlock['poser_kapla'] = function (block) { return `robot.poseKapla()\n`; };
    Blockly.Python.forBlock['pousse_kapla'] = function (block) { return 'robot.pousse_kapla()\n'; };
    Blockly.Python.forBlock['robot_stop'] = function (block) { return 'robot.stop()\n'; };
    Blockly.Python.forBlock['robot_gobase_at'] = function (block) {
        return `robot.wait_until_and_return(${block.getFieldValue('SECONDS')})\n`;
    };
    Blockly.Python.forBlock['robot_approche_kapla'] = function (block) { return 'robot.approcheKapla()\n'; };
    Blockly.Python.forBlock['robot_thermometre'] = function (block) { return 'robot.thermometre()\n'; };
    Blockly.Python.forBlock['robot_recalage_camera'] = function (block) { return 'robot.recalage_camera()\n'; };
    Blockly.Python.forBlock['robot_attendre'] = function (block) {
        return `robot.attendre(${block.getFieldValue('SECONDES')})\n`;
    };
    Blockly.Python.forBlock['robot_si_approche_reussie'] = function (block) {
        var do_branch = Blockly.Python.statementToCode(block, 'DO');
        var else_branch = Blockly.Python.statementToCode(block, 'ELSE');
        var code = 'if robot.approche_reussie:\n';
        code += do_branch || '  pass\n';
        if (else_branch) {
            code += 'else:\n';
            code += else_branch;
        }
        return code;
    };

    Blockly.Python.forBlock['actionneur_unique'] = function (block) {
        return `robot.cmd_actionneurs(act${block.getFieldValue('ID')}='${block.getFieldValue('CMD')}')\n`;
    };

    Blockly.Python.forBlock['prendre_tous_kaplas'] = function (block) {
        return `robot.prendre_kaplas_camera()\n`;
    };

    Blockly.Python.forBlock['play_animation'] = function (block) { return `robot.play_animation("${block.getFieldValue('ANIM_NAME')}")\n`; };
    Blockly.Python.forBlock['play_sound'] = function (block) { return `robot.play_sound("${block.getFieldValue('SOUND_NAME')}")\n`; };

    // --- INITIALISATION WORKSPACE ---
    // Thème Blockly construit depuis les variables CSS du thème de l'interface (blockly.css)
    var blocklyThemes = {};
    function blocklyTheme() {
        var name = document.documentElement.getAttribute('data-theme') || 'stk';
        if (blocklyThemes[name]) return blocklyThemes[name];
        var cs = getComputedStyle(document.documentElement);
        var v = function (n) { return cs.getPropertyValue(n).trim(); };
        blocklyThemes[name] = Blockly.Theme.defineTheme('stk_' + name, {
            base: Blockly.Themes.Classic,
            componentStyles: {
                workspaceBackgroundColour: v('--bk-workspace'),
                toolboxBackgroundColour: v('--bk-toolbox'),
                toolboxForegroundColour: v('--bk-toolbox-text'),
                flyoutBackgroundColour: v('--bk-flyout'),
                flyoutForegroundColour: v('--text'),
                flyoutOpacity: 0.95,
                scrollbarColour: v('--bk-scrollbar'),
                scrollbarOpacity: 0.8,
                insertionMarkerColour: v('--accent'),
                insertionMarkerOpacity: 0.4,
                cursorColour: v('--accent')
            },
            fontStyle: { family: v('--font'), size: 11 },
            startHats: false
        });
        return blocklyThemes[name];
    }

    // Rendu Windows 95 des blocs : coins carrés, encoches et tenons rectangulaires ; le relief
    // clair / foncé de geras donne l'effet bouton Win95
    class W95Constants extends Blockly.geras.ConstantProvider {
        constructor() {
            super();
            this.CORNER_RADIUS = 0;
            this.FIELD_BORDER_RECT_RADIUS = 0;
            this.NOTCH_WIDTH = 12;
            this.FIELD_TEXT_FONTFAMILY = 'W95FA, Tahoma, "Microsoft Sans Serif", Arial, sans-serif';
            this.FIELD_TEXT_FONTWEIGHT = 'normal';
            this.FIELD_TEXT_FONTSIZE = 13;
        }
        makeNotch() {
            var P = Blockly.utils.svgPaths, w = this.NOTCH_WIDTH, h = this.NOTCH_HEIGHT;
            var side = function (d) { return P.line([P.point(0, h), P.point(d * w, 0), P.point(0, -h)]); };
            return { type: this.SHAPES.NOTCH, width: w, height: h, pathLeft: side(1), pathRight: side(-1) };
        }
        makePuzzleTab() {
            var P = Blockly.utils.svgPaths, w = this.TAB_WIDTH, h = this.TAB_HEIGHT;
            var tab = function (d) { return P.line([P.point(-w, 0), P.point(0, d * h), P.point(w, 0)]); };
            return { type: this.SHAPES.PUZZLE, width: w, height: h, pathDown: tab(1), pathUp: tab(-1) };
        }
    }
    class W95Highlight extends Blockly.geras.HighlightConstantProvider {
        // Pas de reflet le long du tenon (celui de geras suit la forme arrondie)
        makePuzzleTab() {
            var P = Blockly.utils.svgPaths, h = this.constantProvider.TAB_HEIGHT;
            var up = P.moveBy(0, -h), down = P.moveBy(0, h);
            return { width: this.constantProvider.TAB_WIDTH, height: h,
                     pathUp: function () { return up; }, pathDown: function () { return down; } };
        }
    }
    // Couleur d'un bloc ramenée à la palette 16 couleurs de Windows (teintes foncées : texte blanc lisible)
    function w95Colour(hex) {
        var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || '');
        if (!m) return '#808080';
        var r = parseInt(m[1], 16) / 255, g = parseInt(m[2], 16) / 255, b = parseInt(m[3], 16) / 255;
        var max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
        if (max === 0 || d / max < 0.15) return '#808080';
        var h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
        h *= 60;
        if (h < 20 || h >= 340) return '#800000';   // bordeaux
        if (h < 75) return '#808000';               // olive
        if (h < 160) return '#008000';              // vert
        if (h < 195) return '#008080';              // sarcelle
        if (h < 255) return '#000080';              // bleu marine
        if (h < 300) return '#800080';              // violet
        return '#008080';                           // rose -> sarcelle (distinct du violet)
    }
    class W95PathObject extends Blockly.geras.PathObject {
        applyColour(block) {
            super.applyColour(block);
            var shadow = block.isShadow();
            this.svgPath.setAttribute('fill', shadow ? '#ffffff' : w95Colour(this.style.colourPrimary));
            this.svgPath.setAttribute('stroke', shadow ? '#808080' : 'none');
            this.svgPathLight.setAttribute('stroke', '#ffffff');   // reflet blanc en haut à gauche
            this.svgPathDark.setAttribute('fill', '#000000');      // ombre noire en bas à droite
        }
    }
    class W95Renderer extends Blockly.geras.Renderer {
        makeConstants_() { return new W95Constants(); }
        makeHighlightConstants_() { return new W95Highlight(this.getConstants()); }
        makePathObject(root, style) { return new W95PathObject(root, style, this.getConstants()); }
    }
    Blockly.blockRendering.register('win95', W95Renderer);

    function wantedRenderer() {
        return document.documentElement.getAttribute('data-theme') === 'win95' ? 'win95' : 'geras';
    }

    var currentRenderer = wantedRenderer();
    function injectWorkspace() {
        var ws = Blockly.inject('blocklyDiv', {
            toolbox: document.getElementById('toolbox'),
            scrollbars: true, trashcan: true, sounds: false,
            renderer: currentRenderer,
            theme: blocklyTheme(),
            grid: { spacing: 24, length: 2, colour: '#cccccc', snap: false }
        });
        if (currentRenderer === 'win95') {
            var flyout = ws.getToolbox() && ws.getToolbox().getFlyout();
            if (flyout) flyout.CORNER_RADIUS = 0;
        }
        ws.addChangeListener(function () { if (window.refreshStudioStatus) window.refreshStudioStatus(); });
        return ws;
    }

    // Recrée l'éditeur en gardant les blocs (changement de rendu, police chargée après coup)
    function rebuildWorkspace() {
        var state = Blockly.serialization.workspaces.save(workspace);
        workspace.dispose();
        currentRenderer = wantedRenderer();
        workspace = injectWorkspace();
        Blockly.serialization.workspaces.load(state, workspace);
    }

    var workspace = injectWorkspace();
    // Changement de thème : couleurs à chaud ; le rendu des blocs (Win95 ou non) impose de
    // recréer l'éditeur
    new MutationObserver(function () {
        if (wantedRenderer() === currentRenderer) workspace.setTheme(blocklyTheme());
        else rebuildWorkspace();
        if (currentRenderer === 'win95') whenW95FontReady();
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // Blockly mesure le texte des blocs à l'affichage : si la police Win95 arrive après,
    // on redessine pour que les blocs aient la bonne largeur
    function whenW95FontReady() {
        if (!document.fonts || document.fonts.check('13px W95FA')) return;
        document.fonts.load('13px W95FA').then(function () {
            if (currentRenderer === 'win95') rebuildWorkspace();
        });
    }
    if (currentRenderer === 'win95') whenW95FontReady();
    window.addEventListener('resize', function () { Blockly.svgResize(workspace); }, false);


    // ============================================================
    // 2. MOTEUR GRAPHIQUE (CANVAS)
    // ============================================================

    const canvas = document.getElementById('simCanvas');
    const ctx = canvas.getContext('2d');
    const imgTable = document.getElementById('imgTable');
    const imgRobot = document.getElementById('imgRobot');
    const consoleDiv = document.getElementById('simConsole');

    // Création de l'infobulle (Tooltip) pour la souris
    const coordTooltip = document.createElement('div');
    coordTooltip.style.position = 'absolute';
    coordTooltip.style.background = 'var(--chip-bg)';
    coordTooltip.style.color = 'var(--text)';
    coordTooltip.style.border = '2px solid var(--line)';
    coordTooltip.style.padding = '4px 8px';
    coordTooltip.style.borderRadius = 'var(--radius-sm)';
    coordTooltip.style.pointerEvents = 'none'; // Click-through
    coordTooltip.style.display = 'none';
    coordTooltip.style.fontSize = '12px';
    coordTooltip.style.fontFamily = 'var(--font-mono)';
    coordTooltip.style.zIndex = '1000';
    document.body.appendChild(coordTooltip);

    // État du Robot
    let robot = {
        x: DEFAULT_START_X,
        y: DEFAULT_START_Y,
        theta: DEFAULT_START_THETA,
        currentIcon: null,
        bezier: null,
        isMoving: false
    };

    let actionQueue = [];
    let previewPath = [];

    // --- FONCTIONS DE CONVERSION ---

    // Convertit Millimètres vers Pixels Écran (Nouveau Repère)
    function worldToScreen(x_mm, y_mm) {
        const scaleX = canvas.width / TABLE_WIDTH; // 3000 -> correspond à Y
        const scaleY = canvas.height / TABLE_HEIGHT; // 2000 -> correspond à X
        return {
            x: (canvas.width / 2) + (y_mm * scaleX),
            y: x_mm * scaleY
        };
    }

    // Convertit Pixels Écran vers Millimètres (Pour la souris)
    function screenToWorld(px, py) {
        const scaleX = canvas.width / TABLE_WIDTH;
        const scaleY = canvas.height / TABLE_HEIGHT;
        return {
            x: Math.round(py / scaleY),
            y: Math.round((px - (canvas.width / 2)) / scaleX)
        };
    }

    // Calcul Point Segment (t entre 0 et 1)
    function getSegmentPoint(t, p0, p3) {
        return {
            x: p0.x + t * (p3.x - p0.x),
            y: p0.y + t * (p3.y - p0.y)
        };
    }

    // Vérifie si un point est hors de la table
    function isOutOfBounds(p) {
        // X : 0 à 2000, Y : -1500 à 1500
        return p.x < 0 || p.x > TABLE_HEIGHT || p.y < -1500 || p.y > 1500;
    }

    // --- ERREURS & BLOCKLY ---
    function clearBlockWarnings() {
        workspace.getAllBlocks().forEach(b => b.setWarningText(null));
        workspace.highlightBlock(null);
        canvas.classList.remove("collision-alert");
    }

    function markBlockError(blockId, msg) {
        if (!blockId) return;
        let block = workspace.getBlockById(blockId);
        if (block) block.setWarningText(msg);
        canvas.classList.add("collision-alert");
    }

    // --- FONCTIONS DE DESSIN ---

    function drawGrid() {
        ctx.strokeStyle = "rgba(0, 0, 0, 0.15)"; // Gris foncé transparent
        ctx.fillStyle = "rgba(0, 0, 0, 0.6)";    // Texte gris foncé
        ctx.lineWidth = 1;
        ctx.font = "10px Arial";
        ctx.textAlign = "center";

        // Lignes pour Y (gauche à droite)
        for (let y = -1500; y <= 1500; y += GRID_STEP) {
            let p = worldToScreen(0, y);
            ctx.beginPath(); ctx.moveTo(p.x, 0); ctx.lineTo(p.x, canvas.height); ctx.stroke();
            if (y % 500 === 0) ctx.fillText(y, p.x, 10);
        }
        // Lignes pour X (haut en bas)
        ctx.textAlign = "left";
        for (let x = 0; x <= 2000; x += GRID_STEP) {
            let p = worldToScreen(x, 0);
            ctx.beginPath(); ctx.moveTo(0, p.y); ctx.lineTo(canvas.width, p.y); ctx.stroke();
            if (x % 500 === 0 && x > 0) ctx.fillText(x, 5, p.y - 2);
        }
    }

    function drawStraightPath(bz, color, width, showFootprint = false) {
        let p0_scr = worldToScreen(bz.p0.x, bz.p0.y);
        let p3_scr = worldToScreen(bz.p3.x, bz.p3.y);

        ctx.beginPath();
        ctx.moveTo(p0_scr.x, p0_scr.y);
        ctx.lineTo(p3_scr.x, p3_scr.y);
        ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke();

        if (showFootprint) {
            // --- TRACÉ DE L'ENCOMBREMENT (TUNNEL) ---
            let dx = bz.p3.x - bz.p0.x;
            let dy = bz.p3.y - bz.p0.y;
            let dist = Math.sqrt(dx * dx + dy * dy);

            if (dist > 0) {
                let nx = dx / dist;
                let ny = dy / dist;
                let offsetX = -ny * (ROBOT_WIDTH_MM / 2);
                let offsetY = nx * (ROBOT_WIDTH_MM / 2);

                // Points des bords
                let p0L = worldToScreen(bz.p0.x + offsetX, bz.p0.y + offsetY);
                let p0R = worldToScreen(bz.p0.x - offsetX, bz.p0.y - offsetY);
                let p3L = worldToScreen(bz.p3.x + offsetX, bz.p3.y + offsetY);
                let p3R = worldToScreen(bz.p3.x - offsetX, bz.p3.y - offsetY);

                ctx.beginPath();
                ctx.moveTo(p0L.x, p0L.y); ctx.lineTo(p3L.x, p3L.y);
                ctx.moveTo(p0R.x, p0R.y); ctx.lineTo(p3R.x, p3R.y);
                ctx.strokeStyle = "rgba(255, 0, 0, 0.4)";
                ctx.setLineDash([5, 5]); // Lignes pointillées pour le tunnel
                ctx.lineWidth = 1;
                ctx.stroke();
                ctx.setLineDash([]); // Reset

                // Remplissage léger du tunnel
                ctx.beginPath();
                ctx.moveTo(p0L.x, p0L.y); ctx.lineTo(p3L.x, p3L.y);
                ctx.lineTo(p3R.x, p3R.y); ctx.lineTo(p0R.x, p0R.y);
                ctx.closePath();
                ctx.fillStyle = "rgba(255, 0, 0, 0.1)";
                ctx.fill();
            }
        }
    }

    function drawRobotFootprint(x_mm, y_mm, theta, color) {
        let screenPos = worldToScreen(x_mm, y_mm);
        const scaleX = canvas.width / TABLE_WIDTH;
        const w = ROBOT_WIDTH_MM * scaleX;
        const l = ROBOT_LENGTH_MM * scaleX;

        ctx.save();
        ctx.translate(screenPos.x, screenPos.y);
        let rotationRad = -theta * (Math.PI / 180) + Math.PI / 2;
        ctx.fillStyle = color;
        ctx.fillRect(-w / 2, -l / 2, w, l);
        ctx.strokeStyle = "rgba(255, 0, 0, 0.3)";
        ctx.lineWidth = 1;
        ctx.strokeRect(-w / 2, -l / 2, w, l);
        ctx.restore();
    }

    // BOUCLE DE RENDU PRINCIPALE
    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 1. Fond de Table
        if (imgTable.complete && imgTable.naturalHeight !== 0) ctx.drawImage(imgTable, 0, 0, canvas.width, canvas.height);
        else { ctx.fillStyle = "#2e8b57"; ctx.fillRect(0, 0, canvas.width, canvas.height); }

        // 2. Grille
        drawGrid();

        // 3. Prévisualisation (Trait Cyan ou Orange si erreur)
        if (previewPath.length > 0) {
            previewPath.forEach(bz => {
                let mid = getSegmentPoint(0.5, bz.p0, bz.p3);
                if (isOutOfBounds(bz.p3) || isOutOfBounds(mid)) {
                    drawStraightPath(bz, "rgba(255, 140, 0, 0.8)", 3, true); // Orange Alerte
                } else {
                    drawStraightPath(bz, "rgba(0, 255, 255, 0.6)", 2, true); // Cyan OK
                }
            });
        }

        // 4. Mouvement Actif (Trait Rouge)
        if (robot.isMoving && robot.bezier) {
            robot.bezier.t += 0.02; // Vitesse animation

            if (robot.bezier.t >= 1) {
                // Fin du segment
                robot.x = robot.bezier.p3.x;
                robot.y = robot.bezier.p3.y;
                // On garde l'angle actuel (sera mis à jour par la rotation finale si besoin)
                robot.isMoving = false;
                processNextAction();
            } else {
                // Calcul position courante
                let pos = getSegmentPoint(robot.bezier.t, robot.bezier.p0, robot.bezier.p3);

                // Calcul orientation (Tangente)
                let dx = robot.bezier.p3.x - robot.bezier.p0.x;
                let dy = robot.bezier.p3.y - robot.bezier.p0.y;

                if (dx !== 0 || dy !== 0) {
                    let moveAngle = Math.atan2(dy, dx) * (180 / Math.PI);

                    // --- GESTION MARCHE ARRIERE ---
                    // Si l'angle de mouvement est opposé à l'orientation actuelle (>90°), on ne change pas robot.theta
                    // Le robot recule.
                    let diff = Math.abs(((moveAngle - robot.theta + 180 + 360) % 360) - 180);
                    if (diff < 90) {
                        robot.theta = moveAngle;
                    }
                }

                robot.x = pos.x;
                robot.y = pos.y;
                drawStraightPath(robot.bezier, "rgba(255, 0, 0, 0.8)", 4);
            }
        }

        // 4.5 Rotation Active
        if (robot.isRotating && robot.rotateTarget !== undefined) {
            let diff = ((robot.rotateTarget - robot.theta + 180 + 360) % 360) - 180;
            if (Math.abs(diff) < 2) {
                robot.theta = robot.rotateTarget;
                robot.isRotating = false;
                processNextAction();
            } else {
                robot.theta += (diff > 0 ? 2 : -2); // 2 degrés par frame
            }
        }

        // 5. Robot
        let screenPos = worldToScreen(robot.x, robot.y);
        const robotSizePx = (370 / TABLE_WIDTH) * canvas.width;

        ctx.save();
        ctx.translate(screenPos.x, screenPos.y);

        // Gestion Rotation : Adaptation au nouveau repère
        // Dans le repère map: MapTheta=0 -> X_map (vers le bas)
        // MapTheta=90 -> Y_map (vers la droite sur l'écran)
        let rotationRad = -robot.theta * (Math.PI / 180) + Math.PI / 2;

        // Correction Orientation Image
        if (ROBOT_IMAGE_ORIENTATION === 'UP') rotationRad += Math.PI / 2;
        if (ROBOT_IMAGE_ORIENTATION === 'DOWN') rotationRad -= Math.PI / 2;
        if (ROBOT_IMAGE_ORIENTATION === 'LEFT') rotationRad += Math.PI;

        ctx.rotate(rotationRad);

        if (imgRobot.complete && imgRobot.naturalHeight !== 0) {
            ctx.drawImage(imgRobot, -robotSizePx / 2, -robotSizePx / 2, robotSizePx, robotSizePx);
        } else {
            // Dessin secours
            ctx.fillStyle = "#007bff";
            ctx.beginPath();
            ctx.moveTo(robotSizePx / 2, 0);
            ctx.lineTo(-robotSizePx / 2, -robotSizePx / 2);
            ctx.lineTo(-robotSizePx / 2, robotSizePx / 2);
            ctx.fill();
        }
        ctx.restore();

        // 6. Icone Action
        if (robot.currentIcon) {
            // Étiquette texte contourée (lisible sur la table)
            ctx.font = "bold 16px Arial"; ctx.textAlign = "center";
            ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.fillStyle = "#fff";
            ctx.strokeText(robot.currentIcon, screenPos.x, screenPos.y - robotSizePx / 2 - 10);
            ctx.fillText(robot.currentIcon, screenPos.x, screenPos.y - robotSizePx / 2 - 10);
        }

        requestAnimationFrame(draw);
    }


    // ============================================================
    // 3. LISTENERS & INTERACTION SOURIS
    // ============================================================

    canvas.addEventListener('mousemove', function (evt) {
        var rect = canvas.getBoundingClientRect();
        var scaleX_mouse = canvas.width / rect.width;
        var scaleY_mouse = canvas.height / rect.height;
        var mx = (evt.clientX - rect.left) * scaleX_mouse;
        var my = (evt.clientY - rect.top) * scaleY_mouse;

        let worldPos = screenToWorld(mx, my);

        // Affiche tooltip
        coordTooltip.style.display = 'block';
        coordTooltip.style.left = (evt.pageX + 15) + 'px';
        coordTooltip.style.top = (evt.pageY + 15) + 'px';
        coordTooltip.innerHTML = `X: <b>${worldPos.x}</b><br>Y: <b>${worldPos.y}</b>`;
    });

    canvas.addEventListener('mouseout', function () {
        coordTooltip.style.display = 'none';
    });

    // Clic pour logguer la position
    canvas.addEventListener('click', function (evt) {
        var rect = canvas.getBoundingClientRect();
        var scaleX_mouse = canvas.width / rect.width;
        var scaleY_mouse = canvas.height / rect.height;
        let worldPos = screenToWorld((evt.clientX - rect.left) * scaleX_mouse, (evt.clientY - rect.top) * scaleY_mouse);
        logSim(`Clic : X=${worldPos.x}, Y=${worldPos.y}`);
    });


    // ============================================================
    // 4. PARSING & LOGIQUE SÉQUENTIELLE
    // ============================================================

    function applySymmetry(x, y, theta) {
        // Symétrie d'équipe : définition unique dans frames.js (cf. Rasp/core/frames.py)
        let symToggle = document.getElementById('symToggle');
        return EirbotFrames.mirrorForTeam(x, y, theta, symToggle && symToggle.checked ? 'JAUNE' : 'BLEUE');
    }

    function parseSequence(firstBlock, currentX, currentY, currentTheta) {
        let queue = []; let pPath = [];
        let simX = currentX, simY = currentY, simTheta = currentTheta;

        let currentBlock = firstBlock;
        while (currentBlock) {
            let blockId = currentBlock.id;

            if (currentBlock.type === 'robot_start') {
                let rawX = parseInt(currentBlock.getFieldValue('X'));
                let rawY = parseInt(currentBlock.getFieldValue('Y'));
                let rawTheta = parseInt(currentBlock.getFieldValue('THETA'));

                let sym = applySymmetry(rawX, rawY, rawTheta);
                simX = sym.x; simY = sym.y; simTheta = sym.theta;

                queue.push({ type: 'start', x: simX, y: simY, theta: simTheta, blockId: blockId });
            }
            else if (currentBlock.type === 'robot_goto') {
                let rawX = parseInt(currentBlock.getFieldValue('X'));
                let rawY = parseInt(currentBlock.getFieldValue('Y'));
                let rawTheta = parseInt(currentBlock.getFieldValue('THETA'));

                let sym = applySymmetry(rawX, rawY, rawTheta);
                let targetX = sym.x; let targetY = sym.y; let targetTheta = sym.theta;

                let p0 = { x: simX, y: simY };
                let p3 = { x: targetX, y: targetY };

                queue.push({ type: 'goto', x: targetX, y: targetY, theta: targetTheta, blockId: blockId });
                pPath.push({ p0, p3, targetTheta: targetTheta, blockId: blockId });

                simX = targetX; simY = targetY; simTheta = targetTheta;
            }
            else if (currentBlock.type === 'controls_repeat_ext') {
                let times = 0;
                let timesBlock = currentBlock.getInputTargetBlock('TIMES');
                if (timesBlock && timesBlock.type === 'math_number') {
                    times = parseInt(timesBlock.getFieldValue('NUM'));
                }
                let doBlock = currentBlock.getInputTargetBlock('DO');
                for (let i = 0; i < times; i++) {
                    let subResult = parseSequence(doBlock, simX, simY, simTheta);
                    queue = queue.concat(subResult.queue);
                    pPath = pPath.concat(subResult.path);
                    simX = subResult.endX; simY = subResult.endY; simTheta = subResult.endTheta;
                }
            }
            else if (currentBlock.type === 'robot_gobase_at') {
                let targetX = DEFAULT_START_X;
                let targetY = DEFAULT_START_Y;
                let targetTheta = DEFAULT_START_THETA + 180;

                let p0 = { x: simX, y: simY };
                let p3 = { x: targetX, y: targetY };

                queue.push({ type: 'action', msg: "Attente fin match...", blockId: blockId });
                queue.push({ type: 'goto', x: targetX, y: targetY, theta: targetTheta, blockId: blockId });
                pPath.push({ p0, p3, targetTheta: targetTheta, blockId: blockId });

                simX = targetX; simY = targetY; simTheta = targetTheta;
            }
            else if (currentBlock.type.includes('kapla') || currentBlock.type.includes('stop') || currentBlock.type.includes('play_') || currentBlock.type.includes('actionneur')) {
                let msg = "Action";
                if (currentBlock.type === 'prendre_kapla') msg = "Prise Kapla";
                if (currentBlock.type === 'retourner_kapla') msg = "Retourne Kapla";
                if (currentBlock.type === 'poser_kapla') msg = "Pose Kapla";
                if (currentBlock.type === 'pousse_kapla') msg = "Pousse Kapla";
                if (currentBlock.type === 'robot_stop') msg = "STOP";
                if (currentBlock.type === 'play_animation') msg = "Animation: " + currentBlock.getFieldValue('ANIM_NAME');
                if (currentBlock.type === 'play_sound') msg = "Son: " + currentBlock.getFieldValue('SOUND_NAME');
                if (currentBlock.type === 'actionneur_unique') msg = `Act. ${currentBlock.getFieldValue('ID')}: ${currentBlock.getFieldValue('CMD')}`;
                if (currentBlock.type === 'prendre_tous_kaplas') msg = "Prise 4 Kaplas (Caméra)";

                queue.push({ type: 'action', msg: msg, blockId: blockId });
            }
            currentBlock = currentBlock.getNextBlock();
        }
        return { queue, path: pPath, endX: simX, endY: simY, endTheta: simTheta };
    }

    function parseBlocks(isPreview) {
        var topBlocks = workspace.getTopBlocks(true);
        if (topBlocks.length === 0) return { queue: [], path: [] };
        topBlocks.sort((a, b) => a.getRelativeToSurfaceXY().y - b.getRelativeToSurfaceXY().y);

        let res = parseSequence(topBlocks[0], DEFAULT_START_X, DEFAULT_START_Y, DEFAULT_START_THETA);
        return { queue: res.queue, path: res.path };
    }

    function generatePreview() {
        clearBlockWarnings(); // Reset
        let result = parseBlocks(true);
        previewPath = result.path;

        let errorCount = 0;
        previewPath.forEach(bz => {
            let mid = getSegmentPoint(0.5, bz.p0, bz.p3);
            if (isOutOfBounds(bz.p3) || isOutOfBounds(mid)) {
                // MARQUAGE ERREUR
                markBlockError(bz.blockId, "Hors table !");
                errorCount++;
            }
        });
        if (errorCount > 0) logSim(`${errorCount} erreurs détectées.`);
        else logSim("Aperçu généré.");
    }

    function runSimulation() {
        clearBlockWarnings(); // NETTOYAGE
        previewPath = [];
        consoleDiv.innerHTML = "";
        logSim("Simulation...");
        robot.isMoving = false; robot.isRotating = false; robot.bezier = null; robot.currentIcon = null; robot.currentBlockId = null;

        let result = parseBlocks(false);
        actionQueue = result.queue;
        processNextAction();
    }

    function processNextAction() {
        if (actionQueue.length > 0) {
            const action = actionQueue.shift();

            // HIGHLIGHT DU BLOC
            if (action.blockId) {
                robot.currentBlockId = action.blockId;
                workspace.highlightBlock(action.blockId);
            }

            if (action.type === 'start') {
                robot.x = action.x;
                robot.y = action.y;
                robot.theta = action.theta;
                logSim(`Départ : ${action.x}, ${action.y}`);
                processNextAction();
            }
            else if (action.type === 'goto') {
                logSim(`Go (${action.x}, ${action.y})`);

                let p0 = { x: robot.x, y: robot.y };
                let p3 = { x: action.x, y: action.y };

                // Étape 1 : Rotation vers le point (si pas en marche arrière)
                let dx = p3.x - p0.x;
                let dy = p3.y - p0.y;
                let moveAngle = Math.atan2(dy, dx) * (180 / Math.PI);
                let diff = Math.abs(((moveAngle - robot.theta + 180 + 360) % 360) - 180);

                if (diff > 5 && diff < 175) {
                    // On ajoute une rotation AVANT le mouvement
                    actionQueue.unshift({ ...action, type: 'goto_move' }); // On remettra le mouvement après
                    actionQueue.unshift({ type: 'rotate', theta: moveAngle, blockId: action.blockId });
                    processNextAction();
                    return;
                }

                robot.bezier = { p0, p3, targetTheta: action.theta, t: 0 };
                robot.isMoving = true;

                // On ajoute la rotation finale APRÈS le mouvement
                actionQueue.unshift({ type: 'rotate', theta: action.theta, blockId: action.blockId });
            }
            else if (action.type === 'goto_move') {
                let p0 = { x: robot.x, y: robot.y };
                let p3 = { x: action.x, y: action.y };
                robot.bezier = { p0, p3, targetTheta: action.theta, t: 0 };
                robot.isMoving = true;
                actionQueue.unshift({ type: 'rotate', theta: action.theta, blockId: action.blockId });
            }
            else if (action.type === 'rotate') {
                if (Math.abs(((action.theta - robot.theta + 180 + 360) % 360) - 180) < 1) {
                    processNextAction();
                    return;
                }
                robot.rotateTarget = action.theta;
                robot.isRotating = true;
            }
            else if (action.type === 'action') {
                robot.currentIcon = getIcon(action.msg);
                logSim(action.msg);

                // --- FEEDBACK RÉEL (TEST) ---
                if (action.msg.includes("Animation: ")) {
                    let animName = action.msg.split(": ")[1];
                    fetch('/api/play_animation', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: animName })
                    });
                } else if (action.msg.includes("Son: ")) {
                    let soundName = action.msg.split(": ")[1];
                    fetch('/api/play_test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename: soundName })
                    });
                }
                // -----------------------------

                setTimeout(() => { robot.currentIcon = null; processNextAction(); }, 1000);
            }
        } else {
            logSim("Terminé.");
            workspace.highlightBlock(null); // ETEINDRE HIGHLIGHT
        }
    }

    function getIcon(msg) {
        // Étiquette courte affichée au-dessus du robot dans la simulation
        if (msg.includes("Prise")) return "PRISE";
        if (msg.includes("Retourne")) return "RETOURNE";
        if (msg.includes("Pose")) return "POSE";
        if (msg.includes("Pousse")) return "POUSSE";
        if (msg.includes("STOP")) return "STOP";
        if (msg.includes("Animation")) return "ANIM";
        if (msg.includes("Son")) return "SON";
        return "ACTION";
    }

    function logSim(msg) {
        consoleDiv.innerHTML += `<div>> ${msg}</div>`;
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    }


    // ============================================================
    // 5. GESTION API (LOAD/SAVE/LIST) & BOUTONS
    // ============================================================

    var simuBtn = document.getElementById('simuBtn'); if (simuBtn) simuBtn.addEventListener('click', runSimulation);
    var previewBtn = document.getElementById('previewBtn'); if (previewBtn) previewBtn.addEventListener('click', generatePreview);

    // Chargement initial des stratégies
    loadBlocklyStrats('stratSelect');

    document.getElementById('loadBtn').addEventListener('click', function () {
        var n = document.getElementById('stratSelect').value;
        if (!n) return;
        fetch('/api/load_strat/' + n)
            .then(r => r.json())
            .then(d => {
                if (d.status === 'success') {
                    workspace.clear();
                    Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(d.xml), workspace);
                    document.getElementById('filename').value = n;
                    refreshDocName();
                }
            });
    });

    document.getElementById('saveBtn').addEventListener('click', function () {
        var f = document.getElementById('filename').value;
        if (!f) return;
        var c = Blockly.Python.workspaceToCode(workspace).replace(/^/gm, "    ");
        var final = `from strat.actions import RobotActions\nimport time\nMETADATA={"name":"${f}"}\ndef run(robot: RobotActions):\n    print("Start ${f}")\n${c}\n    print("End")`;

        fetch('/api/save_strat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: f,
                code: final,
                xml: Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace))
            })
        })
            .then(r => r.json())
            .then(d => {
                if (d.status === 'success') {
                    loadBlocklyStrats('stratSelect');
                    document.getElementById('status').innerHTML = d.robot
                        ? icon('check') + " Sauvegardé et envoyé au robot"
                        : icon('triangle-alert') + " Sauvegardé sur la base, robot injoignable (utiliser Update code RASP)";
                }
            });
    });

    // --- INTERFACE WINDOWS 95 : nom du document, barre d'état, barre de menus ---
    var filenameInput = document.getElementById('filename');
    var symToggleEl = document.getElementById('symToggle');

    function refreshDocName() {
        document.querySelectorAll('.doc-name').forEach(function (e) {
            e.textContent = filenameInput.value || 'sans titre';
        });
    }
    filenameInput.addEventListener('input', refreshDocName);

    window.refreshStudioStatus = function () {
        var n = workspace.getAllBlocks(false).length;
        var sb = document.getElementById('sbBlocks');
        if (sb) sb.textContent = n + (n > 1 ? ' blocs' : ' bloc');
        var team = document.getElementById('sbTeam');
        if (team) team.textContent = symToggleEl.checked ? 'Équipe jaune (symétrie)' : 'Équipe bleue';
        var check = document.querySelector('[data-action="sym"]');
        if (check) check.classList.toggle('is-checked', symToggleEl.checked);
    };
    symToggleEl.addEventListener('change', window.refreshStudioStatus);

    // Les messages de #status (sauvegarde…) s'affichent aussi dans la barre d'état
    var statusEl = document.getElementById('status');
    new MutationObserver(function () {
        var sb = document.getElementById('sbMsg');
        if (sb) sb.textContent = statusEl.textContent.trim() || 'Prêt';
    }).observe(statusEl, { childList: true, subtree: true, characterData: true });

    var menubar = document.getElementById('w95Menubar');
    function closeMenus() {
        menubar.querySelectorAll('.w95-mb-item.is-open').forEach(function (i) { i.classList.remove('is-open'); });
    }
    menubar.querySelectorAll('.w95-mb-item > button').forEach(function (b) {
        b.addEventListener('click', function (e) {
            e.stopPropagation();
            var item = b.parentElement, open = item.classList.contains('is-open');
            closeMenus();
            if (!open) item.classList.add('is-open');
        });
        // Un menu ouvert : survoler les autres titres les ouvre, comme sous Windows
        b.addEventListener('mouseenter', function () {
            if (menubar.querySelector('.w95-mb-item.is-open')) { closeMenus(); b.parentElement.classList.add('is-open'); }
        });
    });
    document.addEventListener('click', closeMenus);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenus(); });

    var MENU_ACTIONS = {
        quit: function () { location.href = '/'; },
        undo: function () { workspace.undo(false); },
        redo: function () { workspace.undo(true); },
        cleanup: function () { workspace.cleanUp(); },
        clear: function () {
            askConfirm('Effacer tous les blocs de la stratégie ?').then(function (ok) { if (ok) workspace.clear(); });
        },
        sym: function () { symToggleEl.checked = !symToggleEl.checked; symToggleEl.dispatchEvent(new Event('change')); },
        about: showAbout,
    };
    menubar.querySelectorAll('.w95-mb-menu button').forEach(function (b) {
        b.addEventListener('click', function () {
            closeMenus();
            if (b.dataset.click) document.getElementById(b.dataset.click).click();
            else if (MENU_ACTIONS[b.dataset.action]) MENU_ACTIONS[b.dataset.action]();
        });
    });

    function showAbout() {
        var overlay = document.createElement('div');
        overlay.className = 'pin-overlay';
        overlay.innerHTML =
            '<div class="card w95-about">' +
            '<h2 class="card-title">À propos de Strat Studio</h2>' +
            '<div class="w95-about-body">' +
            '<svg class="w95-about-ico"><use href="/static/icons/win95.svg?v=5#w95-puzzle"></use></svg>' +
            '<div><b>Strat Studio pour Windows 95</b><br>Eirbot — Coupe de France de robotique<br><br>' +
            'Ce logiciel est fourni « tel quel ».<br>Le robot aussi.</div></div>' +
            '<div class="row"><button type="button" class="btn">OK</button></div></div>';
        overlay.querySelector('button').addEventListener('click', function () { overlay.remove(); });
        document.body.appendChild(overlay);
        overlay.querySelector('button').focus();
    }

    refreshDocName();
    window.refreshStudioStatus();

    requestAnimationFrame(draw);
});