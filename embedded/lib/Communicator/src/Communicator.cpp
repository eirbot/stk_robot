#include "Communicator.hpp"
#include "AppState.hpp"
#include "Arm_ActuatorVTask.hpp"
#include "Arduino.h"
#include <cstdint>

// TODO: check if the cpu assignment without affinity is an issue the CPU core
ComWithRasp::ComWithRasp() { Serial.begin(115200); }

void ComWithRasp::StartWorkers() {
  act1.initialiser();
  act2.initialiser();
  act3.initialiser();
  act4.initialiser();

  xTaskCreatePinnedToCore(ActVTaskRunner, "TaskWorkerAct1", 4000, &actVTask1, 1, NULL, tskNO_AFFINITY);
  xTaskCreatePinnedToCore(ActVTaskRunner, "TaskWorkerAct2", 4000, &actVTask2, 1, NULL, tskNO_AFFINITY);
  xTaskCreatePinnedToCore(ActVTaskRunner, "TaskWorkerAct3", 4000, &actVTask3, 1, NULL, tskNO_AFFINITY);
  xTaskCreatePinnedToCore(ActVTaskRunner, "TaskWorkerAct4", 4000, &actVTask4, 1, NULL, tskNO_AFFINITY);
}

void ComWithRasp::StartCom() {
  // Crée une tâche FreeRTOS qui appelle this->Receive()
  xTaskCreatePinnedToCore([](void *obj) { static_cast<ComWithRasp *>(obj)->Receive(); },
              "ComWithRasp", 4000, this, 1, NULL, tskNO_AFFINITY);
}

void ComWithRasp::Receive() {
  // On crée un tableau fixe de 64 cases en mémoire (ultra rapide et sûr)
  char rx_buffer[64];
  int rx_index = 0;
  Serial.println("Booting up...");
  

  while (!appState.timeout) {
    while (!appState.timeout && Serial.available()) {
      char c = (char)Serial.read();
      // Si on détecte la touche Entrée (\r ou \n)
      if (c == '\n' || c == '\r') {
        // On vérifie qu'on a bien reçu au moins une lettre
        if (rx_index > 0) {
          rx_buffer[rx_index] =
              '\0'; // On met le caractère de fin de chaîne obligatoire en C
          // On transfère le tableau sécurisé dans ta variable String habituelle
          commande = String(rx_buffer);
          Serial.println("-> Ligne complete securisee pour actionneurs : [" + commande + "]");
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
          Serial.println("Parsed ! Buffer state : ");
          //Serial.println(rx_buffer);
        } else {
          Serial.println("-> ERREUR : Buffer plein, message trop long !");
          rx_index = 0; // On vide pour éviter de bloquer l'ESP
        }
      }
    }
    //Serial.println("[Task|Com] Serial empty, delegating CPU...");
    // On rend la main à FreeRTOS
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }

  vTaskDelete(NULL);
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

void ComWithRasp::processCommand(const String &cmd,const std::vector<int> &params) {
  // wait for all inits
  if (cmd == "I") {
    TaskParams taskParams = TaskParams(cmd.charAt(0), 0, 0);
    xQueueSendToBack(actVTask1._queue, &taskParams, 0);
    xQueueSendToBack(actVTask2._queue, &taskParams, 0);
    xQueueSendToBack(actVTask3._queue, &taskParams, 0);
    xQueueSendToBack(actVTask4._queue, &taskParams, 0);

    while (!actVTask1.flagInit) { Serial.println("waiting for flag init"); vTaskDelay(0); };
    Serial.println("Init Act1 terminé");
    while (!actVTask2.flagInit) { Serial.println("waiting for flag init"); vTaskDelay(0); };
    Serial.println("Init Act2 terminé"); 
    while(!actVTask3.flagInit) { Serial.println("waiting for flag init"); vTaskDelay(0); };
    Serial.println("Init Act3 terminé");
    while(!actVTask4.flagInit) { Serial.println("waiting for flag init"); vTaskDelay(0); };
    Serial.println("Init Act4 terminé");
    flagInit = true;
    return;
  }

  if (params.size() == 0) {
    Serial.println("No parameters for other actions, thus not valid ! Ignoring...");
    return;
  }
  
  int actioStatus = 0;
  int actId = (int) params[0];
  int A_param1 = 0;
  uint8_t P_angleFlag = 0;
  if (cmd == "P") {
    if (params.size() != 2) {
      Serial.println("Invalid number of parameters for command P");
      return;
    }
    P_angleFlag = params[1];
  } else if (cmd == "A") {
    if (params.size() != 2) {
      Serial.println("Invalid number of parameters for command A");
      return;
    }
    A_param1 = params[1];
  }
  char buf[8];
  Serial.print(itoa(actId, buf, 10));
  Serial.println(" id");
  TaskParams taskParams = TaskParams(cmd.charAt(0), P_angleFlag, A_param1);
  
  switch (actId) {
    case 1:
      xQueueSendToBack(actVTask1._queue, &taskParams, 0);
      break;
    case 2:
      xQueueSendToBack(actVTask2._queue, &taskParams, 0);
      break;
    case 3:
      xQueueSendToBack(actVTask3._queue, &taskParams, 0);
      break;
    case 4:
      xQueueSendToBack(actVTask4._queue, &taskParams, 0);
      break;
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
  // bool success = serialGoto.Go(args->x, args->y, args->angle);

  // Fin du déplacement
  // if (success) {
  //   Serial.println("D"); // Done
  // } else {
  //   Serial.println("A"); // Aborted
  // }

  args->instance->isMoving = false;

  delete args;
  vTaskDelete(NULL);
}
