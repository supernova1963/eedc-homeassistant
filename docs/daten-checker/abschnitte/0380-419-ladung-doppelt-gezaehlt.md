<!-- anker: 419-ladung-doppelt-gezaehlt -->
### 4.19 Ladung doppelt gezählt (Wallbox + E-Auto) <a name="419-ladung-doppelt-gezaehlt"></a>

**Was wird geprüft:** Gibt es in den letzten 180 Tagen gespeicherte Tage, an denen **Wallbox und E-Auto beide mindestens 1 kWh Ladung** tragen?

**Warum das zählt:** Wer sein Auto zu Hause lädt, hat oft beide Geräte erfasst — die Wallbox misst, das Auto meldet. Beide Zahlen zu addieren verdoppelt den Verbrauch. eedc kennt die Regel inzwischen (*trägt die Wallbox die Ladeenergie, ist sie die Quelle*), aber **bereits gespeicherte** Tage tragen die alte Rechnung weiter.

> **Warum das kein automatischer Lauf beim Start ist:** Die Berichtigung überschreibt gespeicherte Messwerte. Das passiert in eedc nie ungefragt — du siehst den Befund, die Tage, und entscheidest.

---
