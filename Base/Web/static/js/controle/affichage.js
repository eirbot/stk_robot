// Pilotage : jauges et réglages des vitesses max.
// Fichiers de la page chargés dans l'ordre par templates/controle.html (portée globale partagée).

// =======================================================
// 4. JAUGE & AFFICHAGES EN DIRECT
// =======================================================
function updateGauges(vx, vtheta) {
    const elVx = document.getElementById('val-vx');
    const elVtheta = document.getElementById('val-vtheta');
    const barVx = document.getElementById('bar-vx');
    const barVtheta = document.getElementById('bar-vtheta');

    if (elVx) elVx.innerHTML = `${vx} <small>mm/s</small>`;
    if (elVtheta) elVtheta.innerHTML = `${vtheta} <small>°/s</small>`;

    if (barVx) {
        // -linearMax -> 0%, 0 -> 50%, +linearMax -> 100%
        const pct = 50 + (vx / (linearMax || 1)) * 50;
        barVx.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }

    if (barVtheta) {
        const pct = 50 + (vtheta / (angularMax || 1)) * 50;
        barVtheta.style.width = `${Math.min(100, Math.max(0, pct))}%`;
    }

    // Vitesses des roues, comme le firmware (kinematics::wheelSpeedsFromTwist) : vtheta > 0 =
    // rotation dans le sens trigonométrique, donc roue droite plus rapide
    const omega = (vtheta * Math.PI) / 180.0;
    const vl = Math.round(vx - omega * (ecartRoues / 2.0));
    const vr = Math.round(vx + omega * (ecartRoues / 2.0));

    const elVl = document.getElementById('val-vl');
    const elVr = document.getElementById('val-vr');
    if (elVl) elVl.innerText = `${vl} mm/s`;
    if (elVr) elVr.innerText = `${vr} mm/s`;
}

// =======================================================
// 5. RÉGLAGES & PRESETS
// =======================================================
function initSettings() {
    const toggle = document.getElementById('toggle-invert-y');
    if (toggle) {
        toggle.addEventListener('change', (e) => {
            invertY = e.target.checked;
        });
    }
}

function setLinearMax(val) {
    linearMax = parseInt(val, 10);
    const slider = document.getElementById('slider-linear-max');
    if (slider) slider.value = val;
    const badge = document.getElementById('label-linear-max');
    if (badge) badge.innerText = `${val} mm/s`;

    updateActivePresets('slider-linear-max', val);
    updateGauges(currentVx, currentVtheta);
}

function onLinearSliderChange(val) {
    linearMax = parseInt(val, 10);
    const badge = document.getElementById('label-linear-max');
    if (badge) badge.innerText = `${val} mm/s`;
    updateActivePresets('slider-linear-max', val);
    updateGauges(currentVx, currentVtheta);
}

function setAngularMax(val) {
    angularMax = parseInt(val, 10);
    const slider = document.getElementById('slider-angular-max');
    if (slider) slider.value = val;
    const badge = document.getElementById('label-angular-max');
    if (badge) badge.innerText = `${val} °/s`;

    updateActivePresets('slider-angular-max', val);
    updateGauges(currentVx, currentVtheta);
}

function onAngularSliderChange(val) {
    angularMax = parseInt(val, 10);
    const badge = document.getElementById('label-angular-max');
    if (badge) badge.innerText = `${val} °/s`;
    updateActivePresets('slider-angular-max', val);
    updateGauges(currentVx, currentVtheta);
}

function updateActivePresets(sliderId, val) {
    const parent = document.getElementById(sliderId)?.closest('.setting-group');
    if (!parent) return;
    const buttons = parent.querySelectorAll('.btn-preset');
    buttons.forEach(btn => {
        if (btn.innerText.includes(val.toString())) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}
