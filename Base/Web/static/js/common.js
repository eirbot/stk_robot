// Échappe une chaîne avant insertion via innerHTML (logs, IP, noms venant du robot)
function escapeHtml(v) {
    return String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Écritures DOM seulement si la valeur change : la télémétrie arrive à 10 Hz et
// chaque écriture inutile coûte un recalcul de mise en page (sensible sur téléphone)
function setText(el, v) {
    if (!el) return;
    const s = String(v);
    if (el.textContent !== s) el.innerText = s;
}

function setClass(el, v) {
    if (el && el.className !== v) el.className = v;
}

// --- SocketWrapper to emulate Socket.IO client using standard HTML5 WebSockets ---
class SocketWrapper {
    constructor() {
        this.listeners = {};
        this.connect();

        // Onglet en arrière-plan (téléphone verrouillé...) : on coupe le flux 10 Hz
        // pour économiser batterie et CPU, et on se reconnecte au retour
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.ws) this.ws.close();
            } else if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
                this.connect();
            }
        });
    }

    connect() {
        clearTimeout(this.reconnectTimer);
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        this.ws.onmessage = (event) => {
            try {
                const packet = JSON.parse(event.data);
                const type = packet.type;
                const data = packet.data;
                if (!type) return;

                // Dispatch the direct event
                if (this.listeners[type]) {
                    this.listeners[type].forEach(callback => callback(data));
                }

                // If this is a state_update, dispatch virtual events for compatibility
                if (type === 'state_update' && data) {
                    if (data.server_ip) {
                        window.serverIP = data.server_ip;
                    }
                    // Dispatch virtual 'robot_position'
                    if (data.telemetry && this.listeners['robot_position']) {
                        this.listeners['robot_position'].forEach(callback => callback(data.telemetry));
                    }
                    // Dispatch virtual 'sys_info'
                    if (data.telemetry && this.listeners['sys_info']) {
                        const volt = formatVoltage(data.telemetry.voltage);
                        const volt_float = data.telemetry.voltage || 0.0;
                        let displayIp = window.serverIP || data.server_ip;
                        if (!displayIp || displayIp === 'localhost' || displayIp === '127.0.0.1') {
                            if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                                displayIp = window.location.hostname;
                            }
                        }
                        const sysInfoData = {
                            volt: volt,
                            volt_float: volt_float,
                            ip: displayIp || window.location.hostname,
                            rasp_ip: data.telemetry.rasp_ip || window.raspIP || "??",
                            cpu: "N/A"
                        };
                        this.listeners['sys_info'].forEach(callback => callback(sysInfoData));
                    }
                }
            } catch (err) {
                console.error("Error parsing WebSocket message:", err);
            }
        };

        this.ws.onclose = () => {
            if (document.hidden) return; // Reconnexion au retour sur l'onglet
            console.log("WebSocket disconnected, reconnecting in 2s...");
            this.reconnectTimer = setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = (err) => {
            console.error("WebSocket error:", err);
        };
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    emit(event, data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: event, data: data }));
        } else {
            console.warn("WebSocket not open, cannot emit:", event, data);
        }
    }
}

window.socket = new SocketWrapper();
let localState = {};

// --- FONCTIONS PARTAGÉES ---
function sendAction(act) {
    console.log("Envoi action :", act);
    fetch('/api/action/' + act, { method: 'POST' });  // erreurs affichées par le fetch ci-dessous
}

// --- NOTIFICATIONS ---
function toast(msg, type) {
    let box = document.getElementById('toast-box');
    if (!box) {
        box = document.createElement('div');
        box.id = 'toast-box';
        document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = 'toast toast-' + (type || 'info');
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => el.classList.add('toast-out'), 3500);
    setTimeout(() => el.remove(), 4000);
}

// Le robot est la source de vérité : la base peut refuser une commande (robot hors ligne,
// réglage invalide...). Toute réponse en erreur des routes de commande est affichée.
(function () {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (url, opts) {
        const p = nativeFetch(url, opts);
        if (typeof url === 'string' && /^\/api\/(action|config_edit)/.test(url)) {
            p.then(r => {
                if (!r.ok) r.clone().json().then(b => toast(b.msg || ('Erreur ' + r.status), 'err')).catch(() => toast('Erreur ' + r.status, 'err'));
            }).catch(() => toast('Base injoignable', 'err'));
        }
        return p;
    };
})();

