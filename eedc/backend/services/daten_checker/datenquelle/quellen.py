"""Daten-Checker — Quellen: Provenance-Konflikte, Datenquelle-Status und -Drift (IST je Komponente gegen HA-LTS).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

import logging
import json
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from backend.models.anlage import Anlage
from backend.models.data_provenance_log import DataProvenanceLog
from backend.core.berechnungen import PV_KOMPONENTEN_PREFIXE
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    LINK_DATENQUELLEN,
    LINK_ENERGIEPROFIL,
    _quelle_label,
)
from backend.core.zahlenformat import fmt_zahl, fmt_pct

logger = logging.getLogger(__name__)


class QuellenChecks:
    """Prüfungen zu Quellen-Konflikten, Datenquelle-Status und Drift gegen HA."""

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
                link=LINK_ENERGIEPROFIL,
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
        nach |Δ| desc, Limit 20 Einträge.

        **Zwei Achsen, seit N-201.** Bis dahin verglich diese Prüfung
        ausschließlich die PV-Tagessumme (Σ ``pv_*`` + ``bkw_*``) — die
        Begründung dafür lautete „andere Größen koppeln meistens mit" und war
        nie gemessen. Wallbox, E-Auto, Wärmepumpe und Sonstiges liefen damit
        **nie** gegen HA, obwohl ihre Werte ROI, Ersparnis und CO₂ tragen.

        * **PV/BKW als Summe.** Mehrere Strings messen dieselbe Sache; ihre
          Summe ist die Größe, die der Anwender kennt.
        * **Alles andere je Gerät.** Geräte sind keine gemeinsame Menge — in
          einer Summe gliche ein Plus an der Wärmepumpe ein Minus an der
          Wallbox aus, und übrig bliebe eine unauffällige Null. Ausgabe: ein
          Eintrag je Komponente mit dem größten Tag als Beleg und
          Reparatur-Ziel.

        Nicht in der zweiten Achse: ``batterie_*`` (Netto darf 0 sein, das
        Vorzeichen hat ``_check_batterie_vorzeichen_historie``) und jeder Key,
        der auf einer der beiden Seiten fehlt oder 0 ist — das ist eine Lücke
        und gehört ``_check_leere_tage_trotz_zaehler``, kein zweiter Turm.

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
        # HA-Bauform S5 (E-S5-2, Bauplan §5): die eedc-Seite über die Lesestelle — an einem Kanal-Tag der Bilanz
        # PV/BKW, Netz und Speicher aus dem HA-Spiegel bzw. den eigenen Zählerständen (wie Cockpit → Tag; der Vergleich
        # mit HA ergibt dort keinen Befund), alle übrigen Schlüssel und jeder Bestandstag aus der Tageszeile.
        from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

        komp_je_tag = await komponenten_der_tage(self.db, anlage.id, von, bis)

        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        alle_invs = list(inv_result.scalars().all())

        drift_pro_tag: list[tuple[date, float, float]] = []  # (datum, eedc, ha)
        # N-201, zweite Achse: dieselbe Frage je NICHT-PV-Komponente.
        # `{key: [(datum, eedc, ha), …]}` — je Gerät gesammelt statt je Tag,
        # weil eine Wallbox mit 30 Drift-Tagen sonst 30 Zeilen erzeugt, die
        # alle dasselbe sagen.
        drift_komponente: dict[str, list[tuple[date, float, float]]] = {}
        # Der LTS-Read ist das Teure an dieser Prüfung. Er wird EINMAL gefahren
        # und aufgehoben — die zweite Achse liest nicht noch einmal.
        ha_komp_je_tag: dict[date, dict] = {}
        for tz in tz_list:
            # N-64 — **die Aktiv-Grenze gehört PRO TAG gezogen**, sonst entsteht
            # Phantom-Drift. `get_komponenten_tageskwh_lts` liest, was das
            # `sensor_mapping` hergibt, und filtert selbst nicht; der Schreiber
            # der Gegenseite (`energie_profil.aggregator.aggregate_day`) lädt
            # seine Investitionen dagegen mit `aktiv_am_tag(datum)`. Ein an
            # diesem Tag noch nicht angeschafftes, bereits stillgelegtes oder
            # auf `aktiv=False` gesetztes PV-Modul stand damit auf der HA-Seite
            # mit voller Tagesernte und auf der eedc-Seite gar nicht — Drift
            # ≥ 2 kWh und ≥ 5 %, also eine Meldung samt „Tag reparieren".
            # Der Knopf löst sie nicht auf: der Lauf schreibt für diese
            # Komponente nichts, antwortet HTTP 200, die Meldung bleibt stehen.
            #
            # **Exakt der Befund, den der Zwilling `_check_leere_tage_trotz_
            # zaehler` seit N-57/#368 (v4.0.6) nicht mehr hat** — dort über
            # `erwartete_komponenten_keys`, ebenfalls tagesabhängig. Dass eine
            # von zwei baugleichen Funktionen den Filter trägt und die andere
            # nicht, ist die Klasse aus #236/#239: *ein Filter auf einer Schicht
            # reicht nicht, wenn zwei Pfade parallel laufen.*
            #
            # `ist_aktiv_an` ist die In-Memory-Zwillingsdefinition von
            # `utils.investition_filter.aktiv_am_tag` (dort im Docstring als
            # identisch festgehalten) — dieselbe Wahl wie beim Zwilling, aus
            # demselben Grund: die Investitionen sind bereits geladen.
            invs_by_id = {
                str(inv.id): inv for inv in alle_invs if inv.ist_aktiv_an(tz.datum)
            }
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
            ha_komp_je_tag[tz.datum] = ha_komp

            # #311 JanKgh: Nur PV-/BKW-Keys vergleichen, die der LTS-Read
            # tatsächlich liefern konnte. Fehlt ein Key im LTS-Read (Sensor
            # mit has_sum=0 / nicht in statistics_meta / Stunden-Lücke), ist
            # das „nicht gelesen", NICHT „= 0". Sonst meldet der Check Phantom-
            # Drift (-100 %) und bietet einen destruktiven „Tag reparieren"-Knopf
            # an, der die korrekten (Snapshot-)Werte mit 0 überschreiben würde.
            # Der Aggregator selbst fällt in genau diesem Fall auf den Snapshot-
            # Pfad zurück (energie_profil/aggregator.py) — der Drift-Check darf
            # die fehlende LTS-Lesbarkeit nicht als Abweichung interpretieren.
            tz_komp = komp_je_tag.get(tz.datum) or {}
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

        # ── N-201: dieselbe Prüfung für alles, was keine PV ist ──────────────
        #
        # Bis hierher vergleicht dieser Check **nur** die PV-/BKW-Tagessumme;
        # Wallbox, E-Auto, Wärmepumpe und Sonstiges liefen nie gegen HA. Das
        # war keine Aussage, sondern eine Lücke: Diese Werte tragen ROI, CO₂
        # und die Ersparnis-Rechnung, eine Drift dort ist genauso teuer.
        #
        # **Warum je Komponente und nicht als zweite Summe.** Eine Wallbox in
        # dieselbe Summe zu werfen versteckt beide: ein Plus bei der Wärmepumpe
        # gleicht ein Minus bei der Wallbox aus, und am Ende steht eine
        # unauffällige Null. Geräte sind keine gemeinsame Menge — die PV-Summe
        # ist eine, weil dort mehrere Strings *dasselbe* messen.
        #
        # **Drei Abgrenzungen, jede gegen einen bestehenden Turm:**
        # * ``batterie_*`` bleibt draußen — das Netto darf legitim ~0 sein und
        #   sein Vorzeichen hat mit ``_check_batterie_vorzeichen_historie``
        #   seinen eigenen Punkt.
        # * Beide Seiten müssen einen Wert **> 0** tragen. Ein Key, den HA
        #   liefert und die gespeicherte Zeile nicht, ist eine *Lücke* und
        #   gehört ``_check_leere_tage_trotz_zaehler`` (Kategorie
        #   TAGESWERTE_FEHLEN) — kein zweiter Turm über denselben Sachverhalt.
        # * Dieselben Schwellen wie oben (≥ 2 kWh UND ≥ 5 %). Eigene Zahlen je
        #   Gerätetyp wären erfunden, solange sie niemand gemessen hat.
        for tz in tz_list:
            ha_komp = ha_komp_je_tag.get(tz.datum)
            if not ha_komp:
                continue
            tz_komp = komp_je_tag.get(tz.datum) or {}
            for k, ha_v in ha_komp.items():
                if not isinstance(ha_v, (int, float)):
                    continue
                if any(k.startswith(p) for p in PV_KOMPONENTEN_PREFIXE):
                    continue  # oben als Summe geprüft
                if k.startswith("batterie_"):
                    continue
                eedc_v = tz_komp.get(k)
                if not isinstance(eedc_v, (int, float)):
                    continue
                if eedc_v <= 0 or ha_v <= 0:
                    continue  # Lücke, nicht Abweichung → TAGESWERTE_FEHLEN
                k_delta = abs(eedc_v - ha_v)
                k_max = max(eedc_v, ha_v)
                if k_delta >= 2.0 and (k_delta / k_max) >= 0.05:
                    drift_komponente.setdefault(k, []).append(
                        (tz.datum, float(eedc_v), float(ha_v))
                    )

        if not drift_pro_tag and not drift_komponente:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Keine signifikanten Abweichungen zu HA-Statistics (letzte 90 Tage)",
                details=(
                    "Geprüft wurde die PV-Tagessumme gegen die HA-Statistics-"
                    "Tagessumme — und zusätzlich jede andere zugeordnete "
                    "Komponente einzeln (Wallbox, E-Auto, Wärmepumpe, "
                    "Sonstiges). Schwelle je Vergleich: ≥ 2 kWh UND ≥ 5 % "
                    "Abweichung gleichzeitig — kleinere Boundary-Drift wird "
                    "bewusst ignoriert. Der Speicher steht nicht in dieser "
                    "Liste: sein Tages-Netto darf 0 sein, und sein Vorzeichen "
                    "hat eine eigene Prüfung."
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
                f"Dein eedc-Wert für {datum_.isoformat()} ist {fmt_zahl(eedc, 2)} kWh PV-Erzeugung. "
                f"Die HA-Statistics liefert für denselben Tag {fmt_zahl(ha, 2)} kWh. "
                f"Mit „Tag reparieren“ schreibt eedc den Wert aus HA-Statistics "
                f"in deine Tages-Zusammenfassung."
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"{datum_.isoformat()}: PV {fmt_zahl(eedc, 1)} → HA {fmt_zahl(ha, 1)} kWh "
                    f"(Δ {fmt_zahl(delta_signed, 1, vorzeichen=True)} kWh, "
                    f"{fmt_pct(rel_signed, 1, vorzeichen=True)})"
                ),
                details=details,
                link=LINK_ENERGIEPROFIL,
                action_kind="reaggregate_day",
                action_params={"anlage_id": anlage.id, "datum": datum_.isoformat()},
                action_label="Tag reparieren",
            ))

        # N-201: je Komponente EIN Eintrag — mit dem schlimmsten Tag als
        # Beleg und als Reparatur-Ziel. Dreißig gleichlautende Tageszeilen für
        # eine Wallbox wären keine Auskunft, sondern Rauschen.
        from backend.services.snapshot.komponenten_beitraege import komponenten_key_label

        inv_je_id = {str(inv.id): inv for inv in alle_invs}
        for key in sorted(
            drift_komponente,
            key=lambda k: max(abs(e - h) for _, e, h in drift_komponente[k]),
            reverse=True,
        ):
            tage = drift_komponente[key]
            _, _, rest_id = key.rpartition("_")
            label = komponenten_key_label(key, inv_je_id.get(rest_id))
            schlimmster = max(tage, key=lambda t: abs(t[1] - t[2]))
            datum_, eedc, ha = schlimmster
            delta_signed = ha - eedc
            rel_signed = (delta_signed / max(eedc, ha)) * 100 if max(eedc, ha) > 0 else 0.0
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"{label}: {len(tage)} Tag(e) weichen von HA-Statistics ab "
                    f"(größte Abweichung {datum_.isoformat()}: "
                    f"{fmt_zahl(eedc, 1)} → {fmt_zahl(ha, 1)} kWh, "
                    f"Δ {fmt_zahl(delta_signed, 1, vorzeichen=True)} kWh, "
                    f"{fmt_pct(rel_signed, 1, vorzeichen=True)})"
                ),
                details=(
                    f"Für diese Komponente steht in deiner Tages-Zusammenfassung "
                    f"an {len(tage)} Tag(en) ein anderer Wert als in den "
                    f"HA-Statistics. Diese Werte tragen die Wirtschaftlichkeits- "
                    f"und CO₂-Rechnung mit. „Tag reparieren“ schreibt den Tag "
                    f"{datum_.isoformat()} aus HA-Statistics neu; für alle Tage "
                    f"auf einmal: Einstellungen → Daten → Energieprofil → "
                    f"Reparatur-Werkbank."
                ),
                link=LINK_ENERGIEPROFIL,
                action_kind="reaggregate_day",
                action_params={"anlage_id": anlage.id, "datum": datum_.isoformat()},
                action_label="Tag reparieren",
                investition_id=(
                    int(rest_id) if rest_id.isdigit() else None
                ),
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
