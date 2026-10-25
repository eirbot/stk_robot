// Strat Studio : chargement / sauvegarde des stratégies et boutons.
// Fichiers du Strat Studio chargés dans l'ordre (defer, après Blockly) par templates/blockly.html :
// portée globale partagée.

// ============================================================
// 5. GESTION API (LOAD/SAVE/LIST) & BOUTONS
// ============================================================

var simuBtn = document.getElementById('simuBtn'); if (simuBtn) simuBtn.addEventListener('click', runSimulation);
var previewBtn = document.getElementById('previewBtn'); if (previewBtn) previewBtn.addEventListener('click', generatePreview);

// Chargement initial des stratégies
loadBlocklyStrats('stratSelect');

document.getElementById('loadBtn').addEventListener('click', function () {
    var n = document.getElementById('stratSelect').value;
    if (!n) return;
    fetch('/api/load_strat/' + n)
        .then(r => r.json())
        .then(d => {
            if (d.status === 'success') {
                workspace.clear();
                Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(d.xml), workspace);
                document.getElementById('filename').value = n;
                refreshDocName();
            }
        });
});

document.getElementById('saveBtn').addEventListener('click', function () {
    var f = document.getElementById('filename').value;
    if (!f) return;
    var c = Blockly.Python.workspaceToCode(workspace).replace(/^/gm, "    ");
    var final = `from strat.actions import RobotActions\nimport time\nMETADATA={"name":"${f}"}\ndef run(robot: RobotActions):\n    print("Start ${f}")\n${c}\n    print("End")`;

    fetch('/api/save_strat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filename: f,
            code: final,
            xml: Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace))
        })
    })
        .then(r => r.json())
        .then(d => {
            if (d.status === 'success') {
                loadBlocklyStrats('stratSelect');
                document.getElementById('status').innerHTML = d.robot
                    ? icon('check') + " Sauvegardé et envoyé au robot"
                    : icon('triangle-alert') + " Sauvegardé sur la base, robot injoignable (utiliser Update code RASP)";
            }
        });
});