// --- LOGIQUE PARTAGÉE STRATÉGIES ---
function loadBlocklyStrats(selectId) {
    fetch('/api/list_blockly_strats')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById(selectId);
            if (sel) {
                // Save current selection to restore it if it still exists
                const currentVal = sel.value;

                sel.innerHTML = '<option value="" disabled>Choisir...</option>';
                data.forEach(s => {
                    let opt = document.createElement('option');
                    opt.value = s;
                    opt.innerText = s;
                    if (s === currentVal) opt.selected = true;
                    sel.appendChild(opt);
                });

                // If nothing selected, restore initial "Choisir..."
                if (!sel.value && sel.querySelector('option[disabled]')) {
                    sel.querySelector('option[disabled]').selected = true;
                }
            }
        })
        .catch(e => console.error("Erreur chargement strats", e));
}

// --- SOCKET GLOBAL STATE WATCHER ---
window.socket.on('state_update', (state) => {
    if (!state) return;
    if (state.config) window.localConfig = state.config;
    if (state.robot_online !== undefined && state.robot_online !== window.robotOnline) {
        window.robotOnline = state.robot_online;
        updateSysInfoDisplay();
    }
    localState = Object.assign(localState, state);
    if (window.localConfig && !localState.config) localState.config = window.localConfig;

    // Gestion des classes globales (couleur équipe, animation match)
    if (state.team) {
        const cl = document.body.classList;
        cl.toggle('mode-BLEUE', state.team === 'BLEUE');
        cl.toggle('mode-JAUNE', state.team === 'JAUNE');
        cl.toggle('breathing-BLEUE', !!state.match_finished && state.team === 'BLEUE');
        cl.toggle('breathing-JAUNE', !!state.match_finished && state.team === 'JAUNE');
    }

    if (state.telemetry && state.telemetry.rasp_ip && state.telemetry.rasp_ip !== '??' && state.telemetry.rasp_ip !== 'Err') {
        window.raspIP = state.telemetry.rasp_ip;
        updateSysInfoDisplay();
    }
});

// --- DÉTECTION DU MODE ÉCRAN ROBOT & RÉCUPÉRATION IP RÉSEAU SERVEUR ---
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'robot') {
        document.body.classList.add('robot-screen');
        console.log("[COMMON] Mode Robot activé (classe CSS robot-screen ajoutée)");
    }

    // Récupération immédiate de la véritable adresse IP réseau du serveur
    fetch('/api/server_ip')
        .then(r => r.json())
        .then(res => {
            if (res && res.ip && res.ip !== '127.0.0.1') {
                window.serverIP = res.ip;
            }
            if (res && res.rasp_ip && res.rasp_ip !== 'Err' && res.rasp_ip !== '' && res.rasp_ip !== '??') {
                window.raspIP = res.rasp_ip;
            }
            updateSysInfoDisplay();
        })
        .catch(() => {});
});

function formatVoltage(val) {
    if (val === null || val === undefined || val === '') return '--.-V';
    if (typeof val === 'number') {
        return val.toFixed(1) + 'V';
    }
    if (typeof val === 'string') {
        const m = val.match(/([0-9]+(?:\.[0-9]+)?)/);
        if (m) {
            const num = parseFloat(m[1]);
            if (!isNaN(num)) return num.toFixed(1) + 'V';
        }
    }
    return '--.-V';
}

function updateSysInfoDisplay(rawVolt) {
    const sysInfoEl = document.getElementById('sys-info');
    if (!sysInfoEl) return;
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'robot') return;

    const baseIp = window.serverIP || '?.?.?.?';
    const raspIp = window.raspIP || '??';
    if (rawVolt) {
        const fv = formatVoltage(rawVolt);
        if (fv !== '--.-V') window.lastVolt = fv;
    }
    const v = window.lastVolt || '--.-V';
    const html = `<span class="sys-info-item">Base: ${escapeHtml(baseIp)}</span><span class="sys-info-sep">|</span><span class="sys-info-item${window.robotOnline === false ? ' sys-info-offline' : ''}">Robot: ${window.robotOnline === false ? 'hors ligne' : escapeHtml(raspIp)}</span><span class="sys-info-sep">|</span><span class="sys-info-item sys-info-volt">${v}</span>`;
    if (html !== window._lastSysInfoHtml) {
        window._lastSysInfoHtml = html;
        sysInfoEl.innerHTML = html;
    }
}

// --- MISE À JOUR COMMUNE DES INFOS SYSTEME (IP & Batterie) SUR PC ---
window.socket.on('sys_info', (data) => {
    const incoming = data.rasp_ip || data.ip;
    if (incoming && incoming !== '??' && incoming !== 'Err' && incoming !== '127.0.0.1' && incoming !== window.serverIP) {
        window.raspIP = incoming;
    }
    updateSysInfoDisplay(data.volt || data.volt_float);
});
