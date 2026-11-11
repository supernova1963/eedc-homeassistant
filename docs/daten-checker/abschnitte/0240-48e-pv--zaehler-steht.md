<!-- anker: 48e-pv--zaehler-steht -->
### 4.8e PV – Zähler steht <a name="48e-pv--zaehler-steht"></a>

Ein PV-Gesamtzähler (Feld „PV gesamt“), der **eingefroren** ist — der Sensor meldet weiter, aber sein Stand bewegt sich
nicht —, sieht für eedc aus wie ein Zähler ohne Erzeugung. Läuft dabei die Einspeisung weiter, passt die Tagesbilanz
nicht mehr zusammen, und Tages- und Monatsansicht im Cockpit zeigen unplausible Werte, etwa eine **negative Autarkie**.
eedc rechnet diese Werte bewusst so, wie sie gemessen sind, und biegt sie nicht zurecht; diese Kategorie nennt die
Ursache.

Geprüft werden die letzten 31 abgeschlossenen Tage des Anlagenzählers „PV gesamt“, soweit eedc ihn lückenlos kennt. Die
Zähler einzelner Strings prüft diese Kategorie nicht: steht ein String, während die anderen erzeugen, ist das meist
Teilbeschattung oder Schnee auf einem Teil der Module — eine richtige Messung.

**Was diese Meldung bewusst nicht auslöst** — das sind richtige Messungen:

- ein Einspeisezähler, der steht, während die PV erzeugt (**Nulleinspeisung**, Wintertage mit 100 % Eigenverbrauch);
- ein Netzbezugszähler, der steht (**autarke Tage** mit Speicher);
- ein PV-Zähler, der steht, während nur der Netzbezug läuft (**Schnee** auf den Modulen);
- ein einzelner String-Zähler, der steht, während die anderen erzeugen (**Teilbeschattung**, Schnee auf einem Teil der
  Module);
- ein Speicher, der bei PV 0 ins Netz entlädt — seine Entladung wird abgezogen. Hat dein Speicher keinen
  Entladungs-Zähler, nimmt eedc die Einspeisung gar nicht als Vergleich.

---
