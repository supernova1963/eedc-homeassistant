# Anlagenzähler zählt mehr als die Strings

## Was eedc sieht
In den genannten Monaten liegt der Anlagenzähler (Feld „PV gesamt“) um mehr als 2 % über der Summe der String-Zähler.
Nach dem Wechselrichter kann nicht mehr ankommen, als die Strings davor liefern — meist zählt der Anlagenzähler eine
weitere Quelle mit (ein Balkonkraftwerk, ein zweiter Wechselrichter), oder ein String-Zähler misst zu wenig.
Geprüft werden abgeschlossene Monate, in denen der Anlagenzähler einen Wert hat und jede PV-Quelle einen eigenen Zähler.
Bei einem DC-gekoppelten Speicher schweigt die Prüfung: Der Anlagenzähler zählt dann die Netzladung der Batterie mit.

## Lösungsweg
1. Am Befund **«Zur Zuordnung»** klicken — die Datenquellen-Zuordnung öffnet sich beim Anlagenzähler
   („PV-Erzeugung Zählerstand“).
2. Prüfen, was der Sensor dort mitzählt: Zählt er eine weitere Quelle mit, braucht diese Quelle einen eigenen Eintrag
   unter den Komponenten mit eigenem Zähler; misst ein String zu wenig, dessen Zähler beim PV-Modul prüfen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile nennt nur noch Monate, in denen der Anlagenzähler
   weiter vorn liegt.

## Was ohne Handlung gilt
eedc rechnet in diesen Monaten mit der Summe der Strings; Wandlungsverluste gibt es dort keine.
