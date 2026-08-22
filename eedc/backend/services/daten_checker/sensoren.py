"""
Daten-Checker — Sensor-Mapping-LTS & MQTT-Topic-Abdeckung (`SensorChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage

from .kategorien import (
    CheckErgebnis, CheckKategorie, CheckSeverity, LINK_DATENQUELLEN,
)


class SensorChecks:
    """Prüfungen für Sensor-Mapping-LTS-Verfügbarkeit und MQTT-Topics."""

    # ─── MQTT-Topic-Abdeckung (Issue #134) ───────────────────────────────

    async def _check_mqtt_topic_abdeckung(self, anlage: Anlage) -> list[CheckErgebnis]:
        """
        Prüft ob die erwarteten MQTT-Inbound-Topics tatsächlich ankommen.

        Issue #134: Schließt die Lücke zwischen dynamischer Konsumenten-Seite
        (Erwartungsliste aus `field_definitions.py`) und statisch hartkodierter
        Publisher-Seite (HA-Automationen). Wenn ein Topic erwartet, aber nie
        empfangen wird oder veraltete Werte trägt, ist die Publisher-Seite
        gegen die Konsumenten-Seite gedriftet.
        """
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        from backend.services.mqtt_topic_registry import build_expected_topics
        from backend.services.datenquellen_resolver import (
            erwartet_inbound_topic, feld_id_aus_match_key,
        )
        from backend.models.settings import Settings as SettingsModel

        kat = CheckKategorie.MQTT_TOPIC_ABDECKUNG
        ergebnisse: list[CheckErgebnis] = []

        service = get_mqtt_inbound_service()
        if service is None or not service._running:
            # Kategorie nur anzeigen, wenn der Nutzer MQTT-Inbound bewusst
            # aktiviert hat. Sonst stiller Skip — wer MQTT nicht nutzt, soll
            # die Kategorie gar nicht erst sehen.
            result = await self.db.execute(
                select(SettingsModel).where(SettingsModel.key == "mqtt_inbound")
            )
            setting = result.scalar_one_or_none()
            inbound_enabled_in_settings = bool(
                setting and setting.value and setting.value.get("enabled")
            )
            if not inbound_enabled_in_settings:
                return []
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="MQTT-Inbound aktiviert, Subscriber läuft jedoch nicht",
                details=(
                    "Möglicherweise konnte beim letzten Start keine Verbindung "
                    "zum Broker aufgebaut werden. Prüfe Broker-Adresse und "
                    "Zugangsdaten unter Daten → Einrichtung → MQTT-Inbound, "
                    "oder deaktiviere MQTT-Inbound dort, wenn du keine "
                    "Live-Daten via MQTT brauchst."
                ),
                link="/einstellungen/mqtt-inbound",
            ))
            return ergebnisse

        # `nur_manuell`-Felder sind kein erwartetes Topic — sie sind bewusst
        # nicht zuordenbar; als „nie empfangen" gemeldet wären sie eine Lücke,
        # die niemand schließen kann (dieselbe Begründung wie bei den
        # Preis-Slots in `_basis_preis_eintraege`).
        #
        # `zustand`-Felder ebenso (#263 K-2): Der MQTT-Inbound-Parser ist
        # `float(payload)` — ein Betriebsmodus kann über MQTT gar nicht
        # ankommen, und die Fläche bietet ihn dort auch nicht an. Als „nie
        # empfangen" gemeldet stünde hier ein Dauer-Hinweis auf ein Topic, auf
        # das niemand publizieren soll. Sie tragen deshalb schon in der
        # Registry ein leeres `topic`.
        #
        # Und drittens (F-50, #389): Felder, deren Quelle der Anwender bewusst
        # auf „Keine" oder einen HA-Sensor gesetzt hat. Die Erwartungsliste
        # kommt aus der Felder-Registry und kannte die Zuordnung bis v4.0.22
        # gar nicht — vier auf „Keine" gestellte Felder standen deshalb
        # dauerhaft als „erwartet, nie empfangen" in den Warnungen.
        # Begründung je Quelle in `erwartet_inbound_topic` (Gateway bleibt
        # bewusst drin: sein Re-Publish landet im selben Cache).
        quellen = (anlage.sensor_mapping or {}).get("quellen") or {}
        if not isinstance(quellen, dict):
            quellen = {}
        erwartet = [
            e for e in await build_expected_topics(self.db, anlage)
            if not e.get("nur_manuell") and not e.get("zustand")
            and erwartet_inbound_topic(quellen, feld_id_aus_match_key(e["match_key"]))
        ]
        if not erwartet:
            return ergebnisse

        live_data = service.cache.get_all_live_raw().get(anlage.id, {})
        energy_data = service.cache.get_all_energy_raw().get(anlage.id, {})
        basis_live: dict = live_data.get("basis", {})
        inv_live: dict = live_data.get("inv", {})

        now = datetime.now()
        # Schwellwerte: live ≤ 2 min (sensorgetrieben), energy ≤ 10 min
        # (alle-5-Pattern + Puffer). Oberhalb gilt der Wert als veraltet.
        LIVE_MAX_AGE = timedelta(minutes=2)
        ENERGY_MAX_AGE = timedelta(minutes=10)

        nie_empfangen: list[str] = []
        veraltet: list[tuple[str, int]] = []  # (topic, alter_minuten)

        for entry in erwartet:
            mk = entry["match_key"]
            kategorie = entry["kategorie"]
            threshold = LIVE_MAX_AGE if kategorie == "live" else ENERGY_MAX_AGE

            ts: Optional[datetime] = None
            kind = mk[0]
            if kind == "basis_live":
                pair = basis_live.get(mk[1])
                if pair:
                    _, ts = pair
            elif kind == "basis_energy":
                pair = energy_data.get(mk[1])
                if pair:
                    _, ts = pair
            elif kind == "inv_live":
                pair = inv_live.get(mk[1], {}).get(mk[2])
                if pair:
                    _, ts = pair
            elif kind == "inv_energy":
                pair = energy_data.get(f"inv/{mk[1]}/{mk[2]}")
                if pair:
                    _, ts = pair

            if ts is None:
                nie_empfangen.append(entry["topic"])
            elif now - ts > threshold:
                age_min = int((now - ts).total_seconds() // 60)
                veraltet.append((entry["topic"], age_min))

        if nie_empfangen:
            # Voller Topic-Pfad statt nur des letzten Segments (#389): „leistung_w"
            # gibt es an jedem Gerät — erst der Pfad sagt, an welchem. Der Melder
            # konnte die Warnung ohne ihn nicht auf ein Gerät zurückführen.
            beispiele = ", ".join(nie_empfangen[:6])
            if len(nie_empfangen) > 6:
                beispiele += f" (+{len(nie_empfangen) - 6} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{len(nie_empfangen)} MQTT-Topic(s) erwartet, nie empfangen",
                details=(
                    "Der Subscriber läuft, aber für diese Topics liefert noch "
                    "keine Quelle Daten. Mögliche Ursachen: Publisher-Automation "
                    "(HA-Automation, ioBroker, Node-RED) noch nicht eingerichtet, "
                    "oder Investitions-IDs nach Re-Import nicht in der Automation "
                    "nachgezogen. Wenn du keine Live-Daten via MQTT brauchst, "
                    "kannst du MQTT-Inbound unter Daten → Einrichtung → "
                    "MQTT-Inbound deaktivieren. "
                    f"Betroffen: {beispiele}"
                ),
                link="/einstellungen/mqtt-inbound",
            ))

        if veraltet:
            beispiele = "; ".join(
                f"{t} (vor {a} min)" for t, a in veraltet[:5]
            )
            if len(veraltet) > 5:
                beispiele += f" (+{len(veraltet) - 5} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{len(veraltet)} MQTT-Topic(s) mit veralteten Werten",
                details=(
                    "Live-Topics sollten innerhalb 2 min, Energy-Topics innerhalb "
                    "10 min aktualisiert werden. Mögliche Ursache: "
                    "Publisher-Automation läuft nicht oder hat ihre Quelle "
                    "verloren. Wenn du keine Live-Daten via MQTT brauchst, "
                    "kannst du MQTT-Inbound unter Daten → Einrichtung → "
                    "MQTT-Inbound deaktivieren. "
                    f"Betroffen: {beispiele}"
                ),
                link="/einstellungen/mqtt-inbound",
            ))

        if not nie_empfangen and not veraltet:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=f"Alle {len(erwartet)} erwarteten MQTT-Topics aktuell empfangen",
            ))

        return ergebnisse

    # ─── Sensor-Mapping LTS-Verfügbarkeit (v3.24.1) ──────────────────────

    async def _check_sensor_mapping_lts(self, anlage: Anlage) -> list[CheckErgebnis]:
        """
        Prüft ob die im Sensor-Mapping verwendeten Sensoren in HA's Long-Term-
        Statistics-Tabelle landen.

        Sensoren ohne `state_class` fehlen dort und liefern für kWh-basierte
        Monatswerte und Vollbackfill keine Daten — der Energy-Filter im Wizard
        wurde in v3.24.1 aufgeweicht (damit z.B. Nibe-Roh-Counter ohne Metadaten
        für WP-Starts auswählbar sind), und damit kann ein Nutzer auch
        versehentlich einen LTS-losen Sensor in ein kWh-Feld eintragen. Diese
        Kategorie macht das sichtbar:

        - **kWh-Feld + nicht in LTS** → WARNING (Korrektur-Werkzeuge wirken nicht)
        - **Counter-Feld + nicht in LTS** → WARNING (Korrektur-Werkzeuge wirken nicht;
          jeder Aussetzer permanent verloren, einzelne Stunden können fehlen)
        - **kWh-/Counter-Feld + in LTS, aber OHNE Summen-Spalte** → WARNING
          (`state_class: measurement` statt `total_increasing`; die Aggregation
          kann daraus keine Deltas bilden — s. u.)
        - **kWh-Feld + LTS-Eintrag mit Summen-Spalte** → OK

        Geprüft werden nur **Energie-Felder** (Einheit kWh/Wh/MWh) und die
        reinen Counter. Preis-, km-, Anzahl- und Temperatur-Slots sind hier
        nicht zuständig — s. Filter unten.

        Der dritte Fall ist der stille: HA legt auch für `measurement` eine
        `statistics_meta`-Zeile an, nur ohne `sum`. Wer bloß die Existenz prüft,
        meldet OK, während `get_hourly_kwh_deltas_for_day` jede Zeile dieses
        Sensors überspringt und Cockpit/Tag auf 0 bleibt. Betroffen ist vor allem
        die Familie, bei der `state_class` von Hand nachgetragen wird
        (bitShake/Tasmota — Tasmota-Discovery setzt gar keins, HA-Core #104305);
        `measurement` ist dort der bekannte Griff daneben.
        Forum simon42 #89667/44.
        """
        from backend.core.field_definitions import (
            FELD_EINHEITEN, FELD_LABELS, basis_feld_key, einheit_klasse,
        )
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.sensor_snapshot_service import KUMULATIVE_COUNTER_FELDER

        kat = CheckKategorie.SENSOR_MAPPING_LTS
        ergebnisse: list[CheckErgebnis] = []

        mapping = anlage.sensor_mapping or {}
        if not mapping:
            return []

        # Sensor-IDs sammeln, getrennt nach kWh-Feld und Counter-Feld.
        # Live-Mappings (basis.live, inv.live) werden ignoriert — die lesen
        # `state` direkt und brauchen kein LTS.
        counter_fields = {f for fs in KUMULATIVE_COUNTER_FELDER.values() for f in fs}
        kwh_sensors: list[tuple[str, str]] = []      # (sensor_id, label)
        counter_sensors: list[tuple[str, str]] = []

        basis = mapping.get("basis") or {}
        # Nur kumulative kWh-Counter prüfen. `strompreis` ist ct/kWh bzw. €/kWh
        # (Live-Preis-Sensor) und braucht kein state_class — wird nur live
        # gelesen, nicht aus LTS aggregiert.
        # (Joachim-PN 2026-05-04: grid_price_monitor wurde fälschlich als
        # fehlender kWh-Sensor gemeldet.)
        #
        # `pv_gesamt` gehört seit 2026-07-29 dazu (N131/M1): der Zählerstand ist
        # über `BASIS_ENERGY_TOPICS` zuordenbar und wird von
        # `aktueller_monat._ha_stats_monatswerte` als `pv_erzeugung_kwh` aus LTS
        # gelesen — ein Sammelzähler ohne state_class liefert dort still nichts.
        # BEWUSST OHNE GUARD „liest die Rechnung ihn diesen Monat überhaupt?":
        # das wäre die Laufzeitfrage, dieser Check beantwortet die
        # Konfigurationsfrage („diesem Feld ist ein Sensor zugeordnet — hat er
        # Langzeitstatistik?"). Die Antwort darauf ist in JEDER Präzedenz-Stufe
        # von `pv_verteilung.resolve_pv_je_modul` dieselbe, und die Stufe kann
        # jeden Monat wechseln (fällt ein String-Sensor aus, ist der
        # Sammelzähler plötzlich die einzige Quelle). Ein Check, der die
        # Präzedenz nachbaut, wäre die zweite Wahrheit neben ihr.
        for key in ("einspeisung", "netzbezug", "pv_gesamt"):
            m = basis.get(key)
            if isinstance(m, dict) and m.get("strategie") == "sensor" and m.get("sensor_id"):
                kwh_sensors.append((m["sensor_id"], f"Basis: {FELD_LABELS.get(key, key)}"))

        # Investitions-Bezeichnungen für aussagekräftige Labels + Lifecycle-Status
        inv_label = {str(i.id): i.bezeichnung for i in (anlage.investitionen or [])}
        heute = date.today()
        inv_aktiv = {str(i.id): i.ist_aktiv_an(heute) for i in (anlage.investitionen or [])}

        for inv_id, inv_data in (mapping.get("investitionen") or {}).items():
            if not isinstance(inv_data, dict):
                continue
            # Stillgelegte Investition überspringen (#613 MartyBr, #608-Folge):
            # ein stillgelegter WR braucht seinen alten kWh-Sensor nicht mehr in
            # HA-LTS. Den #608-Sweep (a209f084/1b95ffd8) hat dieser Pfad verpasst,
            # weil er das sensor_mapping-Dict iteriert statt anlage.investitionen.
            # Default True: verwaiste Mapping-Einträge (Inv. gelöscht) weiter melden.
            if not inv_aktiv.get(str(inv_id), True):
                continue
            felder = inv_data.get("felder") or {}
            for feld, m in felder.items():
                if not isinstance(m, dict) or m.get("strategie") != "sensor":
                    continue
                sid = m.get("sensor_id")
                if not sid:
                    continue
                # N-310 — **der Feld-Key kann eine Innengeräte-Adresse tragen**
                # (`betriebsart_strom_kuehlen_kwh-3`, #263). Jede Namens-Tabelle
                # hier führt ihn nur unter dem Basis-Namen; ohne Auflösung
                # liefert `FELD_EINHEITEN` `None`, der Sensor fällt aus dem
                # Energie-Filter und wird **nie** auf `has_sum` geprüft — still,
                # mit einem Label, das den Rohschlüssel zeigt. Wortgleiche
                # Warnung steht seit #263 an `snapshot/keys._is_kumulativ_feld`;
                # `field_definitions` nennt `FELD_EINHEITEN` dort namentlich als
                # Leser, der auflösen muss. Dieser hier tat es als einziger nicht.
                basis = basis_feld_key(feld)
                lbl = (
                    f"{inv_label.get(str(inv_id), f'Inv. {inv_id}')}: "
                    f"{FELD_LABELS.get(basis, feld)}"
                )
                if basis in counter_fields:
                    counter_sensors.append((sid, lbl))
                elif einheit_klasse(FELD_EINHEITEN.get(basis)) == "energie":
                    kwh_sensors.append((sid, lbl))
                # sonst: kein Energie-Feld — dieser Check ist nicht zuständig.
                # Die Basis-Ebene zieht diese Grenze seit 2026-05-04 per Whitelist
                # (s. o., Joachim-PN `grid_price_monitor`); auf Investitionsebene
                # fehlte sie, und der Ø-Ladepreis eines Speichers (ct/kWh) wurde
                # als „kWh-Sensor ohne Summen-Spalte" gemeldet — ein Preis-Sensor
                # mit `state_class: measurement` ist aber korrekt konfiguriert und
                # hat naturgemäß kein `has_sum` (Forum simon42 #89667/54, MartyBr).
                # Betrifft ebenso `km_gefahren`, `ladevorgaenge`,
                # `ladung_extern_euro`, `soc`, `warmwasser_temperatur_c`.
                #
                # Einheiten-Filter statt `KUMULATIVE_ZAEHLER_FELDER`: dort fehlen
                # echte kWh-Felder (`ladung_extern_kwh`, `v2h_entladung_kwh`,
                # `verbrauch_sonstig_kwh`), die Zähler-Whitelist würde Deckung
                # VERLIEREN. Gleiche Mechanik wie `_check_sensor_mapping_einheit`.
                # Wächter gegen fehlende `FELD_EINHEITEN`-Einträge:
                # test_daten_checker_lts_summen_spalte.py::test_alle_zaehlerfelder_bleiben_gedeckt

        if not kwh_sensors and not counter_sensors:
            return []

        ha_service = get_ha_statistics_service()
        if not ha_service.is_available:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="HA Long-Term-Statistics nicht erreichbar — Mapping-Prüfung übersprungen",
            ))
            return ergebnisse

        # Summen-fähig statt nur „vorhanden" (2026-07-29): ein Sensor mit
        # `state_class: measurement` steht in `statistics_meta`, hat aber kein
        # `has_sum` — `get_hourly_kwh_deltas_for_day` überspringt ihn dann
        # vollständig. Vorher meldete dieser Check dafür OK, während Cockpit/Tag
        # auf 0 stand (Forum simon42 #89667/44).
        all_sids = list({s for s, _ in kwh_sensors} | {s for s, _ in counter_sensors})
        _mit_sum, ohne_sum_sids, missing_sids = await asyncio.to_thread(
            ha_service.filter_summen_faehige_sensor_ids, all_sids
        )
        missing = set(missing_sids)
        ohne_sum = set(ohne_sum_sids)

        kwh_missing = [(sid, lbl) for sid, lbl in kwh_sensors if sid in missing]
        counter_missing = [(sid, lbl) for sid, lbl in counter_sensors if sid in missing]
        kwh_ohne_sum = [(sid, lbl) for sid, lbl in kwh_sensors if sid in ohne_sum]
        counter_ohne_sum = [(sid, lbl) for sid, lbl in counter_sensors if sid in ohne_sum]

        if kwh_missing:
            beispiele = "; ".join(f"{lbl} ({sid})" for sid, lbl in kwh_missing[:5])
            if len(kwh_missing) > 5:
                beispiele += f" (+{len(kwh_missing) - 5} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{len(kwh_missing)} kWh-Sensor(en) nicht in HA-Long-Term-Statistics",
                details=(
                    "Diese Sensoren haben kein state_class — typisch bei Modbus-"
                    "Roh-Werten oder Hersteller-Integrationen ohne Metadaten. "
                    "Folgen: die Korrektur-Werkzeuge in der Datenverwaltung "
                    "(Vollbackfill, Verlauf nachrechnen, Per-Tag-Reaggregation) "
                    "wirken auf diese Sensoren nicht — sie lesen alle aus HA's "
                    "LTS. Jeder Aussetzer ist permanent verloren, vergangene "
                    "Monate bleiben leer. Lösung: in Home Assistant unter "
                    "Einstellungen → Geräte & Dienste → Helfer einen "
                    "Verbrauchszähler auf diesen Sensor anlegen, Zurücksetzen "
                    "„nie“ (ohne Zyklus) — der Helfer bringt die nötigen "
                    "Statistik-Angaben mit und behält seinen Namen auch nach "
                    "einem Gerätetausch. Seine Historie beginnt bei null: "
                    "vergangene Monate sammelt Home Assistant nicht nach. "
                    "Alternativ einen anderen Sensor mit "
                    "state_class=total_increasing wählen (oder, wer die YAML "
                    "ohnehin pflegt, state_class per customize ergänzen). "
                    f"Betroffen: {beispiele}"
                ),
                link=LINK_DATENQUELLEN,
            ))

        if counter_missing:
            beispiele = "; ".join(f"{lbl} ({sid})" for sid, lbl in counter_missing[:5])
            if len(counter_missing) > 5:
                beispiele += f" (+{len(counter_missing) - 5} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{len(counter_missing)} Counter-Sensor(en) ohne state_class — "
                    "Korrektur-Werkzeuge wirken nicht"
                ),
                details=(
                    "Counter-Felder wie WP-Kompressor-Starts werden über den stündlichen "
                    "Snapshot-Service erfasst. Ohne state_class fehlt aber HA-Long-Term-"
                    "Statistics: damit greifen die Korrektur-Werkzeuge in der "
                    "Datenverwaltung nicht (Vollbackfill, Verlauf nachrechnen, "
                    "Per-Tag-Reaggregation lesen alle aus HA's LTS). Jeder Aussetzer "
                    "(HA-/EEDC-Neustart, Polling-Hänger) ist permanent verloren; im "
                    "Normalbetrieb fehlt zusätzlich häufig die letzte Stunde des Tages "
                    "(23–24 Uhr). Empfohlen: in Home Assistant unter Einstellungen → "
                    "Geräte & Dienste → Helfer einen Verbrauchszähler auf diesen "
                    "Sensor anlegen, Zurücksetzen „nie“ (ohne Zyklus) — dann laufen "
                    "alle Reparatur-Werkzeuge auf diesem Zähler. Die Historie des "
                    "Helfers beginnt bei null; Vergangenes sammelt Home Assistant "
                    "nicht nach. Wer die YAML ohnehin pflegt, kann state_class "
                    "stattdessen per customize ergänzen. "
                    f"Betroffen: {beispiele}"
                ),
                link=LINK_DATENQUELLEN,
            ))

        if kwh_ohne_sum:
            beispiele = "; ".join(f"{lbl} ({sid})" for sid, lbl in kwh_ohne_sum[:5])
            if len(kwh_ohne_sum) > 5:
                beispiele += f" (+{len(kwh_ohne_sum) - 5} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{len(kwh_ohne_sum)} kWh-Sensor(en) ohne Summen-Spalte — "
                    "Tages- und Stundenwerte bleiben leer"
                ),
                details=(
                    "Diese Sensoren stehen in HA's Langzeitstatistik, aber ohne "
                    "Summen-Spalte: ihr `state_class` ist `measurement` statt "
                    "`total_increasing`. Damit führt HA nur Mittel-/Min-/Max-Werte "
                    "und keine Zählerstände — eedc kann daraus keine Stunden- und "
                    "Tagesdeltas bilden. Die Live-Ansicht ist NICHT betroffen, sie "
                    "rechnet aus den Watt-Sensoren; deshalb sieht man dort Werte, "
                    "während Cockpit → Tag und die Stundenwerte auf 0 stehen. "
                    "Lösung: in Home Assistant unter Einstellungen → Geräte & "
                    "Dienste → Helfer einen Verbrauchszähler auf diesen Sensor "
                    "anlegen, Zurücksetzen „nie“ (ohne Zyklus) — er führt die "
                    "Summen-Spalte, die eedc braucht, und der zugeordnete Sensor "
                    "wird dann der Helfer. Seine Historie beginnt bei null: "
                    "Vergangenes sammelt Home Assistant nicht nach. Wer die YAML "
                    "ohnehin pflegt, kann stattdessen `state_class: "
                    "total_increasing` per `customize` setzen (HA-Neustart nötig). "
                    "Danach die Tage über die Reparatur-Werkbank neu berechnen — "
                    "HA sammelt die Summenwerte erst ab der Umstellung. "
                    f"Betroffen: {beispiele}"
                ),
                link=LINK_DATENQUELLEN,
            ))

        if counter_ohne_sum:
            beispiele = "; ".join(f"{lbl} ({sid})" for sid, lbl in counter_ohne_sum[:5])
            if len(counter_ohne_sum) > 5:
                beispiele += f" (+{len(counter_ohne_sum) - 5} weitere)"
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=(
                    f"{len(counter_ohne_sum)} Counter-Sensor(en) ohne Summen-Spalte — "
                    "Korrektur-Werkzeuge wirken nicht"
                ),
                details=(
                    "Der laufende Betrieb erfasst diese Counter über den stündlichen "
                    "Snapshot-Service und funktioniert. Ihr `state_class` ist aber "
                    "`measurement` statt `total_increasing`, deshalb führt HA für sie "
                    "keine Summen-Spalte — und alle Korrektur-Werkzeuge lesen genau "
                    "die (Vollbackfill, Verlauf nachrechnen, Per-Tag-Reaggregation). "
                    "Ein Aussetzer lässt sich damit nicht nachholen. Empfohlen: in "
                    "Home Assistant unter Einstellungen → Geräte & Dienste → Helfer "
                    "einen Verbrauchszähler auf diesen Sensor anlegen, Zurücksetzen "
                    "„nie“ (ohne Zyklus) — er führt die Summen-Spalte, die die "
                    "Korrektur-Werkzeuge brauchen, und behält seinen Namen auch nach "
                    "einem Gerätetausch; zugeordnet wird dann der Helfer. Seine "
                    "Historie beginnt bei null: Vergangenes sammelt Home Assistant "
                    "nicht nach. Wer die YAML ohnehin pflegt, kann stattdessen "
                    "`state_class: total_increasing` per `customize` setzen "
                    "(HA-Neustart nötig). "
                    f"Betroffen: {beispiele}"
                ),
                link=LINK_DATENQUELLEN,
            ))

        if kwh_sensors and not kwh_missing and not kwh_ohne_sum:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK,
                meldung=(
                    f"Alle {len(kwh_sensors)} kWh-Sensor(en) im Mapping in "
                    "HA-Long-Term-Statistics verfügbar"
                ),
            ))

        return ergebnisse

    # ─── Sensor-Mapping-Einheit: Leistung ↔ Energie (#674 + #200) ────────

    async def _check_sensor_mapping_einheit(self, anlage: Anlage) -> list[CheckErgebnis]:
        """
        Prüft alle gemappten Slots auf Leistung↔Energie-Verwechslung — in BEIDE
        Richtungen, einheiten-getrieben aus `FELD_EINHEITEN` (SoT field_definitions).

        - **Energie-Sensor (kWh) in einem Leistungs-Slot (W)** → ERROR (#674,
          mameier1234): der Zählerstand wird als Momentanleistung gelesen
          (7130 kWh → 7130 W), der live als Residual berechnete Hausverbrauch
          klemmt auf 0. PV/Batterie und der kWh-Tagesverlauf bleiben korrekt,
          deshalb sehen die kWh-Monatschecks (#3/#6) den Fall nicht.
        - **Leistungssensor (W) in einem kWh-Slot** → WARNING (#200): die
          state-Differenz ist eine Leistungs-, keine Energie-Differenz; die
          Laufzeit fällt auf Trapez-Integration zurück (degradiert, nicht null).

        Nur diese eindeutig gefährliche Verwechslung; SoC (%)/Temperatur (°C)/
        Preis (ct/kWh)/km bleiben bewusst außen vor (legitime Einheiten-Varianten
        → Fehlalarm-Risiko). Deterministisch + zeitunabhängig (HA-Einheit statt
        Live-Werte).
        """
        from backend.core.field_definitions import (
            FELD_EINHEITEN, FELD_LABELS, basis_feld_key, einheit_klasse as _klasse,
        )
        from backend.services.live_sensor_config import extract_live_config

        kat = CheckKategorie.SENSOR_MAPPING_EINHEIT

        mapping = anlage.sensor_mapping or {}
        inv_label = {str(i.id): i.bezeichnung for i in (anlage.investitionen or [])}

        # Slots sammeln: (entity_id, label, erwartete_klasse) — nur Slots, deren
        # erwartete Einheit (aus FELD_EINHEITEN) Leistung oder Energie ist.
        slots: list[tuple[str, str, str]] = []

        def _add(eid: Optional[str], schluessel: str, label: str) -> None:
            # N-310 — Basis-Key-Auflösung, siehe die ausführliche Begründung in
            # `_check_sensor_mapping_lts`. Hier wiegt sie schwerer als dort: zu
            # den acht kWh-Feldern je Innengerät kommt `leistung_w`, und damit
            # fiel der **#674-ERROR** (kWh-Zähler im Leistungs-Slot ⇒ der live
            # als Residual gerechnete Hausverbrauch klemmt auf 0) für jedes
            # Innengerät aus der Prüfung.
            #
            # ⚠ Gegengeprüft, dass das keinen Fehlalarm baut: `betriebsmodus-3`
            # löst zu `betriebsmodus` auf, dessen Einheit `''` ist ⇒ `_klasse`
            # liefert `None` ⇒ der Zustands-Slot bleibt draußen. Das war vorher
            # nur ZUFÄLLIG richtig (der rohe Key stand gar nicht in der Tabelle);
            # jetzt ist es die Regel aus `ZUSTAND_LIVE_FELDER`, die es trägt.
            erwartet = _klasse(FELD_EINHEITEN.get(basis_feld_key(schluessel)))
            if eid and erwartet:
                slots.append((eid, label, erwartet))

        # Live-Slots (basis + investitionen)
        basis_live, inv_live_map, _, _ = extract_live_config(anlage)
        for key, eid in basis_live.items():
            _add(eid, key, f"{FELD_LABELS.get(basis_feld_key(key), key)} (Live)")
        for inv_id, live in inv_live_map.items():
            name = inv_label.get(str(inv_id), f"Inv. {inv_id}")
            for key, eid in live.items():
                _add(eid, key, f"{name}: {FELD_LABELS.get(basis_feld_key(key), key)} (Live)")

        # Basis-Zähler (mapping["basis"][mapping_key] = {strategie, sensor_id})
        for mk, m in (mapping.get("basis") or {}).items():
            if isinstance(m, dict) and m.get("strategie") == "sensor" and m.get("sensor_id"):
                _add(m["sensor_id"], mk, FELD_LABELS.get(mk, mk))

        # Investitions-Felder (kWh-Zähler etc.)
        for inv_id, inv_data in (mapping.get("investitionen") or {}).items():
            if not isinstance(inv_data, dict):
                continue
            name = inv_label.get(str(inv_id), f"Inv. {inv_id}")
            for feld, m in (inv_data.get("felder") or {}).items():
                if isinstance(m, dict) and m.get("strategie") == "sensor" and m.get("sensor_id"):
                    _add(m["sensor_id"], feld,
                         f"{name}: {FELD_LABELS.get(basis_feld_key(feld), feld)}")

        if not slots:
            return []

        from backend.services.ha_state_service import get_ha_state_service
        units = await get_ha_state_service().get_sensor_units([eid for eid, _, _ in slots])
        if not units:
            # HA nicht erreichbar (Standalone) → Einheit unbekannt, stiller Skip.
            return []

        ergebnisse: list[CheckErgebnis] = []
        for eid, label, erwartet in slots:
            actual_unit = units.get(eid)
            actual = _klasse(actual_unit)
            # Nur die klare Leistung↔Energie-Verwechslung melden. Unbekannte/
            # andere Einheiten (None) erzeugen keinen Fehlalarm.
            if actual is None or actual == erwartet:
                continue

            if erwartet == "leistung":  # Energie-Sensor im Leistungs-Slot (#674)
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.ERROR,
                    meldung=(
                        f"Leistungs-Slot „{label}\" trägt einen Energie-Sensor "
                        f"(Einheit {actual_unit})"
                    ),
                    details=(
                        "In einen Leistungs-Slot gehört ein Leistungssensor (W/kW), "
                        "kein kWh-Zähler. Der Zählerstand wird sonst als Momentan"
                        "leistung gelesen (z. B. 7130 kWh → 7130 W) — im Live-"
                        "Energiefluss kippt dadurch der berechnete Hausverbrauch "
                        f"(klemmt auf 0). Bitte für „{label}\" einen Leistungssensor "
                        f"(W/kW) wählen; aktuell: {eid}."
                    ),
                    link=LINK_DATENQUELLEN,
                ))
            else:  # erwartet == "energie": Leistungssensor im kWh-Slot (#200)
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=(
                        f"Energie-Slot „{label}\" trägt einen Leistungssensor "
                        f"(Einheit {actual_unit})"
                    ),
                    details=(
                        "In einen Energie-Slot gehört ein kumulativer kWh-Zähler, "
                        "kein Leistungssensor (W/kW). Aus einem Leistungssensor "
                        "lässt sich die Energie nur näherungsweise per Integration "
                        "ableiten (ungenauer, anfällig für Lücken). Bitte für "
                        f"„{label}\" einen kWh-Zähler wählen; aktuell: {eid}."
                    ),
                    link=LINK_DATENQUELLEN,
                ))

        return ergebnisse
