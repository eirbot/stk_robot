// Page Debug : caméra zénithale (flux, résolution, ArUco, worker de vision).
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

/* ==========================================================================
   GESTION DU FLUX CAMÉRA ZÉNITHALE USB & PLEIN ÉCRAN
   ========================================================================== */

let isArucoActive = true;
let currentCamResolution = "4K";
let zenithaleStatusTimer = null;
let isZenithaleStreamConnected = false;

function initZenithaleVision() {
    // S'assurer que les boutons quitter plein écran sont strictement masqués au démarrage
    document.querySelectorAll('.fullscreen-close-btn').forEach(btn => {
        btn.style.setProperty('display', 'none', 'important');
    });

    // Initialisation de la surveillance du statut zénithale
    checkZenithaleStatus();
    if (!zenithaleStatusTimer) {
        zenithaleStatusTimer = setInterval(checkZenithaleStatus, 1000);
    }

    // Écouteur pour le mode plein écran
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' || e.key === 'Esc') {
            exitFullscreen();
        }
    });
}

/**
 * Bascule la résolution de la caméra USB (4K @ 30fps <-> 1080p @ 60fps)
 */
async function toggleCameraResolution() {
    const btn = document.getElementById('btn-toggle-resolution');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
    }

    try {
        const host = window.location.hostname || 'localhost';
        const resp = await fetch(`http://${host}:8082/api/toggle_resolution`);
        if (resp.ok) {
            const data = await resp.json();
            currentCamResolution = data.requested || (currentCamResolution === '4K' ? '1080P' : '4K');
            updateResolutionButtonUI(currentCamResolution);
        } else {
            // Fallback via Go backend
            const resp2 = await fetch('/api/vision/resolution', { method: 'POST' });
            if (resp2.ok) {
                const data2 = await resp2.json();
                currentCamResolution = data2.requested || (currentCamResolution === '4K' ? '1080P' : '4K');
                updateResolutionButtonUI(currentCamResolution);
            }
        }
    } catch (e) {
        console.error("Erreur toggleCameraResolution:", e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
        setTimeout(checkZenithaleStatus, 600);
    }
}

function updateResolutionButtonUI(resKey) {
    const btn = document.getElementById('btn-toggle-resolution');
    if (!btn) return;
    const cleanKey = (resKey || '4K').toUpperCase();
    if (cleanKey === '1080P') {
        btn.innerHTML = icon('zap') + ' 1080p @ 60fps';
        btn.className = 'btn-video-action btn-resolution-toggle mode-60fps';
        btn.title = 'Actuellement 1080p @ 60fps (Cliquer pour basculer en 4K @ 30fps)';
    } else if (cleanKey === '2K') {
        btn.innerHTML = icon('zap') + ' 2K @ 60fps';
        btn.className = 'btn-video-action btn-resolution-toggle mode-60fps';
        btn.title = 'Actuellement 2K @ 60fps (Cliquer pour basculer en 4K @ 30fps)';
    } else {
        btn.innerHTML = icon('video') + ' 4K @ 30fps';
        btn.className = 'btn-video-action btn-resolution-toggle';
        btn.title = 'Actuellement 4K @ 30fps (Cliquer pour basculer en 1080p @ 60fps)';
    }
}

/**
 * Bascule l'incrustation ArUco dans le flux vidéo
 */
function toggleArucoOverlay() {
    isArucoActive = !isArucoActive;
    console.log("Toggle ArUco Overlay ->", isArucoActive);

    const btn = document.getElementById('btn-toggle-aruco');
    if (btn) {
        if (isArucoActive) {
            btn.innerHTML = icon('scan') + ' ArUco : ON';
            btn.className = 'btn-video-action btn-aruco-active';
        } else {
            btn.innerHTML = icon('scan') + ' ArUco : OFF';
            btn.className = 'btn-video-action btn-aruco-inactive';
        }
    }

    // Mise à jour immédiate du flux avec la nouvelle requête
    const img = document.getElementById('zenithale-stream');
    if (img && img.style.display !== 'none') {
        const host = window.location.hostname || 'localhost';
        img.src = `http://${host}:8082/stream?aruco=${isArucoActive ? 1 : 0}&t=${Date.now()}`;
    }

    // Notifier le serveur vision en arrière-plan
    try {
        const host = window.location.hostname || 'localhost';
        fetch(`http://${host}:8082/api/toggle_aruco?state=${isArucoActive ? 1 : 0}`, { mode: 'no-cors' }).catch(() => {});
    } catch (e) {}
}

