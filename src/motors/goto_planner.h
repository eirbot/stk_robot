// Découpage d'un GoTo en segments simples : rotation vers la cible, ligne droite,
// rotation au cap final. Fonctions pures, testées sur PC.
//
// Chaque segment est calculé AU MOMENT où il commence, depuis la pose mesurée par
// l'odométrie : une rotation un peu courte est rattrapée par la ligne droite suivante,
// rien ne s'accumule d'un GoTo à l'autre (défaut de l'ancien GoToPosition).
//
// Utilisation (tâche de mouvement) :
//   planner.start(cible);
//   pour chaque segment : seg = planner.next(odometrie.pose()); exécuter seg; ...
//   jusqu'à seg.type == Segment::Type::None.
//   Segment interrompu (obstacle puis voie libre) : planner.restartSegment() puis next().
#pragma once

#include "pose.h"

struct Segment {
  enum class Type { None, Rotate, Drive };
  Type type = Type::None;
  // Rotate : degrés (> 0 = sens trigonométrique) ; Drive : mm (< 0 = marche arrière)
  float amount = 0.0f;
};

class GotoPlanner {
 public:
  void start(const Pose& target);

  // Segment suivant, calculé depuis la pose actuelle. Les segments trop petits
  // (config MIN_DRIVE_MM, MIN_ROTATE_DEG) sont sautés. None = GoTo terminé.
  Segment next(const Pose& current);

  // Le dernier segment rendu par next() sera recalculé au prochain next()
  void restartSegment();

  bool done() const { return phase_ == Phase::Done; }

 private:
  enum class Phase { RotateToPath, Drive, RotateFinal, Done };
  Pose target_;
  Phase phase_ = Phase::Done;
  Phase last_phase_ = Phase::Done;
};
