<!-- anker: 418-pv-doppelerfassung -->
### 4.18 PV-Doppelerfassung (Verdacht) <a name="418-pv-doppelerfassung"></a>

**Was wird geprüft:** Liefert deine Anlage an mehreren Tagen **mehr**, als physikalisch plausibel ist? Zwei unabhängige Signale aus den letzten 30 Tagen: eine Performance Ratio über 1,05 und ein spezifischer Tagesertrag über 7 kWh/kWp.

**Warum das zählt:** Der häufigste Grund ist keine Wundertechnik, sondern **dieselbe Erzeugung zweimal gezählt** — etwa ein String-Sensor *und* der Anlagen-Summenzähler, beide zugeordnet. Alles, was auf der Erzeugung aufbaut, wird dadurch zu gut: Eigenverbrauch, Autarkie, Ersparnis, CO₂.

> **Der Verdacht hat zwei Seiten, und die zweite wird leicht übersehen.** Die Performance Ratio ist `Ertrag ÷ (Einstrahlung × kWp)`. Sie steigt also nicht nur, wenn der **Ertrag** zu hoch ist, sondern auch, wenn der **Vergleichsmaßstab** zu klein angesetzt ist — und der hat zwei Faktoren: die eingetragene kWp *und* die Einstrahlung. Wer alle Zuordnungen geprüft hat und nichts Doppeltes findet, sieht deshalb als Nächstes bei **Ausrichtung und Neigung der Module** nach (*Einstellungen → Komponenten → PV-Module*): Ohne sie rechnet eedc mit einer Einstrahlung, die nicht zu deinem Dach passt.

> **Und eine dritte Spur, die nicht bei dir liegt: die Einstrahlung der letzten Tage ist vorläufig.** Den Strahlungswert holt eedc beim Wetterdienst. Für Tage, die weiter als fünf Tage zurückliegen, kommt er aus dem endgültigen Messarchiv; für die Tage davor gibt es das Archiv noch nicht, eedc nimmt dort den Modellwert. Der ist im Mittel gut, an **bewölkten** Tagen aber deutlich zu klein — und ein zu kleiner Vergleichsmaßstab treibt die Performance Ratio nach oben, ohne dass an deiner Anlage etwas falsch wäre. eedc holt den endgültigen Wert von selbst nach, sobald ein Tag alt genug ist (nur die Wetterzeile, die gemessene Energie bleibt). Ein Verdacht, der nur an solchen Tagen hing, verschwindet damit von allein.

> **Liest eedc deine Anlage aus der Statistik von Home Assistant,** zählt für den spezifischen Tagesertrag die PV von dort — dieselbe Zahl wie in der Tagesansicht im Cockpit; die Performance Ratio bleibt die der gespeicherten Tageszeile.

> **eedc kürzt hier nichts.** Es gibt keinen Knopf, der die Erzeugung „gerade zieht" — die Entscheidung, welche Zuordnung die richtige ist, kann nur der Anlagenbetreiber treffen.

---