/**
 * Vérifie l'état de la caméra zénithale et met à jour l'interface
 */
async function checkZenithaleStatus() {
    const img = document.getElementById('zenithale-stream');
    const placeholder = document.getElementById('zenithale-placeholder');
    const badge = document.getElementById('zenithale-badge');
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    const host = window.location.hostname || 'localhost';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1200);
        const resp = await fetch(`http://${host}:8082/api/status`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (resp.ok) {
            const data = await resp.json();
            isZenithaleStreamConnected = true;

            if (img && placeholder) {
                const streamUrl = `http://${host}:8082/stream?aruco=${isArucoActive ? 1 : 0}`;
                if (!img.src || !img.src.includes(':8082/stream') || img.style.display === 'none') {
                    img.src = streamUrl;
                }
                img.style.display = 'block';
                placeholder.style.display = 'none';
            }

            if (badge) {
                if (data.robot_detected) {
                    badge.innerText = `ROBOT VU (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                } else if (data.homography_ready) {
                    badge.innerText = `TABLE CALIBRÉE (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                } else {
                    badge.innerText = `EN DIRECT (${data.fps || 30} FPS)`;
                    badge.className = 'badge-status-pill badge-online';
                }
            }

            if (data.resolution) {
                currentCamResolution = data.resolution;
                updateResolutionButtonUI(data.resolution);
            }

            if (pwrBtn) {
                pwrBtn.innerHTML = icon('circle-stop') + ' Arrêter';
                pwrBtn.className = 'btn-video-action btn-vision-power running';
            }

            // Mise à jour des coordonnées et statuts du panneau télémétrie zénithale
            updateZenithaleTelemetryUI(data);
            return;
        }
    } catch (err) {
        // En cas d'erreur de communication avec le port 8082
        isZenithaleStreamConnected = false;
    }

    // Si le port 8082 ne répond pas, vérification via le backend Go
    try {
        const resp = await fetch('/api/vision/status');
        if (resp.ok) {
            const data = await resp.json();
            if (pwrBtn) {
                if (data.running) {
                    pwrBtn.innerHTML = icon('circle-stop') + ' Arrêter';
                    pwrBtn.className = 'btn-video-action btn-vision-power running';
                } else {
                    pwrBtn.innerHTML = icon('play') + ' Démarrer';
                    pwrBtn.className = 'btn-video-action btn-vision-power';
                }
            }
        }
    } catch (e) {}

    // Affichage de l'état déconnecté
    if (img && placeholder) {
        img.style.display = 'none';
        placeholder.style.display = 'flex';
    }
    if (badge) {
        badge.innerText = 'HORS LIGNE';
        badge.className = 'badge-status-pill badge-offline';
    }

    // Réinitialisation du panneau télémétrie zénithale
    updateZenithaleTelemetryUI(null);
}

/**
 * Met à jour le bandeau d'affichage de la télémétrie zénithale (X, Y, Theta, Robot, Table)
 */
