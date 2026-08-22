"""Energie-Bilanz aus stündlichen ``TagesEnergieProfil``-Rows (ADR-001).

Single Source of Truth für die **Σ-über-Stunden**-Bilanz eines beliebigen
Zeitfensters (ein Tag, ein Monat). Die NULL-/Summen-Semantik ist 1:1 die des
Monats-Endpoints ``get_monatsauswertung`` (energie_profil/views.py): NULL-
Stunden zählen **nicht** als 0, Überschuss/Defizit/Direktverbrauch nur wenn
PV **und** Verbrauch vorhanden, Batterie richtungsgetrennt.

Eine **Summe** darf dabei 0 bleiben (additiv, richtungssicher), eine
**Differenz** nicht: ``eigenverbrauch_kwh`` ist ``None``, solange keine
einzige Stunde einen PV-Wert trug — sonst entsteht aus gemessener
Einspeisung ohne PV-Zähler ein negativer Eigenverbrauch. Regel und
Begründung: ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``; Träger ist
``pv_erfasst``.

Eine Summe darf 0 bleiben — **behaupten** darf sie es nicht. Deshalb trägt
jede der vier Achsen ihr eigenes ``*_erfasst``-Flag (``pv`` · ``verbrauch`` ·
``einspeisung`` · ``netzbezug``). Der Layer liefert weiterhin Zahl **und**
Träger; ob daraus „0" oder „—" wird, entscheidet die anzeigende Schicht
(``services/energie_profil/tage_werte.py``) — dieselbe Arbeitsteilung wie seit
jeher bei der PV. Bis 15.08.2026 gab es den Träger nur dort, und die Netz-Seite
lieferte 0.0 ohne jede Unterscheidung (T89667 #162).

Damit gilt für jedes additive Feld die Invariante

    Σ ( bilanz_aus_stundenrows(tag_n) )  ==  bilanz_aus_stundenrows(ganzer_monat)

per Konstruktion — die der Symmetrie-Test
``test_tage_werte_symmetrie`` gegen den bestehenden Monats-Endpoint absichert
([[feedback_aggregator_symmetrie]]). Die Tages-Werte-Embed-Sicht (IA v4 E3,
Cockpit/Monat) speist sich daraus, statt die Aggregat-Logik im Frontend zu
duplizieren ([[feedback_aggregations_drift]]).

DB-frei: nimmt eine Iterable beliebiger Objekte mit den Attributen
``pv_kw``/``verbrauch_kw``/``einspeisung_kw``/``netzbezug_kw``/``batterie_kw``/
``waermepumpe_kw`` (duck-typed → ORM-Rows wie Test-Stubs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
)


class _StundenRow(Protocol):
    pv_kw: Optional[float]
    verbrauch_kw: Optional[float]
    einspeisung_kw: Optional[float]
    netzbezug_kw: Optional[float]
    batterie_kw: Optional[float]
    waermepumpe_kw: Optional[float]


@dataclass
class TagesBilanz:
    """Σ-über-Stunden-Bilanz eines Zeitfensters. Alle kWh additiv über Tage."""

    # Additive kWh-Summen (Σ stündlicher kW × 1 h)
    erzeugung_kwh: float            # = Σ pv_kw (registry: erzeugung); 0.0 auch wenn
                                    #   KEINE Stunde einen PV-Wert trug — dafür
                                    #   steht `pv_erfasst`, s. u.
    gesamtverbrauch_kwh: float      # = Σ verbrauch_kw
    einspeisung_kwh: float
    netzbezug_kwh: float
    ueberschuss_kwh: float          # = Σ max(0, pv − verbrauch)
    defizit_kwh: float              # = Σ max(0, verbrauch − pv)
    direktverbrauch_kwh: float      # = Σ min(pv, verbrauch)
    # = erzeugung − einspeisung (PV-Eigenverbrauch). `None`, wenn keine einzige
    # Stunde einen PV-Wert trug: eine Differenz ohne Minuenden ist keine Zahl,
    # sondern eine Lücke (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`).
    eigenverbrauch_kwh: Optional[float]
    speicher_ladung_kwh: float      # = Σ max(0, −batterie_kw)
    speicher_entladung_kwh: float   # = Σ max(0,  batterie_kw)
    wp_strom_kwh: float             # = Σ waermepumpe_kw
    # Nicht-additive Quoten (%) — None wenn Nenner 0
    autarkie_prozent: Optional[float]
    ev_quote_prozent: Optional[float]
    speicher_effizienz_prozent: Optional[float]
    # Datenqualität
    stunden: int
    # True, sobald EINE Stunde `pv_kw is not None` trug. Trennt „0 kWh
    # gemessen" (Nacht/Schnee/Anlage aus — gültig) von „PV nirgends erfasst"
    # (kein kWh-Zähler je Erzeuger — Lücke). Wer eine PV-abhängige Größe
    # anzeigt, prüft dieses Feld, nicht `erzeugung_kwh > 0`.
    pv_erfasst: bool = False
    # Dieselbe Trennung für die drei übrigen Achsen der Bilanz. Bis 15.08.2026
    # gab es sie nur für die PV — die Netz-Seite konnte „nicht gemessen"
    # überhaupt nicht ausdrücken und lieferte 0.0. Sichtbar geworden an
    # Strikers Januar (T89667 #162): Einspeisung aus der HA-Historie vorhanden,
    # Netzbezug nirgends erfasst, und die Tageszeile behauptete „0 kWh
    # Netzbezug" neben einem korrekten „—" in der PV-Spalte derselben Zeile.
    # Regel und Begründung unverändert `docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`;
    # Träger statt `> 0`, damit eine gemessene Null eine Aussage bleibt.
    verbrauch_erfasst: bool = False
    einspeisung_erfasst: bool = False
    netzbezug_erfasst: bool = False
    # **Abdeckung je Achse in Stunden** (N-92, 2026-08-22). `stunden` oben zählt
    # **Rows**, nicht Feld-Abdeckung — und beantwortet damit die Frage nicht, die
    # eine Differenz stellt: *haben beide Summanden dieselbe Grundlage?* Die
    # `*_erfasst`-Flags beantworten nur „mindestens eine Stunde". Dazwischen
    # liegt der Fall, der `eigenverbrauch_kwh` still zu hoch machte: PV über alle
    # 24 Stunden, Einspeisung nur über 18 ⇒ die Differenz ist um die sechs nicht
    # gemessenen Stunden zu gross. Gemessen 22.08.2026: 48 − 18 = 30 kWh statt 24.
    pv_stunden: int = 0
    verbrauch_stunden: int = 0
    einspeisung_stunden: int = 0
    netzbezug_stunden: int = 0
    #: Stunden, in denen **beide** Summanden der jeweiligen Differenz vorlagen.
    #: Nur wenn sie mit **beiden** Einzelabdeckungen übereinstimmen, ruht die
    #: Differenz auf einer gemeinsamen Grundlage.
    pv_und_einspeisung_stunden: int = 0
    verbrauch_und_netzbezug_stunden: int = 0


def bilanz_aus_stundenrows(rows: Iterable[_StundenRow]) -> TagesBilanz:
    """Aggregiert stündliche TEP-Rows zur Energie-Bilanz (siehe Modul-Docstring)."""
    pv_sum = 0.0
    pv_erfasst = False
    # Abdeckung je Achse + die beiden Paar-Abdeckungen der Differenzen (N-92).
    pv_n = verbrauch_n = einspeisung_n = netzbezug_n = 0
    pv_ein_n = verb_netz_n = 0
    verbrauch_erfasst = False
    einspeisung_erfasst = False
    netzbezug_erfasst = False
    verbrauch_sum = 0.0
    einspeisung_sum = 0.0
    netzbezug_sum = 0.0
    ueberschuss_sum = 0.0
    defizit_sum = 0.0
    direkt_sum = 0.0
    batt_lade_sum = 0.0
    batt_entlade_sum = 0.0
    wp_sum = 0.0
    n = 0

    for r in rows:
        n += 1
        pv = r.pv_kw
        verbrauch = r.verbrauch_kw
        einspeisung = r.einspeisung_kw
        netzbezug = r.netzbezug_kw
        batt = r.batterie_kw
        wp = getattr(r, "waermepumpe_kw", None)

        # NULL überspringt still (statt als 0 zu zählen) — wie get_monatsauswertung.
        if pv is not None:
            pv_sum += pv
            pv_erfasst = True
            pv_n += 1
        if verbrauch is not None:
            verbrauch_sum += verbrauch
            verbrauch_erfasst = True
            verbrauch_n += 1
        if einspeisung is not None:
            einspeisung_sum += einspeisung
            einspeisung_erfasst = True
            einspeisung_n += 1
        if netzbezug is not None:
            netzbezug_sum += netzbezug
            netzbezug_erfasst = True
            netzbezug_n += 1
        if pv is not None and einspeisung is not None:
            pv_ein_n += 1
        if verbrauch is not None and netzbezug is not None:
            verb_netz_n += 1
        if wp is not None:
            wp_sum += wp

        if pv is not None and verbrauch is not None:
            ueberschuss = pv - verbrauch
            if ueberschuss > 0:
                ueberschuss_sum += ueberschuss
            else:
                defizit_sum += -ueberschuss
            direkt_sum += min(pv, verbrauch)

        if batt is not None:
            if batt < 0:
                batt_lade_sum += -batt
            elif batt > 0:
                batt_entlade_sum += batt

    # Eigenverbrauch ist eine DIFFERENZ — fehlt die Erzeugung ganz, ist die
    # Richtung des Fehlers unbekannt und der Wert wird unterdrückt statt
    # geraten (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`). Ohne diese Regel
    # lieferte ein Tag mit gemessener Einspeisung, aber ohne PV-Zähler
    # `0 − 25 = −25 kWh` (Forum kaba-kakao, 2026-08-07): ein physikalisch
    # unmöglicher Wert, den keine Sicht als Lücke erkennen konnte.
    #
    # Träger ist `pv_erfasst`, NICHT `pv_sum > 0`: eine gemessene Null
    # (Nacht, Schnee, Anlage aus) ist ein gültiger Wert und muss 0 bleiben
    # ([[feedback_legacy_felder]] — `is not None` statt `if val`).
    #
    # ⚑ **N-92 (2026-08-22): `pv_erfasst` allein reicht nicht.** Es beantwortet
    # nur „trug IRGENDEINE Stunde einen PV-Wert" und schützt damit den Total-
    # Fall. Die Differenz braucht mehr: **beide Summanden müssen dieselbe
    # Grundlage haben.** Zwei Lagen liefen bis dahin still falsch —
    #   * *Teilabdeckung:* PV 24 h, Einspeisung 18 h ⇒ 48 − 18 = **30 kWh**
    #     statt 24; die Differenz ist um die sechs ungemessenen Stunden zu hoch.
    #   * *Einspeisung nie gemessen:* ⇒ `pv_sum − 0` behauptet, die ganze
    #     Erzeugung sei selbst verbraucht worden. Die Tageszeile schrieb dabei
    #     schon „—" in die Einspeisungs-Spalte und daneben eine EV-Zahl, die
    #     genau diese fehlende Spalte als 0 gelesen hat.
    # Regel: `KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 — eine **Differenz** wird
    # **unterdrückt**, nicht beschriftet, weil ihre Fehlerrichtung davon abhängt,
    # *welcher* Summand fehlt. Und §3 Regel 1 wörtlich: „Eine Differenz erbt die
    # Unvollständigkeit jedes Summanden."
    eigenverbrauch = (
        (pv_sum - einspeisung_sum)
        if pv_erfasst and pv_n == einspeisung_n == pv_ein_n
        else None
    )
    # Quoten über den SoT (kennzahlen-Layer); None statt 0 wenn Nenner fehlt,
    # damit die UI '—' statt '0 %' zeigt.
    #
    # ⚑ **Die Autarkie ist ebenfalls eine Differenz** (`Verbrauch − Netzbezug`),
    # und sie war bis 2026-08-22 **gar nicht** geschützt — nicht einmal gegen den
    # Total-Fall, den `eigenverbrauch` seit dem 15.08. kennt. Gemessen: Verbrauch
    # über 24 h erfasst, Netzbezug nirgends ⇒ `netzbezug_sum` bleibt 0.0 ⇒
    # **Autarkie 100,0 %**. Das ist exakt Strikers Januar (T89667 #162) eine
    # Kachel weiter: dieselbe Tageszeile zeigte in der Netzbezug-Spalte bereits
    # „—" (die Anzeige liest `netzbezug_erfasst`), daneben aber „100 %
    # Autarkie" — ein Wert, der aus der fehlenden Spalte gerechnet ist.
    # Eine 100 %, die niemand gemessen hat, ist keine Bestleistung, sondern
    # eine Lücke mit Ausrufezeichen.
    autarkie = (
        autarkie_prozent(verbrauch_sum - netzbezug_sum, verbrauch_sum)
        if verbrauch_sum > 0
        and netzbezug_erfasst
        and verbrauch_n == netzbezug_n == verb_netz_n
        else None
    )
    ev_quote = (
        eigenverbrauchsquote_prozent(eigenverbrauch, pv_sum)
        if pv_erfasst and eigenverbrauch is not None and pv_sum > 0 else None
    )
    speicher_eff = (
        batt_entlade_sum / batt_lade_sum * 100 if batt_lade_sum > 0.1 else None
    )

    return TagesBilanz(
        erzeugung_kwh=pv_sum,
        gesamtverbrauch_kwh=verbrauch_sum,
        einspeisung_kwh=einspeisung_sum,
        netzbezug_kwh=netzbezug_sum,
        ueberschuss_kwh=ueberschuss_sum,
        defizit_kwh=defizit_sum,
        direktverbrauch_kwh=direkt_sum,
        eigenverbrauch_kwh=eigenverbrauch,
        speicher_ladung_kwh=batt_lade_sum,
        speicher_entladung_kwh=batt_entlade_sum,
        wp_strom_kwh=wp_sum,
        autarkie_prozent=autarkie,
        ev_quote_prozent=ev_quote,
        speicher_effizienz_prozent=speicher_eff,
        stunden=n,
        pv_erfasst=pv_erfasst,
        pv_stunden=pv_n,
        verbrauch_stunden=verbrauch_n,
        einspeisung_stunden=einspeisung_n,
        netzbezug_stunden=netzbezug_n,
        pv_und_einspeisung_stunden=pv_ein_n,
        verbrauch_und_netzbezug_stunden=verb_netz_n,
        verbrauch_erfasst=verbrauch_erfasst,
        einspeisung_erfasst=einspeisung_erfasst,
        netzbezug_erfasst=netzbezug_erfasst,
    )
