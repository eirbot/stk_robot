// Strat Studio : souris sur la simulation (coordonnées, clic).
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 3. LISTENERS & INTERACTION SOURIS
// ============================================================

canvas.addEventListener('mousemove', function (evt) {
    var rect = canvas.getBoundingClientRect();
    var scaleX_mouse = canvas.width / rect.width;
    var scaleY_mouse = canvas.height / rect.height;
    var mx = (evt.clientX - rect.left) * scaleX_mouse;
    var my = (evt.clientY - rect.top) * scaleY_mouse;

    let worldPos = screenToWorld(mx, my);

    // Affiche tooltip
    coordTooltip.style.display = 'block';
    coordTooltip.style.left = (evt.pageX + 15) + 'px';
    coordTooltip.style.top = (evt.pageY + 15) + 'px';
    coordTooltip.innerHTML = `X: <b>${worldPos.x}</b><br>Y: <b>${worldPos.y}</b>`;
});

canvas.addEventListener('mouseout', function () {
    coordTooltip.style.display = 'none';
});

// Clic pour logguer la position
canvas.addEventListener('click', function (evt) {
    var rect = canvas.getBoundingClientRect();
    var scaleX_mouse = canvas.width / rect.width;
    var scaleY_mouse = canvas.height / rect.height;
    let worldPos = screenToWorld((evt.clientX - rect.left) * scaleX_mouse, (evt.clientY - rect.top) * scaleY_mouse);
    logSim(`Clic : X=${worldPos.x}, Y=${worldPos.y}`);
});
