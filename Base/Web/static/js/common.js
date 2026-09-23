// --- SocketWrapper to emulate Socket.IO client using standard HTML5 WebSockets ---
class SocketWrapper {
    constructor() {
        this.listeners = {};
        this.connect();
    }

    connect() {
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
            console.log("WebSocket disconnected, reconnecting in 2s...");
            setTimeout(() => this.connect(), 2000);
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
    // Petit feedback visuel console
    console.log("Envoi action :", act);
    // Use fetch API instead of socket.emit because the server exposes a REST endpoint
    fetch('/api/action/' + act, { method: 'POST' });
}

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
    localState = state;
    // Gestion des classes globales (couleur équipe, animation match)
    document.body.classList.remove('mode-BLEUE', 'mode-JAUNE');
    document.body.classList.add('mode-' + state.team);

    if (state.match_finished) document.body.classList.add('breathing-' + state.team);
    else document.body.classList.remove('breathing-BLEUE', 'breathing-JAUNE');

    if (state && state.telemetry && state.telemetry.rasp_ip && state.telemetry.rasp_ip !== '??' && state.telemetry.rasp_ip !== 'Err') {
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
    sysInfoEl.innerHTML = `<span class="sys-info-item">Base: ${baseIp}</span><span class="sys-info-sep">|</span><span class="sys-info-item">Robot: ${raspIp}</span><span class="sys-info-sep">|</span><span class="sys-info-item sys-info-volt">${v}</span>`;
}

// --- MISE À JOUR COMMUNE DES INFOS SYSTEME (IP & Batterie) SUR PC ---
window.socket.on('sys_info', (data) => {
    const incoming = data.rasp_ip || data.ip;
    if (incoming && incoming !== '??' && incoming !== 'Err' && incoming !== '127.0.0.1' && incoming !== window.serverIP) {
        window.raspIP = incoming;
    }
    updateSysInfoDisplay(data.volt || data.volt_float);
});
