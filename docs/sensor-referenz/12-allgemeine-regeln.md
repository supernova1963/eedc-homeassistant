## Allgemeine Regeln für Sensoren

### Tagessensoren (Utility Meter)

HA Utility Meter setzen den Zählerstand täglich um 0:00 auf 0 zurück. **Über HA ist das folgenlos:** eedc liest den
reset-bereinigten `sum`-Wert der Langzeitstatistik, ein Tagessensor taugt dort wie ein fortlaufender Zähler.

**Über MQTT Energy Topics nicht als Zählerquelle:** eedc bildet Tag und Monat aus der Differenz zweier Stände; einen
Rücksprung dazwischen erkennt es und liefert dann **keinen Wert** statt einer hochgerechneten Menge (#341, Legende
„Tagessensor"). Für MQTT deshalb den **fortlaufenden Stand** senden (`utility_meter` mit Zurücksetzen „nie").
Ein Feld mit Sensortyp „Tagessensor" (Tageswert-Feld, z. B. Speicher „Ladung heute") erwartet dagegen genau den Tageswert.

### Vorzeichen-Konvention

| Kategorie | Positiv | Negativ |
|-----------|---------|---------|
| PV-Leistung | Erzeugung | — (immer positiv) |
| Einspeisung | Ins Netz | — (immer positiv) |
| Netzbezug | Aus dem Netz | — (immer positiv) |
| Netz-Kombi | Netzbezug | Einspeisung |
| Batterie-Leistung | Ladung (Senke) | Entladung (Quelle) |
| E-Auto V2H | Ladung | Entladung ins Haus |

⚠️ Manche Wechselrichter liefern das Vorzeichen umgekehrt. In der [Datenquellen-Zuordnung](HANDBUCH_EINSTELLUNGEN.md#7-datenquellen--feld-zentrische-zuordnung) gibt es dafür am signierten Leistungs-Feld das **±**-Symbol (Vorzeichen umkehren, `live_invert`) — quellen-unabhängig direkt am Wert.

### Einheiten-Konvertierung

Live-Leistungssensoren werden automatisch konvertiert: `kW → W`, `MW → W`. Für kWh-Sensoren wird `Wh → kWh` und `MWh → kWh` automatisch skaliert. Counter-Felder (siehe §9) bleiben mit Faktor 1.0 — kein automatisches Wh→kWh, da physikalisch keine Energie.

---

*Letzte Aktualisierung: 2026-07-25 (v4.0)*
