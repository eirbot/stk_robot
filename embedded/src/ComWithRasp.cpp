#include "ComWithRasp.hpp"

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
          Serial.println("-> Ligne complete securisee : [" + commande + "]");
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
    // On rend la main à FreeRTOS
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

void ComWithRasp::TelemetryLoop() {
  float x, y, angle;

  while (1) {
    mot.GetPosition(x, y, angle);

    Serial.print("T ");
    Serial.print(x);
    Serial.print(" ");
    Serial.print(y);
    Serial.print(" ");
    Serial.println(angle * RAD_TO_DEG);

    vTaskDelay(100 / portTICK_PERIOD_MS);
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
  Serial.print("-> Commande reconnue : '");
  Serial.print(command);
  Serial.print("' | Parametres [");
  for (int i = 0; i < params.size(); i++) {
    Serial.print(params[i]);
    if (i < params.size() - 1)
      Serial.print(", ");
  }
  Serial.println("]");

  // 5. Exécution
  processCommand(command, params);
}

void ComWithRasp::processCommand(const String &cmd,
                                 const std::vector<int> &params) {
  if (cmd == "G" && params.size() == 3) {
    if (!isMoving) {
      Serial.println("GoToPosition (async)");
      isMoving = true;

      // On alloue une structure pour passer les arguments + l'instance courante
      struct GoToArgs {
        float x, y, angle;
        ComWithRasp *instance;
      };

      GoToArgs *args = new GoToArgs{(float)params[0], (float)params[1],
                                    (float)params[2], this};
      xTaskCreate(GoToTask, "GoToTask", 4096, args, 2, NULL);
    } else {
      Serial.println("Deplacement deja en cours");
    }
  } else if (cmd == "L") {
    if (params.size() == 1) {
      LiDAR_state = params[0];
    } else {
      LiDAR_state = (LiDAR_state == 0) ? 1 : 0; // Legacy toggle
    }
    Serial.print("LiDAR Mode: ");
    Serial.println(LiDAR_state);
  } else if (cmd == "S" && params.size() == 3) {
    Serial.println("SetPos");
    serialGoto.SetPos((float)params[0], (float)params[1], (float)params[2]);
  } else if (cmd == "H") {
    Serial.println("Halt");
    mot.Stop();
    FLAG_STOP = true;
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

  // Fin du déplacement
  if (success) {
    Serial.println("D"); // Done
  } else {
    Serial.println("A"); // Aborted
  }

  args->instance->isMoving = false;

  delete args;
  vTaskDelete(NULL);
}
