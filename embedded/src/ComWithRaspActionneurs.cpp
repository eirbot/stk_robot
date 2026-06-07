#include "ComWithRaspActionneurs.hpp"
#include "Actionneurs.hpp"

ComWithRasp::ComWithRasp() { Serial.begin(115200); }

void ComWithRasp::StartCom() {
  // Crée une tâche FreeRTOS qui appelle this->Receive()
  xTaskCreate([](void *obj) { static_cast<ComWithRasp *>(obj)->Receive(); },
              "ComWithRasp", 4000, this, 1, NULL);
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
  int actioStatus = 0;
  if (cmd == "G" && params.size() == 1) {
    if((int)params[0]==1){
      act1.closePiston();
    } else if((int)params[0]==2) {
      act2.closePiston();
    } else if((int)params[0]==3) {
      act3.closePiston();
    } else if((int)params[0]==4) {
      act4.closePiston();
    }
  } else if (cmd == "R" && params.size() == 1) {
    if((int)params[0]==1){
      act1.openPiston();
    } else if((int)params[0]==2) {
      act2.openPiston();
    } else if((int)params[0]==3) {
      act3.openPiston();
    } else if((int)params[0]==4) {
      act4.openPiston();
    }
  } else if (cmd == "T" && params.size() == 1) {
    if((int)params[0]==1){
      if(act1.p9G_status == 0){
        act1.servo_9G(180);
        act1.p9G_status = 180;
      }
      else{
        act1.servo_9G(0);
        act1.p9G_status = 0;
      }
    } else if((int)params[0]==2) {
      if(act2.p9G_status == 0){
        act2.servo_9G(180);
        act2.p9G_status = 180;
      }
      else{
        act2.servo_9G(0);
        act2.p9G_status = 0;
      }
    } else if((int)params[0]==3) {
      if(act3.p9G_status == 0){
        act3.servo_9G(180);
        act3.p9G_status = 180;
      }
      else{
        act3.servo_9G(0);
        act3.p9G_status = 0;
      }
    } else if((int)params[0]==4) {
      if(act4.p9G_status == 0){
        act4.servo_9G(180);
        act4.p9G_status = 180;
      }
      else{
        act4.servo_9G(0);
        act4.p9G_status = 0;
      }
    }
  } else if (cmd == "P" && params.size() == 2) {
    if((int)params[0]==1){
      int angle = 90;
      if((int)params[1] == 1){
        angle = 40;
      }
      act1.soft_servo(angle);
    }
    if((int)params[0]==2){
      int angle = 90;
      if((int)params[1] == 1){
        angle = 60;
      }
      act2.soft_servo(angle);
    }
    if((int)params[0]==3){
      int angle = 90;
      if((int)params[1] == 1){
        angle = 120;
      }
      act3.soft_servo(angle);
    }
    if((int)params[0]==4){
      int angle = 90;
      if((int)params[1] == 1){
        angle = 140;
      }
      act4.soft_servo(angle);
    }
  } else if (cmd == "A" && params.size() == 2) {
    Serial.println("SetPos");
    int mmToStep =80;
    int asked_height = (int)params[1]* mmToStep;
    if((int)params[0]==1){
      if(asked_height - act1.asc_height >=0){
        act1.goUp(asked_height - act1.asc_height);
      }
      else{
        act1.goDown(act1.asc_height - asked_height);
      }
      act1.asc_height = asked_height;
    }
    else if((int)params[0]==2){
      if(asked_height - act2.asc_height >=0){
        act2.goUp(asked_height - act2.asc_height);
      }
      else{
        act2.goDown(act2.asc_height - asked_height);
      }
      act2.asc_height = asked_height;
    }
    else if((int)params[0]==3){
      if(asked_height - act3.asc_height >=0){
        act3.goUp(asked_height - act3.asc_height);
      }
      else{
        act3.goDown(act3.asc_height - asked_height);
      }
      act3.asc_height = asked_height;
    }
    else if((int)params[0]==4){
      if(asked_height - act4.asc_height >=0){
        act4.goUp(asked_height - act4.asc_height);
      }
      else{
        act4.goDown(act4.asc_height - asked_height);
      }
      act4.asc_height = asked_height;
    }
    
  } else if (cmd == "I") {
    Serial.println("init_robot");
    act2.homming();
    act3.homming();
    act1.homming();
    act4.homming();
    flagInit=true;

  } else {
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
