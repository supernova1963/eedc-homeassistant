"""Daten-Checker — Speicher: Vorzeichen-Historie der Batterie-Zähler und SoC-Ablage bei mehreren Speichern (#389).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

import logging
from sqlalchemy import select
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

logger = logging.getLogger(__name__)


class SpeicherChecks:
    """Prüfungen zum Speicher: Vorzeichen-Historie und SoC-Ablage."""

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
        # HA-Bauform S5 (E-S5-2, Bauplan §5): das gespeicherte Netto über die Lesestelle — an einem Kanal-Tag der Bilanz
        # das Speicher-Netto des HA-Spiegels bzw. der eigenen Zählerstände (wie Cockpit → Tag; gegen HA kein Befund),
        # an jedem Bestandstag die Tageszeile.
        from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

        komp_je_tag = await komponenten_der_tage(self.db, anlage.id, von, bis)

        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        alle_invs = list(inv_result.scalars().all())

        # Beidseitige Mindest-Magnitude: Balance-/Rauschtage (Netto ~0 kWh)
        # raus, sonst kippt das Vorzeichen zufällig → Fehlalarm. 1 kWh ist
        # konservativ (ein realer Speicher lädt/entlädt deutlich mehr/Tag).
        SCHWELLE_KWH = 1.0
        hat_batterie = False
        konflikt_tage: list[date] = []
        for tz in tz_list:
            stored_netto = summe_batterie_netto_kwh(komp_je_tag.get(tz.datum) or {})
            if abs(stored_netto) < SCHWELLE_KWH:
                continue  # kein nennenswertes gespeichertes Batterie-Netto
            hat_batterie = True
            # N-313 — **die Aktiv-Grenze gehört PRO TAG gezogen**, wortgleich
            # zum Drift-Check darüber (N-64). `invs_by_id` entscheidet, welche
            # Sensoren `get_komponenten_tageskwh_lts` überhaupt liest; die
            # Gegenseite (`energie_profil.aggregator.aggregate_day`) lädt ihre
            # Investitionen mit `aktiv_am_tag(datum)`. Ohne den Filter steht ein
            # an diesem Tag stillgelegter, noch nicht angeschaffter oder auf
            # `aktiv=False` gesetzter Speicher nur auf der HA-Seite — und wenn
            # sein Beitrag das Netto-Vorzeichen kippt, meldet eedc einen
            # „vertauschten" Tag samt Reparatur-Knopf, den die Neu-Aggregation
            # nicht auflösen kann: sie schreibt für dieses Gerät nichts, die
            # Meldung bleibt stehen. Genau die P-6-Falle aus N-57/#368.
            #
            # ⚠ Das braucht einen **zweiten, aktiven** Speicher: bei nur einem
            # ist `stored_netto` unter der Schwelle und die Schleife bricht
            # oben ab, bevor überhaupt gelesen wird.
            invs_by_id = {
                str(inv.id): inv for inv in alle_invs if inv.ist_aktiv_an(tz.datum)
            }
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
        # N-313-Klasse, fuenfte Stelle (Radiocarbonat, simon42 T89667 #273).
        # Die Menge `mit_soc` ist die HEUTIGE Ausstattung; ein Tag braucht die,
        # die an IHM aktiv war. Ohne diesen Filter meldet jeder Speicher-Tausch
        # nach der dokumentierten Anleitung (HANDBUCH_EINSTELLUNGEN §3.2, Weg B:
        # altes Geraet stilllegen, neues mit Gesamtkapazitaet anlegen) die ganze
        # Zeit VOR dem Wechsel als defekt — beim Melder 114 Tage, an denen es
        # tatsaechlich nur einen Speicher gab.
        # ⚠ Stilllegung setzt `stilllegungsdatum`, NICHT `aktiv=False` (die
        # Anleitung verbietet den Haken ausdruecklich) — ein reiner Aktiv-Filter
        # wie bei N-313 greift hier also nicht, es braucht die Tages-Ebene.
        # ⛔ Es ist die P-6-Falle aus N-313 im Wortlaut: „Zeitraum neu
        # aggregieren" kann den zweiten Ladestand nicht erzeugen, den es nie gab
        # — der Lauf laeuft und die Meldung bleibt stehen.
        # `ist_aktiv_an` wortgleich zu :401 und :1027 (dort steht die Begruendung).
        alt_tage = sorted(
            d for d in alt_result.scalars().all()
            if sum(1 for s in mit_soc if s.ist_aktiv_an(d)) >= 2
        )

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
                    "würden hier auftauchen — Tage vor einem Geräte-Wechsel "
                    "dagegen nicht: An ihnen war nur ein Speicher aktiv, ein "
                    "zweiter Ladestand konnte gar nicht entstehen."
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
