#ifndef COM_WITH_RASP_HPP
#define COM_WITH_RASP_HPP

#include "ClassMotors.hpp"
#include "GoToPosition.hpp"
#include "main_robot.h"
#include <Arduino.h>
#include <vector>

/*
 * Protocole série Rasp <-> ESP moteurs (115200 bauds, une commande par ligne
 * terminée par '\n', paramètres entiers séparés par des espaces).
 *
 * Rasp -> ESP :
 *   G x y theta : GoTo asynchrone (mm, mm, deg) -> réponse "D" ou "A" à la fin
 *   V vx vtheta : consigne de vitesse (mm/s, deg/s), à renouveler < 500 ms
 *   S x y theta : SetPos (recalage odométrie)
 *   L [etat]    : état LiDAR (0 libre, 1 stop, 2 devant, 3 derrière)
 *   H           : Halt, arrêt immédiat
 *   K           : battement de cœur (envoyé toutes les 100 ms par la Rasp
 *                 si aucune autre commande n'est partie entre-temps)
 *
 * ESP -> Rasp :
 *   T x y theta : odométrie (10 Hz)
 *   D / A       : GoTo terminé / annulé
 *   W           : watchdog liaison déclenché, moteurs arrêtés
 *
 * Watchdog liaison : tout octet reçu de la Rasp est un signe de vie. Le
 * watchdog s'arme au premier octet reçu ; si plus rien n'arrive pendant
 * RASP_TIMEOUT_MS, l'ESP annule le GoTo et la consigne de vitesse, arrête les
 * moteurs et envoie "W" une seule fois. Au retour de la liaison rien ne
 * reprend tout seul : la Rasp doit renvoyer une commande.
 */

class ComWithRasp {
public:
  ComWithRasp();
  void StartCom(); // Lance la tâche FreeRTOS
  void StartTelemetry(); 
  void Send();     // Envoie la commande (debug/test)

private:
  void Receive();     // Lecture UART dans une boucle
  void TelemetryLoop(); // Envoi périodique de la télémétrie
  void processLine(); // Découpe et traite la commande
  void processCommand(const String &cmd, const std::vector<int> &params);
  void asyncGoTo(float x, float y, float angle);
  static void GoToTask(void* pvParameters);

  String commande;
  char rcv;
  static constexpr int MAX_COMMAND_LENGTH = 64;
  volatile bool isMoving = false;
  TaskHandle_t goToTaskHandle = NULL;

  // Watchdog liaison Rasp : armé au premier octet reçu (voir protocole en tête)
  static constexpr unsigned long RASP_TIMEOUT_MS = 300;
  volatile unsigned long lastRxMillis = 0;
  volatile bool raspSeen = false;      // Au moins un octet reçu depuis le boot
  volatile bool watchdogTripped = false; // "W" déjà envoyé pour cette coupure
  void CheckRaspLink();
};

#endif