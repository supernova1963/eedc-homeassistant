"""
Daten-Checker — Provenance-Konflikte, Datenquelle-Status & -Drift
(`DatenquelleChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.core.berechnungen import (
    PV_KOMPONENTEN_PREFIXE,
    summe_pv_bkw_kwh as _summe_pv_bkw_kwh,
)

from .kategorien import (
    CheckErgebnis, CheckKategorie, CheckSeverity, LINK_DATENQUELLEN, _quelle_label,
)

logger = logging.getLogger(__name__)


class DatenquelleChecks:
    """Prüfungen zu Quellen-Konflikten und HA-LTS-Datenquellen-Pfad."""

    async def _check_provenance_conflicts(
        self, anlage: Anlage, days: int = 30,
    ) -> list[CheckErgebnis]:
        """Prüft das Audit-Log auf Felder mit ≥ 2 distinct sources im Zeitraum.

        Hinweis-Charakter (Memory-Linie feedback_daten_checker_kein_akzeptiert.md):
        kein Quittier-Knopf, nur Diagnose. Der Resolver hat den angezeigten Wert
        bereits aus der höchstprioren Quelle gewählt — für den Anwender gibt es
        nichts zu tun, daher INFO und kein Aktions-Link (#305 Befund 1). Eine
        echte „Quellen-Konflikte auflösen"-Aktion bleibt eine eigene spätere
        Etappe (P4); erst wenn sie existiert, darf hier wieder ein Link stehen.
        """
        from sqlalchemy import func

        kat = CheckKategorie.PROVENANCE_CONFLICT.value
        cutoff = datetime.now() - timedelta(days=days)

        # Investition-IDs der Anlage für InvestitionMonatsdaten-Joins
        inv_ids = [inv.id for inv in anlage.investitionen]

        # row_pk_json als Substring-Filter:
        #   - monatsdaten / tages_zusammenfassung / tages_energie_profil:
        #     '{"anlage_id": <id>, ...}'
        #   - investition_monatsdaten: '{"investition_id": <id>, ...}' für jede
        #     Investition der Anlage
        anlage_needle = f'"anlage_id": {anlage.id}'
        inv_needles = [f'"investition_id": {iid}' for iid in inv_ids]

        from sqlalchemy import or_
        row_filter = DataProvenanceLog.row_pk_json.contains(anlage_needle)
        for needle in inv_needles:
            row_filter = or_(row_filter, DataProvenanceLog.row_pk_json.contains(needle))

        stmt = (
            select(
                DataProvenanceLog.table_name,
                DataProvenanceLog.row_pk_json,
                DataProvenanceLog.field_name,
                func.count(func.distinct(DataProvenanceLog.source)).label("n_sources"),
                func.group_concat(DataProvenanceLog.source.distinct()).label("sources"),
            )
            .where(
                DataProvenanceLog.written_at >= cutoff,
                row_filter,
            )
            .group_by(
                DataProvenanceLog.table_name,
                DataProvenanceLog.row_pk_json,
                DataProvenanceLog.field_name,
            )
            .having(func.count(func.distinct(DataProvenanceLog.source)) >= 2)
        )
        result = await self.db.execute(stmt)
        konflikte = result.all()

        if not konflikte:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung=f"Keine Quellen-Konflikte in den letzten {days} Tagen",
            )]

        # Detail-Zeile nennt künftig „Feld X im Zeitraum Y (Quelle ↔ Quelle)"
        # statt nur „1× in monatsdaten" — Safi105 #301: der Anwender will den
        # konkreten Treffer sehen, um in Einstellungen → Daten gezielt
        # nachzusehen. row_pk_json trägt den Natural Key (jahr/monat bzw. datum),
        # group_concat(sources) die beteiligten Schreiber.
        inv_label = {
            inv.id: f"{inv.bezeichnung}" for inv in anlage.investitionen
        }

        def _zeitraum(pk_raw: str) -> str:
            try:
                pk = json.loads(pk_raw)
            except (TypeError, ValueError):
                return ""
            if "datum" in pk:
                stunde = pk.get("stunde")
                return f"{pk['datum']} {stunde:02d}:00" if stunde is not None else str(pk["datum"])
            if "jahr" in pk and "monat" in pk:
                return f"{pk['jahr']}-{pk['monat']:02d}"
            return ""

        def _kontext(table_name: str, pk_raw: str) -> str:
            # investition_monatsdaten: Komponenten-Name statt anonymer Tabelle
            if table_name == "investition_monatsdaten":
                try:
                    iid = json.loads(pk_raw).get("investition_id")
                except (TypeError, ValueError):
                    iid = None
                return inv_label.get(iid, "Komponente")
            return "Monatsdaten" if table_name == "monatsdaten" else "Tagesdaten"

        details_lines = []
        for table_name, pk_raw, field_name, _n, sources in konflikte:
            zeitraum = _zeitraum(pk_raw)
            quellen = " ↔ ".join(
                _quelle_label(s) for s in sorted((sources or "").split(",")) if s
            )
            teile = [_kontext(table_name, pk_raw), field_name]
            if zeitraum:
                teile.append(zeitraum)
            zeile = " · ".join(teile)
            if quellen:
                zeile += f" ({quellen})"
            details_lines.append(zeile)

        # Bei vielen Treffern Liste kürzen, damit der Hinweis lesbar bleibt.
        MAX_ZEILEN = 15
        if len(details_lines) > MAX_ZEILEN:
            rest = len(details_lines) - MAX_ZEILEN
            details_lines = details_lines[:MAX_ZEILEN] + [f"… und {rest} weitere"]
        details = "\n".join(details_lines)

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO.value,
            meldung=(
                f"{len(konflikte)} Felder hatten in den letzten {days} Tagen "
                f"Werte aus mehreren Quellen — der Resolver hat automatisch die "
                f"höchstpriore Quelle gewählt. Reiner Nachvollziehbarkeits-"
                f"Hinweis, kein Handlungsbedarf."
            ),
            details=details,
        )]

    async def _check_datenquelle_status(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Etappe 4 v3.31.0: zeigt, welcher Datenquellen-Pfad für die Energie-
        Aggregate aktiv ist.

        Drei Konstellationen:
          a) HA-LTS aktiv (HA-Add-on-Modus, sensor_mapping vorhanden) →
             externe Statistics-Quelle, höchste Genauigkeit (Σ Hourly == Daily)
          b) Snapshot-Fallback (HA-LTS verfügbar, aber Aggregat-Provenance
             noch auf älteren Quellen) → typischer Zustand nach Upgrade,
             heilt sich mit nächstem Auto-Vollbackfill
          c) Standalone-Modus (kein HA-LTS) → MQTT-Sensor-Snapshots,
             eingeschränkt durch Sub-Stunden-Boundary-Effekte

        Memory-Linie `feedback_grenze_externe_daten_diagnose.md`: ehrliche
        Diagnose, keine Beschönigung. Memory `project_etappe_4_ha_lts_sot.md`.
        """
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.models.tages_energie_profil import TagesZusammenfassung

        kat = CheckKategorie.DATENQUELLE_STATUS.value
        ha_svc = get_ha_statistics_service()
        ha_lts_verfuegbar = ha_svc.is_available

        # Letzte TagesZusammenfassung-Provenance prüfen (Hint, welcher Pfad
        # tatsächlich beim letzten Aggregator-Lauf griff).
        # stunden_verfuegbar > 0 schließt leere Stub-Rows aus: Ein Monats-
        # abschluss für den laufenden Monat legt via backfill_range auch für
        # noch nicht stattgefundene Tage TagesZusammenfassung-Rows an
        # (stunden_verfuegbar=0, Source 'auto:monatsabschluss'). Ohne diesen
        # Filter griffe datum.desc() so eine Zukunfts-Row und der Hint zeigte
        # bis zum Verstreichen dieser Tage einen Fehlalarm.
        result = await self.db.execute(
            select(TagesZusammenfassung)
            .where(TagesZusammenfassung.anlage_id == anlage.id)
            .where(TagesZusammenfassung.stunden_verfuegbar > 0)
            .order_by(TagesZusammenfassung.datum.desc())
            .limit(1)
        )
        tz = result.scalar_one_or_none()

        letzte_source: Optional[str] = None
        if tz and tz.source_provenance:
            # source_provenance ist {field_name: {source, writer, at}} —
            # nehme die häufigste Source als Repräsentant
            sources = [
                entry.get("source", "") for entry in tz.source_provenance.values()
                if isinstance(entry, dict)
            ]
            if sources:
                # Häufigste Source als Repräsentant
                from collections import Counter
                letzte_source = Counter(sources).most_common(1)[0][0]

        if ha_lts_verfuegbar and letzte_source in (
            "external:ha_statistics:hourly", "external:ha_statistics:daily",
        ):
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="HA-Statistics als Source-of-Truth aktiv",
                details=(
                    "Energie-Aggregate werden direkt aus den HA-Long-Term-"
                    "Statistics gelesen. Stunden- und Tageswerte sind konsistent "
                    "(Σ Stundenwerte = Tagessumme per Konstruktion)."
                ),
            )]
        if ha_lts_verfuegbar and tz is None:
            # Es gibt ÜBERHAUPT keine aggregierte Tageszeile. Bis 2026-08-05
            # fiel dieser Fall in den Zweig darunter und erzeugte den Satz
            # „die TagesZusammenfassung vom **?** wurde aber noch aus
            # **unbekannt** geschrieben" — eine Behauptung über eine Zeile, die
            # es nicht gibt, und ein Fehlerbild, das jeder frisch eingerichtete
            # Anwender in der ersten Stunde zu sehen bekam. Der Zustand ist
            # nicht „falsche Quelle", sondern „noch nichts da"; ein Anwender,
            # der nach der Quelle sucht, sucht am falschen Ort.
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung="Noch keine Tageswerte aggregiert",
                details=(
                    "HA-Statistics ist erreichbar, aber es liegt noch keine "
                    "Tageszusammenfassung mit Stundenwerten vor. Direkt nach "
                    "der Einrichtung ist das normal — die Aggregation läuft "
                    "stündlich, die ersten Werte stehen also innerhalb einer "
                    "Stunde bereit. Bleibt es dabei, fehlt meist die Zuordnung "
                    "der kWh-Zähler (Einstellungen → Datenquellen — es müssen "
                    "die kWh-Zeilen belegt sein, nicht nur die Watt-Zeilen). "
                    "Zurückliegende Tage holt „Lücken aus HA-LTS nachfüllen“ "
                    "in der Reparatur-Werkbank."
                ),
                link=LINK_DATENQUELLEN,
            )]
        if ha_lts_verfuegbar:
            # HA verfügbar, aber Aggregate aus älterem Pfad — typisch nach
            # Upgrade auf v3.31.0 vor erstem Reaggregations-Lauf. Ab hier ist
            # `tz` garantiert vorhanden (der Zweig darüber fängt None ab).
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung="HA-Statistics-Pfad bereit, Aggregate aus älterer Quelle",
                details=(
                    "HA-Statistics ist verfügbar, die Tageszusammenfassung "
                    f"vom {tz.datum.isoformat()} wurde aber noch "
                    f"aus '{letzte_source or 'unbekannt'}' geschrieben. "
                    "Sobald diese Tage neu aus HA-Statistics aggregiert "
                    "werden (nächster Monatsabschluss oder Tag-Reparatur), "
                    "gilt HA-LTS als Source-of-Truth."
                ),
                link="/einstellungen/energieprofil",
            )]
        # HA-LTS nicht verfügbar → Standalone-Modus (Docker ohne HA-Verbindung
        # oder fehlende HA-Recorder-URL)
        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO.value,
            meldung="Standalone-Modus aktiv (kein HA-LTS)",
            details=(
                "Keine HA-Long-Term-Statistics verfügbar — Energie-Aggregate "
                "werden aus 5-Minuten-Sensor-Snapshots berechnet. Im HA-Add-on-"
                "Modus wäre eine höhere Konsistenz möglich (Σ Stunden = Tag)."
            ),
        )]

    async def _check_datenquelle_drift(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Etappe 6 v3.31.1: Per-Tag-PV-Tagessumme der TagesZusammenfassung
        gegen HA-LTS-Daily-Read der letzten 90 Tage vergleichen. Bei Drift
        über Schwelle pro Tag ein Eintrag mit Inline-Reparatur-Action.

        Hintergrund: Etappe 4 hat den Aggregator auf HA-LTS umgestellt,
        bestehende Tage stehen aber noch auf alten Mix-Source-Werten
        (additive Migration, #190). Dieses Werkzeug macht die Drift
        sichtbar und bietet pro Tag einen Reparatur-Pfad — getrennt von
        Sammel-Aktionen in der Reparatur-Werkbank, damit Massen-
        Reparaturen aktiv gewählt werden müssen.

        Schwelle: |Δ| ≥ 2 kWh UND |Δ|/max ≥ 5 % gleichzeitig. Sortierung
        nach |Δ| desc, Limit 20 Einträge. Vergleicht NUR PV-Tagessumme
        (Σ pv_* + bkw_* Keys), nicht andere Kategorien — fokussierte
        Liste, andere Größen koppeln meistens mit.

        #311: Verglichen wird ausschließlich über PV-/BKW-Keys, die der
        LTS-Read für den Tag liefern konnte. Keys, die der LTS-Pfad nicht
        lesen kann (Sensor ohne `has_sum`, nicht in statistics_meta,
        Stunden-Lücke), werden NICHT als „HA = 0" gewertet — sonst entsteht
        Phantom-Drift (-100 %) plus ein destruktiver Reparatur-Knopf, der
        korrekte Snapshot-Werte überschreiben würde. Der Aggregator fällt im
        selben Fall auf den Snapshot-Pfad zurück; der Check tut es analog,
        indem er nicht-lesbare Keys aus dem Vergleich ausnimmt.

        Memory-Linien:
          - feedback_kein_grosser_heiler_knopf.md (keine Sammel-Reparatur
            in der Liste — Verweis auf Reparatur-Werkbank)
          - feedback_daten_checker_kein_akzeptiert.md (keine Quittier-
            Aktion — Eintrag verschwindet nur durch tatsächliche Reparatur)
          - feedback_reparatur_statt_loesch_features.md (Reparatur-Pfad
            ist der einzige Pfad)
          - feedback_grenze_externe_daten_diagnose.md („nicht gelesen"
            ≠ „= 0" — #311 Phantom-Drift)
        """
        from datetime import date, timedelta as _td
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from backend.models.investition import Investition as _Inv

        kat = CheckKategorie.DATENQUELLE_DRIFT.value

        ha_svc = get_ha_statistics_service()
        if not ha_svc.is_available:
            return []  # Standalone-Modus: kein Vergleich möglich

        bis = date.today() - _td(days=1)
        von = bis - _td(days=89)  # 90 Tage inkl. bis

        tz_result = await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )
        tz_list = list(tz_result.scalars().all())
        if not tz_list:
            return []  # Keine Daten — frische Anlage, kein Vergleich nötig

        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

        drift_pro_tag: list[tuple[date, float, float]] = []  # (datum, eedc, ha)
        for tz in tz_list:
            try:
                ha_komp = await get_komponenten_tageskwh_lts(
                    anlage, invs_by_id, tz.datum,
                )
            except Exception as e:
                logger.debug(
                    f"Drift-Check Anlage {anlage.id} {tz.datum}: "
                    f"HA-LTS-Read fehlgeschlagen: {type(e).__name__}: {e}"
                )
                continue

            # #311 JanKgh: Nur PV-/BKW-Keys vergleichen, die der LTS-Read
            # tatsächlich liefern konnte. Fehlt ein Key im LTS-Read (Sensor
            # mit has_sum=0 / nicht in statistics_meta / Stunden-Lücke), ist
            # das „nicht gelesen", NICHT „= 0". Sonst meldet der Check Phantom-
            # Drift (-100 %) und bietet einen destruktiven „Tag reparieren"-Knopf
            # an, der die korrekten (Snapshot-)Werte mit 0 überschreiben würde.
            # Der Aggregator selbst fällt in genau diesem Fall auf den Snapshot-
            # Pfad zurück (energie_profil/aggregator.py) — der Drift-Check darf
            # die fehlende LTS-Lesbarkeit nicht als Abweichung interpretieren.
            tz_komp = tz.komponenten_kwh or {}
            vergleich_keys = {
                k for k, v in ha_komp.items()
                if isinstance(v, (int, float))
                and any(k.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)
            }
            if not vergleich_keys:
                continue  # LTS konnte keinen PV-Sensor lesen → kein Vergleich

            # Tagessumme NUR über die LTS-lesbaren Keys — auf beiden Seiten
            # identische Key-Basis (analog _summe_pv_bkw_kwh: nur positiv).
            eedc_kwh = sum(
                v for k in vergleich_keys
                if isinstance((v := tz_komp.get(k)), (int, float)) and v > 0
            )
            ha_kwh = sum(
                v for k in vergleich_keys
                if isinstance((v := ha_komp.get(k)), (int, float)) and v > 0
            )

            if eedc_kwh <= 0 and ha_kwh <= 0:
                continue  # Nichts zu vergleichen (z. B. Inbetriebnahme-Monat)

            delta = abs(eedc_kwh - ha_kwh)
            maxv = max(eedc_kwh, ha_kwh)
            rel = delta / maxv if maxv > 0 else 0.0

            if delta >= 2.0 and rel >= 0.05:
                drift_pro_tag.append((tz.datum, eedc_kwh, ha_kwh))

        if not drift_pro_tag:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Keine signifikanten Abweichungen zu HA-Statistics (letzte 90 Tage)",
                details=(
                    "Geprüft wurde die PV-Tagessumme gegen die HA-Statistics-Tagessumme. "
                    "Schwelle: ≥ 2 kWh UND ≥ 5 % Abweichung gleichzeitig — kleinere "
                    "Boundary-Drift wird bewusst ignoriert."
                ),
            )]

        # Sortierung nach |Δ| desc, max 20 Einträge
        drift_pro_tag.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
        gekuerzt = drift_pro_tag[:20]
        rest = len(drift_pro_tag) - len(gekuerzt)

        ergebnisse: list[CheckErgebnis] = []
        for datum_, eedc, ha in gekuerzt:
            delta_signed = ha - eedc
            rel_signed = (delta_signed / max(eedc, ha)) * 100 if max(eedc, ha) > 0 else 0.0
            details = (
                f"Dein eedc-Wert für {datum_.isoformat()} ist {eedc:.2f} kWh PV-Erzeugung. "
                f"Die HA-Statistics liefert für denselben Tag {ha:.2f} kWh. "
                f"Mit „Tag reparieren“ schreibt eedc den Wert aus HA-Statistics "
                f"in deine Tages-Zusammenfassung."
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"{datum_.isoformat()}: PV {eedc:.1f} → HA {ha:.1f} kWh "
                    f"(Δ {delta_signed:+.1f} kWh, {rel_signed:+.1f}%)"
                ),
                details=details,
                link=f"/einstellungen/energieprofil?datum={datum_.isoformat()}",
                action_kind="reaggregate_day",
                action_params={"anlage_id": anlage.id, "datum": datum_.isoformat()},
                action_label="Tag reparieren",
            ))

        if rest > 0:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=f"… plus {rest} weitere Tag(e) mit Drift",
                details=(
                    f"Anzeige auf die 20 Tage mit größtem |Δ| begrenzt. "
                    f"Für alle Drift-Tage auf einmal: Einstellungen → Daten → "
                    f"Energieprofil → Reparatur-Werkbank → Bereich neu aggregieren "
                    f"(Datumsbereich aktiv wählen, keine automatische Sammel-Aktion)."
                ),
            ))

        return ergebnisse

    async def _check_leere_tage_trotz_zaehler(
        self, anlage: Anlage,
    ) -> list[CheckErgebnis]:
        """Nachlauf v4.0.3: „Zähler zugeordnet, Tageswerte fehlen".

        Nach dem v4.0.3-Fix (Zuordnung der Datenquellen-Fläche landet wieder im
        ``sensor_mapping``) ist die Zuordnung heil — die **Historie** bleibt
        leer, denn für die Tage davor hat nie ein Aggregator-Lauf stattgefunden.
        Der Daten-Checker meldete dafür „Zähler-Abdeckung: OK": technisch
        richtig (der Zähler IST zugeordnet), für den Anwender irreführend. Drei
        Melder sind genau hier hängengeblieben, und die Energieprofil-Daten
        stehen in keiner Exportdatei — nach einem Restore können sie
        ausschließlich aus HA-LTS kommen.

        **Erkennung per Daten-Signal** (Muster von
        ``_check_batterie_vorzeichen_historie``): ein frischer HA-LTS-Read gegen
        die gespeicherte ``TagesZusammenfassung``. Gemeldet wird ein Tag, wenn
        HA für einen zugeordneten Zähler einen nennenswerten Tageswert liefert
        und die gespeicherte Zeile für denselben Key leer oder 0 ist.

        Leitplanken:

        - **#311:** fehlende LTS-Lesbarkeit ist „nicht gelesen", nie „= 0".
          Verglichen wird ausschließlich über Keys, die der LTS-Read wirklich
          geliefert hat — sonst meldete der Check Phantom-Lücken und böte einen
          Knopf an, der korrekte Snapshot-Werte mit 0 überschreibt.
        - **Kein Dauer-Nörgeln** (``feedback_daten_checker_kein_akzeptiert``):
          gemeldet wird nur, solange HA-LTS den Wert überhaupt hergibt. Reicht
          die Lücke weiter zurück als die HA-Historie, ist sie kein Befund,
          sondern eine Tatsache — und die Meldung sagt genau das.
        - **Kein zweiter Turm:** PV/BKW auf einer **vorhandenen** Tageszeile
          gehört ``_check_datenquelle_drift`` (dort „PV 0,0 → HA 30,0 kWh" mit
          demselben Reparatur-Knopf). Hier zählen solche Keys nur, wenn die
          Tageszeile ganz fehlt — dann ist der Drift-Check blind.
        - **Speicher-Keys bleiben außen vor:** ``batterie_*`` ist ein Netto und
          darf legitim ~0 sein; das Vorzeichen-/Historien-Thema hat mit
          ``_check_batterie_vorzeichen_historie`` seinen eigenen Punkt.
        - **Reichweite benennen:** die Tagesreparatur heilt Tag und Stunden,
          **nicht** die Monatswerte — dafür der Statistik-Import.

        Aktion: ``reaggregate_range`` über das jüngste
        ``REAGGREGATE_RANGE_MAX_DAYS``-Fenster plus Einzeltag-Knöpfe —
        user-getriggert, nie als Start-Migration
        (``feedback_migration_startup_kein_http``,
        ``feedback_kein_grosser_heiler_knopf``).

        Nur HA-LTS-Modus: im Standalone-Betrieb fehlt die unabhängige Referenz.
        """
        from datetime import date, timedelta as _td
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
        from backend.services.snapshot.komponenten_beitraege import (
            erwartete_komponenten_keys, komponenten_key_label,
        )
        from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from backend.models.investition import Investition as _Inv

        kat = CheckKategorie.TAGESWERTE_FEHLEN.value

        ha_svc = get_ha_statistics_service()
        if not ha_svc.is_available:
            return []  # Standalone: keine unabhängige Referenz

        sensor_mapping = anlage.sensor_mapping or {}

        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

        bis = date.today() - _td(days=1)  # heute ist unvollständig
        von = bis - _td(days=89)
        if anlage.installationsdatum:
            # Vor der Inbetriebnahme hat eedc keinen Anspruch auf Tageswerte —
            # die Basiszähler existierten in HA womöglich lange vorher
            # (feedback_anschaffungsdatum_grenze).
            von = max(von, anlage.installationsdatum)
        if von > bis:
            return []

        tz_result = await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )
        tz_by_datum = {tz.datum: tz for tz in tz_result.scalars().all()}

        def _erwartet_am_tag(tag: date) -> set[str]:
            """Welche Keys verspricht die Zuordnung für GENAU diesen Tag?

            Dieselbe Normalisierung, die auch der Aggregator benutzt — keine
            zweite Feld-Liste daneben. **Pro Tag**, weil `aggregate_day` seine
            Investitionen per `aktiv_am_tag(datum)` lädt: für eine an diesem
            Tag noch nicht angeschaffte, bereits stillgelegte oder auf
            `aktiv=False` gesetzte Komponente schreibt der Lauf nichts. Bis
            v4.0.6 stand die Menge einmal für alle 90 Tage — der Check meldete
            solche Tage als Lücke und bot „Tag reparieren" an, der Lauf
            antwortete HTTP 200 und schrieb nichts, die Meldung blieb stehen
            (N-57, dietmar1968, Forum simon42 #89667/83).

            Speicher-Netto (`batterie_*`) bleibt draußen: darf legitim ~0 sein
            und hat mit `_check_batterie_vorzeichen_historie` seinen eigenen
            Punkt.
            """
            return {
                k for k in erwartete_komponenten_keys(sensor_mapping, invs_by_id, tag)
                if not k.startswith("batterie_")
            }

        # Vorfilter aus der DB — teuer ist nur der LTS-Read. Eine gesunde
        # Anlage kommt so ganz ohne HA-Abfrage aus.
        kandidaten: list[tuple[date, set[str]]] = []
        etwas_versprochen = False
        for d in (bis - _td(days=i) for i in range((bis - von).days + 1)):
            erwartete_keys = _erwartet_am_tag(d)
            if not erwartete_keys:
                # An diesem Tag war keine zugeordnete Komponente aktiv → nichts
                # versprochen, also auch keine Lücke.
                continue
            etwas_versprochen = True
            tz = tz_by_datum.get(d)
            if tz is None:
                # Zeile fehlt ganz → auch PV zählt, der Drift-Check sieht sie nicht.
                pruef_keys = set(erwartete_keys)
                gespeichert: dict = {}
            else:
                # Vorhandene Zeile: PV/BKW gehört dem Drift-Check.
                pruef_keys = {
                    k for k in erwartete_keys
                    if not any(k.startswith(p) for p in PV_KOMPONENTEN_PREFIXE)
                }
                gespeichert = tz.komponenten_kwh or {}
            leer = {
                k for k in pruef_keys
                if not isinstance(gespeichert.get(k), (int, float))
                or gespeichert.get(k) <= 0
            }
            if leer:
                kandidaten.append((d, leer))

        if not etwas_versprochen:
            # Kein kWh-Zähler zugeordnet — oder keine zugeordnete Komponente war
            # im Fenster überhaupt aktiv. Beides verspricht nichts, also gibt es
            # auch nichts zu bestätigen.
            return []

        if not kandidaten:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Alle Tage mit zugeordnetem Zähler tragen Werte (letzte 90 Tage)",
                details=(
                    "Für jeden zugeordneten kWh-Zähler steht in der gespeicherten "
                    "Tages-Zusammenfassung ein Wert. Tage, an denen die Zuordnung "
                    "zwar steht, aber nie aggregiert wurde, würden hier mit einem "
                    "Reparatur-Knopf erscheinen."
                ),
            )]

        # LTS-Reads deckeln — ohne stilles Abschneiden (die Meldung nennt den Rest).
        MAX_LTS_READS = 45
        gepruefte = kandidaten[:MAX_LTS_READS]
        ungeprueft = len(kandidaten) - len(gepruefte)

        # (datum, {key: ha_kwh})
        befunde: list[tuple[date, dict[str, float]]] = []
        SCHWELLE_KWH = 1.0
        for datum_, leere_keys in gepruefte:
            try:
                ha_komp = await get_komponenten_tageskwh_lts(
                    anlage, invs_by_id, datum_,
                )
            except Exception as e:
                logger.debug(
                    f"Leere-Tage-Check Anlage {anlage.id} {datum_}: "
                    f"HA-LTS-Read fehlgeschlagen: {type(e).__name__}: {e}"
                )
                continue
            # #311: nur Keys, die der LTS-Read WIRKLICH geliefert hat.
            fehlend = {
                k: v for k in leere_keys
                if isinstance((v := ha_komp.get(k)), (int, float)) and v >= SCHWELLE_KWH
            }
            if fehlend:
                befunde.append((datum_, fehlend))

        if not befunde:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Keine reparierbaren Tages-Lücken gefunden (letzte 90 Tage)",
                details=(
                    f"{len(kandidaten)} Tag(e) tragen für einen zugeordneten Zähler "
                    f"keinen Wert — die HA-Langzeitstatistik liefert für diese Tage "
                    f"aber ebenfalls nichts. eedc reicht nur so weit zurück wie HA "
                    f"selbst; solche Lücken sind keine Fehlfunktion, sondern lassen "
                    f"sich nicht mehr füllen."
                ),
            )]

        befunde.sort(key=lambda x: x[0])
        aeltester, neuester = befunde[0][0], befunde[-1][0]

        # Kann die Reparatur überhaupt etwas holen? `aggregate_day` steigt ohne
        # Leistungs-Zuordnung (`basis.live` / `inv.live`) und ohne MQTT-Energie
        # sofort aus (`energie_profil/aggregator.py:143-168`) — dann liefert der
        # Bereichs-Lauf `erfolgreich: 0, keine_daten: n` bei HTTP 200. Am
        # 2026-07-30 E2E gemessen. Ein Knopf, der garantiert nichts holen kann,
        # ist schlimmer als keiner (der Anwender sucht den Fehler bei sich),
        # deshalb wird er hier gar nicht angeboten und die Meldung sagt, was
        # fehlt. Dieselbe Bedingung wie im Aggregator, nicht eine zweite —
        # seit v4.0.10 auch buchstäblich: `ermittle_aggregations_quelle` ist der
        # geteilte Ort, vorher stand hier eine wortgleiche Kopie.
        from backend.services.energie_profil.aggregations_quelle import (
            ermittle_aggregations_quelle,
        )
        reparatur_moeglich = (
            await ermittle_aggregations_quelle(self.db, anlage, aeltester)
        ).vorhanden

        # Bereichs-Knopf auf das jüngste erlaubte Fenster begrenzen; ältere Tage
        # bleiben für einen zweiten Lauf stehen (Cap mehrfach anbieten statt
        # still abschneiden).
        range_von = max(aeltester, neuester - _td(days=REAGGREGATE_RANGE_MAX_DAYS - 1))
        rest_aelter = sum(1 for dt, _ in befunde if dt < range_von)

        def _key_label(key: str) -> str:
            # Geteilt mit der Reparatur-Rückmeldung (N-58) — dieselbe Komponente
            # darf nicht in zwei Sichten verschieden heißen.
            _praefix, _, inv_id = key.rpartition("_")
            return komponenten_key_label(key, invs_by_id.get(inv_id))

        betroffene_keys = sorted({k for _dt, f in befunde for k in f})
        keys_text = ", ".join(_key_label(k) for k in betroffene_keys)

        ergebnisse: list[CheckErgebnis] = []

        summen_details = (
            f"{len(befunde)} Tag(e) zwischen {aeltester.isoformat()} und "
            f"{neuester.isoformat()} tragen keinen Wert für: {keys_text}. Die "
            f"HA-Langzeitstatistik hat für dieselben Tage Werte — die Zuordnung "
            f"stand damals nur noch nicht, deshalb hat nie ein Lauf sie "
            f"aufgeschrieben."
        )
        if reparatur_moeglich:
            summen_details += (
                f" „Zeitraum neu aggregieren“ holt {range_von.isoformat()} bis "
                f"{neuester.isoformat()} aus HA-Statistics nach "
                f"(max. {REAGGREGATE_RANGE_MAX_DAYS} Tage/Lauf)."
            )
        else:
            summen_details += (
                " Nachrechnen ist hier allerdings NICHT möglich: der Tages-Lauf "
                "braucht zusätzlich eine Leistungs-Zuordnung (W), und dieser "
                "Anlage ist keine zugeordnet. Der Zählerstand allein genügt ihm "
                "nicht. Deshalb steht hier bewusst kein Knopf — er würde "
                "durchlaufen und nichts schreiben. Zuerst unter Einstellungen → "
                "Datenquellen einen Leistungssensor zuordnen (z. B. „Netz-"
                "Leistung“), danach erscheint die Reparatur hier."
            )
        if rest_aelter > 0:
            summen_details += (
                f" {rest_aelter} ältere(r) Tag(e) liegen außerhalb des Fensters — "
                f"nach dem Lauf erneut prüfen oder einzeln reparieren."
            )
        if ungeprueft > 0:
            summen_details += (
                f" Weitere {ungeprueft} Tag(e) wurden noch nicht gegen HA geprüft "
                f"(max. {MAX_LTS_READS} Abfragen pro Durchlauf) — nach dem Lauf "
                f"erneut prüfen."
            )
        summen_details += (
            " Reichweite: die Tagesreparatur heilt Tages- und Stundenwerte, "
            "NICHT die Monatswerte. Für abgeschlossene Monate anschließend "
            "Einstellungen → Integration → Statistik-Import: „Vorschau laden“ — "
            "bereits belegte Monate stehen dort unter „Konflikte“ und sind zum "
            "Überschreiben vorausgewählt, also vor dem Import einmal durchsehen."
        )

        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(befunde)} Tag(e) ohne Werte trotz zugeordnetem Zähler "
                f"({aeltester.isoformat()} … {neuester.isoformat()})"
            ),
            details=summen_details,
            link=(
                "/einstellungen/energieprofil" if reparatur_moeglich
                else LINK_DATENQUELLEN
            ),
            action_kind="reaggregate_range" if reparatur_moeglich else None,
            action_params={
                "anlage_id": anlage.id,
                "von": range_von.isoformat(),
                "bis": neuester.isoformat(),
            } if reparatur_moeglich else None,
            action_label="Zeitraum neu aggregieren" if reparatur_moeglich else None,
        ))

        if not reparatur_moeglich:
            # Ohne Reparatur-Pfad keine Einzeltag-Zeilen: 15 Knöpfe, die alle
            # nichts holen können, sind fünfzehnmal derselbe falsche Eindruck.
            return ergebnisse

        MAX_EINZEL = 15
        for datum_, fehlend in sorted(befunde, key=lambda x: x[0], reverse=True)[:MAX_EINZEL]:
            teile = ", ".join(
                f"{_key_label(k)} {v:.1f} kWh" for k, v in sorted(fehlend.items())
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=f"{datum_.isoformat()}: keine Tageswerte, HA hat {teile}",
                details=(
                    "Einzelnen Tag aus HA-Statistics nachaggregieren — schreibt "
                    "Tages- und Stundenwerte, nicht die Monatswerte."
                ),
                link=f"/einstellungen/energieprofil?datum={datum_.isoformat()}",
                action_kind="reaggregate_day",
                action_params={"anlage_id": anlage.id, "datum": datum_.isoformat()},
                action_label="Tag reparieren",
            ))
        if len(befunde) > MAX_EINZEL:
            rest = len(befunde) - MAX_EINZEL
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"… plus {rest} weitere(r) Tag(e) — am besten per "
                    f"„Zeitraum neu aggregieren“."
                ),
            ))

        return ergebnisse

    async def _check_batterie_vorzeichen_historie(
        self, anlage: Anlage,
    ) -> list[CheckErgebnis]:
        """v3.45.9: Erkennt Alt-Tage mit vertauschtem Batterie-Vorzeichen.

        Vor dem Vorzeichen-Fix (v3.45.7/8, SoT ``batterie_kw_spalte``:
        **ENTLADUNG positiv**) schrieb der Aggregator das Batterie-Netto in
        umgekehrter Richtung. Bestehende Tage tragen den Fehler bis zur
        Neu-Aggregation weiter — die Live-Ansicht ist NICHT betroffen (eigener
        Pfad), nur die gespeicherte Tages-/Energieprofil-Historie.

        Erkennung per **Daten-Signal** (kein Zeitstempel-Heuristik): das
        gespeicherte Tages-Netto (``summe_batterie_netto_kwh`` über
        ``TagesZusammenfassung.komponenten_kwh``) wird gegen einen **frischen**
        HA-LTS-Read mit aktueller Konvention verglichen. Zeigen beide Seiten
        bei beidseitig nennenswertem Betrag in **entgegengesetzte** Richtung,
        ist der Tag mit alter Logik aggregiert. Reine Betrags-Drift (Achse-2,
        gleiche Richtung) wird hier bewusst NICHT geflaggt — das ist ein
        getrenntes, diagnose-only Thema.

        Aktion: manueller Re-Aggregations-Trigger — ein Summen-Eintrag mit
        Bereichs-Knopf (Bulk, max. ``REAGGREGATE_RANGE_MAX_DAYS`` Tage/Lauf)
        plus Einzeltag-Knöpfe (bestehender ``reaggregate_day``-Pfad). NIE als
        Start-Migration (Memory ``feedback_migration_startup_kein_http`` — der
        v3.45.7-Migrations-Versuch hat das Add-on in eine Neustart-Schleife
        gebracht): Pull statt Push, user-getriggert, nicht beim Boot.

        Nur HA-LTS-Modus — im Standalone-Betrieb fehlt die unabhängige
        Referenz für den Vorzeichen-Vergleich (analog ``_check_datenquelle_drift``).
        """
        from datetime import date, timedelta as _td
        from backend.services.ha_statistics_service import get_ha_statistics_service
        from backend.services.snapshot.lts_aggregator import get_komponenten_tageskwh_lts
        from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS
        from backend.core.berechnungen import summe_batterie_netto_kwh
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from backend.models.investition import Investition as _Inv

        kat = CheckKategorie.BATTERIE_VORZEICHEN_HISTORIE.value

        ha_svc = get_ha_statistics_service()
        if not ha_svc.is_available:
            return []  # Standalone: keine unabhängige Referenz für den Vergleich

        bis = date.today() - _td(days=1)
        von = bis - _td(days=89)  # 90 Tage inkl. bis

        tz_result = await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            )
        )
        tz_list = list(tz_result.scalars().all())
        if not tz_list:
            return []

        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

        # Beidseitige Mindest-Magnitude: Balance-/Rauschtage (Netto ~0 kWh)
        # raus, sonst kippt das Vorzeichen zufällig → Fehlalarm. 1 kWh ist
        # konservativ (ein realer Speicher lädt/entlädt deutlich mehr/Tag).
        SCHWELLE_KWH = 1.0
        hat_batterie = False
        konflikt_tage: list[date] = []
        for tz in tz_list:
            stored_netto = summe_batterie_netto_kwh(tz.komponenten_kwh or {})
            if abs(stored_netto) < SCHWELLE_KWH:
                continue  # kein nennenswertes gespeichertes Batterie-Netto
            hat_batterie = True
            try:
                ha_komp = await get_komponenten_tageskwh_lts(
                    anlage, invs_by_id, tz.datum,
                )
            except Exception as e:
                logger.debug(
                    f"Vorzeichen-Check Anlage {anlage.id} {tz.datum}: "
                    f"HA-LTS-Read fehlgeschlagen: {type(e).__name__}: {e}"
                )
                continue
            ha_netto = summe_batterie_netto_kwh(ha_komp)
            if abs(ha_netto) < SCHWELLE_KWH:
                continue  # HA lieferte kein nennenswertes Netto → kein Vergleich
            # Vorzeichen-Konflikt: gespeichert und frisch zeigen in andere Richtung.
            if (stored_netto > 0) != (ha_netto > 0):
                konflikt_tage.append(tz.datum)

        if not konflikt_tage:
            if not hat_batterie:
                return []  # Keine Batterie-Aktivität → Kategorie nicht zeigen
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Batterie-Vorzeichen in der Historie konsistent (letzte 90 Tage)",
                details=(
                    "Gespeichertes Batterie-Tagesnetto und frischer HA-Statistics-"
                    "Read zeigen in dieselbe Richtung (ENTLADUNG positiv). Tage, die "
                    "vor dem Vorzeichen-Fix (v3.45.7) aggregiert wurden, würden hier "
                    "mit umgekehrtem Vorzeichen erscheinen."
                ),
            )]

        konflikt_tage.sort()
        aeltester, neuester = konflikt_tage[0], konflikt_tage[-1]

        # Bereichs-Knopf: max. REAGGREGATE_RANGE_MAX_DAYS pro Lauf. Bei größerem
        # Span auf das jüngste 31-Tage-Fenster begrenzen; ältere Konflikt-Tage
        # bleiben für einen zweiten Lauf / Einzeltag-Knopf stehen.
        range_von = max(aeltester, neuester - _td(days=REAGGREGATE_RANGE_MAX_DAYS - 1))
        rest_aelter = sum(1 for d in konflikt_tage if d < range_von)

        ergebnisse: list[CheckErgebnis] = []

        # 1) Summen-Eintrag mit Bereichs-Knopf (Bulk-Reparatur).
        summen_details = (
            f"{len(konflikt_tage)} Tag(e) zwischen {aeltester.isoformat()} und "
            f"{neuester.isoformat()} wurden vor dem Vorzeichen-Fix (v3.45.7) "
            f"aggregiert und tragen das Batterie-Netto in vertauschter Richtung "
            f"(Laden/Entladen verdreht). Die Live-Ansicht ist NICHT betroffen — "
            f"nur die gespeicherte Historie. „Zeitraum neu aggregieren“ rechnet "
            f"{range_von.isoformat()} bis {neuester.isoformat()} aus HA-Statistics "
            f"neu (max. {REAGGREGATE_RANGE_MAX_DAYS} Tage/Lauf)."
        )
        if rest_aelter > 0:
            summen_details += (
                f" {rest_aelter} ältere(r) Tag(e) liegen außerhalb des Fensters — "
                f"nach dem Lauf erneut prüfen oder einzeln reparieren."
            )
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(konflikt_tage)} Tag(e) mit vertauschtem Batterie-Vorzeichen "
                f"({aeltester.isoformat()} … {neuester.isoformat()})"
            ),
            details=summen_details,
            action_kind="reaggregate_range",
            action_params={
                "anlage_id": anlage.id,
                "von": range_von.isoformat(),
                "bis": neuester.isoformat(),
            },
            action_label="Zeitraum neu aggregieren",
        ))

        # 2) Einzeltag-Einträge (bestehender reaggregate_day-Pfad) — bis 15 Tage,
        #    neueste zuerst (Datums-Listen Default absteigend, Regel 0a).
        MAX_EINZEL = 15
        for d in sorted(konflikt_tage, reverse=True)[:MAX_EINZEL]:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=f"{d.isoformat()}: Batterie-Vorzeichen vertauscht",
                details=(
                    "Einzelnen Tag neu aus HA-Statistics aggregieren — schreibt das "
                    "Batterie-Netto in der korrigierten Richtung (ENTLADUNG positiv)."
                ),
                action_kind="reaggregate_day",
                action_params={"anlage_id": anlage.id, "datum": d.isoformat()},
                action_label="Tag reparieren",
            ))
        if len(konflikt_tage) > MAX_EINZEL:
            rest = len(konflikt_tage) - MAX_EINZEL
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"… plus {rest} weitere(r) Tag(e) — am besten per "
                    f"„Zeitraum neu aggregieren“."
                ),
            ))

        return ergebnisse

    async def _check_soc_nur_ein_speicher(self, anlage: Anlage) -> list[CheckErgebnis]:
        """N-239: Mehrspeicher-Anlage, deren Historie nur EINEN Ladestand kennt.

        Bis 2026-08-12 nahm ``_get_soc_history`` den **ersten** gemappten
        SoC-Sensor mit Daten und brach ab. ``TagesEnergieProfil.soc_prozent``
        trug damit den Ladestand *eines* Geräts — welches, entschied die
        Reihenfolge im Sensor-Mapping —, während Vollzyklen, SoC-Hübe, die
        Potential-Heatmap und die Sizing-Kalibrierung ihn als anlagenweit lasen.

        **Die Erkennung braucht weder HA-Read noch Heuristik.** Die Spalte
        ``soc_je_speicher`` existiert erst seit dem Fix; ihr Fehlen auf einer
        Stunde mit Ladestand IST die Signatur eines vor dem Fix aggregierten
        Tages. Zusammen mit „≥ 2 Speicher mit gemapptem SoC-Sensor" ist das
        eindeutig — keine Schwelle, kein Ratespiel.

        **Anlagen mit einem Speicher tauchen hier nie auf**: dort war die alte
        Rechnung wertgleich mit der neuen (``anlagen_soc_prozent`` über ein
        Gerät ist dessen SoC), es gibt also nichts zu reparieren.

        Aktion wie beim Vorzeichen-Befund: manueller Re-Aggregations-Trigger,
        **nie** eine Start-Migration.
        """
        from datetime import date, timedelta as _td
        from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS
        from backend.models.investition import Investition as _Inv
        from backend.models.tages_energie_profil import TagesEnergieProfil as _TEP

        kat = CheckKategorie.SOC_NUR_EIN_SPEICHER.value

        inv_result = await self.db.execute(
            select(_Inv).where(
                _Inv.anlage_id == anlage.id,
                _Inv.typ == "speicher",
            )
        )
        speicher = list(inv_result.scalars().all())
        mapping = (anlage.sensor_mapping or {}).get("investitionen", {}) or {}
        mit_soc = [
            s for s in speicher
            if isinstance(mapping.get(str(s.id)), dict)
            and (mapping[str(s.id)].get("live") or {}).get("soc")
        ]
        if len(mit_soc) < 2:
            return []   # Ein Speicher (oder keiner mit Sensor) — nichts zu heilen.

        alt_result = await self.db.execute(
            select(_TEP.datum)
            .where(
                _TEP.anlage_id == anlage.id,
                _TEP.soc_prozent.isnot(None),
                _TEP.soc_je_speicher.is_(None),
            )
            .distinct()
        )
        alt_tage = sorted(alt_result.scalars().all())

        if not alt_tage:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung=(
                    f"Ladestand aller {len(mit_soc)} Speicher wird in der Historie "
                    f"getrennt geführt"
                ),
                details=(
                    "Der gespeicherte Anlagen-Ladestand ist das kapazitätsgewichtete "
                    "Mittel über alle Speicher; die Aufschlüsselung je Gerät steht "
                    "daneben. Tage, die vor dieser Umstellung aggregiert wurden, "
                    "würden hier auftauchen."
                ),
            )]

        aeltester, neuester = alt_tage[0], alt_tage[-1]
        range_von = max(aeltester, neuester - _td(days=REAGGREGATE_RANGE_MAX_DAYS - 1))
        rest_aelter = sum(1 for d in alt_tage if d < range_von)

        details = (
            f"Diese Anlage hat {len(mit_soc)} Speicher mit eigenem Ladestands-Sensor. "
            f"An {len(alt_tage)} Tag(en) zwischen {aeltester.isoformat()} und "
            f"{neuester.isoformat()} wurde nur der Ladestand EINES Geräts gespeichert — "
            f"welches, entschied die Reihenfolge der Zuordnung. Betroffen sind die "
            f"Vollzyklen dieser Tage, die SoC-Hübe und die Speicher-Auswertungen im "
            f"Komponenten-Hub; Erzeugung, Verbrauch und Netzbezug sind es NICHT. "
            f"„Zeitraum neu aggregieren“ rechnet {range_von.isoformat()} bis "
            f"{neuester.isoformat()} neu (max. {REAGGREGATE_RANGE_MAX_DAYS} Tage/Lauf)."
        )
        if rest_aelter > 0:
            details += (
                f" {rest_aelter} ältere(r) Tag(e) liegen außerhalb des Fensters — "
                f"nach dem Lauf erneut prüfen."
            )

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(alt_tage)} Tag(e) kennen nur den Ladestand eines von "
                f"{len(mit_soc)} Speichern ({aeltester.isoformat()} … "
                f"{neuester.isoformat()})"
            ),
            details=details,
            action_kind="reaggregate_range",
            action_params={
                "anlage_id": anlage.id,
                "von": range_von.isoformat(),
                "bis": neuester.isoformat(),
            },
            action_label="Zeitraum neu aggregieren",
        )]

    # Ein Connector, der lange nichts mehr geliefert hat, kann für den laufenden
    # Monat kein Delta bilden — nach diesen Tagen gilt das nicht mehr als
    # „gleich behoben". Kürzer wäre Rauschen: am Monatsersten fehlt der Snapshot
    # IM Monat noch bei jedem aktiven Connector, bis der Tagesabruf gelaufen ist.
    CONNECTOR_STILL_TAGE = 2

    async def _check_connector_monatswert(self, anlage: Anlage) -> list[CheckErgebnis]:
        """#360/N-73: Connector eingerichtet, aber für den laufenden Monat ist
        kein Wert ableitbar — und niemand sagt es.

        Das Connector-Delta ist die Differenz zweier Zähler-Snapshots. Fehlt
        einer davon, liefert `_calc_month_delta` `None`, `_collect_connector_data`
        gibt ein leeres Dict zurück, und die Monats-Sicht zeigt einfach eine
        Quelle weniger — ohne Log, ohne Hinweis, ohne Response-Feld. Die Route
        `GET /connector/monatswerte/…` sagt es zwar mit 404, hat aber keinen
        Aufrufer im Client; der Anwender erfährt es also nirgends.

        Zuständigkeitsgrenze (P4-Konzept §4): die Sicht beantwortet „worauf
        beruht diese Zahl" — hier steht gar keine Zahl, es gibt nichts zu
        beschriften. Der Checker beantwortet „was musst du nachtragen", und dazu
        gibt es einen Weg (Abruf anstoßen bzw. einschalten). Der Wortlaut ist
        der geprüfte 404-Text der Route, nicht neu erfunden (E5).

        Kein Connector konfiguriert ⇒ kein Befund — sonst meldete der Checker
        jedem HA-Nutzer etwas Unauflösbares.
        """
        from datetime import date
        from backend.api.routes.connector import _calc_month_delta

        config = anlage.connector_config
        if not config:
            return []

        snapshots = config.get("meter_snapshots") or {}
        heute = date.today()
        if _calc_month_delta(snapshots, heute.year, heute.month):
            return []

        # Frisch genug, um sich selbst zu heilen? Dann schweigen. Snapshot-
        # Zeitstempel sind UTC-naiv (Schreibpfad `connector.py`, Lesepfad
        # `_calc_month_delta`) — die Gegenwart muss es hier genauso sein.
        juengster = _juengster_snapshot(snapshots)
        jetzt = datetime.now(timezone.utc).replace(tzinfo=None)
        if (
            len(snapshots) >= 2
            and juengster is not None
            and (jetzt - juengster) < timedelta(days=self.CONNECTOR_STILL_TAGE)
        ):
            return []

        geraet = config.get("geraet_name") or config.get("connector_id") or "Connector"
        if len(snapshots) < 2:
            bestand = (
                f"Gespeichert ist bisher {len(snapshots)} Snapshot"
                f"{'s' if len(snapshots) != 1 else ''}."
            )
        else:
            bestand = (
                "Der jüngste Snapshot ist vom "
                f"{juengster.strftime('%d.%m.%Y') if juengster else 'unbekannten Datum'}."
            )
        weg = (
            "Der tägliche Abruf ist aktiv — mit dem nächsten Snapshot trägt der "
            "Connector den Monat wieder mit."
            if config.get("auto_fetch_enabled")
            else "Der tägliche Abruf ist ausgeschaltet; ohne ihn kommt kein "
            "weiterer Snapshot dazu."
        )
        return [CheckErgebnis(
            kategorie=CheckKategorie.DATENQUELLE_STATUS.value,
            schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"Connector „{geraet}“ liefert für "
                f"{heute.month:02d}/{heute.year} keinen Wert"
            ),
            details=(
                f"Nicht genügend Snapshots für {heute.month:02d}/{heute.year}. "
                "Mindestens ein Snapshot vor und einer nach dem Monatsbeginn "
                f"nötig. {bestand} {weg}"
            ),
            link=LINK_DATENQUELLEN,
        )]


    async def _check_zeitzone_ha(self, anlage: Anlage) -> list[CheckErgebnis]:
        """N-161: läuft eedc in derselben Zeitzone wie Home Assistant?

        Verglichen wird der **aktuelle UTC-Offset**, nicht der Zonenname —
        Wien, Zürich und Amsterdam teilen sich Berlins Offset, und ein
        Namensvergleich meldete dort einen Fehler, den es nicht gibt.

        Der Check **schweigt**, wenn keine HA-Verbindung besteht, HA nicht
        antwortet oder seine Zone unbekannt ist: ein Hinweis, den niemand
        auflösen kann, ist genau die P-6-Klasse. Die HA-Verbindung kommt aus
        `resolve_ha_connection` und deckt damit **beide** Modi ab (Supervisor
        und Remote-Token) — die N-156-Falle („liest nur den Supervisor-Token“)
        entsteht hier gar nicht erst.

        **Was er nicht kann:** bereits schief gespeicherte Tageszeilen erkennen
        oder heilen. Er misst den Zustand von jetzt.
        """
        from backend.services.ha_connection import resolve_ha_connection, HA_APP

        kat = CheckKategorie.ZEITZONE_ABWEICHUNG.value
        api_url, token, kind = await resolve_ha_connection(self.db)
        if not api_url or not token:
            return []

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{api_url}/config",
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                ha_zone = (resp.json() or {}).get("time_zone")
        except Exception as e:
            logger.debug(f"Zeitzonen-Check: HA-Konfiguration nicht lesbar: {e}")
            return []

        if not ha_zone:
            return []
        try:
            ha_offset = datetime.now(ZoneInfo(str(ha_zone))).utcoffset()
        except Exception:
            logger.debug(f"Zeitzonen-Check: unbekannte HA-Zeitzone {ha_zone!r}")
            return []

        eigen_offset = _lokaler_utc_offset()
        if ha_offset is None or eigen_offset is None or ha_offset == eigen_offset:
            return []

        stunden = (eigen_offset - ha_offset).total_seconds() / 3600
        betrag = abs(stunden)
        betrag_text = (
            f"{int(betrag)} Stunde" if betrag == 1
            else f"{int(betrag)} Stunden" if betrag == int(betrag)
            else f"{betrag:.1f} Stunden".replace(".", ",")
        )
        richtung = "vor" if stunden > 0 else "hinter"

        if kind == HA_APP:
            weg = (
                "Das Add-on übernimmt die Zeitzone beim Start von Home Assistant. "
                "Starte das Add-on einmal neu, damit es die aktuelle Einstellung "
                "übernimmt."
            )
        else:
            weg = (
                "eedc läuft in einem eigenen Container. Setze dort die "
                f"Umgebungsvariable TZ={ha_zone} (in docker-compose.yml unter "
                "environment) und starte den Container neu."
            )

        return [CheckErgebnis(
            kategorie=kat,
            schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"eedc und Home Assistant rechnen mit verschiedenen Zeitzonen "
                f"({betrag_text} Unterschied)"
            ),
            details=(
                f"Home Assistant steht auf {ha_zone} ({_offset_text(ha_offset)}), "
                f"eedc läuft {betrag_text} {richtung} dieser Zeit "
                f"({_offset_text(eigen_offset)}). Rund um Mitternacht werden "
                "Stundenwerte dadurch dem falschen Tag zugeordnet. "
                f"{weg} Bereits gespeicherte Tage ändern sich davon nicht — "
                "die lassen sich anschließend über die Datenverwaltung neu "
                "berechnen."
            ),
            link=LINK_DATENQUELLEN,
        )]


def _juengster_snapshot(snapshots: dict) -> Optional[datetime]:
    """Zeitstempel des jüngsten Snapshots (naiv, wie `_calc_month_delta`)."""
    neuster: Optional[datetime] = None
    for ts_str in snapshots:
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
        if neuster is None or ts > neuster:
            neuster = ts
    return neuster


def _lokaler_utc_offset() -> Optional[timedelta]:
    """UTC-Offset der Systemzeit, in der eedc `date.today()` auswertet.

    Eigene Funktion, weil genau das im Test gesetzt werden muss: die Alternative
    wäre, im Test die Prozess-Zeitzone umzuschalten (`time.tzset()`), was den
    gesamten Testlauf beeinflusst. Eine Stelle, ein Vertrag.
    """
    return datetime.now().astimezone().utcoffset()


def _offset_text(offset: timedelta) -> str:
    """`timedelta` → „UTC+2“ / „UTC-3:30“ (halbe Stunden kommen vor)."""
    minuten = int(offset.total_seconds() // 60)
    vz = "+" if minuten >= 0 else "-"
    minuten = abs(minuten)
    return (
        f"UTC{vz}{minuten // 60}"
        if minuten % 60 == 0
        else f"UTC{vz}{minuten // 60}:{minuten % 60:02d}"
    )
