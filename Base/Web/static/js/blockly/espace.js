// Strat Studio : espace de travail Blockly (thème, rendu Win95, création).
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

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
