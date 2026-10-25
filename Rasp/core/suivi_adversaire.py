"""Suivi et prédiction de trajectoire des robots adverses (pur Python, testé).

Un filtre de Kalman par robot (état x, y, vx, vy ; mesure x, y de la caméra zénithale), modèle à
vitesse quasi constante : l'accélération inconnue est le bruit de processus (un robot de Coupe
accélère / freine vite). Pour prédire plus loin qu'une seconde, la vitesse est amortie
(exp(-t / AMORTISSEMENT_S)) : un robot adverse s'arrête souvent (actions), il ne file pas tout
droit jusqu'au bord. L'incertitude de position grandit avec l'horizon : c'est elle qui gonfle la
zone à éviter dans le planificateur (core/planif.py).

Repère table, mm, secondes.
"""

import math

SIGMA_MESURE_MM = 25.0
SIGMA_ACCEL_MM_S2 = 1500.0
VITESSE_MAX_MM_S = 1500.0
AMORTISSEMENT_S = 1.5
PERDU_APRES_S = 3.0           # plus d'observation depuis : le robot n'est plus suivi
ACCEL_PREDICTION_MM_S2 = 250.0  # changements de vitesse « moyens » à venir (incertitude de prédiction)
SIGMA_MAX_MM = 500.0


class PisteAdversaire:
    def __init__(self, id_, x, y, t):
        self.id = id_
        self.x = [x, y, 0.0, 0.0]
        s2 = SIGMA_MESURE_MM ** 2
        self.P = [[s2, 0, 0, 0], [0, s2, 0, 0], [0, 0, 1e6, 0], [0, 0, 0, 1e6]]
        self.t = t
        self.t_obs = t
        self.n_obs = 1

    # --- filtre ---------------------------------------------------------------------------
    def _predire_etat(self, dt):
        q = SIGMA_ACCEL_MM_S2 ** 2
        x, y, vx, vy = self.x
        self.x = [x + vx * dt, y + vy * dt, vx, vy]
        P = self.P
        # F = [[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]] ; P = F P F^T + Q (accélération blanche)
        n = [[P[i][j] for j in range(4)] for i in range(4)]
        for a, va in ((0, 2), (1, 3)):
            n[a][a] = P[a][a] + 2 * dt * P[a][va] + dt * dt * P[va][va]
            n[a][va] = n[va][a] = P[a][va] + dt * P[va][va]
        n[0][1] = n[1][0] = P[0][1] + dt * (P[0][3] + P[2][1]) + dt * dt * P[2][3]
        n[0][3] = n[3][0] = P[0][3] + dt * P[2][3]
        n[1][2] = n[2][1] = P[1][2] + dt * P[3][2]
        n[2][3] = n[3][2] = P[2][3]
        for a, va in ((0, 2), (1, 3)):
            n[a][a] += q * dt ** 4 / 4
            n[a][va] += q * dt ** 3 / 2
            n[va][a] += q * dt ** 3 / 2
            n[va][va] += q * dt * dt
        self.P = n

    def observer(self, x, y, t):
        dt = t - self.t
        if dt < 0:
            return
        self._predire_etat(dt)
        self.t = t
        r = SIGMA_MESURE_MM ** 2
        P = self.P
        # Mesure H = [[1,0,0,0],[0,1,0,0]] : innovation 2D, gain K = P H^T S^-1
        s00, s01, s11 = P[0][0] + r, P[0][1], P[1][1] + r
        det = s00 * s11 - s01 * s01
        inv = [[s11 / det, -s01 / det], [-s01 / det, s00 / det]]
        K = [[P[i][0] * inv[0][0] + P[i][1] * inv[1][0], P[i][0] * inv[0][1] + P[i][1] * inv[1][1]] for i in range(4)]
        ix, iy = x - self.x[0], y - self.x[1]
        self.x = [self.x[i] + K[i][0] * ix + K[i][1] * iy for i in range(4)]
        self.P = [[P[i][j] - (K[i][0] * P[0][j] + K[i][1] * P[1][j]) for j in range(4)] for i in range(4)]
        v = math.hypot(self.x[2], self.x[3])
        if v > VITESSE_MAX_MM_S:
            self.x[2] *= VITESSE_MAX_MM_S / v
            self.x[3] *= VITESSE_MAX_MM_S / v
        self.t_obs = t
        self.n_obs += 1

    # --- prédiction -------------------------------------------------------------------------
    @property
    def vitesse(self):
        return self.x[2], self.x[3]

    def position(self, t):
        """(x, y, sigma) prévus à l'instant absolu t (vitesse amortie, incertitude croissante)."""
        dt = max(0.0, t - self.t)
        tau = AMORTISSEMENT_S
        k = tau * (1.0 - math.exp(-dt / tau))       # intégrale de la vitesse amortie
        x = self.x[0] + self.x[2] * k
        y = self.x[1] + self.x[3] * k
        sig_pos = math.sqrt(max(self.P[0][0], self.P[1][1]))
        sig_v = math.sqrt(max(self.P[2][2], self.P[3][3]))
        sig_v = min(sig_v, VITESSE_MAX_MM_S)
        # incertitude : position actuelle + vitesse mal connue + accélérations à venir
        sig = math.sqrt(sig_pos ** 2 + (sig_v * k) ** 2 + (0.5 * ACCEL_PREDICTION_MM_S2 * dt * dt) ** 2)
        return x, y, min(sig, SIGMA_MAX_MM)

    def trajectoire(self, t0, horizon_s=3.0, pas_s=0.25):
        """[(t relatif, x, y, sigma)] de t0 à t0 + horizon : affichage, journal."""
        n = int(horizon_s / pas_s)
        return [(round(k * pas_s, 2),) + tuple(round(v, 1) for v in self.position(t0 + k * pas_s))
                for k in range(n + 1)]


class SuiviAdversaires:
    """Toutes les pistes, alimentées par les observations caméra (id du tag -> piste)."""

    def __init__(self):
        self.pistes = {}

    def observer(self, id_, x, y, t):
        p = self.pistes.get(id_)
        if p is None or t - p.t_obs > PERDU_APRES_S:
            self.pistes[id_] = PisteAdversaire(id_, x, y, t)
        else:
            p.observer(x, y, t)

    def actives(self, t):
        for id_ in [i for i, p in self.pistes.items() if t - p.t_obs > PERDU_APRES_S]:
            del self.pistes[id_]
        return list(self.pistes.values())
