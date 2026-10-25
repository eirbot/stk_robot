// Page Debug : journaux du robot et infos système (CPU, batterie, périphériques).
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

function appendLog(msg, type = 'info') {
    const box = document.getElementById('logs-box');
    if (!box) return;
    const div = document.createElement('div');
    div.className = 'log-line';
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    let cls = 'log-info';
    if (type === 'warn' || msg.includes('[WARN]')) cls = 'log-warn';
    if (type === 'err' || msg.includes('[ERR]')) cls = 'log-err';
    div.innerHTML = `<span class="log-time">${timeStr}</span> <span class="${cls}">${escapeHtml(msg)}</span>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// Reception des logs
window.socket.on('new_log', (log) => {
    appendLog(log.msg);
});

// Infos système & mise à jour du graphique et des statuts périphériques
window.socket.on('sys_info', (data) => {
    // Le sys_info virtuel (dérivé de la télémétrie à 10 Hz) n'a pas de courant : on l'ignore pour le graphe
    if (currentChart && data.current !== undefined) {
        const now = new Date().toLocaleTimeString();
        currentChart.data.labels.push(now);
        currentChart.data.datasets[0].data.push(parseFloat(data.current));
        // 1200 points max : au-delà, le redessin du graphe rame sur téléphone
        if (currentChart.data.labels.length > 1200) {
            currentChart.data.labels.shift();
            currentChart.data.datasets[0].data.shift();
        }
        currentChart.update('none'); // Sans animation : redessin bien moins coûteux
    }
    if (data.devs && document.getElementById('status-lidar')) {
        updateDevStatus('status-lidar', data.devs.lidar);
        updateDevStatus('status-esp_motors', data.devs.esp_motors);
        updateDevStatus('status-esp_arms', data.devs.esp_arms);
        updateDevStatus('status-camera', data.devs.camera);

        // Mise à jour de la source du flux vidéo caméra (HTTP MJPEG)
        const img = document.getElementById('camera-stream');
        const placeholder = document.getElementById('camera-placeholder');
        const embarqueeBadge = document.getElementById('embarquee-badge');
        if (img && placeholder) {
            if (data.devs.camera && data.ip) {
                const streamUrl = 'http://' + data.ip + ':8081/stream' + (window.arucoEmbarquee ? '?aruco=1' : '');
                // Évite de réassigner inutilement l'URL pour ne pas interrompre le flux continu
                if (img.src !== streamUrl) {
                    img.src = streamUrl;
                }
                img.style.display = 'block';
                placeholder.style.display = 'none';
                if (embarqueeBadge) {
                    embarqueeBadge.innerText = 'EN DIRECT';
                    embarqueeBadge.className = 'badge-status-pill badge-online';
                }
            } else {
                img.style.display = 'none';
                placeholder.style.display = 'block';
                placeholder.innerHTML = '<div class="placeholder-icon">' + icon('camera', 'icon-lg') + '</div><div id="camera-placeholder-text">Flux caméra inactif ou arrêté.</div>';
                if (embarqueeBadge) {
                    embarqueeBadge.innerText = 'HORS LIGNE';
                    embarqueeBadge.className = 'badge-status-pill badge-offline';
                }
            }
        }
    }
});

// Tags ArUco sur la caméra embarquée (Rasp/Vision/aruco.py) : ?aruco=1 dessine les tags et active la
// détection tant que le flux est ouvert ; l'URL change au prochain sys_info (1 s).
window.arucoEmbarquee = false;
function toggleArucoEmbarquee() {
    window.arucoEmbarquee = !window.arucoEmbarquee;
    const btn = document.getElementById('btn-toggle-aruco-emb');
    if (btn) {
        btn.innerHTML = icon('scan') + (window.arucoEmbarquee ? ' Tags : ON' : ' Tags : OFF');
        btn.classList.toggle('btn-aruco-active', window.arucoEmbarquee);
    }
}
