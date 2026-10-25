// Strat Studio : lecture des blocs et déroulé de la simulation.
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 4. PARSING & LOGIQUE SÉQUENTIELLE
// ============================================================

function applySymmetry(x, y, theta) {
    // Symétrie d'équipe : définition unique dans frames.js (cf. Rasp/core/frames.py)
    let symToggle = document.getElementById('symToggle');
    return EirbotFrames.mirrorForTeam(x, y, theta, symToggle && symToggle.checked ? 'JAUNE' : 'BLEUE');
}

function parseSequence(firstBlock, currentX, currentY, currentTheta) {
    let queue = []; let pPath = [];
    let simX = currentX, simY = currentY, simTheta = currentTheta;

    let currentBlock = firstBlock;
    while (currentBlock) {
        let blockId = currentBlock.id;

        if (currentBlock.type === 'robot_start') {
            let rawX = parseInt(currentBlock.getFieldValue('X'));
            let rawY = parseInt(currentBlock.getFieldValue('Y'));
            let rawTheta = parseInt(currentBlock.getFieldValue('THETA'));

            let sym = applySymmetry(rawX, rawY, rawTheta);
            simX = sym.x; simY = sym.y; simTheta = sym.theta;

            queue.push({ type: 'start', x: simX, y: simY, theta: simTheta, blockId: blockId });
        }
        else if (currentBlock.type === 'robot_goto') {
            let rawX = parseInt(currentBlock.getFieldValue('X'));
            let rawY = parseInt(currentBlock.getFieldValue('Y'));
            let rawTheta = parseInt(currentBlock.getFieldValue('THETA'));

            let sym = applySymmetry(rawX, rawY, rawTheta);
            let targetX = sym.x; let targetY = sym.y; let targetTheta = sym.theta;

            let p0 = { x: simX, y: simY };
            let p3 = { x: targetX, y: targetY };

            queue.push({ type: 'goto', x: targetX, y: targetY, theta: targetTheta, blockId: blockId });
            pPath.push({ p0, p3, targetTheta: targetTheta, blockId: blockId });

            simX = targetX; simY = targetY; simTheta = targetTheta;
        }
        else if (currentBlock.type === 'controls_repeat_ext') {
            let times = 0;
            let timesBlock = currentBlock.getInputTargetBlock('TIMES');
            if (timesBlock && timesBlock.type === 'math_number') {
                times = parseInt(timesBlock.getFieldValue('NUM'));
            }
            let doBlock = currentBlock.getInputTargetBlock('DO');
            for (let i = 0; i < times; i++) {
                let subResult = parseSequence(doBlock, simX, simY, simTheta);
                queue = queue.concat(subResult.queue);
                pPath = pPath.concat(subResult.path);
                simX = subResult.endX; simY = subResult.endY; simTheta = subResult.endTheta;
            }
        }
        else if (currentBlock.type === 'robot_gobase_at') {
            let targetX = DEFAULT_START_X;
            let targetY = DEFAULT_START_Y;
            let targetTheta = DEFAULT_START_THETA + 180;

            let p0 = { x: simX, y: simY };
            let p3 = { x: targetX, y: targetY };

            queue.push({ type: 'action', msg: "Attente fin match...", blockId: blockId });
            queue.push({ type: 'goto', x: targetX, y: targetY, theta: targetTheta, blockId: blockId });
            pPath.push({ p0, p3, targetTheta: targetTheta, blockId: blockId });

            simX = targetX; simY = targetY; simTheta = targetTheta;
        }
        else if (currentBlock.type.includes('kapla') || currentBlock.type.includes('stop') || currentBlock.type.includes('play_') || currentBlock.type.includes('actionneur')) {
            let msg = "Action";
            if (currentBlock.type === 'prendre_kapla') msg = "Prise Kapla";
            if (currentBlock.type === 'retourner_kapla') msg = "Retourne Kapla";
            if (currentBlock.type === 'poser_kapla') msg = "Pose Kapla";
            if (currentBlock.type === 'pousse_kapla') msg = "Pousse Kapla";
            if (currentBlock.type === 'robot_stop') msg = "STOP";
            if (currentBlock.type === 'play_animation') msg = "Animation: " + currentBlock.getFieldValue('ANIM_NAME');
            if (currentBlock.type === 'play_sound') msg = "Son: " + currentBlock.getFieldValue('SOUND_NAME');
            if (currentBlock.type === 'actionneur_unique') msg = `Act. ${currentBlock.getFieldValue('ID')}: ${currentBlock.getFieldValue('CMD')}`;
            if (currentBlock.type === 'prendre_tous_kaplas') msg = "Prise 4 Kaplas (Caméra)";

            queue.push({ type: 'action', msg: msg, blockId: blockId });
        }
        currentBlock = currentBlock.getNextBlock();
    }
    return { queue, path: pPath, endX: simX, endY: simY, endTheta: simTheta };
}

