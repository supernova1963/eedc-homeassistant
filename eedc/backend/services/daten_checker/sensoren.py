"""
Daten-Checker — Sensor-Mapping-LTS & MQTT-Topic-Abdeckung (`SensorChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


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

        erwartet = await build_expected_topics(self.db, anlage)
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
            beispiele = ", ".join(t.split("/")[-1] for t in nie_empfangen[:6])
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
                f"{t.split('/')[-1]} (vor {a} min)" for t, a in veraltet[:5]
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
        - **kWh-Feld + LTS vorhanden** → OK
        """
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
        # gelesen, nicht aus LTS aggregiert. `pv_gesamt` ist heute nur als
        # `pv_gesamt_w` (Live-W) gemappt, ebenfalls kein LTS-Bedarf.
        # (Joachim-PN 2026-05-04: grid_price_monitor wurde fälschlich als
        # fehlender kWh-Sensor gemeldet.)
        for key in ("einspeisung", "netzbezug"):
            m = basis.get(key)
            if isinstance(m, dict) and m.get("strategie") == "sensor" and m.get("sensor_id"):
                kwh_sensors.append((m["sensor_id"], f"Basis: {key}"))

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
                lbl = f"{inv_label.get(str(inv_id), f'Inv. {inv_id}')}: {feld}"
                if feld in counter_fields:
                    counter_sensors.append((sid, lbl))
                else:
                    kwh_sensors.append((sid, lbl))

        if not kwh_sensors and not counter_sensors:
            return []

        ha_service = get_ha_statistics_service()
        if not ha_service.is_available:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO,
                meldung="HA Long-Term-Statistics nicht erreichbar — Mapping-Prüfung übersprungen",
            ))
            return ergebnisse

        all_sids = list({s for s, _ in kwh_sensors} | {s for s, _ in counter_sensors})
        valid_sids, missing_sids = await asyncio.to_thread(
            ha_service.filter_valid_sensor_ids, all_sids
        )
        missing = set(missing_sids)

        kwh_missing = [(sid, lbl) for sid, lbl in kwh_sensors if sid in missing]
        counter_missing = [(sid, lbl) for sid, lbl in counter_sensors if sid in missing]

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
                    "Monate bleiben leer. Lösung: state_class via "
                    "configuration.yaml customize ergänzen, oder einen anderen "
                    "Sensor mit state_class=total_increasing wählen. "
                    f"Betroffen: {beispiele}"
                ),
                link="/einstellungen/sensor-mapping",
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
                    "(23–24 Uhr). Empfohlen: state_class via configuration.yaml "
                    "customize ergänzen — dann laufen alle Reparatur-Werkzeuge auf "
                    f"diesem Sensor. Betroffen: {beispiele}"
                ),
                link="/einstellungen/sensor-mapping",
            ))

        if kwh_sensors and not kwh_missing:
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
        from backend.core.field_definitions import FELD_EINHEITEN, FELD_LABELS
        from backend.services.live_sensor_config import extract_live_config

        kat = CheckKategorie.SENSOR_MAPPING_EINHEIT

        _POWER = {"W", "kW", "MW"}
        _ENERGY = {"kWh", "Wh", "MWh"}

        def _klasse(unit: Optional[str]) -> Optional[str]:
            if unit in _POWER:
                return "leistung"
            if unit in _ENERGY:
                return "energie"
            return None

        mapping = anlage.sensor_mapping or {}
        inv_label = {str(i.id): i.bezeichnung for i in (anlage.investitionen or [])}

        # Slots sammeln: (entity_id, label, erwartete_klasse) — nur Slots, deren
        # erwartete Einheit (aus FELD_EINHEITEN) Leistung oder Energie ist.
        slots: list[tuple[str, str, str]] = []

        def _add(eid: Optional[str], schluessel: str, label: str) -> None:
            erwartet = _klasse(FELD_EINHEITEN.get(schluessel))
            if eid and erwartet:
                slots.append((eid, label, erwartet))

        # Live-Slots (basis + investitionen)
        basis_live, inv_live_map, _, _ = extract_live_config(anlage)
        for key, eid in basis_live.items():
            _add(eid, key, f"{FELD_LABELS.get(key, key)} (Live)")
        for inv_id, live in inv_live_map.items():
            name = inv_label.get(str(inv_id), f"Inv. {inv_id}")
            for key, eid in live.items():
                _add(eid, key, f"{name}: {FELD_LABELS.get(key, key)} (Live)")

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
                    _add(m["sensor_id"], feld, f"{name}: {FELD_LABELS.get(feld, feld)}")

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
                    link="/einstellungen/sensor-mapping",
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
                    link="/einstellungen/sensor-mapping",
                ))

        return ergebnisse
