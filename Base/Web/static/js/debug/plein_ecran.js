// Page Debug : affichage plein écran des flux caméra.
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

/**
 * Met à jour l'affichage d'un conteneur vidéo selon qu'il est en plein écran ou non
 */
function updateContainerFullscreenUI(containerId, isFs) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const isZenithale = (containerId === 'container-zenithale');
    const closeBtn = document.getElementById(isZenithale ? 'fs-close-zenithale' : 'fs-close-embarquee');
    const toggleBtn = document.getElementById(isZenithale ? 'btn-fullscreen-zenithale' : 'btn-fullscreen-embarquee');
    const img = container.querySelector('.video-feed');

    if (isFs) {
        container.classList.add('is-fullscreen');
        if (closeBtn) closeBtn.style.setProperty('display', 'block', 'important');
        if (toggleBtn) toggleBtn.innerHTML = icon('x') + ' Quitter';
        if (img) {
            img.style.setProperty('max-height', '100vh', 'important');
            img.style.setProperty('height', '100vh', 'important');
            img.style.setProperty('width', '100vw', 'important');
            img.style.setProperty('object-fit', 'contain', 'important');
        }
    } else {
        container.classList.remove('is-fullscreen');
        if (closeBtn) closeBtn.style.setProperty('display', 'none', 'important');
        if (toggleBtn) toggleBtn.innerHTML = icon('maximize') + ' Plein écran';
        if (img) {
            img.style.removeProperty('max-height');
            img.style.removeProperty('height');
            img.style.removeProperty('width');
            img.style.removeProperty('object-fit');
        }
    }
}

/**
 * Bascule le plein écran pour un conteneur vidéo donné
 */
async function toggleFullscreen(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    const isCurrentFs = (fsEl === container) || container.classList.contains('is-fullscreen');

    if (isCurrentFs) {
        await exitFullscreen();
    } else {
        // Quitter tout plein écran préexistant d'abord
        if (fsEl || document.querySelector('.video-display-container.is-fullscreen')) {
            await exitFullscreen();
        }

        try {
            if (container.requestFullscreen) {
                await container.requestFullscreen();
            } else if (container.webkitRequestFullscreen) {
                container.webkitRequestFullscreen();
            } else if (container.mozRequestFullScreen) {
                container.mozRequestFullScreen();
            } else if (container.msRequestFullscreen) {
                container.msRequestFullscreen();
            } else {
                updateContainerFullscreenUI(containerId, true);
            }
        } catch (err) {
            console.warn('requestFullscreen a échoué, fallback CSS:', err);
            updateContainerFullscreenUI(containerId, true);
        }
    }
}

/**
 * Quitte le mode plein écran proprement et restaure la page de debug
 */
async function exitFullscreen() {
    // 1. Réinitialiser immédiatement l'état visuel de tous les conteneurs
    updateContainerFullscreenUI('container-zenithale', false);
    updateContainerFullscreenUI('container-embarquee', false);

    // 2. Quitter le plein écran natif du navigateur si actif
    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    if (fsEl) {
        try {
            if (document.exitFullscreen) {
                await document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        } catch (e) {
            console.warn('Erreur lors de exitFullscreen:', e);
        }
    }

    // 3. Forcer une seconde fois la remise à zéro
    updateContainerFullscreenUI('container-zenithale', false);
    updateContainerFullscreenUI('container-embarquee', false);
}

/**
 * Met à jour l'état et l'interface lors des changements d'état plein écran du navigateur
 */
function handleFullscreenChange() {
    const fsEl = document.fullscreenElement || 
                 document.webkitFullscreenElement || 
                 document.mozFullScreenElement || 
                 document.msFullscreenElement;

    const isZenithaleFs = Boolean(fsEl && (fsEl.id === 'container-zenithale' || fsEl.contains(document.getElementById('zenithale-stream'))));
    const isEmbarqueeFs = Boolean(fsEl && (fsEl.id === 'container-embarquee' || fsEl.contains(document.getElementById('camera-stream'))));

    updateContainerFullscreenUI('container-zenithale', isZenithaleFs);
    updateContainerFullscreenUI('container-embarquee', isEmbarqueeFs);
}
