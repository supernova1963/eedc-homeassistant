# Stunden ohne Stundenwerte

## Was eedc sieht
An diesen Tagen hat die Erfassung für einige Stunden keine Stundenwerte geliefert: sie stand still — etwa während Home
Assistant neu startete oder der Rechner aus war — oder es fehlten Werte. Danach haben die Zähler die Menge dieser Stunden
auf einmal nachgetragen, und sie steht in einer einzigen Stunde. Die Meldung nennt je Tag die Stunden, die Mengen je
Zähler und wie eedc Überschuss, Defizit und Direktverbrauch dieses Tages bestimmt hat: aus den Zählerständen gerechnet,
nicht bestimmbar (die drei Spalten bleiben leer) oder wie an jedem anderen Tag, wenn die nachgetragene Menge kaum PV
enthält. Reicht ein Ausfall über mehrere Tage, steht die Menge dieser Tage am letzten. Steht die Erfassung so oft still,
dass es zur Art der Erfassung gehört, sagt die Meldung das in einem Satz. In der Tagestabelle tragen Überschuss, Defizit
und Direktverbrauch eines solchen Tages das Zeichen «geschätzt»; der Link «Im Daten-Checker nachlesen» öffnet diesen Text,
auch für Tage, die älter als 90 Tage sind.

## Lösungsweg
1. Die genannten Tage ansehen. Ein einzelner Ausfall braucht keine Handlung: die Mengen stimmen, und eedc rechnet die drei
   Spalten des Tages aus den Zählerständen, so gut es geht.
2. Steht die Erfassung oft oder lange, die Ursache in Home Assistant suchen: läuft der Rechner durch, startet Home
   Assistant regelmäßig neu, verliert die Integration des Wechselrichters oder Zählers die Verbindung? Die Stundenwerte
   eines vergangenen Ausfalls lassen sich nicht nachholen — auch Home Assistant hat sie nicht.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile bleibt, solange ein solcher Tag in den letzten 90 Tagen
   liegt, und steht danach unter den bestandenen Prüfungen.

## Was ohne Handlung gilt
Die Summen stimmen: Erzeugung, Einspeisung, Netzbezug, Verbrauch und Speicher zählen im Tag, im Monat und im Jahr
vollständig. Die Stundenwerte dieser Stunden lassen sich nicht nachholen; die Menge steht in der Stunde, in der die Zähler
sie nachgetragen haben. Sichten, die Stunde gegen Stunde stellen, lassen diese Stunden aus: die Verbrauchsprognose und die
Tagesprognose, die Leistungsspitzen des Monats, die Heatmap, die Auswertungen des Speichers (Speichergröße, Netzladung,
Ladepreis — dort steht «nicht bestimmbar (Erfassungslücke)») und der Vergleich mit Tagen davor.

Überschuss, Defizit und Direktverbrauch eines solchen Tages sind für diese Stunden aus den Zählerständen gerechnet. Die
Rechnung hat zwei Vorbehalte, beide mit bekannter Richtung:
- Lädt der Speicher in diesen Stunden aus dem Netz, sind Überschuss und Defizit um diese Ladung zu hoch und der
  Direktverbrauch um sie zu niedrig. Ging mehr ins Netz und in den Speicher, als die PV erzeugt hat, nennt die Meldung,
  wie viel der Speicher mindestens aus dem Netz geladen hat; der Überschuss ist dann auf die PV-Menge begrenzt.
- Die Rechnung aus Stundenwerten verrechnet je Stunde, was ins Netz und in den Speicher ging (Einspeisung und Ladung), mit
  dem, was aus dem Netz und aus dem Speicher kam (Netzbezug und Entladung). Für die Stunden des Ausfalls kann die Rechnung
  aus den Zählerständen das nicht und liegt deshalb etwas darüber: Überschuss und Defizit höchstens zu hoch,
  Direktverbrauch höchstens zu niedrig. An einer Beispielanlage sind es über ganze Tage gerechnet im Mittel 0,8 kWh
  je Tag; ein Ausfall von wenigen Stunden liegt darunter, einer über mehrere Tage deutlich darüber.

Können die drei Spalten nicht bestimmt werden — die Zähler haben ihre Mengen nicht für dieselben Stunden nachgetragen, oder
der Speicher ist für den Tag nur als Saldo von Ladung und Entladung gespeichert —, bleiben sie leer, und die Summe des
Monats nennt, wie viele Tage ihr fehlen. Der Sensor «Überschuss heute», den eedc an Home Assistant gibt, hat an einem
solchen Tag keinen Wert (nicht 0). Die Speicher-Auswertung «Hätte mehr Kapazität geholfen?» zählt die Netzladung dieser
Stunden nicht mit.

Was eedc nicht erkennt oder nicht kennzeichnet:
- Ohne Zähler für den Netzbezug und mindestens einen weiteren Zähler (PV oder Einspeisung) erkennt eedc keinen Ausfall —
  ebenso wenig an einer Anlage mit Speicher, wenn Ladung und Entladung des Speichers keine eigenen Zähler haben.
- Ein Ausfall in der Nacht, nach dem nur ein Zähler eine Menge nachträgt, wird nicht erkannt.
- Steht nur ein einzelner Zähler, während die übrigen weiterlaufen, ist das kein erkennbarer Ausfall der Erfassung.
- Ein Ausfall von nur einer Stunde bleibt wie bisher: die Menge zweier Stunden steht in einer.
- Ein Zähler, der nur in groben Schritten (0,1 kWh oder mehr) meldet, und eine Erfassung, die regelmäßig stehen bleibt,
  werden nicht gekennzeichnet — dort zählt die nachgetragene Menge als eine Stunde.
- Tage, die eedc aus eigenen Zählerständen statt aus der Statistik von Home Assistant rechnet, tragen keine Kennzeichnung;
  dort nennt der Befund «Nachtrag nach eingefrorenem Zähler» eine solche Stunde.
- Der PV-Anteil einer Heimladung und die Kosten der Stunde, in der die Menge nachgetragen wurde, bleiben eine Näherung:
  eedc bewertet die Menge mit dem Preis dieser einen Stunde.
- Ein Ausfall, der länger als 90 Tage dauert, wird nur in seinen letzten 90 Tagen erkannt.
- Im Diagnose-Paket steht die Kennzeichnung nicht; sie entsteht beim Lesen und lässt sich aus den Daten nachrechnen.
- Eine Zeit, deren Zählerstände eine Korrektur verworfen hat und die nichts wieder füllt, nennt dieser Befund nicht; sie
  steht unter «Zählerstände – Zeit verworfen».
