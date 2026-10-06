"""kWp-anteilige PV-Verteilung — Read-time-SoT (kWp-Verteilung-Etappe).

Multi-String-Anlagen mit nur EINEM Gesamt-PV-Wert (ein manuell eingetragenes
Aggregat in ``Monatsdaten.pv_erzeugung_kwh`` bzw. ein importiertes Gesamt-
Aggregat) bekommen die Erzeugung anteilig nach ``leistung_kwp`` auf die
einzelnen PV-Module/Strings aufgeschlüsselt — zur **Lesezeit**, nie als
geschriebener Wert (Design final, [[project_kwp_verteilung_aggregator]],
Anlass NongJoWo #289 + JayJayX #651).

Invariante: ``Monatsdaten.pv_erzeugung_kwh`` ist ein optionales, rein
manuelles/importiertes Aggregat und wird NIE programmatisch gefüllt. Die
Pro-Modul-Sicht wird aus Aggregat + im Monat aktiven Modulen deterministisch
neu gebildet — es gibt damit keine „historisch verteilten Werte" zum
Rekonstruieren.

**Präzedenz je Modul** (``resolve_pv_je_modul``) — Gernot 2026-07-29:

  1. Modul hat einen eigenen Wert → ``gemessen``. **Immer und ausnahmslos.**
  2. Modul ohne eigenen Wert, Aggregat gesetzt → Anteil am **Rest**
     (``Aggregat − Σ gemessene``), kWp-gewichtet → ``verteilt``
  3. Modul ohne eigenen Wert, kein Aggregat → ``fehlt``

Die Regel ist **modulweise**, nicht anlagenweit. Bis 2026-07-29 galt sie
anlagenweit: sobald **ein** Modul keinen Wert hatte, wurde das Aggregat über
**alle** Module verteilt — die echten Messwerte der übrigen Strings wurden
dabei verworfen und durch kWp-Anteile ersetzt. Das war nicht der Zweck des
Aggregats: es existiert, um **Lücken zu füllen** (Anlass war ein Anwender mit
Nur-Gesamt-Historie und neu unterstützten Einzelstrings), nicht um Messungen
zu überschreiben. Teil-Messung ist außerdem kein Sonderfall — sie entsteht bei
jedem Sensor-Aussetzer, jedem neu angelegten String und in jedem Monat vor der
Umstellung auf Pro-String-Messung.

**Das Aggregat ist reiner Eingang dieser Auflösung.** Es darf in keiner
einzelnen Berechnung direkt gelesen werden; jede PV-Zahl kommt aus der
Pro-Modul-Schicht bzw. deren Summe (siehe ``ist_vollstaendig``).

Σ-Invariante (Symmetrie-Test Pflicht, [[feedback_aggregator_symmetrie]]):
Σ der zurückgegebenen Pro-Modul-Werte == Gesamterzeugung — == Σ der gemessenen
Werte (keine Lücken) bzw. == Aggregat (Lücken + Aggregat). Die Verteilung
rundet NICHT, damit die Summe exakt erhalten bleibt; Rundung ist Aufgabe der
Anzeige-Schicht. **Eine Ausnahme:** übersteigt Σ der gemessenen Werte das
Aggregat, wird der Rest auf 0 geklemmt statt negativ verteilt — dann ist
Σ > Aggregat. Das ist ein Messfehler und gehört gemeldet, nicht weggerechnet.

**Unvollständigkeit ist ein eigener Zustand, keine kleine Zahl.** Bleibt auch
nur ein Modul auf ``fehlt``, ist die Σ **keine Anlagensumme** — sie sähe wie
die Gesamterzeugung aus und wäre systematisch zu klein. Plausibilitäts-Prüfung
dafür: ``ist_vollstaendig``. Die Pro-Modul-Sicht zeigt trotzdem, was gemessen
wurde (das ist der Sinn der modulweisen Regel).

Architektur-Anker: ADR-001 (core/berechnungen). 0-Werte gelten als Daten
(``is not None``, CLAUDE.md „0-Werte prüfen") — ein Aggregat von 0 (dunkler
Wintermonat) ist „verteilt", nicht „fehlt".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Herkunft eines aufgelösten Pro-Modul-Werts.
QUELLE_GEMESSEN = "gemessen"
QUELLE_VERTEILT = "verteilt"
QUELLE_FEHLT = "fehlt"

# Monats-Klassifikation für den Daten-Checker (Severity-Mapping beim Aufrufer).
STATUS_OK = "ok"                # vollständig gemessen → OK
STATUS_VERTEILT = "verteilt"    # Aggregat deckt ab → INFO
STATUS_TEIL_LUECKE = "teil_luecke"  # teilgemessen, kein Aggregat → WARNING
STATUS_FEHLT = "fehlt"          # gar keine PV-Quelle → ERROR


@dataclass(frozen=True)
class PvModul:
    """Eingabe: ein im Monat aktives PV-Modul.

    - ``inv_id``: Investitions-ID
    - ``leistung_kwp``: kWp für die Gewichtung (SoT-Wert via ``get_inv_value``)
    - ``eigen_kwh``: gemessener Pro-Modul-Wert aus den IMD; ``None`` = nicht
      erfasst (löst Aggregat-Verteilung aus, sobald nicht alle Module messen).
    - ``eigen_ist_abgeleitet``: der gespeicherte Wert IST bereits eine
      kWp-Zerlegung (#352) — ein Import oder ein übernommener Connector-/
      Cloud-Vorschlag hat ihn geschrieben, gemessen wurde er nie. Der Wert
      bleibt unangetastet (er steht so in der DB), nur seine **Herkunft** ist
      ``verteilt`` statt ``gemessen``. Die Markierung kommt aus
      ``InvestitionMonatsdaten.source_provenance`` (Ladepfad
      ``services/pv_monatswerte.py``).
    """

    inv_id: int
    leistung_kwp: float
    eigen_kwh: Optional[float]
    eigen_ist_abgeleitet: bool = False


@dataclass(frozen=True)
class PvModulWert:
    """Ausgabe: aufgelöster Pro-Modul-Wert + Herkunft."""

    inv_id: int
    pv_erzeugung_kwh: float
    quelle: str  # QUELLE_GEMESSEN | QUELLE_VERTEILT | QUELLE_FEHLT


def verteile_basis_kwh_nach_kwp(
    basis_kwh: float,
    module: list[tuple[int, float]],
) -> dict[int, float]:
    """Verteilt ``basis_kwh`` anteilig nach kWp auf die Module.

    Args:
        basis_kwh: Gesamt-Erzeugung, die verteilt werden soll.
        module: ``[(inv_id, leistung_kwp), …]``.

    Returns:
        ``{inv_id: kwh}`` mit ``Σ == basis_kwh``. Fallback bei ``Σ kWp == 0``:
        Gleichverteilung (#229-Muster, repliziert aus import_export/helpers.py).
        Leere Modul-Liste → ``{}``. Es wird NICHT gerundet (Summen-Treue).
    """
    if not module:
        return {}
    total_kwp = sum(max(0.0, kwp or 0.0) for _, kwp in module)
    if total_kwp > 0:
        return {
            inv_id: basis_kwh * (max(0.0, kwp or 0.0) / total_kwp)
            for inv_id, kwp in module
        }
    # keine kWp-Werte → gleichmäßig verteilen
    n = len(module)
    return {inv_id: basis_kwh / n for inv_id, _ in module}


def resolve_pv_je_modul(
    *,
    aggregat_kwh: Optional[float],
    module: list[PvModul],
) -> dict[int, PvModulWert]:
    """Löst die Pro-Modul-PV-Erzeugung zur Lesezeit auf (Präzedenz siehe Modul-Doc).

    Args:
        aggregat_kwh: ``Monatsdaten.pv_erzeugung_kwh`` (manuelles Aggregat) oder
            ``None``. 0 zählt als Daten (``is not None``).
        module: im Monat aktive PV-Module (anschaffungs-/stilllegungs- und
            aktiv-gefiltert beim Aufrufer).

    Returns:
        ``{inv_id: PvModulWert}``. Σ der Werte == Gesamterzeugung.

    **Teil-Lücke ohne Aggregat:**

    Messen nur MANCHE Module und es gibt kein Aggregat, behalten die messenden
    Module ihren Wert (Regel 1), die übrigen bleiben ``QUELLE_FEHLT``/``0.0``;
    ``ist_vollstaendig`` ist ``False``.

    ⭐ **Seit N-626 (Gernot 04.10.2026) ist die Anzeige-Summe dieses Monats die
    Σ der vorhandenen Werte** (``pv_monatswerte.pv_teilsumme_je_monat``): „Ein
    möglicher Modul-Ausfall kann ja auch korrekt sein … der Daten-Checker muss
    darauf hinweisen." Die Monats-Fakten tragen sie mit ``pv_vollstaendig=False``,
    der Hinweis „Teilsumme" und der Daten-Checker sagen, dass ein Wert fehlt.
    Bis dahin galt N42 — die Anlagen-Summe zeigte NICHTS, und **Σ pv_strings ≠
    Σ /monatsdaten/aggregiert** war gewollt; jetzt stimmen beide überein
    (``test_wurzelmuster_p2_symmetrie.py``). Die **Prüf-Leser** (Daten-Checker-
    PV-Map, Import-Vorschau, ``gesamt_pv_kwh``) bleiben bei „nur vollständig":
    gegen eine Teilsumme geprüft, meldeten sie Abweichungen, die es nicht gibt.
    """
    if not module:
        return {}

    gemessen_summe = sum(m.eigen_kwh or 0.0 for m in module if m.eigen_kwh is not None)
    luecken = [m for m in module if m.eigen_kwh is None]

    verteilt: dict[int, float] = {}
    if luecken and aggregat_kwh is not None:
        # Der Rest, den die gemessenen Module NICHT erklären. Negativ = die
        # Messungen übersteigen das Aggregat; dann ist eine der beiden Quellen
        # falsch. Auf 0 klemmen statt negative kWh zu verteilen — die Meldung
        # ist Sache des Daten-Checkers, nicht dieser Formel.
        rest = max(0.0, aggregat_kwh - gemessen_summe)
        verteilt = verteile_basis_kwh_nach_kwp(
            rest, [(m.inv_id, m.leistung_kwp) for m in luecken]
        )

    out: dict[int, PvModulWert] = {}
    for m in module:  # Eingabe-Reihenfolge erhalten (deterministisch)
        if m.eigen_kwh is not None:
            # #352: Ein gespeicherter Wert, der selbst schon eine Zerlegung ist,
            # bleibt als Zahl unverändert — aber er behauptet keine Messung.
            # Sonst kürt das String-Ranking einen „besten String" aus Zahlen,
            # die per Konstruktion proportional zur kWp sind, und der
            # Daten-Checker meldet OK statt INFO.
            out[m.inv_id] = PvModulWert(
                m.inv_id,
                m.eigen_kwh,
                QUELLE_VERTEILT if m.eigen_ist_abgeleitet else QUELLE_GEMESSEN,
            )
        elif aggregat_kwh is not None:
            out[m.inv_id] = PvModulWert(
                m.inv_id, verteilt.get(m.inv_id, 0.0), QUELLE_VERTEILT
            )
        else:
            out[m.inv_id] = PvModulWert(m.inv_id, 0.0, QUELLE_FEHLT)
    return out


def bkw_kinder_luecken_kwh(
    *,
    bkw_kwh: float,
    kinder: list[PvModul],
) -> dict[int, float]:
    """Stufe 2 der P7-Präzedenz: ein Balkonkraftwerk füllt die Lücken SEINER Kinder (N-266/E4).

    Hängen `pv-module` unter einem Balkonkraftwerk, ist dessen Monatswert für sie,
    was der Anlagenwert für die ganze Anlage ist: ein Aggregat, das nur die Lücken
    füllt. Gemessene Kinder behalten ihren Wert, die übrigen teilen
    ``max(0, bkw_kwh − Σ gemessene Kinder)`` nach kWp (``resolve_pv_je_modul``).

    ⚠ **Alle** Kinder übergeben, nicht nur die lückenhaften — sonst wäre Σ der
    gemessenen 0 und eine Lücke bekäme den ganzen BKW-Wert.

    Returns:
        ``{inv_id: kWh}`` nur für die Kinder ohne eigenen Wert (``eigen_kwh is
        None``). Ohne Lücke ``{}``. Der Wert ist eine kWp-Zerlegung, keine Messung —
        der Aufrufer markiert ihn so (#352).

    Zwei Aufrufer, eine Formel: ``services/pv_monatswerte.py::lade_pv_je_monat``
    (abgeschlossener Monat) und ``api/routes/aktueller_monat/aggregation.py``
    (Monat ohne Abschluss, N-627).
    """
    luecken = [k.inv_id for k in kinder if k.eigen_kwh is None]
    if not luecken:
        return {}
    verteilt = resolve_pv_je_modul(aggregat_kwh=bkw_kwh, module=kinder)
    return {i: verteilt[i].pv_erzeugung_kwh for i in luecken if i in verteilt}


#: Typen der PV-Träger (wie ``erzeuger_traeger.PV_MODUL_TYP``/``BKW_TYP``; hier als Literal, weil
#: ``erzeuger_traeger`` dieses Modul nicht kennt und das Modul ohne Importe auskommt).
_PV_MODUL = "pv-module"
_BKW = "balkonkraftwerk"


@dataclass(frozen=True)
class PvTraeger:
    """Ein im Zeitraum aktiver PV-Erzeuger — nur Stammdaten (Zeitfilter aktiv · Anschaffung · Stilllegung beim
    Aufrufer). ``kwp`` ist das Gewicht der Verteilung (``services/pv_monatswerte._kwp_gewicht``, dasselbe wie im
    Monat); ``parent_id`` das Balkonkraftwerk eines Modul-Kinds (N-266)."""

    inv_id: int
    typ: str
    kwp: float
    parent_id: Optional[int] = None


@dataclass(frozen=True)
class PvZeitraum:
    """Ergebnis von ``loese_pv_zeitraum_auf``.

    ``werte``: ``{inv_id: kWh}`` je Träger mit Wert (Module samt Kindern, selbst tragende Balkonkraftwerke; ein an
    seine Kinder abgetretenes BKW trägt keinen Eintrag). ``verteilt``: Marke ``kwp_anteil`` (kWp-Anteil am Rest des
    Anlagenzählers bzw. des BKW). ``fehlt``: Module ohne Wert und ohne Anlagenzähler (Teilsumme). ``geraete_kwh``:
    Σ ``werte``. ``bilanz_kwh``: die PV-Summe der Bilanz (W2-R3: Σ Geräte). ``wandlungsverluste_kwh``: ``Σ Geräte −
    Anlagenzähler``, wenn positiv (N-588 — nur geführt, nicht bewertet; E4b); 0 bei Σ Geräte ≤ Anlagenzähler,
    ``None`` ohne Anlagenzähler."""

    werte: dict[int, float]
    verteilt: frozenset
    fehlt: frozenset
    geraete_kwh: float
    bilanz_kwh: Optional[float]
    wandlungsverluste_kwh: Optional[float]


def wandlungsverluste_prozent(verluste_kwh: Optional[float], strings_kwh: Optional[float]) -> Optional[float]:
    """Wandlungsverluste in Prozent der Summe der String-Zähler (HA-Bauform E4b, N-588 — geführt, nicht bewertet).

    ``verluste_kwh`` = ``max(0, Σ Geräte − Anlagenzähler)`` eines Zeitraums (``PvZeitraum.wandlungsverluste_kwh``),
    ``strings_kwh`` = Σ der Geräte-Werte DESSELBEN Zeitraums (``PvZeitraum.geraete_kwh`` — die Zähler vor dem
    Wechselrichter). Beispiel: Strings 630 kWh, Anlagenzähler 594 ⇒ 36 ÷ 630 × 100 = 5,71 %. Für mehrere Monate
    ruft der Aufrufer die Funktion mit den Summen der Monate, die BEIDE Größen tragen (``quote_paarweise``).
    Der Client rechnet das nicht nach (ADR-001, Klasse ``check:kennwert-roh``/``co2-roh``).

    ``None`` ohne Verluste-Wert (kein Anlagenzähler, keine Kanal-Deckung) oder ohne positive String-Summe.
    """
    if verluste_kwh is None or strings_kwh is None or strings_kwh <= 0:
        return None
    return verluste_kwh / strings_kwh * 100


def loese_pv_zeitraum_auf(
    *,
    traeger: list[PvTraeger],
    eigen: dict[int, float],
    anlagenzaehler_kwh: Optional[float],
) -> PvZeitraum:
    """Die PV eines beliebigen Zeitraums aus Zeitraum-Differenzen — **Weg 2** (Bauplan HA-Bauform §6b, Entscheid
    Gernot 06.10.2026). Dieselbe Regel für Tag, Monat und jeden anderen Zeitraum; sie ist die Monatsregel P7
    (``resolve_pv_je_modul`` und Stufe 2 ``bkw_kinder_luecken_kwh``, wie ``services/pv_monatswerte.lade_pv_je_monat``
    sie für den gespeicherten Monat anwendet) auf die Δ des Zeitraums verallgemeinert — keine zweite Fassung:

    * **W2-R1 Quelle je Gerät.** ``eigen`` trägt je Gerät das Δ seines Kanals, nur wenn der Kanal den Zeitraum voll
      deckt (Abdeckungsregel der Lese-Schicht); fehlende Stunden im Inneren stecken in der Folgestunde (wie HA). Ein
      Gerät mit Δ trägt es — gemessene Werte werden nie skaliert.
    * **W2-R2 Rest des Anlagenzählers.** ``max(0, Anlagenzähler − Σ gemessene Geräte)`` geht EINMAL je Zeitraum nach
      kWp auf die Geräte ohne Δ (``resolve_pv_je_modul``). Kinder eines Balkonkraftwerks sind dessen Lücke — am Tag
      wie im Monat: ein abtretendes BKW mit Δ füllt die Lücken seiner Kinder (``bkw_kinder_luecken_kwh``, Marke
      ``kwp_anteil``) und gilt damit als gemessen; ein selbst tragendes BKW mit Δ ist ein gemessenes Gerät (N-611),
      ohne Δ eine Lücke des Anlagenzählers (N-621).
    * **W2-R3 PV-Summe** (Wortlaut Master 06.10.2026 nach Halt H2; B2 vom 05.10. und P7 gelten): die PV-Summe eines
      Zeitraums ist Σ der Geräte-Werte nach R1/R2 — der Anlagenzähler ist NUR Füller, nie Ersatz der Geräte-Summe.
      ``wandlungsverluste_kwh`` = ``max(0, Σ Geräte − Anlagenzähler)`` wird geführt, nicht bewertet (N-588, Klasse
      offen bis nach dem Umbau); ohne Anlagenzähler ``None``. Einzige Ausnahme: ohne jeden PV-Träger hat der Zähler
      niemanden zu füllen und ist die Summe (wie Fassung (b)).
    * **W2-R5 Untergrenze 0 einmal je Zeitraum** (die Klemmung des Rests in ``resolve_pv_je_modul``).

    W2-R4 (Entweder-oder) wirkt VOR dieser Funktion — beim Aufrufer über ``resolve_either_or_eintraege`` mit
    „Kanal deckt voll" (``core/berechnungen/bilanz_zeitraum.py``).

    Ersetzt für Kanal-Zeiträume die Tagesregeln #406 „Wahl je Tag" (``pv_tages_praezedenz.waehle_pv_quelle``) und
    N-623 (``gemessene_tageswerte``, ``loese_aggregat_tag_auf``); die gelten weiter für den Bestandspfad (Lesart 1).
    """
    module = [t for t in traeger if t.typ == _PV_MODUL]
    bkws = [t for t in traeger if t.typ == _BKW]
    bkw_ids = {b.inv_id for b in bkws}
    abgetreten = {m.parent_id for m in module if m.parent_id in bkw_ids}

    roh: dict[int, float] = {m.inv_id: eigen[m.inv_id] for m in module if m.inv_id in eigen}
    abgeleitet: set[int] = set()
    # Stufe 2 (N-266/E4): das abtretende BKW füllt die Lücken SEINER Kinder — alle Kinder übergeben.
    for b in bkws:
        if b.inv_id in abgetreten and b.inv_id in eigen:
            kinder = [m for m in module if m.parent_id == b.inv_id]
            for k_id, kwh in bkw_kinder_luecken_kwh(
                bkw_kwh=eigen[b.inv_id],
                kinder=[PvModul(k.inv_id, k.kwp, roh.get(k.inv_id)) for k in kinder],
            ).items():
                roh[k_id] = kwh
                abgeleitet.add(k_id)
    selbst = [b for b in bkws if b.inv_id not in abgetreten]
    anlagenwert = anlagenzaehler_kwh
    empfaenger: list[PvTraeger] = []
    if anlagenzaehler_kwh is not None:
        # N-611: das Δ der selbst tragenden BKW ist ein gemessenes Gerät — es mindert den Rest.
        anlagenwert = max(0.0, anlagenzaehler_kwh - sum(eigen[b.inv_id] for b in selbst if b.inv_id in eigen))
        empfaenger = [b for b in selbst if b.inv_id not in eigen]          # N-621
    aufgeloest = resolve_pv_je_modul(
        aggregat_kwh=anlagenwert,
        module=[PvModul(m.inv_id, m.kwp, roh.get(m.inv_id), m.inv_id in abgeleitet) for m in module]
        + [PvModul(b.inv_id, b.kwp, None) for b in empfaenger],
    )
    werte: dict[int, float] = {}
    verteilt: set[int] = set()
    fehlt: set[int] = set()
    for i, w in aufgeloest.items():
        if w.quelle == QUELLE_FEHLT:
            fehlt.add(i)
            continue
        werte[i] = w.pv_erzeugung_kwh
        if w.quelle == QUELLE_VERTEILT:
            verteilt.add(i)
    for b in selbst:
        if b.inv_id in eigen:
            werte[b.inv_id] = eigen[b.inv_id]
    geraete = sum(werte.values())
    if werte or eigen:
        bilanz: Optional[float] = geraete
    elif not traeger and anlagenzaehler_kwh is not None:
        # Kein PV-Träger gepflegt: der Zähler hat niemanden zu füllen und ist die einzige Aussage (wie Fassung (b)).
        bilanz = anlagenzaehler_kwh
    else:
        bilanz = None
    verluste = max(0.0, geraete - anlagenzaehler_kwh) if anlagenzaehler_kwh is not None else None
    return PvZeitraum(werte, frozenset(verteilt), frozenset(fehlt), geraete, bilanz, verluste)


def ist_vollstaendig(werte: dict[int, PvModulWert]) -> bool:
    """Ist die Σ der aufgelösten Werte eine **Anlagensumme**?

    Nur wenn jedes Modul aufgelöst ist (gemessen oder verteilt). Bleibt eines
    auf ``fehlt``, ist die Σ eine Teilsumme — als Anzeige-Summe gezeigt nur mit
    der Kennzeichnung ``pv_vollstaendig=False`` (N-626), als Prüfgröße gar nicht
    (N42). Leere Modul-Liste → ``False``: „keine
    Module" ist keine vollständige Erzeugung, sondern gar keine Aussage.
    """
    return bool(werte) and all(w.quelle != QUELLE_FEHLT for w in werte.values())


def gesamt_pv_kwh(
    *,
    aggregat_kwh: Optional[float],
    module: list[PvModul],
) -> Optional[float]:
    """Gesamt-PV eines Monats nach derselben Präzedenz wie ``resolve_pv_je_modul``.

    ``None`` = **unvollständig** (mindestens ein Modul unaufgelöst) — bewusst
    keine Teilsumme, siehe ``ist_vollstaendig``. Sonst Σ der Pro-Modul-Werte,
    deckungsgleich mit ``Σ resolve_pv_je_modul`` (Σ-Invariante).
    """
    werte = resolve_pv_je_modul(aggregat_kwh=aggregat_kwh, module=module)
    if not ist_vollstaendig(werte):
        return None
    return sum(w.pv_erzeugung_kwh for w in werte.values())


def klassifiziere_pv_monat(
    *,
    n_aktive_module: int,
    n_gemessen: int,
    aggregat_kwh: Optional[float],
    n_abgeleitet: int = 0,
) -> str:
    """Klassifiziert die PV-Quellenlage eines Monats (Daten-Checker-SoT).

    Liefert ``STATUS_OK`` (gemessen vollständig), ``STATUS_VERTEILT`` (Aggregat
    deckt fehlende Module ab → INFO), ``STATUS_TEIL_LUECKE`` (ein Teil der
    Module gemessen, kein Aggregat → WARNING) oder ``STATUS_FEHLT`` (gar keine
    PV-Quelle → ERROR). Diese 3-stufige Konvention (Gernot 2026-06-06) wird vom
    Daten-Checker auf Severity gemappt.

    Args:
        n_gemessen: Module mit einem **gemessenen** Pro-Modul-Wert.
        n_abgeleitet: Module, deren gespeicherter Wert selbst eine
            kWp-Zerlegung ist (#352). Sie decken den Monat ab wie ein
            Aggregat — deshalb ``STATUS_VERTEILT`` und **nicht**
            ``STATUS_FEHLT``: die Zahlen sind da, sie sind nur gerechnet.
            Ohne diesen Zweig würde ein vollständig importierter Monat nach
            der Markierung plötzlich als ERROR gemeldet.
    """
    if n_aktive_module <= 0:
        return STATUS_FEHLT
    if n_gemessen >= n_aktive_module:
        return STATUS_OK
    if aggregat_kwh is not None:
        return STATUS_VERTEILT
    if n_gemessen + n_abgeleitet >= n_aktive_module and n_abgeleitet > 0:
        return STATUS_VERTEILT
    if n_gemessen > 0:
        return STATUS_TEIL_LUECKE
    return STATUS_FEHLT
