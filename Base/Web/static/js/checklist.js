// Check-list avant match (calculée par le robot : Rasp/core/preflight.py, reçue dans sys_info.checks).
// Remplit chaque élément .checklist de la page :
//   data-mode="problemes" (accueil, écran du robot) : un résumé + seulement ce qui ne va pas ;
//   data-mode="complet" (Debug) : toutes les vérifications.
(function () {
    const NIVEAU_TXT = { ok: 'OK', warn: 'À vérifier', err: 'Bloquant' };
    let dernier = null;
    let recu = 0;

    function ligne(c) {
        const detail = c.detail ? `<span class="check-detail">${escapeHtml(c.detail)}</span>` : '';
        return `<li class="check-item check-${c.niveau}" title="${NIVEAU_TXT[c.niveau] || ''}">` +
            `<span class="check-dot"></span><span class="check-label">${escapeHtml(c.label)}</span>${detail}</li>`;
    }

    function rendre() {
        const els = document.querySelectorAll('.checklist');
        if (!els.length) return;
        const vieux = !dernier || Date.now() - recu > 4000;
        els.forEach(el => {
            if (vieux) {
                el.innerHTML = '<div class="check-resume check-resume-warn">Check-list : robot muet</div>';
                return;
            }
            const err = dernier.filter(c => c.niveau === 'err');
            const warn = dernier.filter(c => c.niveau === 'warn');
            const resume = err.length ? `${err.length} bloquant${err.length > 1 ? 's' : ''}`
                : warn.length ? `PRÊT · ${warn.length} à vérifier` : 'PRÊT';
            const cls = err.length ? 'err' : warn.length ? 'warn' : 'ok';
            const items = el.dataset.mode === 'complet' ? dernier : err.concat(warn);
            const html = `<div class="check-resume check-resume-${cls}">${resume}</div>` +
                (items.length ? `<ul class="check-list">${items.map(ligne).join('')}</ul>` : '');
            if (el._html !== html) { el._html = html; el.innerHTML = html; }
        });
    }

    window.socket.on('sys_info', (data) => {
        if (!data || !Array.isArray(data.checks)) return;  // sys_info virtuel (télémétrie) : pas de check-list
        dernier = data.checks;
        recu = Date.now();
        rendre();
    });
    setInterval(rendre, 2000);
    document.addEventListener('DOMContentLoaded', rendre);
})();
