// theme.js — choix du thème visuel (chargé SANS defer dans le <head> : le thème
// est posé avant le premier rendu, donc pas de flash de l'ancien thème).
//
// Ordre de priorité : ?theme=xxx dans l'URL (mémorisé ensuite) > choix enregistré
// sur cet appareil > thème par défaut. Les thèmes sont définis dans common.css
// (html[data-theme="..."]).
(function () {
    var THEMES = {
        stk: 'STK (jour)',
        nuit: 'STK (nuit)',
        sombre: 'Sombre'
    };
    var DEFAULT = 'stk';
    var KEY = 'eirbot-theme';

    function save(name) {
        try { localStorage.setItem(KEY, name); } catch (e) { /* navigation privée, stockage bloqué */ }
    }

    function load() {
        try { return localStorage.getItem(KEY); } catch (e) { return null; }
    }

    function apply(name) {
        if (!THEMES[name]) name = DEFAULT;
        document.documentElement.setAttribute('data-theme', name);
        return name;
    }

    var fromUrl = new URLSearchParams(window.location.search).get('theme');
    var current = apply(fromUrl || load() || DEFAULT);
    if (fromUrl && THEMES[fromUrl]) save(current);

    window.EIRBOT_THEMES = THEMES;

    window.getTheme = function () {
        return document.documentElement.getAttribute('data-theme');
    };

    window.setTheme = function (name) {
        save(apply(name));
        document.querySelectorAll('select[data-theme-select]').forEach(function (sel) {
            sel.value = window.getTheme();
        });
    };

    // Remplit automatiquement tous les <select data-theme-select>
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('select[data-theme-select]').forEach(function (sel) {
            sel.innerHTML = '';
            Object.keys(THEMES).forEach(function (key) {
                var opt = document.createElement('option');
                opt.value = key;
                opt.textContent = THEMES[key];
                sel.appendChild(opt);
            });
            sel.value = window.getTheme();
            sel.addEventListener('change', function () { window.setTheme(sel.value); });
        });
    });
})();
