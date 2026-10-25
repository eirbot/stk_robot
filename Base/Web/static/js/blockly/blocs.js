// Strat Studio : définition des blocs Blockly et générateurs Python.
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 1. DÉFINITION DES BLOCS BLOCKLY
// ============================================================

// --- DATA FETCHING FOR DROPDOWNS ---
window.BLOCKLY_ANIMATIONS = [["Aucune", ""]];
window.BLOCKLY_SOUNDS = [["Aucun", ""]];

function fetchDropdownData() {
    // Animations
    fetch('/api/led_animations')
        .then(r => r.json())
        .then(data => {
            let keys = Object.keys(data);
            if (keys.length > 0) {
                window.BLOCKLY_ANIMATIONS = keys.map(k => [k, k]);
            }
        });

    // Sounds
    fetch('/api/list_audio_files')
        .then(r => r.json())
        .then(data => {
            if (data.length > 0) {
                window.BLOCKLY_SOUNDS = data.map(f => [f, f]);
            }
        });
}
fetchDropdownData();


// --- BLOC DÉPART ---
Blockly.Blocks['robot_start'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Départ Match (Bleu)")
            .appendField("X").appendField(new Blockly.FieldNumber(250), "X")
            .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
            .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA");
        this.setNextStatement(true, null);
        this.setColour(290); // Violet
        this.setTooltip("Définit la position de départ pour la simulation.");
    }
};

// --- BLOC GOTO ---
Blockly.Blocks['robot_goto'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Aller à X").appendField(new Blockly.FieldNumber(1000), "X")
            .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
            .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(230); // Bleu
        this.setTooltip("Déplacement en ligne droite puis rotation finale.");
    }
};

// --- ACTIONNEURS ---
Blockly.Blocks['prendre_kapla'] = { init: function () { this.appendDummyInput().appendField("Prendre Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
Blockly.Blocks['retourner_kapla'] = { init: function () { this.appendDummyInput().appendField("Retourne Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
Blockly.Blocks['poser_kapla'] = { init: function () { this.appendDummyInput().appendField("Poser Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
Blockly.Blocks['pousse_kapla'] = { init: function () { this.appendDummyInput().appendField("Pousse Kapla"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(120); } };
Blockly.Blocks['robot_stop'] = { init: function () { this.appendDummyInput().appendField("Arrêter le robot"); this.setPreviousStatement(true, null); this.setNextStatement(true, null); this.setColour(0); } };

Blockly.Blocks['robot_gobase_at'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Retour Base à")
            .appendField(new Blockly.FieldNumber(90), "SECONDS")
            .appendField("secondes");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(0); // Rouge
        this.setTooltip("Attend le temps indiqué puis rentre à la base (coord. départ).");
    }
};

Blockly.Blocks['robot_approche_kapla'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Approche Kapla (Vision)");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(40);
        this.setTooltip("Se positionne devant un Kapla détecté par la caméra.");
    }
};

Blockly.Blocks['robot_thermometre'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Déployer Thermomètre");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200); // Bleu-cyan
        this.setTooltip("Déploie le thermomètre selon la couleur de l'équipe.");
    }
};

Blockly.Blocks['robot_attendre'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Attendre")
            .appendField(new Blockly.FieldNumber(1, 0, 100, 0.1), "SECONDES")
            .appendField("secondes");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(65);
        this.setTooltip("Attend un nombre de secondes (interruptible par l'arrêt d'urgence).");
    }
};

Blockly.Blocks['robot_recalage_camera'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Recaler l'odométrie sur la caméra");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(230);
        this.setTooltip("Robot immobile : corrige la position de l'ESP avec la pose vue par la caméra de la base.");
    }
};

Blockly.Blocks['robot_si_approche_reussie'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Si l'approche a réussi");
        this.appendStatementInput("DO")
            .setCheck(null)
            .appendField("Faire");
        this.appendStatementInput("ELSE")
            .setCheck(null)
            .appendField("Sinon");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(40);
        this.setTooltip("Exécute le bloc 'Faire' si approcheKapla() a réussi, 'Sinon' autrement.");
    }
};

// --- NOUVEAUX ACTIONNEURS (BAS & HAUT NIVEAU) ---
Blockly.Blocks['actionneur_unique'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Actionneur")
            .appendField(new Blockly.FieldDropdown([["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"]]), "ID")
            .appendField("Action:")
            .appendField(new Blockly.FieldDropdown([["FLIP (Prendre + Tourne)", "FLIP"], ["nFLIP (Prendre sans tourner)", "nFLIP"], ["DOWN (Poser)", "DOWN"], ["INIT (Match)", "INIT"], ["RESET (Rangé)", "RESET"]]), "CMD");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(120);
        this.setTooltip("Contrôle individuel bas niveau pour un actionneur.");
    }
};

Blockly.Blocks['prendre_tous_kaplas'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Prendre 4 Kaplas (Auto Caméra)");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(120);
        this.setTooltip("Analyse via la caméra et définit s'il faut faire FLIP ou nFLIP pour chaque Kapla.");
    }
};

// --- SONS & LUMIERES ---
Blockly.Blocks['play_animation'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Jouer Animation")
            .appendField(new Blockly.FieldDropdown(function () { return window.BLOCKLY_ANIMATIONS; }), "ANIM_NAME");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(300); // Violet foncé
        this.setTooltip("Lance une animation LED.");
    }
};

Blockly.Blocks['play_sound'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Jouer Son")
            .appendField(new Blockly.FieldDropdown(function () { return window.BLOCKLY_SOUNDS; }), "SOUND_NAME");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(300);
        this.setTooltip("Joue un fichier audio.");
    }
};

