"""Bilanzieller Stundenverbrauch aus Zähler-Deltas (ADR-001).

Single Source of Truth für die Formel

    verbrauch = PV + Netzbezug − Einspeisung − Batterie-Nettoladung

die bis 29.08.2026 **zweimal wortgleich** im Baum stand: einmal im Snapshot-
Pfad (`services/snapshot/aggregator.py`) und einmal im HA-LTS-Pfad
(`services/snapshot/lts_aggregator.py`). Das Ergebnis wird als
`TagesEnergieProfil.verbrauch_kw` gespeichert und trägt von dort aus die
Tages- und Monatsbilanz, die Grundlast (Nacht-Sockel) und den HA-Sensor
`eedc_grundlast_kw`.

Die Regel dahinter ist die von ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``, in
derselben Lesart wie ``core/berechnungen/tagesbilanz.py`` eine Ebene höher:
**eine Summe darf 0 bleiben, eine Differenz nicht.** Der Verbrauch ist eine
Differenz mit vier Eingängen — fehlt einer, ist er nicht *0*, sondern
*unbekannt*.

⛔ **Dieses Modul ist eine reine Entdopplung — es ändert kein Verhalten.** Der
Wächter zählt hier weiterhin nur PV, Netzbezug und Einspeisung auf; ein
fehlender Batterie-Beitrag wird über ``(batt_netto or 0.0)`` zur 0. **Das ist
bekannt und offen, nicht übersehen:** Ein Speicher ohne (vollständigen) Zähler
macht den Stundenverbrauch nachts zum reinen Netzbezug (Melder OB73-gif, #395;
an einer echten Anlage gegengerechnet: 420 W gegen 0 W).

Die Größe ist damit eine **Differenz mit einem fehlenden Subtrahenden** — der
Fall von ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``. Ob sie unterdrückt oder
beschriftet wird, ist eine **Konzept-Entscheidung** und wird mit N-95/N-94
(Paket B1/B2) für alle drei Fundstellen gemeinsam getroffen — nicht hier
einzeln. ⚠ **Wer sie hier allein unterdrückt, macht es schlimmer:** Die
Erwartung „hat diese Anlage einen Speicher?" kippt am Anschaffungs- bzw.
Stilllegungsdatum, also **mitten im Monat**; ``tagesbilanz`` setzt seinen
Träger ``verbrauch_erfasst`` aber schon bei der **ersten** Stunde mit Wert
(gemessen: 12 von 24 Stunden unterdrückt ⇒ Summe 12 statt 24, Träger ``True``).
Aus einem durchgehend zu niedrigen Monat würde dann ein **noch niedrigerer, als
vollständig ausgewiesener**. Der Träger gehört zur selben Entscheidung.

Dass der Zähler fehlt, meldet der Daten-Checker bereits — Kategorie
*Energieprofil – Zähler-Abdeckung* (``daten_checker/energieprofil.py``,
``erwartete_felder["speicher"]`` verlangt **beide** Richtungen).
"""

from __future__ import annotations

from typing import Optional


def berechne_batterie_netto_kwh(
    *,
    ladung_kwh: Optional[float],
    entladung_kwh: Optional[float],
) -> Optional[float]:
    """Netto-Ladung der Stunde (positiv = Ladung) — ``None``, wenn beide fehlen.

    Konvention: ``Ladung − Entladung``.

    ⚠ **Eine Richtung allein ergibt hier eine halbe Bilanz**, und das ist der
    Bestand, nicht die Absicht: Nachts entlädt der Speicher, ohne zu laden — wer
    nur den Ladezähler kennt, rechnet die Entladung dauerhaft als 0. Gehört zur
    Konzept-Entscheidung im Modul-Docstring, nicht in diese Funktion.
    """
    if ladung_kwh is None and entladung_kwh is None:
        return None
    return (ladung_kwh or 0.0) - (entladung_kwh or 0.0)


def stunden_verbrauch_kwh(
    *,
    pv_kwh: Optional[float],
    netzbezug_kwh: Optional[float],
    einspeisung_kwh: Optional[float],
    batterie_netto_kwh: Optional[float],
) -> Optional[float]:
    """Bilanzieller Hausverbrauch einer Stunde — ``None``, wenn nicht bildbar.

    ``verbrauch = pv + netzbezug − einspeisung − batterie_netto``, auf 0 geklemmt
    (eine negative Bilanz ist ein Zähler-Artefakt, kein negativer Verbrauch).

    Nicht bildbar ist sie, wenn PV, Netzbezug oder Einspeisung fehlt. **Ein
    fehlender Batterie-Beitrag zählt bewusst als 0** — siehe Modul-Docstring:
    das ist der offene Punkt, keine Aussage über seine Richtigkeit.
    """
    if pv_kwh is None or einspeisung_kwh is None or netzbezug_kwh is None:
        return None
    v = pv_kwh + netzbezug_kwh - einspeisung_kwh - (batterie_netto_kwh or 0.0)
    return max(0.0, v)
