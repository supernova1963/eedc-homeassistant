"""Daten-Checker — Tagesebene: leere Tage trotz zugeordnetem Zähler (Tages-Zusammenfassung ohne Wert).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

import logging
from sqlalchemy import select
from backend.models.anlage import Anlage
from backend.core.berechnungen import PV_KOMPONENTEN_PREFIXE
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    LINK_DATENQUELLEN,
    LINK_ENERGIEPROFIL,
)
from backend.core.zahlenformat import fmt_zahl

logger = logging.getLogger(__name__)


class TageChecks:
    """Prüfung der Tagesebene: leere Tage trotz zugeordnetem Zähler."""

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
                # N-619: am Tag aktive Investitionen — dieselbe Menge wie
                # `aggregate_day` (`aktiv_am_tag`) und wie `_erwartet_am_tag`
                # oben. Mit allen las der Check Sensoren von Geräten, die es am
                # Tag noch nicht gab, und verlor dafür den Wert eines Geräts,
                # das der Lauf schreibt (Balkonkraftwerk vor der Anschaffung
                # seiner Modul-Kinder: „Balkon" fehlte in der Liste).
                ha_komp = await get_komponenten_tageskwh_lts(
                    anlage,
                    {k: v for k, v in invs_by_id.items() if v.ist_aktiv_an(datum_)},
                    datum_,
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
                LINK_ENERGIEPROFIL if reparatur_moeglich
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
                f"{_key_label(k)} {fmt_zahl(v, 1)} kWh" for k, v in sorted(fehlend.items())
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=f"{datum_.isoformat()}: keine Tageswerte, HA hat {teile}",
                details=(
                    "Einzelnen Tag aus HA-Statistics nachaggregieren — schreibt "
                    "Tages- und Stundenwerte, nicht die Monatswerte."
                ),
                link=LINK_ENERGIEPROFIL,
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
