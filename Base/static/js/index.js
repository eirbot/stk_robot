// index.js corrigé — Mise à jour de l'affichage en fonction des données de `state`

// Lorsque le serveur envoie un état, on met à jour l'interface si la page possède un score
window.socket.on('state_update', (state) => {
    // Sécurité : si on est sur une autre page, on ne fait rien
    if (!document.getElementById('score')) return;

    // --- 1. ÉQUIPE ---
    document.getElementById('team-display').innerText = 'ÉQUIPE ' + state.team;

    // --- 2. SCORE ---
    // On accepte score_current ou score selon ce qui existe dans le state
    const scoreVal = state.score_current ?? state.score ?? 0;
    document.getElementById('score').innerText = scoreVal;

    // --- 3. TIMER ---
    // On préfère la version string formatée par le Python, sinon on le fait nous-même
    const timer = state.timer_str ?? (typeof state.timer !== 'undefined' ? Number(state.timer).toFixed(1) : '0.0');
    document.getElementById('timer').innerText = timer;

    // --- 4. STRATÉGIE ---
    const stratEl = document.getElementById('strat-display');
    const stratSel = document.getElementById('strat-select');

    if (stratEl && stratSel) {
        const config = state.config || {};
        const mode = state.strat_mode ?? config.strat_mode ?? 'DYNAMIC';

        if (mode === 'STATIC') {
            // Mode interactif : on affiche le sélecteur
            stratEl.style.display = 'none';
            stratSel.style.display = 'inline-block';
            stratSel.style.color = "#FF9800";

            // On sélectionne la bonne valeur si elle existe
            const current = state.strat_id ?? config.static_strat;
            if (current) stratSel.value = current;

        } else {
            // Mode auto : on affiche juste le texte
            stratEl.style.display = 'inline-block';
            stratSel.style.display = 'none';

            stratEl.innerText = 'DYNAMIQUE (Auto)';
            stratEl.style.color = "#ccc";
        }
    }

    // --- 5. ÉTAT FSM ---
    const fsmEl = document.getElementById('fsm-display');
    if (fsmEl) {
        fsmEl.innerText = state.fsm_state ?? 'INIT';
    }

    // --- 6. TIRETTE ---
    const tirDiv = document.getElementById('tirette-status');
    if (tirDiv) {
        const tir = state.tirette ?? false;
        // Gestion souple : supporte les strings ("ARMED") ou les booléens (True/False)
        if (tir === 'ARMED' || tir === true) {
            tirDiv.innerText = 'TIRETTE: ARMÉE (PRÊT)';
            tirDiv.className = 'tirette-box status-armed';
        } else if (tir === 'TRIGGERED') {
            tirDiv.innerText = 'TIRETTE: TIRÉE (GO)';
            tirDiv.className = 'tirette-box status-triggered';
        } else {
            tirDiv.innerText = 'TIRETTE: NON ARMÉE';
            tirDiv.className = 'tirette-box status-non-armed';
        }
    }

    // --- 7. BOUTONS MATCH ---
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const btnReset = document.getElementById('btn-reset');

    if (btnStart && btnStop && btnReset) {
        const running = state.match_running ?? (state.fsm_state === 'MATCH');
        const finished = state.match_finished ?? (state.fsm_state === 'FINISHED');

        if (finished) {
            btnStart.classList.add('hidden');
            btnStop.classList.add('hidden');
            btnReset.classList.remove('hidden');
        } else if (running) {
            btnStart.classList.add('hidden');
            btnStop.classList.remove('hidden');
            btnReset.classList.add('hidden');
        } else {
            btnStart.classList.remove('hidden');
            btnStop.classList.add('hidden');
            btnReset.classList.add('hidden');
        }
    }

    // --- 8. Score Manuel ---
    // On cache les flèches pendant le match pour éviter les fausses manips
    const arrows = document.querySelectorAll('.btn-arrow');
    const manualEnabled = state.manual_score_enabled ?? true;
    const runningMatch = state.match_running ?? (state.fsm_state === 'MATCH');

    arrows.forEach(e => {
        e.style.visibility = (manualEnabled && !runningMatch) ? 'visible' : 'hidden';
    });
});

// Fonction indispensable pour les boutons de score
function adjustScore(delta) {
    fetch('/api/score_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delta: delta })
    });
}

// Initialisation : Chargement des stratégies (Global)
// Initial Load
loadBlocklyStrats('strat-select');

// Auto-Refresh Strategy List every 5 seconds (Sync Robot/PC)
setInterval(() => loadBlocklyStrats('strat-select'), 5000);

// Changement de stratégie via le sélecteur (Global)
async function updateStrat(event_or_val) {
    let val = event_or_val;
    // Handle both direct call (string) and event handler (Event)
    if (event_or_val && event_or_val.target) {
        val = event_or_val.target.value;
    } else if (!val) {
        const sel = document.getElementById('strat-select');
        val = sel ? sel.value : null;
    }

    if (!val) return;

    await fetch('/api/config_edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'static_strat', val: val })
    });
}
