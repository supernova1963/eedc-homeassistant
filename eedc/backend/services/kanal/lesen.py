"""Lese-Schicht der Kanalstatistik — vier Lesefunktionen, jede mit Abdeckungs-Auskunft (HA-Bauform E3, Bauplan §5).

**Stand E3: gebaut und geprüft, von keiner Sicht, Route oder den Monats-Fakten benutzt** (Umhängen ist E4; der
Wächter ``test_kanal_lesen_waechter.py`` hält fest, dass außerhalb ``services/kanal/`` niemand importiert). Die
Wächter-Hilfe aus E2 (``kanalwert``/``delta``) ist hierin aufgegangen.

Vier Funktionen, je als Stapel über mehrere Kanäle in EINEM Aufruf (eine Monatsreihe über viele Kanäle kostet
nicht Kanäle × Abfragen):

* ``zeitraum(_stapel)`` — Δ über ``[von, bis)`` mit ``gedeckt_von``, ``gedeckt_bis``, ``rand_spanne``;
* ``reihe(_stapel)`` — dasselbe je Intervall aufeinanderfolgender Grenzen, über n+1 Randstände (kein Vollscan
  mit ``GROUP BY`` über die Zeit, Konzept §3 „Fehlweg");
* ``stunden(_stapel)`` — Zuwachs je Stunde (HAs ``change``): fehlt eine Zeile, steht ihre Menge in der nächsten
  belegten Stunde, und die Stunde trägt ihre Spanne;
* ``mittel(_stapel)`` — mean/min/max wie HAs ``_get_max_mean_min_statistic`` (Mittel der Stundenmittel, Minimum
  der Minima, Maximum der Maxima), mit der Einheit des Kanals (keine Umrechnung in der Schicht).

**Zeit.** Grenzen sind Parameter in absoluter Zeit (Unix-Sekunden); die Schicht kennt keine Tages- oder
Monatsdefinition (die steht in ``fenster.py``). Eine Zeile ``start_ts = H`` trägt den Stand am ENDE ihrer Stunde
(``H + 3600``) bzw. das Mittel von ``[H, H+1h)``. Der **Stand vor t** ist die letzte Zeile mit ``start_ts < t`` —
HAs ``_statistics_at_time`` wörtlich (``recorder_statistics.py:2464/2502``). Δ über ``[von, bis)`` = Stand vor
``bis`` − Stand vor ``von`` = Σ HA-``change`` der Zeilen mit ``von ≤ start_ts < bis``.

**Kanalwert je Art** (Bauplan §3a, Nachtrag „Leseregel ``stand``"): ``sum`` ⇒ ``sum + offset`` der für die Stunde
geltenden Quelle (``kanal_quelle`` mit dem größten ``gueltig_ab ≤ start_ts``); ``stand`` ⇒ ``state`` roh — die Zahl
auf dem Zähler —, ``offset`` dient nur der Differenz über eine Quellgrenze; ``mean`` ⇒ wörtlich. Eine Zeile, deren
Wertspalte leer ist, ist kein Stand und zählt nirgends mit.

**Abdeckung — die eine Regel** (ersetzt N-92, N-472, N-121, R-9, R-11; Gegenprüfung W4, G2). Ein Mengen-/Stand-Kanal
deckt ``[von, bis)`` voll, wenn

* (a) er einen Stand VOR ``von`` hat. Liegt seine erste Zeile bei oder nach ``von``, beginnt der Zeitraum vor dem
  Kanal ⇒ ``beginnt_nach_von``. HA nennt dort still eine Teilmenge (Anfangsstand 0, ``recorder_statistics.py:1720f.``);
  eedc nicht.
* (b) sein letzter Stand das Ende erreicht: es gibt eine Zeile mit ``start_ts ≥ ende − 3600``, wobei ``ende`` =
  ``min(bis, soll_ende(jetzt))``. Für einen abgeschlossenen Zeitraum ist das die Zeile der letzten Stunde vor ``bis``
  oder eine spätere; für den laufenden reicht der Stand, den der Stundenlauf schon geschrieben haben muss
  (``SCHREIBVERZUG_S``) ⇒ sonst ``endet_vor_bis``.
  **Benannte Eigenschaft — Zähler ohne Nachtzeilen** (Entscheid Master 06.10.): ein Zähler, für den HA nachts keine
  Zeile schreibt (Wechselrichter „nicht verfügbar", Matrix-Form F08), erreicht das Ende des eben beendeten und des
  laufenden Tages erst mit seiner Morgenzeile — die Quellenwahl nimmt dann nachts (gemessen 23:10–07:10) den Bestand und
  morgens wieder den Kanal. Die Werte sind in beiden Quellen gleich (beide haben nachts nichts). Gewollt: eine
  „Ruhe-Toleranz" könnte einen schlafenden Zähler nicht von einem toten unterscheiden. Beobachtet in E4 an F08a/F08b.
* (c) der Zeitraum nicht feiner ist als die Spanne, in der einer seiner Ränder liegt ⇒ sonst ``feiner_als_spanne``.

Eine **Spanne** ist der Abstand zweier aufeinanderfolgender Stände (``start_ts`` − ``start_ts`` der Vorzeile;
lückenlos 3600). ``rand_spanne`` meldet die größere der beiden Spannen über die RÄNDER: die, in der ``von`` liegt
(Stand vor ``von`` bis zur ersten Zeile ab ``von``), und die, in der ``bis`` — beim laufenden Zeitraum das Soll-Ende —
liegt. Nur sie kann Regel (c) auslösen: eine Spanne ganz im Inneren ist nie länger als der Zeitraum. Eine Lücke im
Inneren ist keine fehlende Abdeckung (ihre Menge steht in der Folgestunde, wie in HA); sie meldet ``stunden()`` je Stunde
(``Stundenwert.spanne``). Eine eigene ``luecken()`` gibt es bewusst nicht: die innere Lücke findet nur, wer jede Zeile des
Zeitraums liest — genau der Vollscan, den das Modell vermeidet (gemessen im Bericht E3: 1,9 s für die Monatsreihe über
22 Kanäle gegen 27 ms ohne; Entscheid Master L1/Option A).
**Regel (c) ist ein Sicherheitsnetz:** Kanäle mit dünnen Punkten (ein Stand je Monat) entstehen im ersten Paket nicht —
Importe und Ablesungen bleiben Monatsabschluss (Bauplan §3b). Sollte je einer entstehen, nennt ein Tag in einer
Monatsspanne keinen Wert.

``delta`` steht nur bei voller Abdeckung. Sonst ist es ``None`` (kein stiller Teilwert) und ``teil_delta`` nennt den
Δ über ``[gedeckt_von, gedeckt_bis)`` — die Stände, zwischen denen wirklich gemessen ist (Teilsumme mit Marke,
ADR-002/P4). ``gedeckt_von``/``gedeckt_bis`` sind immer die Zeitpunkte der beiden Stände, über die der (Teil-)Δ
gebildet ist; bei lückenlosen Rändern gleich ``von``/``bis``.

Für einen **Mittelwert-Kanal** gilt dieselbe Regel mit der Lesart „eine Zeile = ihre eigene Stunde": (a) eine Zeile
bei oder vor ``von``, (b) wie oben, die Spannen sind die fehlenden Stunden zwischen zwei Zeilen.

**Abfrage-Budget** (Probe ``test_kanal_lesen.py``): jeder Stapel-Aufruf ist EINE SQL-Anweisung, unabhängig von der
Länge des Zeitraums und der Zahl der Kanäle. ``zeitraum``/``reihe`` lesen dabei nur die Randstände — zwei Index-Schritte
je Kanal und Grenze (``ORDER BY start_ts … LIMIT 1``), kein ``SCAN`` der Tabelle; die Zahl der gelesenen Zeilen hängt
nicht von der Länge ab (Probe über den Abfrageplan und die Zahl der SQLite-VM-Schritte). ``mittel`` und ``stunden``
lesen naturgemäß die Zeilen des Zeitraums (Mittel bzw. je Stunde ein Wert) — über den Index-Bereich, wie HA.

Schwesterdateien: ``fenster.py``, ``quellenwahl.py``, ``monatsraster.py``; Schreiber ``schreiber.py``,
``nachfuellen.py``, ``konsistenz.py``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_MEAN, ART_STAND, ART_SUM, Kanal

_STUNDE = 3600

#: **Schreibverzug des Stundenlaufs** (Annahme E3, Bericht): der :05-Lauf schreibt die Zeile, die zur vollen Stunde H
#: endet, um H:05. Ein laufender Zeitraum verlangt den Stand erst, wenn auch EIN verpasster Lauf (HA hatte die Zeile um
#: :05 noch nicht, ein Lauf fiel aus) beim nächsten nachgeholt sein müsste, plus 5 Minuten für die Laufzeit:
#: 60 + 5 + 5 Minuten. Der laufende Tag gilt damit nicht jede Stunde ein paar Minuten lang als „ungedeckt" (die Quelle
#: wechselte sonst stündlich), und ein Kanal, der zwei Läufe in Folge nichts bekam, gilt nicht mehr als deckend.
SCHREIBVERZUG_S = 70 * 60

GRUND_KEIN_KANAL = "kein_kanal"
GRUND_BEGINNT_NACH_VON = "beginnt_nach_von"
GRUND_ENDET_VOR_BIS = "endet_vor_bis"
GRUND_FEINER_ALS_SPANNE = "feiner_als_spanne"
GRUND_KEINE_ZEILE = "keine_zeile"


def soll_ende(jetzt: int) -> int:
    """Bis wohin der Stundenlauf zum Zeitpunkt ``jetzt`` geschrieben haben muss (volle Stunde, absolute Zeit)."""
    return ((jetzt - SCHREIBVERZUG_S) // _STUNDE) * _STUNDE


def _jetzt(jetzt: Optional[int]) -> int:
    return int(time.time()) if jetzt is None else int(jetzt)


# ── Ergebnisse ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Zeitraum:
    """Δ eines Mengen- oder Stand-Kanals über ``[von, bis)`` samt Abdeckung."""

    key: str
    art: str
    einheit: str
    von: int
    bis: int
    #: Δ — NUR bei voller Abdeckung, sonst ``None``.
    delta: Optional[float]
    #: Δ über ``[gedeckt_von, gedeckt_bis)``, wenn NICHT voll gedeckt (Teilsumme mit Marke); sonst ``None``.
    teil_delta: Optional[float]
    #: Zeitpunkt des Anfangs- bzw. Endstands, über die der (Teil-)Δ gebildet ist.
    gedeckt_von: Optional[int]
    gedeckt_bis: Optional[int]
    #: Die größere der beiden Spannen (Sekunden) über die Ränder — die, in der ``von`` liegt, und die, in der ``bis``
    #: bzw. das Soll-Ende liegt; lückenlos 3600. Lücken im Inneren nennt ``stunden()``.
    rand_spanne: Optional[int]
    voll: bool
    grund: Optional[str]
    laufend: bool
    #: Kanalwert am Anfangs-/Endstand (``sum``: ``sum + offset``; ``stand``: ``state`` roh).
    wert_von: Optional[float] = None
    wert_bis: Optional[float] = None


@dataclass(frozen=True)
class Stundenwert:
    """Eine belegte Stunde: Stand und Zuwachs seit dem vorigen Stand (HAs ``change``)."""

    start_ts: int
    #: Zuwachs seit dem vorigen Stand; ``None`` ohne vorigen Stand (erste Zeile des Kanals).
    change: Optional[float]
    #: Kanalwert dieser Zeile (``sum``: ``sum + offset``; ``stand``: ``state`` roh).
    wert: float
    familie: str
    #: Abstand zum vorigen Stand in Sekunden (lückenlos 3600; größer ⇒ der Zuwachs trägt die fehlenden Stunden).
    spanne: Optional[int]


@dataclass(frozen=True)
class Stunden:
    key: str
    art: str
    einheit: str
    von: int
    bis: int
    werte: list[Stundenwert]
    gedeckt_von: Optional[int]
    gedeckt_bis: Optional[int]
    groesste_spanne: Optional[int]
    voll: bool
    grund: Optional[str]
    laufend: bool


@dataclass(frozen=True)
class Mittel:
    """mean/min/max eines Mittelwert-Kanals über ``[von, bis)`` — wörtlich, in der Einheit des Kanals."""

    key: str
    einheit: str
    von: int
    bis: int
    #: NUR bei voller Abdeckung, sonst ``None``.
    mean: Optional[float]
    min: Optional[float]
    max: Optional[float]
    #: Dieselben Größen über die vorhandenen Stunden, wenn NICHT voll gedeckt.
    teil_mean: Optional[float]
    teil_min: Optional[float]
    teil_max: Optional[float]
    stunden: int
    gedeckt_von: Optional[int]
    gedeckt_bis: Optional[int]
    #: Die größere der Spannen über die Ränder (fehlende Stunden, in die ``von`` bzw. das Ende fällt).
    rand_spanne: Optional[int]
    voll: bool
    grund: Optional[str]
    laufend: bool


# ── Kanäle ──────────────────────────────────────────────────────────────────


async def kanaele_laden(db: AsyncSession, anlage_id: int, keys: Iterable[str]) -> dict[str, Kanal]:
    """Die Kanäle ``keys`` einer Anlage in EINER Abfrage; ein Schlüssel ohne Kanal fehlt im Ergebnis."""
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}
    return {k.key: k for k in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key.in_(keys)))
    )).scalars().all()}


def _kanal_json(kanaele: Sequence[Kanal]) -> str:
    return json.dumps([[k.id, k.art] for k in kanaele])


#: Die Wertspalte je Art, als SQL-Ausdruck über die Spalte ``art`` der Kanal-Liste (eine Anweisung für alle Arten).
def _wert_sql(tab: str, art: str = "k.art") -> str:
    return f"(CASE {art} WHEN 'stand' THEN {tab}.state WHEN 'mean' THEN {tab}.mean ELSE {tab}.sum END)"


def _offset_sql(kid: str, ts: str) -> str:
    return (f'(SELECT q."offset" FROM kanal_quelle q WHERE q.kanal_id = {kid} AND q.gueltig_ab <= {ts} '
            f"ORDER BY q.gueltig_ab DESC LIMIT 1)")


# ── Randstände je Kanal und Grenze (die eine Anweisung von zeitraum/reihe) ──

_RAND_SQL = f"""
WITH k(kid, art) AS (
    SELECT json_extract(value, '$[0]'), json_extract(value, '$[1]') FROM json_each(:kanaele)
), g(j, t) AS (
    SELECT key, value FROM json_each(:grenzen)
), p AS (
    SELECT k.kid, k.art, g.j, g.t,
        (SELECT s.rowid FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts < g.t
            AND {_wert_sql('s')} IS NOT NULL ORDER BY s.start_ts DESC LIMIT 1) AS vor_rid,
        (SELECT s.rowid FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts >= g.t
            AND {_wert_sql('s')} IS NOT NULL ORDER BY s.start_ts ASC LIMIT 1) AS nach_rid
    FROM k CROSS JOIN g
)
SELECT p.kid, p.j,
    v.start_ts, {_wert_sql('v', 'p.art')}, {_offset_sql('p.kid', 'v.start_ts')},
    n.start_ts, {_wert_sql('n', 'p.art')}, {_offset_sql('p.kid', 'n.start_ts')}
