#include "ComWithRasp.hpp"

// Traces de debug série : à 115200 bauds elles coûtent ~8 ms d'UART par commande
#define COM_DEBUG 0

// Trame "T x y theta" écrite en un seul appel : évite qu'elle s'entremêle avec
// un "D"/"A" envoyé par GoToTask depuis une autre tâche
static void SendPose() {
  float x, y, angle;
  mot.GetPosition(x, y, angle);
  char buf[64];
  snprintf(buf, sizeof(buf), "T %.2f %.2f %.2f\n", x, y, angle * RAD_TO_DEG);
  Serial.print(buf);
}

ComWithRasp::ComWithRasp() { Serial.begin(115200); }

void ComWithRasp::StartCom() {
  // Crée une tâche FreeRTOS qui appelle this->Receive()
  xTaskCreate([](void *obj) { static_cast<ComWithRasp *>(obj)->Receive(); },
              "ComWithRasp", 4000, this, 1, NULL);
}

void ComWithRasp::StartTelemetry() {
  // Crée une tâche FreeRTOS qui appelle this->TelemetryLoop()
  xTaskCreate(
      [](void *obj) { static_cast<ComWithRasp *>(obj)->TelemetryLoop(); },
      "TelemetryLoop", 4000, this, 1, NULL);
}

void ComWithRasp::Receive() {
  // On crée un tableau fixe de 64 cases en mémoire (ultra rapide et sûr)
  char rx_buffer[64];
  int rx_index = 0;

  while (1) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      // Si on détecte la touche Entrée (\r ou \n)
      if (c == '\n' || c == '\r') {
        // On vérifie qu'on a bien reçu au moins une lettre
        if (rx_index > 0) {
          rx_buffer[rx_index] =
              '\0'; // On met le caractère de fin de chaîne obligatoire en C
          // On transfère le tableau sécurisé dans ta variable String habituelle
          commande = String(rx_buffer);
#if COM_DEBUG
          Serial.println("-> Ligne complete securisee : [" + commande + "]");
#endif
          // On lance ton découpage
          processLine();
          // On remet le curseur du tableau à zéro pour le prochain message
          rx_index = 0;
          commande = ""; // On nettoie au cas où
        }
      } else {
        // C'est une lettre normale, on la range dans le tableau
        // (On garde une marge de 1 pour le caractère de fin '\0')
        if (rx_index < 63) {
          rx_buffer[rx_index] = c;
          rx_index++;
        } else {
          Serial.println("-> ERREUR : Buffer plein, message trop long !");
          rx_index = 0; // On vide pour éviter de bloquer l'ESP
        }
      }
    }
    // On rend la main à FreeRTOS (1 ms : latence de lecture minimale)
    vTaskDelay(pdMS_TO_TICKS(1));
  }
}

