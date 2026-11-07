## 3. Speicher (Batterie)

### Monatserfassung

<!-- erzeugt: eingabefelder typ=speicher liste=monat -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `ladung_kwh`: Gesamte im Monat in den Speicher geladene Energie, **Netzladung eingeschlossen**. Muss ≥ 0 sein. `ladung_netz_kwh` ist ein *davon*-Anteil, kein zweiter Summand — ein Gerät, das PV- und Netzladung getrennt zählt, braucht hier die Summe beider (HA-Helfer). **Messstelle:** die zur [Kopplung](HANDBUCH_EINSTELLUNGEN.md#34-typ-spezifische-parameter) passende Seite — bei AC-Kopplung hausseitig hinter dem Batterie-Wechselrichter, bei DC-Kopplung am Batterie-Anschluss.
> - `entladung_kwh`: Gesamte im Monat aus dem Speicher entladene Energie. Muss ≥ 0 sein. **Dieselbe Messstelle wie die Ladung** — kommen die beiden von verschiedenen Seiten (etwa Ladung DC aus der Hersteller-Cloud, Entladung AC aus einem Riemann-Sensor), enthält der Wirkungsgrad die Wandlung nur in eine Richtung.
> - `ladung_netz_kwh`: Anteil der Ladung aus dem Netz (Arbitrage). Optional. Muss ≤ `ladung_kwh` sein. **Kanonischer Schlüssel** `ladung_netz_kwh` (Legacy-Fallback `speicher_ladung_netz_kwh` wird noch gelesen).
> - `speicher_ladepreis_cent`: Ø Preis der Netzladung. Nur bei echter Arbitrage relevant — Backup-/Notladung läuft zum Bezugspreis. Erfassung im Monatsdaten-Formular, per CSV-Import oder über den errechneten Vorschlag bei dynamischem Tarif; auf der Datenquellen-Fläche wird das Feld **nicht** zur Zuordnung angeboten (seit v4.0.6).

### Live-Dashboard

<!-- erzeugt: eingabefelder typ=speicher liste=live -->

> **Aus der früheren Spalte „Beschreibung"** — was die Hinweise der Tabelle (noch) nicht sagen:
>
> - `leistung_w`: Positiv = Ladung (Senke), negativ = Entladung (Quelle). ⚠️ Manche WR liefern umgekehrtes Vorzeichen — dann in der Datenquellen-Zuordnung „±" (Vorzeichen umkehren) aktivieren.

**Ladung und Entladung des Tages** sind keine eigenen Registry-Felder: Es sind die Monatsfelder `ladung_kwh`/`entladung_kwh` der Tabelle „Monatserfassung", hier mit einem Tagessensor zugeordnet.

| Feld | Label | Einheit | Sensortyp | Beschreibung | Ausgewertet in |
|------|-------|---------|-----------|-------------|-----------------|
| `ladung_kwh` | Ladung heute | kWh | Tagessensor | Tages-Ladeenergie. Optional — wenn vorhanden, wird für heute-kWh-Anzeige bevorzugt (genauer als Trapez-Integration aus W-Sensor). Wird täglich um 0:00 auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |
| `entladung_kwh` | Entladung heute | kWh | Tagessensor | Tages-Entladeenergie. Optional — wie `ladung_kwh`. Wird täglich auf 0 zurückgesetzt. | Komponenten → Speicher · Cockpit → Monat · HA-Sensoren |

### MQTT Energy Topics

Welche MQTT-Topics eedc für dieses Gerät erwartet — Energie- und Live-Topics je Feld —, steht in [MQTT-Inbound](MQTT_INBOUND.md#topic-struktur).

---