FROM p
LEFT JOIN kanal_statistik v ON v.rowid = p.vor_rid
LEFT JOIN kanal_statistik n ON n.rowid = p.nach_rid
"""

@dataclass
class _Stand:
    start_ts: int
    roh: float
    offset: float

    @property
    def ende(self) -> int:
        return self.start_ts + _STUNDE


def _stand(ts, roh, offset) -> Optional[_Stand]:
    if ts is None or roh is None:
        return None
    return _Stand(int(ts), float(roh), float(offset or 0.0))


def _kanalwert(art: str, st: Optional[_Stand]) -> Optional[float]:
    """Kanalwert eines Standes: ``sum`` ⇒ ``sum + offset``; ``stand`` ⇒ ``state`` roh (F-58)."""
    if st is None:
        return None
    return st.roh + st.offset if art == ART_SUM else st.roh


def _brueckenwert(st: _Stand) -> float:
    """Der Wert, über den ein Δ gebildet wird: Rohwert + ``offset`` (beim Stand die Brücke über eine Quellgrenze)."""
    return st.roh + st.offset


async def _randstaende(db: AsyncSession, kanaele: Sequence[Kanal], grenzen: Sequence[int]):
    res = await db.execute(text(_RAND_SQL), {"kanaele": _kanal_json(kanaele), "grenzen": json.dumps(list(grenzen))})
    vor: dict[tuple[int, int], Optional[_Stand]] = {}
    nach: dict[tuple[int, int], Optional[_Stand]] = {}
    for kid, j, v_ts, v_roh, v_off, n_ts, n_roh, n_off in res.all():
        vor[(kid, grenzen[j])] = _stand(v_ts, v_roh, v_off)
        nach[(kid, grenzen[j])] = _stand(n_ts, n_roh, n_off)
    return vor, nach


def _pruefe_grenzen(grenzen: Sequence[int]) -> list[int]:
    g = [int(x) for x in grenzen]
    if len(g) < 2 or any(b <= a for a, b in zip(g, g[1:])):
        raise ValueError(f"Grenzen müssen mindestens zwei streng aufsteigende Zeitpunkte sein: {grenzen!r}")
    return g


def _nur_mengen(kanaele: Sequence[Kanal]) -> None:
    for k in kanaele:
        if k.art not in (ART_SUM, ART_STAND):
            raise ValueError(f"Kanal {k.key}: ein Mittelwert hat kein Δ — mittel() benutzen")


def _zeitraum_aus(k: Kanal, von: int, bis: int, a: Optional[_Stand], f: Optional[_Stand], b: Optional[_Stand],
                  nach_bis: Optional[_Stand], ende_vor: Optional[_Stand], ende_nach: Optional[_Stand],
                  jetzt: int) -> Zeitraum:
    """Ein Intervall aus den Randständen: ``a`` = Stand vor ``von``, ``f`` = erste Zeile ab ``von``, ``b`` = Stand
    vor ``bis``, ``nach_bis`` = erste Zeile ab ``bis``; ``ende_vor``/``ende_nach`` dasselbe am Ende der Messung
    (``bis``, beim laufenden Zeitraum das Soll-Ende)."""
    se = soll_ende(jetzt)
    laufend = bis > se
    ende = min(bis, se)
    erreicht = (b is not None and b.start_ts >= ende - _STUNDE) or nach_bis is not None

    # Spannen über die beiden Ränder: die, in der `von` liegt, und die, in der das Ende (bis bzw. Soll-Ende) liegt.
    spannen: list[int] = []
    # Die Spanne über `von` zählt auch, wenn ihre Folgezeile erst nach `bis` liegt (der Zeitraum fällt ganz in die Lücke):
    # sonst nennte ein laufender Zeitraum, der am Soll-Ende beginnt, fünf Minuten lang still Δ 0 (Nachmessung E3, 2c).
    if a is not None and f is not None:
        spannen.append(f.start_ts - a.start_ts)
    if ende > von and ende_vor is not None and ende_nach is not None and ende_vor.ende < ende:
        spannen.append(ende_nach.start_ts - ende_vor.start_ts)
    rand = max(spannen) if spannen else None

    if a is not None:
        anfang = a
    elif f is not None and f.start_ts < bis:
        anfang = f
    else:
        anfang = None
    rechenbar = anfang is not None and b is not None and b.start_ts >= anfang.start_ts
    roh_delta = _brueckenwert(b) - _brueckenwert(anfang) if rechenbar else None

    if b is None:
        grund = GRUND_KEINE_ZEILE          # kein Stand im oder vor dem Zeitraum
    elif a is None:
        grund = GRUND_BEGINNT_NACH_VON
    elif not erreicht:
        grund = GRUND_ENDET_VOR_BIS
    elif rand is not None and rand > bis - von:
        grund = GRUND_FEINER_ALS_SPANNE
    else:
        grund = None
    voll = grund is None
    return Zeitraum(
        key=k.key, art=k.art, einheit=k.einheit, von=von, bis=bis,
        delta=roh_delta if voll else None,
        teil_delta=None if voll else roh_delta,
        gedeckt_von=anfang.ende if rechenbar else None,
        gedeckt_bis=b.ende if rechenbar else None,
        rand_spanne=rand, voll=voll, grund=grund, laufend=laufend,
        wert_von=_kanalwert(k.art, anfang) if rechenbar else None,
        wert_bis=_kanalwert(k.art, b) if rechenbar else None,
    )


# ── zeitraum / reihe ────────────────────────────────────────────────────────


async def reihe_stapel(
    db: AsyncSession, kanaele: Sequence[Kanal], grenzen: Sequence[int], *, jetzt: Optional[int] = None,
) -> dict[str, list[Zeitraum]]:
    """Je Kanal je Intervall ``[g_i, g_i+1)`` ein ``Zeitraum`` — über die n+1 Randstände (und, liegt das Soll-Ende
    mitten in einem Intervall, einen weiteren dort), EINE Anweisung gesamt."""
    g = _pruefe_grenzen(grenzen)
    _nur_mengen(kanaele)
    if not kanaele:
        return {}
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    punkte = sorted(set(g) | ({se} if g[0] < se < g[-1] else set()))
    vor, nach = await _randstaende(db, kanaele, punkte)
    out: dict[str, list[Zeitraum]] = {}
    for k in kanaele:
        liste = []
        for j in range(len(g) - 1):
            von, bis = g[j], g[j + 1]
            ende = min(bis, se)
            liste.append(_zeitraum_aus(
                k, von, bis, vor.get((k.id, von)), nach.get((k.id, von)), vor.get((k.id, bis)),
                nach.get((k.id, bis)), vor.get((k.id, ende)), nach.get((k.id, ende)), jetzt,
            ))
        out[k.key] = liste
    return out


async def reihe(db: AsyncSession, kanal: Kanal, grenzen: Sequence[int], *, jetzt: Optional[int] = None) -> list[Zeitraum]:
    return (await reihe_stapel(db, [kanal], grenzen, jetzt=jetzt))[kanal.key]


async def zeitraum_stapel(
    db: AsyncSession, kanaele: Sequence[Kanal], von: int, bis: int, *, jetzt: Optional[int] = None,
) -> dict[str, Zeitraum]:
    """Δ und Abdeckung über ``[von, bis)`` für mehrere Kanäle — eine Anweisung, gleich welche Länge."""
    return {key: liste[0] for key, liste in (await reihe_stapel(db, kanaele, [von, bis], jetzt=jetzt)).items()}


async def zeitraum(db: AsyncSession, kanal: Kanal, von: int, bis: int, *, jetzt: Optional[int] = None) -> Zeitraum:
    return (await zeitraum_stapel(db, [kanal], von, bis, jetzt=jetzt))[kanal.key]


# ── stunden ─────────────────────────────────────────────────────────────────

_STUNDEN_SQL = f"""
WITH k(kid, art) AS (
    SELECT json_extract(value, '$[0]'), json_extract(value, '$[1]') FROM json_each(:kanaele)
), r AS (
    SELECT k.kid, k.art,
        (SELECT MAX(s.start_ts) FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts < :von
            AND {_wert_sql('s')} IS NOT NULL) AS vor_ts,
        (SELECT MIN(s.start_ts) FROM kanal_statistik s WHERE s.kanal_id = k.kid AND s.start_ts >= :bis
            AND {_wert_sql('s')} IS NOT NULL) AS nach_ts
    FROM k
)
SELECT r.kid, r.nach_ts, s.start_ts, {_wert_sql('s', 'r.art')}, s.familie, {_offset_sql('r.kid', 's.start_ts')}
FROM r LEFT JOIN kanal_statistik s ON s.kanal_id = r.kid AND s.start_ts >= COALESCE(r.vor_ts, :von)
    AND s.start_ts < :bis AND {_wert_sql('s', 'r.art')} IS NOT NULL
