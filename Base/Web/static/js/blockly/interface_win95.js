// Strat Studio : interface Windows 95 (nom du document, barre d'état, menus) et démarrage.
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

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
        '<svg class="w95-about-ico"><use href="/static/icons/win95.svg?v=7#w95-puzzle"></use></svg>' +
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
