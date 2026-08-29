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

⛔ **Ein fehlender Batterie-Beitrag zählt hier als 0, und das bleibt so.** Das
ist entschieden (Gernot, 29.08.2026), nicht offen — wer es ändern will, liest
zuerst die Begründung unten.

**Der Fall:** Ein Speicher ohne (vollständigen) Zähler macht den
Stundenverbrauch nachts zum reinen Netzbezug (Melder OB73-gif, #395; an einer
echten Anlage gegengerechnet: 420 W gegen 0 W). Die Größe ist dann eine
**Differenz mit einem fehlenden Subtrahenden** — auf den ersten Blick der Fall
von ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §3 („Differenz ⇒ unterdrücken").

⛔ **Trotzdem wird hier nicht unterdrückt, aus drei gemessenen Gründen:**

1. **Es ist kein Ausfall, sondern eine fehlende Zuordnung** — und die meldet der
   Daten-Checker bereits samt Reparaturweg (*Energieprofil – Zähler-Abdeckung*,
   ``daten_checker/energieprofil.py``; ``erwartete_felder["speicher"]`` verlangt
   **beide** Richtungen, beidseitig gegengeprüft). Eine Unterdrückung wäre ein
   **zweiter Turm** über einem gemeldeten Sachverhalt — nur in der Anzeige statt
   im Melder. Genau daran ist der Bau vom 29.08. gescheitert und wurde
   zurückgenommen (``c1d57455``).
2. **§3 gilt dem Total-Fall, nicht der Teilabdeckung.** Der Baum zieht die Grenze
   längst so: ``tagesbilanz`` unterdrückt an ``*_erfasst`` — „wurde überhaupt je
   gemessen?" — und nirgends an einer Teilabdeckung. Wer hier unterdrückt,
   verschiebt diese Grenze, statt sie anzuwenden.
3. **Teilweise unterdrücken macht es messbar schlimmer:** ``tagesbilanz`` setzt
   seinen Träger ``verbrauch_erfasst`` schon bei der **ersten** Stunde mit Wert
   (gemessen: 12 von 24 Stunden unterdrückt ⇒ Summe 12 statt 24, Träger
   ``True``). Aus einem durchgehend zu niedrigen Monat würde ein **noch
   niedrigerer, als vollständig ausgewiesener**. Probe:
   ``test_stundenbilanz_sot.py::test_teilunterdrueckung_waere_schlimmer``.

⚑ **Und die sporadische Lücke ist hier ohnehin kein Thema:** ein einzelner
Sensor-Ausfall mitten am Tag wird eine Schicht vorher interpoliert
(``snapshot/aggregator.py::_fill_gaps_linear``, #145), dazu Self-Healing 02:15
und die idempotente Re-Aggregation. Insgesamt neun Schichten kümmern sich um
Tageslücken.

**Was offen bleibt, ist ein SATZ, keine Rechnung:** Die Abdeckungs-Meldung nennt
als Folgen „Prognosen-IST, Heatmap, Lernfaktor, Monatsberichte" — nicht den zu
niedrigen Hausverbrauch und die Grundlast. Das ist **N-346**, ein Fund am Text.
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
