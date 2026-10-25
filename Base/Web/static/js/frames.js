// frames.js — repères de coordonnées côté navigateur.
// MÊMES définitions que Rasp/core/frames.py (référence), testées par test/frames.test.mjs.
//
// Repère table/robot : X = largeur 0 -> 2000 mm, Y = longueur -1500 -> 1500 mm (centrée),
// theta en degrés (0 = +X, 90 = +Y). Équipe JAUNE : symétrie y -> -y, theta -> -theta.
//
// Repère affichage 3D (Three.js, map.js) : table centrée en (0, 0), X_three = longueur,
// Y_three = largeur (+1000 en haut). Donc X_three = Y_robot, Y_three = 1000 - X_robot,
// et la rotation Three.js vaut theta - 90°.
(function (root) {
    function normalizeDeg(theta) {
        let t = theta % 360;
        if (t <= -180) t += 360;
        else if (t > 180) t -= 360;
        return t;
    }

    function mirrorForTeam(x, y, theta, team) {
        if (team !== 'JAUNE') return { x: x, y: y, theta: theta };
        return { x: x, y: -y, theta: theta === undefined || theta === null ? theta : normalizeDeg(-theta) };
    }

    function robotToThree(x, y) {
        return { x: y, y: 1000 - x };
    }

    function threeToRobot(pt) {
        return { x: 1000 - pt.y, y: pt.x };
    }

    function thetaToThreeRad(thetaDeg) {
        return ((thetaDeg || 0) - 90) * Math.PI / 180;
    }

    // Encombrement du robot autour de son point de référence (milieu de l'axe des roues,
    // celui de l'odométrie), mesuré sur le modèle MuJoCo : tools/encombrement_robot.py.
    // L'axe des roues n'est PAS au centre du robot : 245,5 mm devant, 102 mm derrière.
    const ROBOT = { FRONT_MM: 245.5, BACK_MM: 102.0, HALF_WIDTH_MM: 188.2, HEIGHT_MM: 450.0 };

    // Coins de l'encombrement (repère table) pour la pose (x, y, theta) :
    // avant gauche, avant droit, arrière droit, arrière gauche
    function robotCorners(x, y, theta) {
        const t = (theta || 0) * Math.PI / 180, c = Math.cos(t), s = Math.sin(t);
        return [[ROBOT.FRONT_MM, ROBOT.HALF_WIDTH_MM], [ROBOT.FRONT_MM, -ROBOT.HALF_WIDTH_MM],
                [-ROBOT.BACK_MM, -ROBOT.HALF_WIDTH_MM], [-ROBOT.BACK_MM, ROBOT.HALF_WIDTH_MM]]
            .map(([fx, fy]) => ({ x: x + fx * c - fy * s, y: y + fx * s + fy * c }));
    }

    const api = { normalizeDeg, mirrorForTeam, robotToThree, threeToRobot, thetaToThreeRad, ROBOT, robotCorners };
    root.EirbotFrames = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
