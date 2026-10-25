// Tâche FreeRTOS du contrôleur de mouvement : la seule qui touche aux roues.
// Les autres tâches lui parlent par une file de commandes et lisent une copie de la pose.
//
// Boucle : attend une commande au plus MOTION_PERIOD_MS. Une commande est traitée dès
// son arrivée (la file réveille la tâche) ; update() tourne toutes les MOTION_PERIOD_MS.
#pragma once

#include "motion.h"

namespace motion_task {

// Crée la file et la tâche. `wheels` et `listener` doivent exister jusqu'à l'arrêt de
// l'ESP. Les fonctions de `listener` sont appelées depuis la tâche de mouvement.
bool start(WheelDriver& wheels, MotionListener& listener, const Pose& initial_pose);

// Depuis n'importe quelle tâche, sans bloquer. false si la file est pleine (commande perdue).
bool send(const Command& cmd);

// Dernière pose calculée par la tâche (copie cohérente, lisible depuis n'importe quelle tâche)
Pose pose();

}  // namespace motion_task