function parseBlocks(isPreview) {
    var topBlocks = workspace.getTopBlocks(true);
    if (topBlocks.length === 0) return { queue: [], path: [] };
    topBlocks.sort((a, b) => a.getRelativeToSurfaceXY().y - b.getRelativeToSurfaceXY().y);

    let res = parseSequence(topBlocks[0], DEFAULT_START_X, DEFAULT_START_Y, DEFAULT_START_THETA);
    return { queue: res.queue, path: res.path };
}

function generatePreview() {
    clearBlockWarnings(); // Reset
    let result = parseBlocks(true);
    previewPath = result.path;

    let errorCount = 0;
    previewPath.forEach(bz => {
        let mid = getSegmentPoint(0.5, bz.p0, bz.p3);
        if (isOutOfBounds(bz.p3) || isOutOfBounds(mid)) {
            // MARQUAGE ERREUR
            markBlockError(bz.blockId, "Hors table !");
            errorCount++;
        }
    });
    if (errorCount > 0) logSim(`${errorCount} erreurs détectées.`);
    else logSim("Aperçu généré.");
}

function runSimulation() {
    clearBlockWarnings(); // NETTOYAGE
    previewPath = [];
    consoleDiv.innerHTML = "";
    logSim("Simulation...");
    robot.isMoving = false; robot.isRotating = false; robot.bezier = null; robot.currentIcon = null; robot.currentBlockId = null;

    let result = parseBlocks(false);
    actionQueue = result.queue;
    processNextAction();
}

function processNextAction() {
    if (actionQueue.length > 0) {
        const action = actionQueue.shift();

        // HIGHLIGHT DU BLOC
        if (action.blockId) {
            robot.currentBlockId = action.blockId;
            workspace.highlightBlock(action.blockId);
        }

        if (action.type === 'start') {
            robot.x = action.x;
            robot.y = action.y;
            robot.theta = action.theta;
            logSim(`Départ : ${action.x}, ${action.y}`);
            processNextAction();
        }
        else if (action.type === 'goto') {
            logSim(`Go (${action.x}, ${action.y})`);

            let p0 = { x: robot.x, y: robot.y };
            let p3 = { x: action.x, y: action.y };

            // Étape 1 : Rotation vers le point (si pas en marche arrière)
            let dx = p3.x - p0.x;
            let dy = p3.y - p0.y;
            let moveAngle = Math.atan2(dy, dx) * (180 / Math.PI);
            let diff = Math.abs(((moveAngle - robot.theta + 180 + 360) % 360) - 180);

            if (diff > 5 && diff < 175) {
                // On ajoute une rotation AVANT le mouvement
                actionQueue.unshift({ ...action, type: 'goto_move' }); // On remettra le mouvement après
                actionQueue.unshift({ type: 'rotate', theta: moveAngle, blockId: action.blockId });
                processNextAction();
                return;
            }

            robot.bezier = { p0, p3, targetTheta: action.theta, t: 0 };
            robot.isMoving = true;

            // On ajoute la rotation finale APRÈS le mouvement
            actionQueue.unshift({ type: 'rotate', theta: action.theta, blockId: action.blockId });
        }
        else if (action.type === 'goto_move') {
            let p0 = { x: robot.x, y: robot.y };
            let p3 = { x: action.x, y: action.y };
            robot.bezier = { p0, p3, targetTheta: action.theta, t: 0 };
            robot.isMoving = true;
            actionQueue.unshift({ type: 'rotate', theta: action.theta, blockId: action.blockId });
        }
        else if (action.type === 'rotate') {
            if (Math.abs(((action.theta - robot.theta + 180 + 360) % 360) - 180) < 1) {
                processNextAction();
                return;
            }
            robot.rotateTarget = action.theta;
            robot.isRotating = true;
        }
        else if (action.type === 'action') {
            robot.currentIcon = getIcon(action.msg);
            logSim(action.msg);

            // --- FEEDBACK RÉEL (TEST) ---
            if (action.msg.includes("Animation: ")) {
                let animName = action.msg.split(": ")[1];
                fetch('/api/play_animation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: animName })
                });
            } else if (action.msg.includes("Son: ")) {
                let soundName = action.msg.split(": ")[1];
                fetch('/api/play_test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: soundName })
                });
            }
            // -----------------------------

            setTimeout(() => { robot.currentIcon = null; processNextAction(); }, 1000);
        }
    } else {
        logSim("Terminé.");
        workspace.highlightBlock(null); // ETEINDRE HIGHLIGHT
    }
}

function getIcon(msg) {
    // Étiquette courte affichée au-dessus du robot dans la simulation
    if (msg.includes("Prise")) return "PRISE";
    if (msg.includes("Retourne")) return "RETOURNE";
    if (msg.includes("Pose")) return "POSE";
    if (msg.includes("Pousse")) return "POUSSE";
    if (msg.includes("STOP")) return "STOP";
    if (msg.includes("Animation")) return "ANIM";
    if (msg.includes("Son")) return "SON";
    return "ACTION";
}

function logSim(msg) {
    consoleDiv.innerHTML += `<div>> ${msg}</div>`;
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
}
