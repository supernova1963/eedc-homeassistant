<!-- anker: 48j-zaehlerstaende--gespeicherter-monatswert-passt-nicht-mehr -->
### 4.8j Zählerstände – Gespeicherter Monatswert passt nicht mehr <a name="48j-zaehlerstaende--gespeicherter-monatswert-passt-nicht-mehr"></a>

Ein Wechsel der Quelle mit «Bisherige Werte bleiben», ein eingetragener Zählertausch oder eine Korrektur ändert, was eedc für
einen Monat aus der Quelle bildet. Ein Monatswert, den du vorher gespeichert hast (Monatsabschluss, «Aus HA laden», Import),
bleibt dabei, wie er ist — und alles, was eedc für diesen Monat zeigt, rechnet mit ihm. Diese Kategorie nennt einen solchen
Monat, wenn der gespeicherte Wert und der Wert, den die Quelle heute für den ganzen Monat ergibt, um mindestens 1 kWh
auseinanderliegen (dieselbe Schwelle wie die Vorschau von «Monatsdaten aus HA-Statistik laden»).

**Was kein Befund ist.** Ein Monat, den kein Wechsel berührt; ein Monat nach dem Monat, in dem der Wechsel eingetragen wurde
(diesen Wert hast du schon mit dem Wechsel gespeichert); ein Monat ohne gespeicherten Wert; ein Monat, für den eedc heute
keinen vollen Wert hat (etwa über eine verworfene Zeit, [§4.8i](#48i-zaehlerstaende--zeit-verworfen)); der laufende Monat; ein
Wert, den du im Monatsabschluss mit «gespeicherten behalten» bewusst behalten hast. Nicht geprüft werden der
Anlagen-PV-Zähler (sein Monatswert ist die Summe je Modul) und Felder, deren Werte eedc nicht stündlich mitschreibt.

---
