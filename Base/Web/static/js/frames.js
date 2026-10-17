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

    const api = { normalizeDeg, mirrorForTeam, robotToThree, threeToRobot, thetaToThreeRad };
    root.EirbotFrames = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
