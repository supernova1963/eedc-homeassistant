"""
Daten-Checker — geteilte Hilfsmethoden (`_CheckHelpers`-Mixin).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
Die Methoden teilen sich `self` der einen `DatenChecker`-Instanz mit allen
anderen Check-Mixins (gegenseitige Aufrufe `self._get_pv_erzeugung_map` etc.).
"""

from typing import Optional

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose


class _CheckHelpers:
    """Geteilte Lookup-/Berechnungs-Hilfen für die Check-Mixins."""

    def _calculate_performance_ratio(
        self,
        pv_erzeugung_map: dict[tuple[int, int], float],
        pvgis_monat_map: dict[int, float],
        monatsdaten: list[Monatsdaten],
    ) -> tuple[float, int]:
        """Berechnet Ø Performance Ratio (IST/PVGIS).

        Nutzt die letzten 12 Monate (falls verfügbar) für ein aktuelles Bild.
        Filtert unvollständige Monate (Ratio < 0.5, z.B. Installationsmonat).

        Returns:
            (performance_ratio, anzahl_monate) – ratio 1.0 = exakt wie Prognose
        """
        alle_ratios: list[tuple[int, int, float]] = []  # (jahr, monat, ratio)

        for md in monatsdaten:
            pvgis_soll = pvgis_monat_map.get(md.monat)
            if not pvgis_soll or pvgis_soll <= 0:
                continue

            # IST-Erzeugung bestimmen. Kein Rückfall auf
            # `md.pv_erzeugung_kwh` mehr — das Aggregat steckt seit 2026-07-29
            # bereits in der Karte (über `resolve_pv_je_modul`), und wo es fehlt,
            # fehlt es wirklich.
            pv_ist = pv_erzeugung_map.get((md.jahr, md.monat))
            if pv_ist is None or pv_ist <= 0:
                continue

            ratio = pv_ist / pvgis_soll
            # Unvollständige Monate ausfiltern (z.B. Installationsmonat)
            if ratio >= 0.5:
                alle_ratios.append((md.jahr, md.monat, ratio))

        if not alle_ratios:
            return 1.0, 0

        # Letzten 12 Monate bevorzugen (aktuelleres Bild)
        alle_ratios.sort(key=lambda x: (x[0], x[1]))
        letzte = alle_ratios[-12:] if len(alle_ratios) > 12 else alle_ratios
        ratios = [r[2] for r in letzte]

        return sum(ratios) / len(ratios), len(ratios)

    def _erwartete_monate(
        self, inv: Investition, monatsdaten: list[Monatsdaten]
    ) -> list[tuple[int, int]]:
        """Gibt sortierte Liste der Monate zurück, für die diese Investition Daten haben sollte.

        Basis: alle vorhandenen Monatsdaten-Monate ab anschaffungsdatum der Investition.
        """
        if not monatsdaten:
            return []

        start: tuple[int, int] | None = None
        if inv.anschaffungsdatum:
            start = (inv.anschaffungsdatum.year, inv.anschaffungsdatum.month)

        return sorted(
            (md.jahr, md.monat) for md in monatsdaten
            if start is None or (md.jahr, md.monat) >= start
        )

    def _get_pvgis_monat_map(self, prognose: Optional[PVGISPrognose]) -> dict[int, float]:
        """Baut Lookup Monat → erwartete kWh aus aktiver PVGIS-Prognose."""
        if not prognose or not prognose.monatswerte:
            return {}

        monat_map: dict[int, float] = {}
        for eintrag in prognose.monatswerte:
            monat = eintrag.get("monat")
            e_m = eintrag.get("e_m")
            if monat is not None and e_m is not None:
                monat_map[monat] = e_m

        return monat_map

    async def _get_pv_erzeugung_map(self, anlage: Anlage) -> dict[tuple[int, int], float]:
        """Anlagen-PV je Monat aus den Monats-Fakten (seit N-640, 08.10.2026; vorher über ``pv_monatswerte``).

        Bis 2026-07-29 summierte diese Methode die IMD-Werte **roh** und die
        beiden Konsumenten fielen bei fehlender Summe auf
        ``Monatsdaten.pv_erzeugung_kwh`` zurück — das globale Entweder-oder,
        das `19ae5f73` in Cockpit und HA-Export bereits aufgelöst hat. In einem
        Monat mit teilweise gemessenen Strings ging damit eine **Teilsumme** in
        die Prüfung: der Performance-Ratio fiel zu niedrig aus, die SOLL/IST-
        Abweichung meldete einen Einbruch, den es nicht gab.

        Der Lifecycle-Filter (#608/#236) steckt jetzt im Service
        (``ist_aktiv_im_monat`` je Monat) statt in einer eigenen Schleife.

        ⛔ **Bis 2026-09-04 fehlte hier das Balkonkraftwerk** (N-386). Der
        Typ-Filter stand auf ``pv-module`` allein — die Menge war damit eine
        andere als der **Nenner** zwei Ebenen höher, der seit F-58 ausdrücklich
        ``mit_bkw=True`` bildet, mit dem Kommentar „weil `pv_erzeugung` unten
        die anlagenweite Erzeugung ist". Genau das war sie nicht. Folge: An
        einer Anlage mit Balkonkraftwerk meldete Prüfung 3 „Einspeisung >
        PV-Erzeugung" für eine Einspeisung, die die Anlage sehr wohl erzeugt
        hatte — gemessen an einer nachgestellten Anlage (Modul 100 + BKW 50):
        Einspeisung 120 schlug an, obwohl 150 erzeugt wurden. Und die genannte
        PV-Zahl fand der Anwender in **keiner** Sicht wieder, weil die
        Auswertungstabelle über die Monats-Fakten korrekt Module **plus** BKW
        rechnet.

        ⚑ **Betroffen war nur ein Balkonkraftwerk OHNE zugeordnete PV-Module** —
        der historische Erfassungsweg. Wer seinem BKW seit v4.0.18 Module
        zuordnet (N-266), war nie betroffen: dessen Kinder sind ``pv-module``
        und lagen damit ohnehin in beiden Mengen. Vier Konstellationen
        gemessen, drei davon waren immer richtig.

        ⚠ **Der P11-Wächter konnte das nicht fangen**, und das ist kein
        Versehen: Er erkennt Σ-Stellen daran, dass sie ``PV_ERZEUGER_TYPEN``
        bilden, und sichert gegen **Doppelzählung**. Eine Stelle, die das BKW
        gar nicht erst aufnimmt, bildet die Menge nie. Deshalb läuft der Filter
        jetzt durch ``erzeuger_traeger`` — das macht die Abtretung richtig
        **und** die Stelle für den Wächter sichtbar.

        Returns:
            ``{(jahr, monat): kwh}`` — **nur vollständig auflösbare Monate**.
            Bleibt ein aktives Modul ohne Wert und ohne Aggregat, fehlt der
            Monat: eine Teilsumme wäre als Anlagenerzeugung irreführend (N42).
            Die Konsumenten überspringen den Monat, statt mit 0 zu rechnen.
        """
        # ⭐ N-640 (Frank85, Entscheid Master 08.10.2026, ADR-002/P10): die PV des Monats kommt aus den Monats-Fakten —
        # derselben Aufbereitung wie Kopf, Tabelle, Monatsleiste und Cockpit → Jahr (`inkl_nur_tageswerte`: wie die
        # Leiste). Bis dahin löste die Map selbst über `pv_monatswerte` auf (P7 auf gespeicherten Werten) und kannte den
        # Anlagenzähler der Tage nicht: Module mit gespeichertem Monatswert, ein Balkonkraftwerk ohne eigenen Zähler und
        # kein Anlagenwert ⇒ der Monat galt als nicht auflösbar und fehlte, obwohl jede Sicht ihn vollständig nennt.
        # Abtretung (P11, je Monat), Zeitfilter und Lifecycle stecken in den Fakten (N-386 bleibt erfüllt).
        # ⚠ Ohne `inkl_nur_tageswerte` (Messung 08.10.2026): mit ihm füllte die Tagesebene eine Modul-Teilsumme und
        # meldete sie als vollständig — eine Teilsumme ginge wieder in PR- und Plausibilitätsprüfungen (Matrix F07/F16,
        # `test_n626_teilsumme_und_checker.py`). N-640 Variante 1 ist ohne Tageswerte schon vollständig.
        # ⏱ Laufzeit (gemessen 08.10.2026, Demo-Kopie r28, im Lade-Kontext): vorher ≈ 4 ms (Anlage 1) bzw. 1,5 ms
        # (Anlage 2) für `pv_monatswerte`, nachher ≈ 125–145 ms je Anlage — EIN Aufruf `lade_monats_fakten`; der ganze
        # Checker-Lauf 151 → 278 ms bzw. 124 → 245 ms. Hingenommen (Entscheid Master, Nachtrag 3): ein Monat, den PR-,
        # SOLL/IST- und Plausibilitätsprüfungen still übergehen, wiegt schwerer als ≈ 0,13 s in einem Lauf auf Klick bzw.
        # im asynchron ladenden Hub-Block „Daten-Qualität". Hebel: Beobachtungsliste 08.10.2026.
        # „Auflösbar" = `pv_vollstaendig` UND eine PV-Quelle hat einen Wert — ein Monat ohne jeden PV-Wert (keine Module,
        # kein BKW-Wert, kein Anteil) ist keine gemessene 0 und bleibt draußen wie bisher (N42).
        from backend.services.monats_fakten import lade_monats_fakten

        out: dict[tuple[int, int], float] = {}
        for f in await lade_monats_fakten(self.db, anlage.id):
            e = f.erzeugung
            if not e.pv_vollstaendig:
                continue
            if e.pv_module_kwh is None and not (e.bkw_kwh or e.bkw_aus_anlagenwert_kwh):
                continue
            out[(f.jahr, f.monat)] = e.pv_kwh
        return out
