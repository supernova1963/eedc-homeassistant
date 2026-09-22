"""Was eine Kilowattstunde **aus dem Speicher** kostet — Preis ÷ Wirkungsgrad.

Layer-SoT (ADR-001) für die beiden Speicher-Preisgrößen der Stufe 3b:

* **Speicherstrom aus PV** — die eingespeicherte kWh hätte eingespeist werden
  können; ihr Preis ist die entgangene **Vergütung**. Weil der Speicher nicht
  verlustfrei ist, kostet die *entnommene* kWh mehr als die *eingelagerte*:
  ``Vergütung ÷ η``.
* **Netzladen** — dieselbe Rechnung mit dem **Bezugspreis** der Ladestunde.
  Nur für Speicher, die überhaupt aus dem Netz laden dürfen (`laedt_aus_netz`).

⚠ **Der Verschleiß steckt NICHT darin.** Ein Zyklus kostet Batterielebensdauer,
und das ist ein realer Posten — aber er braucht einen gepflegten Wert (Zyklen,
Anschaffungspreis, Restwert), den eedc heute nicht erhebt. Ihn zu schätzen hieße,
eine Zahl zu erfinden und sie in eine Automation zu geben. Er ist ausdrücklich
zurückgestellt, nicht vergessen (S3b §8).

## Der Wirkungsgrad ist nie der Default

Die drei Stufen, in dieser Reihenfolge (`services/speicher_wirtschaftlichkeit
.wirkungsgrad_ist_fuer_speicher` löst sie auf):

1. **gemessen** — `berechne_ist_wirkungsgrad` aus den erfassten Lade-/
   Entlademengen (an der Demo-Anlage 85,0 % über 34 Monate, nicht die gepflegten
   95).
2. **gepflegt** — `investition_kennwerte.get_speicher_wirkungsgrad_gepflegt`,
   und zwar nur, wenn wirklich einer gepflegt **ist**.
3. **keiner** ⇒ **kein Sensor**. Der Kanon-Default (95 %) ist für eine
   Ertragsrechnung über Jahre brauchbar; als Nenner eines ct-Betrags in einer
   Automation wäre er eine Behauptung über *dieses* Gerät.

`wirkungsgrad_messung` nennt immer, welcher Weg es war — auch wenn die Messung
gescheitert ist (`fenster-zu-kurz`, `keine-ladung`, `nicht-ermittelbar`,
`zu-wenig-monate`). Ein stummer Fallback wäre Flex §8 („keine stille
Ersetzung").
"""

from __future__ import annotations

from typing import Iterable, Optional


def speicher_kwh_kosten(preis_cent: Optional[float], eta_prozent: Optional[float]) -> Optional[float]:
    """``Preis ÷ η`` — was die **entnommene** Kilowattstunde kostet.

    Args:
        preis_cent: Vergütung (PV-Ladung) oder Bezugspreis (Netzladung), ct/kWh.
        eta_prozent: Roundtrip-Wirkungsgrad in Prozent.

    Returns:
        ct/kWh, oder `None`, wenn ein Eingang fehlt oder η ≤ 0.

    ⚠ **`is not None` statt truthy:** 0 ct Vergütung ist ein gepflegter Wert
    (Volleinspeisung ohne Vergütung, Vorbelegung eines neuen Tarifs) und ergibt
    hier korrekt 0,0 — nicht „kein Sensor".

    ⛔ **η > 100 % wird nicht abgeschnitten.** Ein solcher Wert sagt nichts über
    den Speicher, sondern über die erfassten Mengen (#281); er kommt hier gar
    nicht erst an — `berechne_ist_wirkungsgrad` meldet dann `nicht-ermittelbar`,
    und der Resolver fällt auf den gepflegten Wert zurück. Käme er doch an, wäre
    ein Kappen auf 100 eine dritte Semantik derselben Frage (N-264).
    """
    if preis_cent is None or eta_prozent is None:
        return None
    try:
        eta = float(eta_prozent)
    except (TypeError, ValueError):
        return None
    if eta <= 0:
        return None
    return round(float(preis_cent) / (eta / 100.0), 2)


def eta_anlage(je_speicher: Iterable[Optional[float]]) -> Optional[float]:
    """Der anlagenweite Wirkungsgrad: das **Minimum** über die Speicher.

    ⭐ **Dieselbe Regel wie `investition_kennwerte.aggregiere_speicher_basis`**
    („Kapazitäten addieren sich physikalisch, ein Wirkungsgrad nicht — die Kette
    kann nicht besser sein als ihr schwächstes Glied"). Ein Mittelwert würde
    einen schlechten Speicher hinter einem guten verstecken; bei nur einem Gerät
    (Normalfall) sind beide Lesarten identisch.

    ⛔ **`None`, sobald EIN Glied unbekannt ist** — nicht „das Minimum der
    bekannten". Zwei Speicher, von denen einer gemessen 85 % hat und der andere
    gar keinen Wert, ergäben sonst 85 % für die ganze Anlage: eine Zahl, die für
    die Hälfte der Kapazität nichts aussagt. Dann lieber kein Sensor
    (ADR-002/P4).

    Eine **leere** Liste ergibt ebenfalls `None` — keine Speicher, kein
    anlagenweiter Wirkungsgrad.
    """
    werte = list(je_speicher)
    if not werte:
        return None
    if any(w is None for w in werte):
        return None
    try:
        return min(float(w) for w in werte)
    except (TypeError, ValueError):
        return None