void ComWithRasp::TelemetryLoop() {
  int telemetryCounter = 0;

  while (1) {
    mot.UpdateOdometry();
    mot.CheckWatchdog();

    telemetryCounter++;
    if (telemetryCounter >= 5) { // 5 * 20ms = 100ms (10 Hz)
      telemetryCounter = 0;
      SendPose();
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void ComWithRasp::Send() {
  Serial.println("Envoi de la commande");
  Serial.println(commande);
}

void ComWithRasp::processLine() {
  commande.trim();
  String command = "";
  std::vector<int> params;

  int spaceIndex = commande.indexOf(' ');
  if (spaceIndex == -1) {
    // Cas 1 : La commande n'a pas de paramètres (ex: "L")
    command = commande;
  } else {
    // Cas 2 : La commande a des paramètres (ex: "G 100 200 90")
    command = commande.substring(0, spaceIndex);

    // On avance pour chercher les nombres
    int currentIndex = spaceIndex + 1;
    while (currentIndex < commande.length()) {
      // On ignore les espaces multiples
      if (commande.charAt(currentIndex) == ' ') {
        currentIndex++;
        continue;
      }

      int nextSpace = commande.indexOf(' ', currentIndex);
      String paramStr;

      if (nextSpace == -1) {
        // C'est le dernier paramètre
        paramStr = commande.substring(currentIndex);
        currentIndex = commande.length(); // Pour sortir du while
      } else {
        // Paramètre intermédiaire
        paramStr = commande.substring(currentIndex, nextSpace);
        currentIndex = nextSpace + 1;
      }

      // On convertit et on ajoute au vecteur
      params.push_back(paramStr.toInt());
    }
  }

  // 4. Affichage de contrôle
#if COM_DEBUG
  Serial.print("-> Commande reconnue : '");
  Serial.print(command);
  Serial.print("' | Parametres [");
  for (int i = 0; i < params.size(); i++) {
    Serial.print(params[i]);
    if (i < params.size() - 1)
      Serial.print(", ");
  }
  Serial.println("]");
#endif

  // 5. Exécution
  processCommand(command, params);
}

void ComWithRasp::processCommand(const String &cmd,
                                 const std::vector<int> &params) {
  if (cmd == "G" && params.size() == 3) {
    mot.StopVelocity();
    if (!isMoving && goToTaskHandle == NULL) {
#if COM_DEBUG
      Serial.println("GoToPosition (async)");
#endif
      isMoving = true;
      FLAG_STOP = false;

      // On alloue une structure pour passer les arguments + l'instance courante
      struct GoToArgs {
        float x, y, angle;
        ComWithRasp *instance;
      };

      GoToArgs *args = new GoToArgs{(float)params[0], (float)params[1],
                                    (float)params[2], this};
      xTaskCreate(GoToTask, "GoToTask", 4096, args, 2, &goToTaskHandle);
    } else {
      Serial.println("Deplacement deja en cours");
    }
  } else if (cmd == "V" && params.size() >= 2) {
    if (isMoving || goToTaskHandle != NULL) {
      FLAG_STOP = true;
      mot.Stop();
      // 2. On ne remet PAS isMoving = false ici manuellement : GoToTask
      // s'interrompt proprement et libère les verrous à sa terminaison
    }
    mot.SetVelocity((float)params[0], (float)params[1]);
  } else if (cmd == "L") {
    if (params.size() == 1) {
      LiDAR_state = params[0];
    } else {
      LiDAR_state = (LiDAR_state == 0) ? 1 : 0; // Legacy toggle
    }
#if COM_DEBUG
    Serial.print("LiDAR Mode: ");
    Serial.println(LiDAR_state);
#endif
  } else if (cmd == "S" && params.size() == 3) {
#if COM_DEBUG
    Serial.println("SetPos");
#endif
    serialGoto.SetPos((float)params[0], (float)params[1], (float)params[2]);
  } else if (cmd == "H") {
#if COM_DEBUG
    Serial.println("Halt");
#endif
    FLAG_STOP = true; // Levé avant Stop() pour que GoToTask n'enchaîne pas le segment suivant
    mot.StopVelocity();
    mot.Stop();
  } else {
    Serial.println("Commande inconnue");
  }
}

void ComWithRasp::GoToTask(void *pvParameters) {
  // Définition locale de la structure pour décoder les arguments
  struct GoToArgs {
    float x, y, angle;
    ComWithRasp *instance;
  };

  GoToArgs *args = static_cast<GoToArgs *>(pvParameters);

  // Lancement du déplacement bloquant DANS CE THREAD séparé
  bool success = serialGoto.Go(args->x, args->y, args->angle);

  // Fin du déplacement : pose finale envoyée avant D/A pour que la strat lise une position à jour
  SendPose();
  if (success) {
    Serial.println("D"); // Done
  } else {
    Serial.println("A"); // Aborted
  }

  args->instance->isMoving = false;
  args->instance->goToTaskHandle = NULL;

  delete args;
  vTaskDelete(NULL);
}