ORDER BY r.kid, s.start_ts
"""


async def stunden_stapel(
    db: AsyncSession, kanaele: Sequence[Kanal], von: int, bis: int, *, jetzt: Optional[int] = None,
) -> dict[str, Stunden]:
    """Zuwachs je belegter Stunde in ``[von, bis)`` für mehrere Kanäle — eine Anweisung.

    HAs ``change``: der Zuwachs einer Zeile ist ihr Wert minus der vorige Stand (auch vor ``von``). Fehlt eine Zeile,
    hat die Stunde keinen Eintrag, und ihre Menge steht in der nächsten belegten Stunde, die dann ihre ``spanne``
    (> 3600) trägt. Abdeckung (a)/(b) wie ``zeitraum``; eine Stunde mit großer Spanne bleibt stehen und nennt sie.
    """
    _nur_mengen(kanaele)
    if not kanaele:
        return {}
    if bis <= von:
        raise ValueError(f"leerer Zeitraum: [{von}, {bis})")
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    res = await db.execute(text(_STUNDEN_SQL), {"kanaele": _kanal_json(kanaele), "von": von, "bis": bis})
    zeilen: dict[int, list] = {k.id: [] for k in kanaele}
    nach_ts: dict[int, Optional[int]] = {}
    for kid, n_ts, ts, roh, familie, off in res.all():
        nach_ts[kid] = n_ts
        if ts is not None:
            zeilen[kid].append((int(ts), float(roh), familie, float(off or 0.0)))
    out: dict[str, Stunden] = {}
    for k in kanaele:
        z = zeilen[k.id]
        vor = z[0] if z and z[0][0] < von else None
        im = z[1:] if vor is not None else z
        werte: list[Stundenwert] = []
        vorher = vor
        for ts, roh, familie, off in im:
            change = (roh + off) - (vorher[1] + vorher[3]) if vorher is not None else None
            spanne = ts - vorher[0] if vorher is not None else None
            werte.append(Stundenwert(ts, change, roh + off if k.art == ART_SUM else roh, familie, spanne))
            vorher = (ts, roh, familie, off)
        laufend = bis > se
        ende = min(bis, se)
        letzte = im[-1][0] if im else (vor[0] if vor else None)
        erreicht = (letzte is not None and letzte >= ende - _STUNDE) or nach_ts.get(k.id) is not None
        spannen = [w.spanne for w in werte if w.spanne is not None]
        if letzte is not None and nach_ts.get(k.id) is not None and letzte + _STUNDE < bis:
            spannen.append(nach_ts[k.id] - letzte)
        if vor is None and not im:
            grund = GRUND_KEINE_ZEILE
        elif vor is None:
            grund = GRUND_BEGINNT_NACH_VON
        elif not erreicht:
            grund = GRUND_ENDET_VOR_BIS
        else:
            grund = None
        anfang = vor if vor is not None else (im[0] if im else None)
        out[k.key] = Stunden(
            key=k.key, art=k.art, einheit=k.einheit, von=von, bis=bis, werte=werte,
            gedeckt_von=anfang[0] + _STUNDE if anfang else None,
            gedeckt_bis=letzte + _STUNDE if letzte is not None else None,
            groesste_spanne=max(spannen) if spannen else None,
            voll=grund is None, grund=grund, laufend=laufend,
        )
    return out


async def stunden(db: AsyncSession, kanal: Kanal, von: int, bis: int, *, jetzt: Optional[int] = None) -> Stunden:
    return (await stunden_stapel(db, [kanal], von, bis, jetzt=jetzt))[kanal.key]


# ── mittel ──────────────────────────────────────────────────────────────────

def _naechste(op: str, wert: str, richtung: str) -> str:
    return (f"(SELECT x.start_ts FROM kanal_statistik x WHERE x.kanal_id = k.kid AND x.start_ts {op} {wert} "
            f"AND x.mean IS NOT NULL ORDER BY x.start_ts {richtung} LIMIT 1)")


_MITTEL_SQL = f"""
WITH k(kid) AS (SELECT value FROM json_each(:kanaele))
SELECT k.kid, COUNT(s.start_ts), MIN(s.start_ts), MAX(s.start_ts), AVG(s.mean), MIN(s.min), MAX(s.max),
    {_naechste('<', ':von', 'DESC')}, {_naechste('>=', ':bis', 'ASC')},
    {_naechste('<', ':ende', 'DESC')}, {_naechste('>=', ':ende', 'ASC')}
