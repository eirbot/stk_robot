// Tests de Base/Web/static/js/frames.js : mêmes cas que test/test_frames.py,
// pour garantir que l'affichage (carte, Strat Studio) et le robot utilisent les mêmes formules.
// Lancer : node --test test/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const F = require('../Base/Web/static/js/frames.js');
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test('normalizeDeg identique à frames.py', () => {
    for (const [raw, exp] of [[0, 0], [180, 180], [-180, 180], [190, -170], [-190, 170],
                              [360, 0], [540, 180], [-725, -5], [270, -90]]) {
        close(F.normalizeDeg(raw), exp);
    }
});

test('symétrie équipe', () => {
    assert.deepEqual(F.mirrorForTeam(700, 1250, 30, 'BLEUE'), { x: 700, y: 1250, theta: 30 });
    const j = F.mirrorForTeam(700, 1250, 30, 'JAUNE');
    assert.equal(j.x, 700);
    assert.equal(j.y, -1250);
    close(j.theta, -30);
    close(F.mirrorForTeam(0, 0, 90, 'JAUNE').theta, -90);
});

test('robot <-> Three.js aller-retour', () => {
    for (const [x, y] of [[0, 0], [2000, -1500], [148, 1149], [1000, 0]]) {
        const p = F.robotToThree(x, y);
        const back = F.threeToRobot(p);
        close(back.x, x);
        close(back.y, y);
    }
    // Coins : X=0 (bord haut) -> Y_three = +1000 ; Y=+1500 -> X_three = +1500
    assert.deepEqual(F.robotToThree(0, 1500), { x: 1500, y: 1000 });
});

test('rotation Three.js : theta=90 (vers +Y robot = droite) -> 0 rad', () => {
    close(F.thetaToThreeRad(90), 0);
    close(F.thetaToThreeRad(0), -Math.PI / 2);
});

test('encombrement du robot : mêmes coins que frames.py', () => {
    // theta = 0 : l'avant est vers +X ; la gauche du robot vers +Y
    const c0 = F.robotCorners(1000, 0, 0);
    close(c0[0].x, 1000 + F.ROBOT.FRONT_MM);
    close(c0[0].y, F.ROBOT.HALF_WIDTH_MM);
    close(c0[2].x, 1000 - F.ROBOT.BACK_MM);
    // theta = 90 : l'avant est vers +Y
    const c90 = F.robotCorners(1000, 0, 90);
    close(c90[0].y, F.ROBOT.FRONT_MM);
    close(c90[0].x, 1000 - F.ROBOT.HALF_WIDTH_MM);
});
