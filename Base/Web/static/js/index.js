// index.js — Mise à jour dynamique de l'affichage (PC et Écran Robot 7")

// Mise à jour de l'affichage de la position du robot (X, Y, Theta)
function updatePositionDisplay(pos) {
    if (!pos) return;
    const posXEl = document.getElementById('pos-x');
    const posYEl = document.getElementById('pos-y');
    const posThetaEl = document.getElementById('pos-theta');
    if (posXEl && pos.x !== undefined && pos.x !== null) {
        posXEl.innerText = Math.round(Number(pos.x));
    }
    if (posYEl && pos.y !== undefined && pos.y !== null) {
        posYEl.innerText = Math.round(Number(pos.y));
    }
    if (posThetaEl && pos.theta !== undefined && pos.theta !== null) {
        posThetaEl.innerText = Number(pos.theta).toFixed(1);
    }
}

// Écoute directe des paquets robot_position
window.socket.on('robot_position', (pos) => {
    updatePositionDisplay(pos);
});

// Écoute de l'état global State
window.socket.on('state_update', (state) => {
    if (!document.getElementById('team-display')) return;

    // --- 1. ÉQUIPE ---
    document.getElementById('team-display').innerText = 'ÉQUIPE ' + state.team;

    // --- 2. TIMER ---
    const timer = state.timer_str ?? (typeof state.timer !== 'undefined' ? Number(state.timer).toFixed(1) : '0.0');
    document.getElementById('timer').innerText = timer;

    // --- 3. POSITION DU ROBOT ---
    if (state.telemetry) {
        updatePositionDisplay(state.telemetry);
    }

    // --- 4. STRATÉGIE ---
    const stratEl = document.getElementById('strat-display');
    const stratSel = document.getElementById('strat-select');

    if (stratEl && stratSel) {
        const config = state.config || {};
        const mode = state.strat_mode ?? config.strat_mode ?? 'DYNAMIC';

        if (mode === 'STATIC') {
            stratEl.style.display = 'none';
            stratSel.style.display = 'inline-block';
            stratSel.style.color = "#FF9800";

            const current = state.strat_id ?? config.static_strat;
            if (current) stratSel.value = current;

        } else {
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

    // --- 8. Infos Système & Stratégie (Haut de l'écran en mode Robot) ---
    const sysInfoEl = document.getElementById('sys-info');
    if (sysInfoEl) {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('mode') === 'robot') {
            const config = state.config || {};
            const stratName = state.strat_id || config.static_strat || 'Aucune';
            let voltStr = '--.-V';
            if (state.telemetry && typeof state.telemetry.voltage === 'number') {
                voltStr = typeof formatVoltage === 'function' ? formatVoltage(state.telemetry.voltage) : state.telemetry.voltage.toFixed(1) + 'V';
            } else if (window.lastVolt) {
                voltStr = window.lastVolt;
            }
            const rIp = (state.telemetry && state.telemetry.rasp_ip) || window.raspIP || '';
            const ipPart = rIp ? `<span class="sys-info-sep">|</span><span class="sys-info-item">${rIp}</span>` : '';
            sysInfoEl.innerHTML = `<span class="sys-info-item">${stratName}</span>${ipPart}<span class="sys-info-sep">|</span><span class="sys-info-item sys-info-volt">${voltStr}</span>`;
        }
    }
});

// Initialisation : Chargement des stratégies (Global)
loadBlocklyStrats('strat-select');

// Auto-Refresh Strategy List every 5 seconds (Sync Robot/PC)
setInterval(() => loadBlocklyStrats('strat-select'), 5000);

// Changement de stratégie via le sélecteur (Global)
async function updateStrat(event_or_val) {
    let val = event_or_val;
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

// Fonction pour faire défiler les stratégies (Bouton 2 sur l'écran robot ou tactile)
function cycleStrat() {
    const sel = document.getElementById('strat-select');
    if (!sel || sel.options.length <= 1) return;
    let nextIdx = sel.selectedIndex + 1;
    if (nextIdx >= sel.options.length) {
        nextIdx = sel.options[0].disabled ? 1 : 0;
    }
    if (sel.options[nextIdx]) {
        sel.selectedIndex = nextIdx;
        updateStrat(sel.options[nextIdx].value);
    }
}