FROM k LEFT JOIN kanal_statistik s ON s.kanal_id = k.kid AND s.start_ts >= :von AND s.start_ts < :bis
    AND s.mean IS NOT NULL
GROUP BY k.kid
"""


async def mittel_stapel(
    db: AsyncSession, kanaele: Sequence[Kanal], von: int, bis: int, *, jetzt: Optional[int] = None,
) -> dict[str, Mittel]:
    """mean/min/max über ``[von, bis)`` für mehrere Mittelwert-Kanäle — EINE Anweisung (Aggregat über den
    Index-Bereich des Zeitraums, dazu die Nachbarzeilen an den Rändern). Wörtlich in ``kanal.einheit``; keine
    Umrechnung. Eine Mittelwert-Zeile ist ihre eigene Stunde: (a) heißt „eine Zeile bei oder vor ``von``", eine
    Spanne sind die fehlenden Stunden zwischen zwei Zeilen; ``rand_spanne`` meldet die über ``von`` und über das Ende."""
    for k in kanaele:
        if k.art != ART_MEAN:
            raise ValueError(f"Kanal {k.key}: Art {k.art} — mittel() gilt nur für Mittelwert-Kanäle")
    if not kanaele:
        return {}
    if bis <= von:
        raise ValueError(f"leerer Zeitraum: [{von}, {bis})")
    jetzt = _jetzt(jetzt)
    se = soll_ende(jetzt)
    laufend = bis > se
    ende = min(bis, se)
    zeilen = {r[0]: r[1:] for r in (await db.execute(text(_MITTEL_SQL), {
        "kanaele": json.dumps([k.id for k in kanaele]), "von": von, "bis": bis, "ende": ende,
    })).all()}
    out: dict[str, Mittel] = {}
    for k in kanaele:
        n, erste, letzte, m_mean, m_min, m_max, vor_ts, nach_ts, ende_vor, ende_nach = (
            zeilen.get(k.id) or (0, None, None, None, None, None, None, None, None, None))
        n = int(n or 0)
        # (a) eine Zeile bei oder vor `von`
        beginnt = (erste is not None and erste <= von) or vor_ts is not None
        spannen: list[int] = []
        f_von = erste if erste is not None else nach_ts          # erste Zeile ab `von`
        if vor_ts is not None and f_von is not None and f_von > von:
            spannen.append(f_von - vor_ts)                        # die Spanne, in der `von` liegt
        if ende > von and ende_vor is not None and ende_nach is not None and ende_vor + _STUNDE < ende:
            spannen.append(ende_nach - ende_vor)                  # die Spanne, in der das Ende liegt
        if not spannen and n >= 2:
            spannen.append(_STUNDE)                               # beide Ränder lückenlos
        rand = max(spannen) if spannen else None
        letzte_bekannt = max(x for x in (letzte, vor_ts, -1) if x is not None)
        erreicht = letzte_bekannt >= ende - _STUNDE or nach_ts is not None
        if not beginnt:
            grund = GRUND_KEINE_ZEILE if nach_ts is None else GRUND_BEGINNT_NACH_VON
        elif not erreicht:
            grund = GRUND_ENDET_VOR_BIS
        elif rand is not None and rand > bis - von:
            grund = GRUND_FEINER_ALS_SPANNE
        else:
            # Auch ein laufender Zeitraum, für den noch keine Stunde fällig ist: voll, aber ohne Mittel (0 Stunden).
            grund = None
        voll = grund is None
        out[k.key] = Mittel(
            key=k.key, einheit=k.einheit, von=von, bis=bis,
            mean=m_mean if voll else None, min=m_min if voll else None, max=m_max if voll else None,
            teil_mean=None if voll else m_mean, teil_min=None if voll else m_min,
            teil_max=None if voll else m_max,
            stunden=n,
            gedeckt_von=erste, gedeckt_bis=letzte + _STUNDE if letzte is not None else None,
            rand_spanne=rand, voll=voll, grund=grund, laufend=laufend,
        )
    return out


async def mittel(db: AsyncSession, kanal: Kanal, von: int, bis: int, *, jetzt: Optional[int] = None) -> Mittel:
    return (await mittel_stapel(db, [kanal], von, bis, jetzt=jetzt))[kanal.key]


__all__ = [
    "GRUND_BEGINNT_NACH_VON", "GRUND_ENDET_VOR_BIS", "GRUND_FEINER_ALS_SPANNE", "GRUND_KEIN_KANAL",
    "GRUND_KEINE_ZEILE", "Mittel", "SCHREIBVERZUG_S", "Stunden", "Stundenwert", "Zeitraum", "kanaele_laden",
    "mittel", "mittel_stapel", "reihe", "reihe_stapel", "soll_ende", "stunden", "stunden_stapel", "zeitraum",
    "zeitraum_stapel",
]
