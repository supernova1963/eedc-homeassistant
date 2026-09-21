"""Fenster-Rechner — die EINE Formel hinter „wann soll ich das einschalten?"

**Warum eine Funktion und nicht fünf.** Stufe 3 von `KONZEPT-EEDC-AT-HA.md` §5
beantwortet fünfmal dieselbe Frage mit anderen Eingängen: Warmwasser (P4),
„bestes Fenster für x kWh" (P5), Heizfenster (P7), Kühlfenster (P8), sonstiger
Verbraucher (P9). Jedes Stück nimmt eine Stundenreihe „Kosten je kWh", eine
Menge, eine Dauer und eine Frist und liefert ein Fenster mit Betrag. Fünf
eigene Rechner wären die Klasse hinter der Drift-Inventur vom 31.07.2026 —
sechs Befunde, **kein** Rechenfehler im Layer, aber sechs Read-Sites, die
selbst falteten. Deshalb steht die Rechnung hier einmal (ADR-001), und die
fünf Stücke rufen sie.

**Was hier NICHT steht.** Keine DB-Zugriffe, keine Zeitzonen-Logik, keine
Sensor-Namen. Die Routen sammeln die Eingänge (Preisreihe, Überschussreihe,
Verbrauchsreihe) und geben sie als Listen herein; was ein Slot bedeutet,
entscheidet der Aufrufer.

## Slot-Konvention

Ein Slot ist eine **volle Stunde** und trägt den Index seiner Stunde in der
Prozesszone (0…23 für heute, 24…47 für morgen — dieselbe Erweiterung, die
`rang_profil_morgen` im Preis-Export benutzt). Die Reihen `preis`,
`ueberschuss_kwh` und `verbrauch_kwh` müssen **dieselbe Länge** haben; eine
Stunde ohne Preis trägt `None` und ist für ein Fenster nicht benutzbar
(ADR-002/P4: fehlender Eingang ⇒ kein Wert, keine 0).

⚠ **Am Ende der Sommerzeit hat ein Tag 23 oder 25 Stunden.** Diese Datei
prüft deshalb **nie** auf `len(...) == 24` (F-6) — sie rechnet über die
Länge, die sie bekommt.

## Der effektive Preis einer zusätzlichen kWh (`kosten_profil`)

Eine zusätzliche Last in einer Stunde mit Überschuss kostet nichts, solange der
Überschuss reicht: sie verdrängt Einspeisung, keinen Netzbezug. Reicht er nur
für einen Teil, ist der Mischpreis fällig.

    kosten[h] = preis[h] × (1 − min(1, ueberschuss_kwh[h] ÷ menge_im_slot))

`menge_im_slot` ist die Menge, die der Aufrufer in dieser Stunde zusätzlich
fahren will — beim mengenneutralen Kostenprofil (P5) ist das **1 kWh**, sonst
die Menge je Stunde des jeweiligen Stücks.

⛔ **Die Einspeisevergütung wird bewusst NICHT gegengerechnet.** Sie wäre ein
zweiter Preis aus einer zweiten Quelle in derselben Zahl; der Export trägt
genau **einen** Preis je Stunde, und das ist der, den `eedc_preis_aktuell_cent`
schon trägt. Wer die entgangene Vergütung berücksichtigen will, tut das in
seiner Automation — die Zahl dafür (`eedc_preis_*`) liegt daneben.

## Vorschlag, kein Urteil

Keine Funktion hier entscheidet etwas. Sie nennen ein Fenster und einen Betrag;
ob jemand danach handelt, entscheidet die Automation des Anwenders
(`feedback_eedc_ist_nicht_die_strom_polizei`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

__all__ = [
    "Arbitrage",
    "Fenster",
    "UeberschussBlock",
    "Verteilung",
    "arbitrage_vorschlag",
    "bestes_fenster",
    "kosten_profil",
    "ueberschuss_bloecke",
    "verteile_auf_guenstigste",
]


@dataclass(frozen=True)
class Fenster:
    """Ein zusammenhängender Block von `dauer_h` Stunden mit minimalen Kosten.

    ``ab``/``bis`` sind Slot-Indizes; ``bis`` ist **exklusiv** (ein 2-h-Fenster
    ab 13 endet bei 15). ``kosten_cent_kwh`` ist der Mittelwert der Slot-Kosten
    im Fenster — mengenneutral, damit derselbe Wert für 1 kWh und für 9 kWh
    gilt. ``delta_vs_jetzt`` ist die Differenz zum Slot ``ab_h`` des Aufrufs
    (negativ = billiger als jetzt); ``None``, wenn „jetzt" keinen Preis trägt.
    """

    ab: int
    bis: int
    kosten_cent_kwh: float
    delta_vs_jetzt: Optional[float] = None


@dataclass(frozen=True)
class UeberschussBlock:
    """Zusammenhängende Stunden, in denen die Erzeugung den Verbrauch übersteigt."""

    ab: int
    bis: int
    stunden: int
    min_kw: float
    summe_kwh: float


@dataclass(frozen=True)
class Verteilung:
    """Das Ergebnis von :func:`verteile_auf_guenstigste` (P7).

    ``stunden`` sind die gewählten Slots, ``ersparnis_cent`` die Differenz
    zwischen dem ungeschobenen Profil und der verschobenen Menge. ``None``
    kommt hier nicht vor: ist nichts zu holen, ist die Ersparnis 0.
    """

    stunden: tuple[int, ...]
    kosten_alt_cent: float
    kosten_neu_cent: float
    ersparnis_cent: float


@dataclass(frozen=True)
class Arbitrage:
    """Ein Netzlade-Vorschlag (P3) — Menge, Stunden und Betrag."""

    menge_kwh: float
    lade_stunden: tuple[int, ...]
    ersparnis_cent: float


def _als_float(wert) -> float:
    """Eine Zahl aus einem Slot-Eintrag; ``None`` und Unsinn werden 0,0.

    Bewusst hier und nicht bei jedem Aufrufer: die Reihen kommen aus
    Sensorwerten, Prognosen und JSON-Feldern, und eine fehlende Menge ist
    dort **immer** „nichts", nie „unbekannt" — die Unbekanntheit trägt allein
    die Preisreihe (``None``), weil nur sie ein Fenster unbenutzbar macht.
    """
    try:
        return float(wert or 0.0)
    except (TypeError, ValueError):
        return 0.0


def kosten_profil(
    preis_cent: Sequence[Optional[float]],
    ueberschuss_kwh: Sequence[float],
    menge_je_slot_kwh: Sequence[float] | float = 1.0,
) -> list[Optional[float]]:
    """Der effektive Preis je kWh für eine **zusätzliche** Last, Slot für Slot.

    Args:
        preis_cent: Slot-Preis in ct/kWh; ``None``, wo kein Preis vorliegt.
        ueberschuss_kwh: prognostizierter Überschuss je Slot (kWh, ≥ 0).
        menge_je_slot_kwh: die Menge, um die es geht — eine Zahl (für alle
            Slots gleich, Default 1 kWh = mengenneutral) oder eine Reihe.

    Returns:
        Liste derselben Länge wie ``preis_cent``; ``None`` bleibt ``None``.

    **Warum der Überschuss die Kosten senkt und nicht die Menge.** Eine
    Automation fragt „was kostet mich diese kWh, wenn ich sie **jetzt**
    beziehe?". In einer Überschussstunde ist die Antwort 0 ct, solange der
    Überschuss reicht — der Strom ist da, er würde sonst eingespeist. Diese
    Sicht hält die Größe mengenneutral vergleichbar; eine gekürzte Menge täte
    das nicht.
    """
    n = len(preis_cent)
    if isinstance(menge_je_slot_kwh, (int, float)):
        mengen: Sequence[float] = [float(menge_je_slot_kwh)] * n
    else:
        mengen = [_als_float(m) for m in menge_je_slot_kwh]

    out: list[Optional[float]] = []
    for h in range(n):
        p = preis_cent[h] if h < len(preis_cent) else None
        if p is None:
            out.append(None)
            continue
        menge = mengen[h] if h < len(mengen) else 0.0
        ueber = _als_float(ueberschuss_kwh[h]) if h < len(ueberschuss_kwh) else 0.0
        anteil = min(1.0, ueber / menge) if menge > 0 else 0.0
        out.append(round(float(p) * (1.0 - anteil), 4))
    return out


def bestes_fenster(
    kosten: Sequence[Optional[float]],
    dauer_h: int,
    ab_h: int = 0,
    frist_h: Optional[int] = None,
) -> Optional[Fenster]:
    """Der zusammenhängende Block aus ``dauer_h`` Slots mit minimalen Σ-Kosten.

    Args:
        kosten: Slot-Kosten je kWh (aus :func:`kosten_profil`); ``None`` =
            unbenutzbar.
        dauer_h: Länge des Blocks in Slots (≥ 1).
        ab_h: frühester Slot (einschließlich) — „ab jetzt".
        frist_h: spätester Slot, der noch **im** Fenster liegen darf
            (einschließlich); ``None`` = bis zum Ende der Reihe.

    Returns:
        ``Fenster`` oder ``None``, wenn kein Block aus ``dauer_h``
        aufeinanderfolgenden Slots **mit Preis** in den Rahmen passt
        (ADR-002/P4 — lieber kein Sensor als ein erfundener).

    ⚠ **Gleichstand geht an das frühere Fenster.** Zwei Blöcke mit
    identischen Kosten sind rechnerisch gleichwertig; der frühere lässt der
    Automation mehr Spielraum und ist die Wahl, die ein Mensch träfe.
    """
    if dauer_h < 1:
        return None
    ende = len(kosten) - 1 if frist_h is None else min(frist_h, len(kosten) - 1)
    start = max(0, ab_h)
    bester: Optional[Fenster] = None
    for a in range(start, ende - dauer_h + 2):
        block = list(kosten[a:a + dauer_h])
        if len(block) < dauer_h or any(k is None for k in block):
            continue
        mittel = sum(float(k) for k in block) / dauer_h
        if bester is None or mittel < bester.kosten_cent_kwh - 1e-9:
            bester = Fenster(ab=a, bis=a + dauer_h, kosten_cent_kwh=round(mittel, 4))
    if bester is None:
        return None
    jetzt = kosten[ab_h] if 0 <= ab_h < len(kosten) else None
    if jetzt is None:
        return bester
    return Fenster(
        ab=bester.ab,
        bis=bester.bis,
        kosten_cent_kwh=bester.kosten_cent_kwh,
        delta_vs_jetzt=round(bester.kosten_cent_kwh - float(jetzt), 4),
    )


def ueberschuss_bloecke(
    pv_kwh: Sequence[float],
    verbrauch_kwh: Sequence[float],
) -> list[UeberschussBlock]:
    """Alle zusammenhängenden Stunden mit ``pv > verbrauch`` (P2).

    Ein Block endet, sobald eine Stunde den Verbrauch nicht mehr deckt. Er
    trägt seine schwächste Stunde (``min_kw``) mit, weil danach entschieden
    wird, ob eine Last überhaupt hineinpasst — die Σ allein verschweigt eine
    Stunde, in der fast nichts übrig ist.
    """
    n = min(len(pv_kwh), len(verbrauch_kwh))
    bloecke: list[UeberschussBlock] = []
    lauf: list[tuple[int, float]] = []

    def _schliessen():
        if not lauf:
            return
        werte = [w for _, w in lauf]
        bloecke.append(UeberschussBlock(
            ab=lauf[0][0],
            bis=lauf[-1][0] + 1,
            stunden=len(lauf),
            min_kw=round(min(werte), 2),
            summe_kwh=round(sum(werte), 2),
        ))

    for h in range(n):
        rest = _als_float(pv_kwh[h]) - _als_float(verbrauch_kwh[h])
        if rest > 0:
            lauf.append((h, rest))
        else:
            _schliessen()
            lauf = []
    _schliessen()
    return bloecke


def verteile_auf_guenstigste(
    kosten: Sequence[Optional[float]],
    menge_je_stunde_kwh: Sequence[float],
    stunden: Iterable[int],
) -> Optional[Verteilung]:
    """Dieselbe Menge auf die günstigsten der erlaubten Stunden schieben (P7).

    Die Wärmepumpe fährt ihr Profil; verschoben wird **nicht** die Arbeit,
    sondern ihr Zeitpunkt. Deshalb bleibt die Gesamtmenge gleich, und die
    Ersparnis ist die Differenz der Kosten vorher/nachher.

    Args:
        kosten: Slot-Kosten je kWh; ``None`` = unbenutzbar.
        menge_je_stunde_kwh: das erwartete Profil (dieselbe Länge wie
            ``kosten``).
        stunden: die Slots, die überhaupt in Frage kommen (z. B. die Heizzeit).

    Returns:
        ``Verteilung`` oder ``None``, wenn keine benutzbare Stunde übrig ist.

    ⚠ **Das ist eine Obergrenze, kein Versprechen.** Wie weit eine Anhebung
    trägt, entscheidet die Regelung der Wärmepumpe — eedc kennt weder
    Heizkurve noch Speichervermögen des Gebäudes (Konzept §5/P7). Die Zahl
    sagt, was der Preisunterschied hergäbe, nicht was die Anlage kann.
    """
    erlaubt = [
        h for h in sorted(set(stunden))
        if 0 <= h < len(kosten) and kosten[h] is not None
    ]
    if not erlaubt:
        return None

    menge_gesamt = sum(
        _als_float(menge_je_stunde_kwh[h])
        for h in erlaubt
        if h < len(menge_je_stunde_kwh)
    )
    kosten_alt = sum(
        _als_float(menge_je_stunde_kwh[h]) * float(kosten[h])
        for h in erlaubt
        if h < len(menge_je_stunde_kwh)
    )

    # Die Menge wandert in die billigsten Stunden — so viel, wie dort im
    # Profil überhaupt Platz hat. Die Kappung auf das Maximum des Profils
    # verhindert, dass eine einzige Stunde rechnerisch den ganzen Tag trägt:
    # eine Wärmepumpe hat eine Leistungsgrenze, und die ist ihr eigenes
    # Stundenmaximum.
    max_je_stunde = max(
        (_als_float(menge_je_stunde_kwh[h]) for h in erlaubt if h < len(menge_je_stunde_kwh)),
        default=0.0,
    )
    if max_je_stunde <= 0:
        return Verteilung(tuple(), 0.0, 0.0, 0.0)

    rest = menge_gesamt
    kosten_neu = 0.0
    gewaehlt: list[int] = []
    for h in sorted(erlaubt, key=lambda x: (float(kosten[x]), x)):
        if rest <= 1e-9:
            break
        nimm = min(rest, max_je_stunde)
        kosten_neu += nimm * float(kosten[h])
        rest -= nimm
        gewaehlt.append(h)

    return Verteilung(
        stunden=tuple(sorted(gewaehlt)),
        kosten_alt_cent=round(kosten_alt, 2),
        kosten_neu_cent=round(kosten_neu, 2),
        ersparnis_cent=round(max(0.0, kosten_alt - kosten_neu), 2),
    )


def arbitrage_vorschlag(
    kosten: Sequence[Optional[float]],
    defizit_kwh: Sequence[float],
    frei_kwh: float,
    wirkungsgrad_prozent: float,
    guenstig: Sequence[bool],
    ab_h: int = 0,
) -> Optional[Arbitrage]:
    """Netzladung in günstigen Stunden, Entladung gegen das teuerste Defizit (P3).

    Args:
        kosten: Slot-Kosten je kWh; ``None`` = unbenutzbar.
        defizit_kwh: was in diesem Slot aus dem Netz käme (kWh, ≥ 0) — die
            Menge, die eine Entladung ersetzen kann.
        frei_kwh: freie Speicherkapazität jetzt (kWh).
        wirkungsgrad_prozent: Round-Trip-Wirkungsgrad des Speichers.
        guenstig: je Slot, ob er als günstig gilt (dieselbe Markierung, die
            `eedc_preis_rang` trägt — **nicht** hier neu gebildet).
        ab_h: frühester Slot.

    Returns:
        ``Arbitrage`` oder ``None``, wenn nichts zu holen ist (Ersparnis ≤ 0,
        kein Platz, keine günstige Stunde, kein Defizit danach). **Kein
        Vorschlag über 0 kWh** — ein Sensor mit 0 wäre eine Aussage, die der
        Anwender als „geprüft und lohnt nicht" liest, und genau das ist der
        Fall, den ADR-002/P4 als fehlenden Sensor abbildet.

    **Die Rechnung.** Jede geladene kWh kostet ``preis_guenstig ÷ η`` (es muss
    mehr hinein, als herauskommt) und ersetzt später eine kWh zum Preis der
    teuersten Defizitstunde **nach** dem Laden. Die Ersparnis ist die Summe
    der positiven Differenzen; Paare, bei denen sie negativ wäre, kommen nicht
    vor — sie werden schlicht nicht gebildet.
    """
    eta = max(0.01, float(wirkungsgrad_prozent or 0.0) / 100.0)
    platz = max(0.0, float(frei_kwh or 0.0))
    if platz <= 0:
        return None

    lade_kandidaten = sorted(
        (
            h for h in range(max(0, ab_h), len(kosten))
            if kosten[h] is not None
            and h < len(guenstig) and bool(guenstig[h])
        ),
        key=lambda h: (float(kosten[h]), h),
    )
    if not lade_kandidaten:
        return None

    # Entlade-Kandidaten: Defizitstunden nach der FRÜHESTEN Ladestunde,
    # absteigend nach Preis. Die Reihenfolge ist die physikalische Bedingung —
    # was nicht geladen ist, kann nicht entladen werden.
    frueheste_ladung = min(lade_kandidaten)
    entlade_kandidaten = sorted(
        (
            h for h in range(frueheste_ladung + 1, len(kosten))
            if kosten[h] is not None
            and h < len(defizit_kwh) and _als_float(defizit_kwh[h]) > 0
        ),
        key=lambda h: (-float(kosten[h]), h),
    )
    if not entlade_kandidaten:
        return None

    geladen = 0.0
    ersparnis = 0.0
    lade_stunden: list[int] = []
    lade_index = 0
    for h in entlade_kandidaten:
        if platz - geladen <= 1e-9 or lade_index >= len(lade_kandidaten):
            break
        lade_h = lade_kandidaten[lade_index]
        if lade_h >= h:
            # Diese günstige Stunde liegt nach dem Bedarf — sie hilft ihm nicht.
            lade_index += 1
            continue
        preis_ein = float(kosten[lade_h]) / eta
        preis_aus = float(kosten[h])
        if preis_aus - preis_ein <= 0:
            break   # der nächste Ladepreis ist nicht billiger, der nächste Bedarf nicht teurer
        menge = min(_als_float(defizit_kwh[h]), platz - geladen)
        if menge <= 1e-9:
            continue
        geladen += menge
        ersparnis += menge * (preis_aus - preis_ein)
        if lade_h not in lade_stunden:
            lade_stunden.append(lade_h)

    if geladen <= 1e-9 or ersparnis <= 0:
        return None
    return Arbitrage(
        menge_kwh=round(geladen, 2),
        lade_stunden=tuple(sorted(lade_stunden)),
        ersparnis_cent=round(ersparnis, 1),
    )
