"""
Daten-Checker — Provenance-Konflikte, Datenquelle-Status & -Drift
(`DatenquelleChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.core.berechnungen import (
    PV_KOMPONENTEN_PREFIXE,
    summe_pv_bkw_kwh as _summe_pv_bkw_kwh,
)

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity, _quelle_label


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
        if ha_lts_verfuegbar:
            # HA verfügbar, aber Aggregate aus älterem Pfad — typisch nach
            # Upgrade auf v3.31.0 vor erstem Reaggregations-Lauf
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung="HA-Statistics-Pfad bereit, Aggregate aus älterer Quelle",
                details=(
                    "HA-Statistics ist verfügbar, die TagesZusammenfassung "
                    f"vom {tz.datum.isoformat() if tz else '?'} wurde aber noch "
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
