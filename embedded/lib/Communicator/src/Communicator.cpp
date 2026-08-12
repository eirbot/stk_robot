#include "Communicator.hpp"
#include "AppState.hpp"
#include "Arduino.h"

// TODO: check the best number with test
#define MAX_SERIAL_READINGS_BEFORE_YIELD 50

void ComWithRasp::task() {
  // On crée un tableau fixe de 64 cases en mémoire (ultra rapide et sûr)
  char rx_buffer[64];
  int rx_index = 0;
  Serial.println("Booting up...");
  
  while (!appState.timeout) {
    // TODO: check if Serial.available is false when IDLE
    for (uint8_t serial_readings = 0;
         !appState.timeout && Serial.available() &&
         serial_readings < MAX_SERIAL_READINGS_BEFORE_YIELD;
         serial_readings++)
      receive(rx_buffer, rx_index);
    _taskLocalArmOrchestrator.loop();
    //Serial.println("[Task|Com] Serial empty, delegating CPU...");
    // On rend la main à FreeRTOS
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }

  vTaskDelete(NULL);
}

void ComWithRasp::receive(char rx_buffer[64], int &rx_index) {
  char c = (char)Serial.read();
  // Si on détecte la touche Entrée (\r ou \n)
  if (c == '\n' || c == '\r') {
    // On vérifie qu'on a bien reçu au moins une lettre
    if (rx_index > 0) {
      rx_buffer[rx_index] =
          '\0'; // On met le caractère de fin de chaîne obligatoire en C
      // On transfère le tableau sécurisé dans ta variable String habituelle
      commande = String(rx_buffer);
      Serial.println("-> Ligne complete securisee pour actionneurs : [" +
                     commande + "]");
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
      // Serial.println(rx_buffer);
    } else {
      Serial.println("-> ERREUR : Buffer plein, message trop long !");
      rx_index = 0; // On vide pour éviter de bloquer l'ESP
    }
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

void ComWithRasp::processCommand(const String &cmd,const std::vector<int> &params) {
  Command orchestratorCommand{_next_command_id, cmd.charAt(0), params};
  _next_command_id++;
  xQueueSendToBack(_armOrchestratorInterface.queue_into_object, &orchestratorCommand, 0);
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
