// Page Debug : mise à jour de la Rasp, flash des ESP, versions du code.
// Fichiers de la page chargés dans l'ordre par templates/debug.html (portée globale partagée).

async function updateRasp() {
    if (!await askConfirm("Mettre à jour le code de la Rasp (git pull sur la base, copie vers le robot, redémarrage du launcher) ?")) {
        return;
    }

    const btn = document.getElementById('btn-update-rasp');
    const oldText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Mise à jour...";
        btn.style.opacity = "0.7";
    }
    appendLog("[RASP] Mise à jour du code de la Rasp...");

    try {
        const resp = await fetch('/api/update_rasp', { method: 'POST' });
        const data = await resp.json();
        if (data.warning) appendLog(`[RASP] ${data.warning}`, 'err');
        if (data.status === 'ok') {
            appendLog(`[RASP] ${data.msg}`);
            (data.files || []).forEach(f => appendLog(`   • ${f}`));
            alert(`${data.msg}`);
        } else {
            const stepMsg = data.step ? `(Étape: ${data.step}) ` : '';
            appendLog(`[RASP] Erreur ${stepMsg}: ${data.msg}`, 'err');
            if (data.output) {
                appendLog(`[DÉTAILS] ${data.output.split('\n').filter(l => l.trim()).slice(-3).join(' | ')}`, 'err');
            }
            alert(`${data.msg}`);
        }
    } catch (err) {
        appendLog(`[RASP] Erreur réseau : ${err.message}`, 'err');
        alert(`Erreur réseau : ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldText;
            btn.style.opacity = "1";
        }
    }
}

async function flashESP(target) {
    const label = (target === 'motors' || target === 'motor') ? 'MOTEURS' : 'BRAS (Actionneurs)';
    if (!await askConfirm(`Compiler et flasher l'ESP ${label} depuis la base déportée (via la Raspberry Pi) ?`)) {
        return;
    }

    const btn = document.getElementById(target === 'motors' ? 'btn-flash-motors' : 'btn-flash-arms');
    const oldText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = "Compilation & Flash...";
        btn.style.opacity = "0.7";
    }

    appendLog(`[FLASH] Démarrage de la procédure de flash pour l'ESP ${label}...`);
    appendLog(`[FLASH] Étape 1/3 : Compilation locale PlatformIO en cours...`);

    try {
        const resp = await fetch('/api/flash_esp/' + target, { method: 'POST' });
        const data = await resp.json();

        if (data.status === 'ok') {
            appendLog(`[FLASH] ${data.msg}`);
            alert(`${data.msg}\n\nLe microcontrôleur a été redémarré avec le nouveau firmware.`);
        } else {
            const stepMsg = data.step ? `(Étape: ${data.step}) ` : '';
            appendLog(`[FLASH] Erreur ${stepMsg}: ${data.msg}`, 'err');
            alert(`Erreur lors du flash :\n${data.msg}\n\nConsultez les logs pour plus de détails.`);
            if (data.output) {
                console.error("Détails d'erreur :", data.output);
                appendLog(`[DÉTAILS] ${data.output.split('\n').filter(l => l.trim()).slice(-3).join(' | ')}`, 'err');
            }
        }
    } catch (err) {
        appendLog(`[FLASH] Erreur réseau : ${err.message}`, 'err');
        alert(`Erreur réseau : ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = oldText;
            btn.style.opacity = "1";
        }
    }
}


// --- Versions du code (base : binaire ; robot : fichier VERSION écrit au déploiement) ---
async function refreshCodeVersions() {
    const el = document.getElementById('code-versions');
    if (!el) return;
    try {
        const v = await (await fetch('/api/version')).json();
        const robot = v.robot && v.robot.commit ? `${v.robot.commit}${v.robot.date ? ' (' + v.robot.date.slice(0, 16).replace('T', ' ') + ')' : ''}` : 'inconnue';
        setText(el, `Base : ${v.base || 'inconnue'} · Robot : ${robot}`);
    } catch (e) {
        setText(el, 'Versions indisponibles');
    }
}
refreshCodeVersions();
setInterval(refreshCodeVersions, 10000);
