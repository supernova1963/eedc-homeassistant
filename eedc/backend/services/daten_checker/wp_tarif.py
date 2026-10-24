"""
Daten-Checker — eigener Wärmepumpen-Tarif (`WpTarifChecks`, N-767, 24.10.2026).

**Was die Meldung benennt.** eedc bewertet jede Eigenverbrauchs-kWh zum Haushaltstarif
(`finanz_aggregat.ev_preis_der_zeile`) — auch die, die eine Wärmepumpe verbraucht hat. Ohne eigenen
Wärmepumpen-Tarif ist das richtig: PV-Seite und Geräteseite rechnen mit demselben Preis, die Summe stimmt
(ADR-002/P9, BERECHNUNGEN Kasten „Der WP-Strom trägt den vollen Netztarif"). **Mit** eigenem Tarif spart die
PV-kWh in der Wärmepumpe dem Haushalt nur den WP-Tarif; die Anlagensumme ist um (Haushaltstarif − WP-Tarif) ×
PV-kWh in der WP verschoben — Vorzeichen je Messpunkt, Menge unbekannt.

⛔ **Keine Zahl wird geändert.** eedc kennt weder die Zähler-Topologie noch den PV-Anteil der Wärmepumpe; eine
Zuteilungsannahme wäre erfundene Genauigkeit (dieselbe Begründung wie `monats_fakten/tarif.py::_komponenten_preis`).
Die Meldung nennt die Grenze und ihre **Obergrenze** — WP-Strom der letzten 12 abgeschlossenen Monate ×
Tarifdifferenz —, ohne Reparatur-Knopf: es gibt nichts zu reparieren.

**Eng gefasst (P-6):** nur wenn zum Monatsersten des Prüfmonats (P8-Stichtag) ein Tarif ``verwendung =
waermepumpe`` mit eigenem Arbeitspreis gilt, der vom allgemeinen abweicht, **und** WP-Strom gemessen ist (über die
Monats-Fakten, ADR-002/P10). Verglichen wird der Stammpreis des Monats, wie ``_lade_tarif`` ihn bildet
(``tarif_des_monats``: Zeitfenster HT/NT über den gemessenen Netzbezug gewichtet, ohne Stunden die Spalte) — keine
zweite Kaskade.
"""

from datetime import date
from typing import Optional

from backend.api.routes.strompreise import resolve_tarif_for_komponente, tarife_zum_stichtag
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

#: Das Fenster der Obergrenze: die letzten zwölf abgeschlossenen Monate vor dem Prüfmonat.
FENSTER_MONATE = 12


def _monat_minus(jahr: int, monat: int, n: int) -> tuple[int, int]:
    """``(jahr, monat)`` minus ``n`` Monate."""
    idx = jahr * 12 + (monat - 1) - n
    return idx // 12, idx % 12 + 1


class WpTarifChecks:
    """N-767: eigener Wärmepumpen-Tarif — benannte Grenze der Eigenverbrauchs-Ersparnis."""

    async def _check_wp_eigener_tarif(
        self, anlage: Anlage, *, heute: Optional[date] = None,
    ) -> list[CheckErgebnis]:
        """INFO, wenn ein eigener WP-Tarif vom allgemeinen abweicht und WP-Strom gemessen ist (Modul-Docstring).

        ``heute`` ist für Proben (keine echte Uhr in Tests); die Produktion prüft den laufenden Monat.
        """
        tag = heute or date.today()
        stichtag = date(tag.year, tag.month, 1)
        zeilen = sorted(
            (t for t in anlage.strompreise if t.gilt_am(stichtag)),
            key=lambda t: t.gueltig_ab, reverse=True,
        )
        tarife = tarife_zum_stichtag(zeilen, stichtag)
        allgemein = resolve_tarif_for_komponente(tarife, "allgemein")
        wp = resolve_tarif_for_komponente(tarife, "waermepumpe")
        if allgemein is None or wp is None or wp is allgemein:
            return []
        if wp.netzbezug_arbeitspreis_cent_kwh == allgemein.netzbezug_arbeitspreis_cent_kwh:
            return []

        from backend.services.monats_fakten import lade_monats_fakten, tarif_des_monats

        tarif = await tarif_des_monats(self.db, anlage.id, stichtag.year, stichtag.month)
        wp_cent, haushalt_cent = tarif.wp_preis_cent, tarif.netzbezug_stammpreis_cent
        differenz_cent = abs(haushalt_cent - wp_cent)
        if round(differenz_cent, 2) == 0:
            return []

        fakten = await lade_monats_fakten(
            self.db, anlage.id,
            von=_monat_minus(stichtag.year, stichtag.month, FENSTER_MONATE),
            bis=_monat_minus(stichtag.year, stichtag.month, 1),
            inkl_nur_tageswerte=True,
        )
        wp_strom_kwh = sum(f.wp.strom_kwh for f in fakten)
        if wp_strom_kwh <= 0:
            return []
        obergrenze_euro = wp_strom_kwh * differenz_cent / 100.0
        return [_meldung(wp_cent, haushalt_cent, differenz_cent, wp_strom_kwh, obergrenze_euro)]


def _meldung(
    wp_cent: float, haushalt_cent: float, differenz_cent: float, wp_strom_kwh: float, obergrenze_euro: float,
) -> CheckErgebnis:
    """Das eine INFO der Anlage — ohne Link: ein „Beheben"-Knopf wäre hier ein Weg, den es nicht gibt."""
    return CheckErgebnis(
        kategorie=CheckKategorie.WP_EIGENER_TARIF.value, schwere=CheckSeverity.INFO.value,
        meldung=(
            f"Eigener Wärmepumpen-Tarif ({fmt_zahl(wp_cent, 2)} ct gegen {fmt_zahl(haushalt_cent, 2)} ct): "
            f"die Ersparnis der letzten 12 Monate kann um bis zu {fmt_zahl(obergrenze_euro, 0)} € abweichen"
        ),
        details=(
            f"eedc kennt den PV-Anteil der Wärmepumpe nicht und bewertet ihn auf der PV-Seite zum "
            f"Haushaltstarif ({fmt_zahl(haushalt_cent, 2)} ct), obwohl er dir nur den Wärmepumpen-Tarif "
            f"({fmt_zahl(wp_cent, 2)} ct) spart. Die Ersparnis der letzten 12 abgeschlossenen Monate kann "
            f"dadurch um bis zu {fmt_zahl(obergrenze_euro, 0)} € abweichen — WP-Strom dieser Monate "
            f"{fmt_zahl(wp_strom_kwh, 0)} kWh × Differenz {fmt_zahl(differenz_cent, 2)} ct. Das ist die "
            f"Obergrenze, wenn die Wärmepumpe nur PV-Strom bezogen hätte; real ist es der PV-Anteil davon. "
            f"Ob die Zahl zu hoch oder zu niedrig steht, hängt davon ab, wo Netzbezug und Einspeisung "
            f"gemessen werden. eedc ändert dafür keine Zahl — es gibt nichts zu reparieren. Erklärt im "
            f"Handbuch „Einstellungen“ (Strompreise, Verwendung Wärmepumpe) und unter „Berechnungen“, "
            f"Kasten „Der WP-Strom trägt den vollen Netztarif“."
        ),
    )
