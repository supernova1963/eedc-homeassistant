# Wetterreihe uneinheitlich oder lückenhaft

## Was eedc sieht
Globalstrahlung und Sonnenstunden sagen, wie viel Sonne ein Monat hatte — ohne sie lässt sich ein schwaches Jahr nicht
von einer schwachen Anlage unterscheiden. Die Zeile nennt bis zu drei Zahlen abgeschlossener Monate: Monate ohne
Globalstrahlung oder Sonnenstunden; Monate aus einer anderen Wetterquelle als der heute gewählten (Open-Meteo und
Bright Sky messen Sonnenstunden nicht gleich, ein Mehrjahresvergleich sagt dann etwas über die Quelle, nicht über die
Sonne); Monate, bei denen nicht festgehalten ist, woher ihre Werte stammen. Das Letzte behauptet nicht, dass die Reihe
gemischt ist — nur, dass es sich nicht mehr feststellen lässt; das ist der Normalfall jeder älteren Anlage.

## Lösungsweg
1. Unter *Einstellungen → Stammdaten → Anlage* prüfen, ob die
   [«Wetterdaten-Quelle»](eedc:/einstellungen/stammdaten?block=anlage&feld=wetter_provider) die ist, die du willst —
   von ihr holt eedc die Werte.
2. Am Befund **«Wetterreihe nachziehen»** klicken, die Vorschau lesen und **«Anwenden»**. eedc holt Globalstrahlung,
   Sonnenstunden und Ø Temperatur aller abgeschlossenen Monate von dieser Quelle (die Ø Temperatur zuerst aus deinen
   Messwerten) und **ersetzt** dabei vorhandene Werte aller drei Felder, auch von Hand gesetzte — die Vorschau nennt
   vorher, wie viele Monate betroffen sind. Der laufende Monat bleibt draußen.
3. Erneut prüfen: im Daten-Checker **«Aktualisieren»** — die Zeile ist verschwunden, sobald jeder abgeschlossene
   Monat Werte mit Quelle trägt; Monate, für die kein messendes Archiv deinen Ort erreicht, bleiben in der Zeile stehen.

## Was ohne Handlung gilt
Einmal täglich füllt eedc nur fehlende Werte abgeschlossener Monate von der gewählten Quelle nach; was dasteht, bleibt.
Eine gemischte Reihe bleibt gemischt, und Jahresvergleiche von Strahlung und Sonnenstunden können die Quelle statt der
Sonne zeigen.
