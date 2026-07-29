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
        """Anlagen-PV je Monat über den EINEN Ladepfad ``pv_monatswerte``.

        Bis 2026-07-29 summierte diese Methode die IMD-Werte **roh** und die
        beiden Konsumenten fielen bei fehlender Summe auf
        ``Monatsdaten.pv_erzeugung_kwh`` zurück — das globale Entweder-oder,
        das `19ae5f73` in Cockpit und HA-Export bereits aufgelöst hat. In einem
        Monat mit teilweise gemessenen Strings ging damit eine **Teilsumme** in
        die Prüfung: der Performance-Ratio fiel zu niedrig aus, die SOLL/IST-
        Abweichung meldete einen Einbruch, den es nicht gab.

        Der Lifecycle-Filter (#608/#236) steckt jetzt im Service
        (``ist_aktiv_im_monat`` je Monat) statt in einer eigenen Schleife.

        Returns:
            ``{(jahr, monat): kwh}`` — **nur vollständig auflösbare Monate**.
            Bleibt ein aktives Modul ohne Wert und ohne Aggregat, fehlt der
            Monat: eine Teilsumme wäre als Anlagenerzeugung irreführend (N42).
            Die Konsumenten überspringen den Monat, statt mit 0 zu rechnen.
        """
        from backend.services.pv_monatswerte import lade_pv_je_monat, pv_summe_je_monat

        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module"]
        summen = pv_summe_je_monat(
            await lade_pv_je_monat(self.db, anlage.id, pv_module)
        )
        return {key: wert for key, wert in summen.items() if wert is not None}