function updateZenithaleTelemetryUI(data) {
    const zenRobotStatus = document.getElementById('zen-robot-status');
    const zenPosX = document.getElementById('zen-pos-x');
    const zenPosY = document.getElementById('zen-pos-y');
    const zenPosTheta = document.getElementById('zen-pos-theta');
    const zenTableStatus = document.getElementById('zen-table-status');
    const zenTagsList = document.getElementById('zen-tags-list');
    const livePosX = document.getElementById('live-pos-x');
    const livePosY = document.getElementById('live-pos-y');
    const livePosTheta = document.getElementById('live-pos-theta');

    if (!data) {
        if (zenRobotStatus) {
            zenRobotStatus.innerText = 'HORS LIGNE';
            zenRobotStatus.className = 'telemetry-badge-status not-detected';
        }
        if (zenPosX) zenPosX.innerText = '--';
        if (zenPosY) zenPosY.innerText = '--';
        if (zenPosTheta) zenPosTheta.innerText = '--';
        if (zenTableStatus) {
            zenTableStatus.innerText = 'HORS LIGNE';
            zenTableStatus.className = 'telemetry-subval';
        }
        if (zenTagsList) zenTagsList.innerText = '--';
        return;
    }

    window.lastVisionData = data;

    if (zenRobotStatus) {
        const tagLabel = data.robot_tag_id ? `TAG #${data.robot_tag_id}` : 'TAG #2';
        if (data.robot_detected) {
            zenRobotStatus.innerText = `DÉTECTÉ (${tagLabel})`;
            zenRobotStatus.className = 'telemetry-badge-status detected';
        } else {
            zenRobotStatus.innerText = `NON DÉTECTÉ (${tagLabel})`;
            zenRobotStatus.className = 'telemetry-badge-status not-detected';
        }
    }

    if (zenPosX && zenPosY && zenPosTheta) {
        if (data.robot_detected) {
            zenPosX.innerText = Math.round(data.robot_x);
            zenPosY.innerText = Math.round(data.robot_y);
            zenPosTheta.innerText = Number(data.robot_theta_deg).toFixed(1);
        } else {
            zenPosX.innerText = '--';
            zenPosY.innerText = '--';
            zenPosTheta.innerText = '--';
        }
    }

    if (zenTableStatus) {
        if (data.homography_ready) {
            zenTableStatus.innerText = 'CALIBRÉE (4/4)';
            zenTableStatus.className = 'telemetry-subval ready';
        } else {
            const tableTags = [10, 11, 12, 13];
            const nbTags = (data.detected_ids || []).filter(id => tableTags.includes(id)).length;
            zenTableStatus.innerText = `ATTENTE (${nbTags}/4)`;
            zenTableStatus.className = 'telemetry-subval';
        }
    }

    if (zenTagsList) {
        if (data.detected_ids && data.detected_ids.length > 0) {
            zenTagsList.innerText = '[' + data.detected_ids.join(', ') + ']';
        } else {
            zenTagsList.innerText = 'Aucun';
        }
    }

    // Mise à jour de la carte odométrie avec la vision en temps réel si détecté
    if (data.robot_detected) {
        if (livePosX) livePosX.innerText = Math.round(data.robot_x);
        if (livePosY) livePosY.innerText = Math.round(data.robot_y);
        if (livePosTheta) livePosTheta.innerText = Number(data.robot_theta_deg).toFixed(1);
    }
}

/**
 * Copie les coordonnées détectées par la caméra zénithale directement dans les champs d'entrée d'odométrie
 */
function copyVisionToInputs() {
    if (!window.lastVisionData || !window.lastVisionData.robot_detected) {
        alert("Le robot n'est pas encore détecté par la caméra zénithale.");
        return;
    }
    const inputX = document.getElementById('pos-x');
    const inputY = document.getElementById('pos-y');
    const inputTheta = document.getElementById('pos-theta');
    if (inputX) inputX.value = Math.round(window.lastVisionData.robot_x);
    if (inputY) inputY.value = Math.round(window.lastVisionData.robot_y);
    if (inputTheta) inputTheta.value = Math.round(window.lastVisionData.robot_theta_deg);

    showNotification("Coordonnées Vision copiées dans les entrées odométriques !");
}

/**
 * Démarre le sous-processus vision_worker
 */
async function startVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn) pwrBtn.innerText = 'Démarrage...';
    try {
        await fetch('/api/vision/start', { method: 'POST' });
    } catch (e) {
        console.error("Erreur startVisionWorker:", e);
    }
    setTimeout(checkZenithaleStatus, 800);
}

/**
 * Arrête le sous-processus vision_worker
 */
async function stopVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn) pwrBtn.innerText = 'Arrêt...';
    try {
        await fetch('/api/vision/stop', { method: 'POST' });
    } catch (e) {
        console.error("Erreur stopVisionWorker:", e);
    }
    setTimeout(checkZenithaleStatus, 400);
}

/**
 * Bascule marche/arrêt du vision_worker
 */
async function toggleVisionWorker() {
    const pwrBtn = document.getElementById('btn-toggle-vision-worker');
    if (pwrBtn && pwrBtn.classList.contains('running')) {
        await stopVisionWorker();
    } else {
        await startVisionWorker();
    }
}
