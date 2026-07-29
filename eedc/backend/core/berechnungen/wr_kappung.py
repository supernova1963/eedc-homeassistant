"""Wechselrichter-Kappung (AC-Grenze) auf ein Prognose-Stundenprofil.

**Warum stündlich und nicht als kWp-Deckel.** Ein überbelegtes System — der
Normalfall beim Balkonkraftwerk, 3 × 420 Wp an einem 600-W-Wechselrichter
(#347, Rainer) — erreicht die AC-Grenze nur um die Mittagsspitze. Morgens und
abends liefert es weit darunter, dort begrenzt der Wechselrichter gar nicht.
Wer stattdessen die Nennleistung auf die AC-Grenze deckelte (1,26 → 0,6 kWp),
kürzte die Randstunden mit und läge systematisch zu niedrig — bei starker
Überbelegung deutlich.

**Warum je Komponente und nicht je Orientierungsgruppe.** Die Grenze gehört zum
Wechselrichter, nicht zur Himmelsrichtung. In einer Gruppe können ein
ungekappter PV-String und ein gekapptes BKW nebeneinander liegen; `min` über
die Summe wäre dann falsch (`min(a+b, grenze) ≠ min(a,∞) + min(b,grenze)`).
Die Aufteilung ist zulässig, weil die Ertragsformel in kWp **strikt linear**
ist (`solar_forecast_service.berechne_pv_ertrag`: kWp ist reiner Multiplikator,
Temperatur- und Schnee-Korrektur hängen nicht davon ab) — der Stundenwert einer
Gruppe lässt sich also verlustfrei auf ihre Mitglieder herunterrechnen.

Ohne gepflegte Grenze wird **nicht** gekappt (`None`, kein Default) — ein
Default machte aus „nicht gepflegt" eine Zahl, die wie eine Messung aussieht.
"""

from __future__ import annotations

from typing import Optional, Sequence

# (kWp der Komponente, AC-Grenze in kW oder None = unbegrenzt)
Mitglied = tuple[float, Optional[float]]


def hat_kappung(mitglieder: Sequence[Mitglied]) -> bool:
    """Trägt mindestens ein Mitglied eine AC-Grenze?

    Der Aufrufer nimmt sonst den unveränderten Pfad — ohne Grenze soll die
    Rechnung **bitgleich** zu vorher bleiben (keine zusätzliche Multiplikation,
    keine Rundungsdrift).
    """
    return any(ac is not None and ac > 0 for _kwp, ac in mitglieder)


def kappe_stunde(
    gruppen_kw: float, gruppen_kwp: float, mitglieder: Sequence[Mitglied],
) -> float:
    """Stundenwert einer Orientierungsgruppe nach AC-Kappung ihrer Mitglieder.

    Args:
        gruppen_kw: unbegrenzter Stundenwert der Gruppe (kW), gerechnet auf
            `gruppen_kwp`.
        gruppen_kwp: kWp, auf die `gruppen_kw` gerechnet wurde.
        mitglieder: (kWp, AC-Grenze kW oder None) je Komponente der Gruppe.

    Returns:
        Summe der je Komponente gekappten Stundenwerte in kW.
    """
    if gruppen_kwp <= 0 or gruppen_kw <= 0 or not mitglieder:
        return max(0.0, gruppen_kw)
    pro_kwp = gruppen_kw / gruppen_kwp
    summe = 0.0
    for kwp, ac_grenze in mitglieder:
        anteil = pro_kwp * kwp
        if ac_grenze is not None and ac_grenze > 0:
            anteil = min(anteil, ac_grenze)
        summe += anteil
    return summe


def kappe_profil(
    stunden_kw: Sequence[float], gruppen_kwp: float, mitglieder: Sequence[Mitglied],
) -> list[float]:
    """`kappe_stunde` über ein ganzes Tagesprofil."""
    return [
        kappe_stunde(v or 0.0, gruppen_kwp, mitglieder) for v in stunden_kw
    ]


def kappungs_faktor(
    stunden_kw: Sequence[float], gruppen_kwp: float, mitglieder: Sequence[Mitglied],
) -> float:
    """Verhältnis gekappte zu ungekappter Tagessumme (1.0 = nichts gekappt).

    Damit lässt sich der **Tageswert** einer Gruppe kappen, ohne ihn aus dem
    Stundenprofil neu zu bilden: der Tageswert der Prognose ist nicht
    zwangsläufig die Σ der Stundenwerte (eigene Rundung, teils andere Quelle),
    und ihn hier neu zu erfinden wäre eine zweite Wahrheit.
    """
    roh = sum(v or 0.0 for v in stunden_kw)
    if roh <= 0:
        return 1.0
    gekappt = sum(kappe_profil(stunden_kw, gruppen_kwp, mitglieder))
    return gekappt / roh
