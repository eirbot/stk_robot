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
        sombre: 'Sombre',
        win95: 'Windows 95'
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

    // Icône du sprite (/static/icons/sprite.svg), à insérer via innerHTML :
    //   btn.innerHTML = icon('camera') + ' Caméra active';
    window.icon = function (name, extraClass) {
        return '<svg class="icon' + (extraClass ? ' ' + extraClass : '') + '" aria-hidden="true">' +
            '<use href="/static/icons/sprite.svg#i-' + name + '"></use></svg>';
    };

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

    // =====================================================================
    // MENUS DÉROULANTS THÉMÉS
    // La liste ouverte d'un <select> natif n'est pas stylable dans Firefox ni
    // WebKitGTK (écran du robot). Chaque <select> reçoit donc un bouton + une
    // liste dessinés avec le thème. Le <select> natif reste dans le DOM (masqué)
    // et reste la source de vérité : les scripts existants qui lisent/écrivent
    // .value, remplissent les <option> ou écoutent onchange marchent tels quels.
    // Opt-out : <select data-native>. Ignorés : multiple / size > 1.
    // =====================================================================
    var openState = null; // { sel, list, items, active }

    function selectedLabel(sel) {
        var opt = sel.options[sel.selectedIndex];
        return opt ? (opt.label || opt.textContent) : '';
    }

    function refreshSelect(sel) {
        var ui = sel._ui;
        if (!ui) return;
        ui.label.textContent = selectedLabel(sel) || ' ';
        var hidden = sel.style.display === 'none' || sel.classList.contains('hidden') || sel.hidden;
        ui.wrap.style.display = hidden ? 'none' : '';
        ui.button.disabled = sel.disabled;
        ui.button.className = ('ui-select-button ' + sel.className.replace('ui-select-native', '')).trim();
        ui.button.title = sel.title || '';
    }

    function closeList(focusButton) {
        if (!openState) return;
        var st = openState;
        openState = null;
        st.list.remove();
        st.sel._ui.button.setAttribute('aria-expanded', 'false');
        st.sel._ui.wrap.classList.remove('is-open');
        if (focusButton) st.sel._ui.button.focus();
    }

    function choose(sel, index) {
        if (index < 0 || index === sel.selectedIndex) { closeList(true); return; }
        sel.selectedIndex = index;
        sel.dispatchEvent(new Event('input', { bubbles: true }));
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        refreshSelect(sel);
        closeList(true);
    }

    function setActive(st, idx) {
        if (!st.items.length) return;
        idx = Math.max(0, Math.min(st.items.length - 1, idx));
        if (st.active >= 0) st.items[st.active].el.classList.remove('is-active');
        st.active = idx;
        var el = st.items[idx].el;
        el.classList.add('is-active');
        el.scrollIntoView({ block: 'nearest' });
    }

    function placeList(sel, list) {
        var r = sel._ui.button.getBoundingClientRect();
        list.style.minWidth = r.width + 'px';
        list.style.left = Math.max(4, Math.min(r.left, window.innerWidth - list.offsetWidth - 4)) + 'px';
        var below = window.innerHeight - r.bottom - 8;
        var above = r.top - 8;
        var h = list.offsetHeight;
        if (h > below && above > below) {
            list.style.top = Math.max(4, r.top - h - 4) + 'px';
            list.classList.add('is-up');
        } else {
            list.style.top = (r.bottom + 4) + 'px';
        }
    }

    function openList(sel) {
        closeList(false);
        var list = document.createElement('div');
        list.className = 'ui-select-list';
        list.setAttribute('role', 'listbox');
        var items = [];
        Array.prototype.forEach.call(sel.options, function (opt, index) {
            if (opt.hidden) return;
            var el = document.createElement('div');
            el.className = 'ui-select-option';
            el.setAttribute('role', 'option');
            el.textContent = opt.label || opt.textContent;
            if (index === sel.selectedIndex) { el.classList.add('is-selected'); el.setAttribute('aria-selected', 'true'); }
            if (opt.disabled) el.classList.add('is-disabled');
            el.addEventListener('mousedown', function (e) { e.preventDefault(); });
            el.addEventListener('click', function () { if (!opt.disabled) choose(sel, index); });
            el.addEventListener('mousemove', function () {
                if (openState && !opt.disabled) setActive(openState, items.findIndex(function (it) { return it.el === el; }));
            });
            list.appendChild(el);
            items.push({ el: el, index: index, disabled: opt.disabled });
        });
        document.body.appendChild(list);
        placeList(sel, list);
        openState = { sel: sel, list: list, items: items, active: -1 };
        var cur = items.findIndex(function (it) { return it.index === sel.selectedIndex; });
        setActive(openState, cur >= 0 ? cur : 0);
        sel._ui.button.setAttribute('aria-expanded', 'true');
        sel._ui.wrap.classList.add('is-open');
    }

    function moveActive(st, delta) {
        var i = st.active;
        do { i += delta; } while (i >= 0 && i < st.items.length && st.items[i].disabled);
        if (i >= 0 && i < st.items.length) setActive(st, i);
    }

    function enhanceSelect(sel) {
        if (sel._ui || sel.multiple || sel.size > 1 || sel.hasAttribute('data-native')) return;

        var wrap = document.createElement('span');
        wrap.className = 'ui-select';
        var button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-haspopup', 'listbox');
        button.setAttribute('aria-expanded', 'false');
        var label = document.createElement('span');
        label.className = 'ui-select-label';
        button.appendChild(label);

        sel.parentNode.insertBefore(wrap, sel);
        wrap.appendChild(button);
        wrap.appendChild(sel);
        sel.classList.add('ui-select-native');
        sel.tabIndex = -1;
        sel.setAttribute('aria-hidden', 'true');
        if (sel.id) {
            var lab = document.querySelector('label[for="' + sel.id + '"]');
            if (lab) lab.addEventListener('click', function (e) { e.preventDefault(); button.focus(); });
        }
        sel._ui = { wrap: wrap, button: button, label: label };

        button.addEventListener('click', function () {
            if (openState && openState.sel === sel) closeList(true); else openList(sel);
        });
        button.addEventListener('keydown', function (e) {
            var st = openState && openState.sel === sel ? openState : null;
            if (!st) {
                if (['ArrowDown', 'ArrowUp', 'Enter', ' '].indexOf(e.key) >= 0) { e.preventDefault(); openList(sel); }
                return;
            }
            if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(st, 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(st, -1); }
            else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (st.active >= 0) choose(sel, st.items[st.active].index); }
            else if (e.key === 'Escape') { e.preventDefault(); closeList(true); }
            else if (e.key === 'Tab') { closeList(false); }
        });

        // Les scripts écrivent .value / .selectedIndex sans événement : on intercepte
        ['value', 'selectedIndex'].forEach(function (prop) {
            var d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, prop);
            Object.defineProperty(sel, prop, {
                configurable: true,
                get: function () { return d.get.call(this); },
                set: function (v) { d.set.call(this, v); refreshSelect(this); }
            });
        });
        sel.addEventListener('change', function () { refreshSelect(sel); });
        // Options reconstruites, select masqué/affiché (style/class), désactivé...
        new MutationObserver(function () { refreshSelect(sel); })
            .observe(sel, { childList: true, subtree: true, characterData: true, attributes: true,
                            attributeFilter: ['style', 'class', 'disabled', 'hidden', 'selected', 'label', 'title'] });
        refreshSelect(sel);
    }

    document.addEventListener('mousedown', function (e) {
        if (openState && !openState.list.contains(e.target) && !openState.sel._ui.wrap.contains(e.target)) closeList(false);
    });
    window.addEventListener('resize', function () { closeList(false); });
    window.addEventListener('scroll', function (e) {
        if (openState && !openState.list.contains(e.target)) closeList(false);
    }, true);

    window.enhanceSelects = function (root) {
        (root || document).querySelectorAll('select').forEach(enhanceSelect);
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.enhanceSelects();
        // Selects ajoutés plus tard par les scripts (modales, listes dynamiques)
        new MutationObserver(function (muts) {
            muts.forEach(function (m) {
                m.addedNodes.forEach(function (n) {
                    if (n.nodeType !== 1) return;
                    if (n.tagName === 'SELECT') enhanceSelect(n);
                    else if (n.querySelectorAll) n.querySelectorAll('select').forEach(enhanceSelect);
                });
            });
        }).observe(document.body, { childList: true, subtree: true });
    });
})();
