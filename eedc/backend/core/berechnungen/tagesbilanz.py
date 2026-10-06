"""Energie-Bilanz aus stündlichen ``TagesEnergieProfil``-Rows (ADR-001).

Single Source of Truth für die **Σ-über-Stunden**-Bilanz eines beliebigen
Zeitfensters (ein Tag, ein Monat). Die NULL-/Summen-Semantik ist 1:1 die des
Monats-Endpoints ``get_monatsauswertung`` (energie_profil/monat.py): NULL-
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

from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol

from backend.core.berechnungen.kennzahlen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
)
from backend.core.berechnungen.verbrauch import berechne_verbrauchs_kennzahlen


def _eigenverbrauch_kwh(
    *, pv_kwh: float, einspeisung_kwh: float, netzbezug_kwh: float,
    speicher_ladung_kwh: float, speicher_entladung_kwh: float,
) -> float:
    """Eigenverbrauch eines Zeitfensters — **die eine Formel** (N-635, 05.10.2026).

    Direktverbrauch + Speicher-Entladung, gebildet von
    ``verbrauch.berechne_verbrauchs_kennzahlen`` (ADR-001: eine Formel an einem
    Ort). Dieselbe Formel rechnet der Monat (Monats-Fakten) und das
    HA-Energie-Dashboard (``src/data/energy.ts::computeConsumptionSingle``:
    ``used_solar`` + ``used_battery``). Bis 05.10.2026 stand hier für Tag und
    Monat-aus-Tagen ``PV − Einspeisung`` — das zählt die Speicher-**Ladung** als
    Eigenverbrauch statt der **Entladung**: ΔSoC und Ladeverlust landeten im
    Eigenverbrauch, der Tag lag dann über seinem Gesamtverbrauch (Matrix-Form
    M02: 12,0 statt 11,0 kWh bei 11,0 kWh Gesamtverbrauch). Ohne Speicher sind
    beide Formeln gleich.
    """
    return berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=pv_kwh,
        einspeisung_kwh=einspeisung_kwh,
        netzbezug_kwh=netzbezug_kwh,
        speicher_ladung_kwh=speicher_ladung_kwh,
        speicher_entladung_kwh=speicher_entladung_kwh,
    ).eigenverbrauch_kwh


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
    # = Direktverbrauch + Speicher-Entladung (`_eigenverbrauch_kwh`, N-635); ohne
    # Speicher = erzeugung − einspeisung. `None`, wenn keine einzige
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
    # HA-Bauform E4d (Bauplan §8a, Rest N-585): dieselbe Trennung für den Wärmepumpen-Strom — eine Stunde mit
    # `waermepumpe_kw is not None` trug einen Wert, auch 0. Eine gemessene 0 ist erfasst (F-5): „kein Betrieb", nicht
    # „keine Wärmepumpe" — die Anzeige liest dieses Feld, nicht `wp_strom_kwh > 0`.
    wp_erfasst: bool = False
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
    #: Zählerlücken wie HA (R7/R9): nach welcher Regel ist diese Bilanz
    #: gerechnet? ``True`` = neue Regel (Tageszeile mit Regelmarke), ``False``
    #: = N-92 (Altbestand ohne Marke, oder Monatsfaltung über rohe Stunden).
    regelmarke: bool = False
    #: Die verworfenen Mengen der Tageszeile (R4) — ``{}`` ohne Befund.
    verworfen: dict = field(default_factory=dict)


def gesamtverbrauch_ha_formel_kwh(
    *,
    pv_kwh: float,
    netzbezug_kwh: float,
    einspeisung_kwh: float,
    speicher_entladung_kwh: float,
    speicher_ladung_kwh: float,
) -> float:
    """Tages-Hausverbrauch nach der Formel des HA-Energie-Dashboards (R7/G2).

    ``PV + Netzbezug + Entladung − Einspeisung − Ladung``, **einmal** auf ≥ 0
    geklemmt (E2: die Stunde klemmt jede Stunde, der Tag rechnet ungeklemmt
    und klemmt einmal). Der Netto-Split je Stunde ist über den Tag algebraisch
    identisch mit Brutto. Bildbarkeit prüft der Aufrufer.
    """
    return max(0.0, pv_kwh + netzbezug_kwh + speicher_entladung_kwh
               - einspeisung_kwh - speicher_ladung_kwh)


def bilanz_aus_stundenrows(
    rows: Iterable[_StundenRow], *, verworfen: Optional[dict] = None,
) -> TagesBilanz:
    """Aggregiert stündliche TEP-Rows zur Energie-Bilanz (siehe Modul-Docstring).

    ⭐ **Zählerlücken wie HA (R7, Vorlage Fassung 7).** ``verworfen`` ist die
    Spalte der Tageszeile und zugleich ihre **Regelmarke** (R9):

    * ``None`` (Altbestand, oder eine Faltung ohne Tageszeile) ⇒ **N-92 wie
      bisher**: Differenzen und Quoten nur bei gleicher Abdeckung ihrer
      Summanden. Die Stunden solcher Tage haben die Energie einer Lücke noch
      verloren (E6) — eine Teilabdeckung ist dort ein echter Fehler.
    * ein Dict (auch ``{}``) ⇒ **R7**: jede Stunde trägt, was HA für sie zeigt,
      die Energie einer Lücke steht in der Folgestunde. Mengen = Σ Stunden;
      **Gesamtverbrauch nach HA-Formel** (`gesamtverbrauch_ha_formel_kwh`),
      ``None`` nur im **Total-Fall** (PV, Netzbezug oder Einspeisung hat am Tag
      keinen einzigen Stundenwert; fehlende Batterie = 0). **EV = Direkt-
      verbrauch + Speicher-Entladung** (`_eigenverbrauch_kwh`, N-635) — die
      Formel des Monats und des HA-Energie-Dashboards (``used_solar`` +
      ``used_battery``); „EV = PV − Einspeisung, wie HA" galt nur ohne
      Speicher. Die Batterie trägt dieselbe Regel wie der Gesamtverbrauch
      daneben: fehlende Batterie = 0, ``verworfen.batterie`` sperrt den
      Eigenverbrauch nicht (er sperrt nur die Autarkie). Unterdrückt werden
      nur noch: EV/EV-Quote bei Total-Fall oder ``verworfen`` auf
      pv/einspeisung; Autarkie bei fehlendem Gesamtverbrauch oder
      ``verworfen`` auf pv/netzbezug/einspeisung/batterie. Teilabdeckung wird
      nicht mehr unterdrückt — wie in HA (G3).

    Direktverbrauch, Überschuss und Defizit bleiben in beiden Regeln Σ über die
    Stunden mit (R6-)Verbrauchswert — benannte Teilsummen.
    """
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
    wp_erfasst = False
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
            wp_erfasst = True

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
    regelmarke = verworfen is not None
    verw = dict(verworfen or {})
    gesamtverbrauch_ha: Optional[float] = None
    if regelmarke:
        # R7: Total-Fall statt Abdeckungsgleichheit.
        if pv_erfasst and netzbezug_erfasst and einspeisung_erfasst:
            gesamtverbrauch_ha = gesamtverbrauch_ha_formel_kwh(
                pv_kwh=pv_sum, netzbezug_kwh=netzbezug_sum,
                einspeisung_kwh=einspeisung_sum,
                speicher_entladung_kwh=batt_entlade_sum,
                speicher_ladung_kwh=batt_lade_sum,
            )
        # ⭐ Vorlage §10: EV einmal bei 0 geklemmt (dieselbe Bauform wie R7
        # für den Gesamtverbrauch). Mehr Einspeisung als PV ist keine Kennzahl,
        # sondern ein Widerspruch der Eingänge (PV-Ausfall bei laufender
        # Einspeisung) — die Quote darf ihn nicht als „−33 %" ausweisen.
        # Die Klemme sitzt seit N-635 in der Layer-Formel selbst.
        eigenverbrauch = (
            _eigenverbrauch_kwh(
                pv_kwh=pv_sum, einspeisung_kwh=einspeisung_sum,
                netzbezug_kwh=netzbezug_sum,
                speicher_ladung_kwh=batt_lade_sum,
                speicher_entladung_kwh=batt_entlade_sum,
            )
            if pv_erfasst and einspeisung_erfasst
            and "pv" not in verw and "einspeisung" not in verw
            else None
        )
    else:
        # N-635: dieselbe Formel auch im Altbestand (N-92-Sperre unverändert).
        # Die Layer-Formel klemmt bei 0 — ein Altbestandstag mit mehr
        # Einspeisung als PV nennt seither 0 statt einer negativen Zahl.
        eigenverbrauch = (
            _eigenverbrauch_kwh(
                pv_kwh=pv_sum, einspeisung_kwh=einspeisung_sum,
                netzbezug_kwh=netzbezug_sum,
                speicher_ladung_kwh=batt_lade_sum,
                speicher_entladung_kwh=batt_entlade_sum,
            )
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
    if regelmarke:
        autarkie = (
            autarkie_prozent(gesamtverbrauch_ha - netzbezug_sum, gesamtverbrauch_ha)
            if gesamtverbrauch_ha is not None and gesamtverbrauch_ha > 0
            and not ({"pv", "netzbezug", "einspeisung", "batterie"} & set(verw))
            else None
        )
    else:
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

    if regelmarke:
        # Der Gesamtverbrauch der neuen Regel ist die HA-Formel; getragen wird
        # er über denselben Träger wie bisher (`verbrauch_erfasst`), damit die
        # Anzeige-Schicht („—" statt 0) unverändert entscheidet.
        verbrauch_sum = gesamtverbrauch_ha if gesamtverbrauch_ha is not None else 0.0
        verbrauch_erfasst = gesamtverbrauch_ha is not None

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
        wp_erfasst=wp_erfasst,
        regelmarke=regelmarke,
        verworfen=verw,
    )



@dataclass
class MonatsBilanz:
    """Monat aus Tagesbilanzen (R8) — dieselben Felder, die Leser brauchen.

    Mengen sind Σ Tage; ``gesamtverbrauch_kwh`` ist Σ der Tages-Gesamtverbräuche
    (Tage ohne Gesamtverbrauch tragen nichts bei). Quoten aus den Summen.
    """
    erzeugung_kwh: float
    einspeisung_kwh: float
    netzbezug_kwh: float
    gesamtverbrauch_kwh: Optional[float]
    eigenverbrauch_kwh: Optional[float]
    autarkie_prozent: Optional[float]
    ev_quote_prozent: Optional[float]
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    direktverbrauch_kwh: float
    ueberschuss_kwh: float
    defizit_kwh: float
    wp_strom_kwh: float
    pv_erfasst: bool
    einspeisung_erfasst: bool
    netzbezug_erfasst: bool
    tage: int


def monatsbilanz_aus_tagen(tage: Iterable[TagesBilanz]) -> MonatsBilanz:
    """Faltet Tagesbilanzen zum Monat — **R8 symmetrisch** (Vorlage Fassung 7).

    Eingang sind die Tagesbilanzen **so, wie der Tag sie rechnet** (R7 mit
    Regelmarke, N-92 ohne). Mengen = Σ Tage; Verbrauch = Σ Tages-Gesamtverbrauch;
    **EV = die eine Formel aus den Monatssummen** (Direktverbrauch + Entladung,
    `_eigenverbrauch_kwh`, N-635) — so rechnen HA und die Monats-Fakten den
    Monat. Σ Tage = Monat gilt, solange an keinem Tag mehr in den Speicher geht,
    als PV nach der Einspeisung übrig ist (Netzladung): dort klemmt der Tag den
    Direktverbrauch bei 0, der Monat verrechnet die Netzladung mit dem
    PV-Überschuss anderer Tage — die benannte Rest-Abweichung (BERECHNUNGEN
    §Eigenverbrauch). Unterdrückt wird:

    * **EV/EV-Quote**, wenn (a) kein Tag einen PV-Wert hat, (b) kein Tag einen
      Einspeisungs-Wert hat, (c) ein Tag ``verworfen.pv`` oder
      ``verworfen.einspeisung`` trägt, oder (d) ein Tag **ohne** Regelmarke
      (Altbestand) EV ``None`` hat — der E6-Schutz: dessen Stunden haben die
      Lückenenergie verloren.
    * **Autarkie** analog: kein Tag mit Gesamtverbrauch, ``verworfen`` auf
      pv/netzbezug/einspeisung/batterie an einem Tag, oder ein Altbestandstag
      mit Autarkie ``None``.

    ⭐ **Ein Total-Fall-Tag propagiert nicht** — genau wie eine Total-Fall-Stunde
    im Tag nicht (W4). Die Autarkie rechnet über die Tage mit Gesamtverbrauch:
    (Σ GV − Σ Netzbezug dieser Tage) / Σ GV.
    """
    alle_tage = list(tage)
    # „Tage ohne jede Bilanz-Achse zählen nicht" (R8) — eine Tageszeile ohne
    # Stundenwert auf PV, Einspeisung und Netzbezug sagt über EV und Autarkie
    # des Monats nichts. Die additiven Mengen (Speicher, WP) summieren dennoch
    # über ALLE Tage: eine Summe darf keinen Tag verlieren.
    tage = [t for t in alle_tage if t.pv_erfasst or t.einspeisung_erfasst or t.netzbezug_erfasst]
    pv = sum(t.erzeugung_kwh for t in tage)
    einsp = sum(t.einspeisung_kwh for t in tage)
    netz = sum(t.netzbezug_kwh for t in tage)
    gv_tage = [t for t in tage if t.verbrauch_erfasst]
    gv = sum(t.gesamtverbrauch_kwh for t in gv_tage) if gv_tage else None
    pv_erfasst = any(t.pv_erfasst for t in tage)
    einsp_erfasst = any(t.einspeisung_erfasst for t in tage)
    netz_erfasst = any(t.netzbezug_erfasst for t in tage)

    ev_gesperrt = (
        not pv_erfasst or not einsp_erfasst
        or any(("pv" in t.verworfen or "einspeisung" in t.verworfen) for t in tage)
        or any((not t.regelmarke and t.eigenverbrauch_kwh is None) for t in tage)
    )
    # Vorlage §10: einmal bei 0 geklemmt, wie am Tag — ein PV-toter Tag mit
    # laufender Einspeisung drückt den Monat höchstens auf 0, nicht darunter.
    # N-635: dieselbe Formel wie am Tag, aus den Summen derselben Tage, die
    # auch PV und Einspeisung tragen.
    ev = None if ev_gesperrt else _eigenverbrauch_kwh(
        pv_kwh=pv, einspeisung_kwh=einsp, netzbezug_kwh=netz,
        speicher_ladung_kwh=sum(t.speicher_ladung_kwh for t in tage),
        speicher_entladung_kwh=sum(t.speicher_entladung_kwh for t in tage),
    )
    aut_gesperrt = (
        gv is None
        or any(({"pv", "netzbezug", "einspeisung", "batterie"} & set(t.verworfen)) for t in tage)
        or any((not t.regelmarke and t.autarkie_prozent is None) for t in tage)
    )
    netz_gv_tage = sum(t.netzbezug_kwh for t in gv_tage)
    autarkie = (
        autarkie_prozent(gv - netz_gv_tage, gv)
        if not aut_gesperrt and gv is not None and gv > 0 else None
    )
    ev_quote = (
        eigenverbrauchsquote_prozent(ev, pv) if ev is not None and pv > 0 else None
    )
    return MonatsBilanz(
        erzeugung_kwh=pv,
        einspeisung_kwh=einsp,
        netzbezug_kwh=netz,
        gesamtverbrauch_kwh=gv,
        eigenverbrauch_kwh=ev,
        autarkie_prozent=autarkie,
        ev_quote_prozent=ev_quote,
        speicher_ladung_kwh=sum(t.speicher_ladung_kwh for t in alle_tage),
        speicher_entladung_kwh=sum(t.speicher_entladung_kwh for t in alle_tage),
        direktverbrauch_kwh=sum(t.direktverbrauch_kwh for t in alle_tage),
        ueberschuss_kwh=sum(t.ueberschuss_kwh for t in alle_tage),
        defizit_kwh=sum(t.defizit_kwh for t in alle_tage),
        wp_strom_kwh=sum(t.wp_strom_kwh for t in alle_tage),
        pv_erfasst=pv_erfasst,
        einspeisung_erfasst=einsp_erfasst,
        netzbezug_erfasst=netz_erfasst,
        tage=len(tage),
    )