// --- DÉPLACEMENT AVEC ÉVITEMENT, CAMÉRA EMBARQUÉE, TEMPS DE MATCH (Rasp/strat/actions.py) ---
Blockly.Blocks['robot_aller'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Aller (évitement) à X").appendField(new Blockly.FieldNumber(1000), "X")
            .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
            .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(200);
        this.setTooltip("Chemin calculé par le robot (A*) autour des obstacles, de l'adversaire et des points LiDAR ; replanifié en route.");
    }
};

Blockly.Blocks['robot_aligner_tag'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("S'aligner sur le tag").appendField(new Blockly.FieldNumber(13, 0, 999, 1), "ID")
            .appendField("à").appendField(new Blockly.FieldNumber(300, 50, 1000, 10), "DIST")
            .appendField("mm");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(160);
        this.setTooltip("Caméra embarquée : se met face au tag le plus proche (distance du point de référence à la face). Résultat : « Si l'approche a réussi ».");
    }
};

Blockly.Blocks['robot_si_temps'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("S'il reste le temps de faire").appendField(new Blockly.FieldNumber(10, 0, 100, 0.5), "SECONDES")
            .appendField("s (puis rentrer)");
        this.appendStatementInput("DO").setCheck(null);
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(65);
        this.setTooltip("Exécute le contenu seulement s'il reste ce temps + le trajet de retour (durées apprises sur les vrais GoTo).");
    }
};

Blockly.Blocks['robot_retour_fin'] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Fin de match : rentrer à X").appendField(new Blockly.FieldNumber(250), "X")
            .appendField("Y").appendField(new Blockly.FieldNumber(0), "Y")
            .appendField("θ").appendField(new Blockly.FieldNumber(0), "THETA")
            .appendField("marge").appendField(new Blockly.FieldNumber(3, 0, 30, 0.5), "MARGE").appendField("s");
        this.setPreviousStatement(true, null);
        this.setNextStatement(true, null);
        this.setColour(290);
        this.setTooltip("À mettre au début : la stratégie est interrompue à temps pour que le robot soit rentré avant 100 s (et il rentre aussi si elle finit plus tôt).");
    }
};

// --- GÉNÉRATEURS PYTHON ---
Blockly.Python.forBlock['robot_start'] = function (block) { return `robot.set_pos(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')})\n`; };
Blockly.Python.forBlock['robot_goto'] = function (block) { return `robot.goto(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')})\n`; };
Blockly.Python.forBlock['prendre_kapla'] = function (block) { return `robot.prendreKapla()\n`; };
Blockly.Python.forBlock['retourner_kapla'] = function (block) { return `robot.retournerKapla()\n`; };
Blockly.Python.forBlock['poser_kapla'] = function (block) { return `robot.poseKapla()\n`; };
Blockly.Python.forBlock['pousse_kapla'] = function (block) { return 'robot.pousse_kapla()\n'; };
Blockly.Python.forBlock['robot_stop'] = function (block) { return 'robot.stop()\n'; };
Blockly.Python.forBlock['robot_gobase_at'] = function (block) {
    return `robot.wait_until_and_return(${block.getFieldValue('SECONDS')})\n`;
};
Blockly.Python.forBlock['robot_approche_kapla'] = function (block) { return 'robot.approcheKapla()\n'; };
Blockly.Python.forBlock['robot_thermometre'] = function (block) { return 'robot.thermometre()\n'; };
Blockly.Python.forBlock['robot_recalage_camera'] = function (block) { return 'robot.recalage_camera()\n'; };
Blockly.Python.forBlock['robot_attendre'] = function (block) {
    return `robot.attendre(${block.getFieldValue('SECONDES')})\n`;
};
Blockly.Python.forBlock['robot_si_approche_reussie'] = function (block) {
    var do_branch = Blockly.Python.statementToCode(block, 'DO');
    var else_branch = Blockly.Python.statementToCode(block, 'ELSE');
    var code = 'if robot.approche_reussie:\n';
    code += do_branch || '  pass\n';
    if (else_branch) {
        code += 'else:\n';
        code += else_branch;
    }
    return code;
};

Blockly.Python.forBlock['actionneur_unique'] = function (block) {
    return `robot.cmd_actionneurs(act${block.getFieldValue('ID')}='${block.getFieldValue('CMD')}')\n`;
};

Blockly.Python.forBlock['prendre_tous_kaplas'] = function (block) {
    return `robot.prendre_kaplas_camera()\n`;
};

Blockly.Python.forBlock['play_animation'] = function (block) { return `robot.play_animation("${block.getFieldValue('ANIM_NAME')}")\n`; };
Blockly.Python.forBlock['play_sound'] = function (block) { return `robot.play_sound("${block.getFieldValue('SOUND_NAME')}")\n`; };

Blockly.Python.forBlock['robot_aller'] = function (block) {
    return `robot.aller(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')})\n`;
};
Blockly.Python.forBlock['robot_aligner_tag'] = function (block) {
    return `robot.aligner_tag(ids=[${block.getFieldValue('ID')}], distance_mm=${block.getFieldValue('DIST')})\n`;
};
Blockly.Python.forBlock['robot_si_temps'] = function (block) {
    const corps = Blockly.Python.statementToCode(block, 'DO') || '  pass\n';
    return `if robot.si_temps(${block.getFieldValue('SECONDES')}):\n` + corps;
};
Blockly.Python.forBlock['robot_retour_fin'] = function (block) {
    return `robot.retour_fin(${block.getFieldValue('X')}, ${block.getFieldValue('Y')}, ${block.getFieldValue('THETA')}, marge_s=${block.getFieldValue('MARGE')})\n`;
};
