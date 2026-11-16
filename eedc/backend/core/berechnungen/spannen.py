"""Spannen gebündelter Stunden — Zählerlücken wie HA (Vorlage Fassung 7, R2/R6/§2).

**Worum es geht.** Fehlt in Home Assistant eine Stundenzeile eines Zählers,
zeigt HA die Energie der Lücke in der ersten Stunde danach (Stand minus letzter
*vorhandener* Stand, beliebig weit zurück). eedc legt je Stunde genau das ab —
und merkt sich in ``TagesEnergieProfil.spannen``, wie viele **reale** Stunden
die Menge einer Achse trägt (nur für n > 1). Diese Datei ist der eine Ort für
die Begriffe, die daraus folgen:

* **Achsen** und welche Energiefluss-Kategorie auf welche Achse fällt (R2).
* **R6** — wann ein Stunden-Hausverbrauch gebildet werden darf.
* **§2** — die drei Leser-Helfer: *Stunde gegen Stunde* lässt eine gebündelte
  Zeile aus; *Tag gegen Tag* lässt **beide** Tage um ein Mitternachtsbündel mit
  Energie aus (D ist um dieselbe Energie zu niedrig, um die D+1 zu hoch ist).

⛔ **Die Energie zählt in jeder Summe.** Keiner dieser Helfer entfernt Energie
aus einer Tages- oder Monatssumme; sie beantworten nur, ob eine Zeile bzw. ein
Tag als Einzelwert gegen einen anderen gestellt werden darf.

DB-frei (ADR-001): nimmt beliebige Objekte mit ``stunde`` und ``spannen``.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

#: Die Achsen einer Stundenzeile, in der Reihenfolge der Spalten
#: (`pv_kw` · `einspeisung_kw` · `netzbezug_kw` · `batterie_kw` ·
#: `waermepumpe_kw` · `wallbox_kw` · `verbrauch_sonstiges`), dazu `v2h`:
#: #110 (Konzept §2, E2) — die V2H-Rückspeisung hat **keine** Spalte der
#: Stundenzeile; ihre Achse trägt nur Spannen und Verworfen (R4), der Wert
#: steht als Tagesgröße im Rollup (`komponenten_kwh["v2h_<id>"]`).
ACHSEN: tuple[str, ...] = (
    "pv", "einspeisung", "netzbezug", "batterie", "waermepumpe", "wallbox", "sonstige", "v2h",
)

#: Energiefluss-Kategorie (`snapshot/keys._categorize_counter`) → Achse.
#: `erzeugung_sonstiges` gehört zur PV-Achse, weil `pv_kw` ihn trägt.
_ACHSE_JE_KATEGORIE: dict[str, str] = {
    "pv": "pv",
    "erzeugung_sonstiges": "pv",
    "einspeisung": "einspeisung",
    "netzbezug": "netzbezug",
    "ladung_batterie": "batterie",
    "entladung_batterie": "batterie",
    "verbrauch_wp": "waermepumpe",
    "ladung_wallbox": "wallbox",
    "verbrauch_eauto": "wallbox",
    "verbrauch_sonstiges": "sonstige",
    "entladung_v2h": "v2h",
}

#: Die Achsen, die ein Plausibilitäts-Deckel schützt (R3). Alle übrigen haben
#: nur die Negativ-Regel (R4).
ACHSEN_MIT_DECKEL: frozenset[str] = frozenset({"pv", "einspeisung"})


#: Obergrenze des Deckel-Fensters aus Nullzeilen (Vorlage §10, Nachträge II).
DECKEL_FENSTER_MAX_STUNDEN = 24


def deckel_fenster_stunden(n: int, stunden_seit_aenderung: float) -> int:
    """R3, Nachträge II (24.05.2026): **das Fenster des Deckels ist die Zeit seit
    der letzten Änderung des Standes**, nicht die Spanne n.

    Ein eingefrorener Zähler liefert Zeilen mit Delta 0, die HA nicht von echten
    Nullen unterscheidet; der Nachtrag steht danach in EINER Zeile mit n = 1
    (Lab 24.05.2026: 13–15 Uhr still, um 16 Uhr +37 kWh). Für die **Menge**
    folgt eedc HA (die Energie bleibt in der Nachtragsstunde, `spannen` bleibt
    n); für die **Plausibilität** zählt die Zeit, in der der Stand unverändert
    war. Nie kleiner als n (ein Bündel über eine Lücke behält sein R3-Fenster),
    der Anteil aus Nullzeilen höchstens bis 24 Stunden.
    """
    n = max(1, int(n or 1))
    seit = max(float(stunden_seit_aenderung or 0), float(n))
    return max(n, min(DECKEL_FENSTER_MAX_STUNDEN, round(seit)))


def deckel_fenster_je_slot(slots: Iterable[tuple[int, float, int]]) -> dict[int, int]:
    """Deckel-Fenster je belegtem Slot einer Reihe ``(h, delta, n)`` (ein Sensor
    oder eine Achse eines Tages). Nullzeilen verlängern das Fenster der nächsten
    Änderung um ihre reale Dauer (Slot-Abstand; eine Nullzeile trägt nach R2
    selbst n = 1, auch über eine Lücke); eine Änderung (Delta ≠ 0, auch ein
    Rücksprung) beendet den Lauf. Die erste Zeile reicht mit ihrem n bis zum
    Anker („im Tagesfenster ab Anker")."""
    out: dict[int, int] = {}
    lauf = 0.0
    h_vor: Optional[int] = None
    for h, delta, n in sorted(slots, key=lambda s: s[0]):
        n = max(1, int(n or 1))
        if delta is not None and abs(delta) <= 1e-9:
            lauf += (h - h_vor) if h_vor is not None else n
            out[h] = n
        else:
            out[h] = deckel_fenster_stunden(n, n + lauf)
            lauf = 0.0
        h_vor = h
    return out


def achse_der_kategorie(kategorie: Optional[str]) -> Optional[str]:
    """Achse einer Energiefluss-Kategorie — ``None`` für eine unbekannte."""
    if kategorie is None:
        return None
    return _ACHSE_JE_KATEGORIE.get(kategorie)


def spanne(spannen: Optional[Mapping[str, int]], achse: str) -> int:
    """n der Achse in einer Zeile — 1, wenn die Zeile keine Spanne für sie trägt. Immer ≥ 1: eine Nullzeile eines
    Erfassungs-Stillstands (n = 0, ``spanne_roh``) zählt hier als ihre eine Stunde (Deckel-Fenster, Mitternachtsbündel)."""
    if not spannen:
        return 1
    n = spannen.get(achse)
    return int(n) if n and n > 1 else 1


def spanne_roh(spannen: Optional[Mapping[str, int]], achse: str) -> int:
    """n der Achse **wie gespeichert bzw. gemischt** — 1 ohne Eintrag, sonst der Eintrag selbst, auch **0**: die Zeile
    trägt keine eigene Menge, ihre Energie steht in einer späteren Zeile (Erfassungs-Stillstand, N-799 E-3)."""
    if not spannen:
        return 1
    n = spannen.get(achse)
    return 1 if n is None else int(n)


def spannen_gebuendelt(spannen: Optional[Mapping[str, int]], achse: str) -> bool:
    """**Stunde gegen Stunde** über das Spannen-Dict einer Zeile: n ≠ 1 (``spanne_roh``) — die Zeile trägt mehr als
    eine reale Stunde (Lücke, Nachtrag eines Stillstands) oder keine (Nullzeile eines Stillstands). Der eine Helfer
    der Leser, die das Dict statt der Zeile in der Hand haben (``zeile_gebuendelt`` für die Zeile)."""
    return spanne_roh(spannen, achse) != 1


def verbrauch_spannen_passen(
    spannen: Optional[Mapping[str, int]], *, batterie_da: bool,
) -> bool:
    """R6: darf der Stunden-Hausverbrauch aus dieser Zeile gebildet werden?

    Nur wenn **pv**, **netzbezug** und **einspeisung** dieselbe Spanne haben —
    sonst stünde Energie aus verschiedenen Zeiträumen in einer Differenz.
    Die **Batterie** zählt als 0, wenn sie in der Stunde fehlt (Entscheid
    29.08., wie `stundenbilanz.stunden_verbrauch_kwh`); trägt sie aber eine
    **andere** Spanne, gehört ihre Energie nicht dieser Stunde ⇒ ``False``.

    Ob die drei Achsen überhaupt einen Wert haben, prüft
    `stunden_verbrauch_kwh` selbst.
    """
    n_pv = spanne(spannen, "pv")
    if spanne(spannen, "netzbezug") != n_pv or spanne(spannen, "einspeisung") != n_pv:
        return False
    if batterie_da and spanne(spannen, "batterie") != n_pv:
        return False
    return True


# ── §2 · Leser-Helfer ───────────────────────────────────────────────────────

#: Achse → Spalte der Stundenzeile, an der „trägt Energie" abgelesen wird.
_SPALTE_JE_ACHSE: dict[str, str] = {
    "pv": "pv_kw",
    "einspeisung": "einspeisung_kw",
    "netzbezug": "netzbezug_kw",
    "batterie": "batterie_kw",
    "waermepumpe": "waermepumpe_kw",
    "wallbox": "wallbox_kw",
}

#: Die Achsen, aus denen der Stunden-Hausverbrauch gebildet wird (R6).
VERBRAUCHS_ACHSEN: tuple[str, ...] = ("pv", "netzbezug", "einspeisung", "batterie")


def zeile_gebuendelt(row: Any, achse: str) -> bool:
    """**Stunde gegen Stunde:** trägt diese Zeile auf der Achse nicht genau
    eine reale Stunde (n ≠ 1, ``spanne_roh``)? — mehr als eine (Lücke,
    Nachtrag eines Erfassungs-Stillstands) oder keine (Nullzeile eines
    Stillstands, N-799 E-3). Dann ist sie keine Stichprobe dieser Stunde
    (Korrekturprofil, Verbrauchsprofil, Speicher-Stundenrechnungen, Spitzen …)
    — ihre Energie zählt trotzdem in jeder Summe."""
    return spannen_gebuendelt(getattr(row, "spannen", None), achse)


def verbrauch_gebuendelt(row: Any) -> bool:
    """Trägt eine der Verbrauchs-Achsen (pv · netzbezug · einspeisung ·
    batterie) mehr als eine Stunde? Dann ist auch ein gebildeter
    Stunden-Hausverbrauch (R6, alle mit gleicher Spanne) keine Stundenmenge —
    Grundlast, Verbrauchsprofil und Grundbedarf lassen die Zeile aus."""
    return any(zeile_gebuendelt(row, a) for a in VERBRAUCHS_ACHSEN)


def _fensterbeginn_ts(datum: date) -> float:
    """Vortag 23:00 lokal als UTC-Sekunden (Ü4: DST-fest über reale Zeit)."""
    return datetime.combine(datum - timedelta(days=1), time(23, 0)).timestamp()


def _slotende_ts(datum: date, stunde: int) -> float:
    """Ende des Backward-Slots ``stunde`` (= Zähler(stunde), Wanduhr ``stunde``:00)."""
    return datetime.combine(datum, time(stunde, 0)).timestamp()


def zeile_traegt_vortagsenergie(row: Any, achse: str, datum: Optional[date] = None) -> bool:
    """Trägt diese Zeile Energie aus der Zeit **vor** dem Fensterbeginn?

    ``n`` der Zeile größer als die realen Stunden zwischen Fensterbeginn
    (Vortag 23:00) und Slot-Ende — **nicht** ``h + 1`` (Ü4: am Herbst-
    Umstellungstag sind es bis Slot 3 fünf reale Stunden), **und** der Wert
    der Achse ist ≠ 0 (ein 0-Bündel trägt keine Energie).
    """
    n = spanne(getattr(row, "spannen", None), achse)
    if n <= 1:
        return False
    tag = datum or getattr(row, "datum")
    stunde = int(getattr(row, "stunde"))
    reale = round((_slotende_ts(tag, stunde) - _fensterbeginn_ts(tag)) / 3600)
    if n <= reale:
        return False
    spalte = _SPALTE_JE_ACHSE.get(achse)
    wert = getattr(row, spalte, None) if spalte else None
    return wert is not None and abs(wert) > 0


def tag_traegt_vortagsenergie(rows: Iterable[Any], achse: str) -> bool:
    """**Tag gegen Tag, D+1-Seite:** trägt eine Zeile des Tages auf der Achse
    Vortagsenergie (ein Mitternachtsbündel mit Wert ≠ 0)?"""
    return any(zeile_traegt_vortagsenergie(r, achse) for r in rows)


def tage_um_mitternachtsbuendel(
    rows_je_tag: Mapping[date, Iterable[Any]], achse: str,
) -> set[date]:
    """**Tag gegen Tag:** die Tage, die um ein Mitternachtsbündel mit Energie
    **beide** aus einem Tagesvergleich fallen — D+1 (trägt die Energie) und D
    (ist um dieselbe Energie zu niedrig, Ü2). Ein 0-Bündel lässt beide drin,
    ein inneres Bündel lässt den Tag drin.
    """
    out: set[date] = set()
    for tag, rows in rows_je_tag.items():
        if tag_traegt_vortagsenergie(list(rows), achse):
            out.add(tag)
            out.add(tag - timedelta(days=1))
    return out


# ── Erfassungs-Stillstand (N-799, Bauplan Fassung 3, E-1 … E-3) ─────────────
#
# Fällt die Erfassung aus (HA-Host aus), holt HA die fehlenden Stunden mit unverändertem Stand nach: Zeilen mit
# Delta 0, danach EINE Stunde mit der Menge des Ausfalls (n = 1 wie HA). Für die Menge folgt eedc HA; für die Leser,
# die Stunde gegen Stunde stellen, bekommt die Zeile beim Lesen eine Marke — die Nachtragszeile n = k + 1, die
# Nullzeilen n = 0 (``spanne_roh``). Erkannt wird nur der Stillstand der GANZEN Erfassung (alle Bilanz-Zähler);
# der eines einzelnen Zählers ist aus Nullzeilen nicht von echten Nullen zu unterscheiden (benannte Grenze G-2).

#: Rolle eines Bilanz-Zählers in der Erkennung (Energiefluss-Kategorie → Rolle; Ladung und Entladung getrennt).
STILLSTAND_ROLLE_JE_KATEGORIE: dict[str, str] = {
    "pv": "pv", "erzeugung_sonstiges": "pv", "einspeisung": "einspeisung", "netzbezug": "netzbezug",
    "ladung_batterie": "ladung", "entladung_batterie": "entladung",
}
#: Rolle → Achse der ``spannen``-Spalte (Ladung und Entladung teilen die Batterie-Achse).
_ACHSE_DER_ROLLE: dict[str, str] = {
    "pv": "pv", "einspeisung": "einspeisung", "netzbezug": "netzbezug", "ladung": "batterie", "entladung": "batterie",
}
#: E-1: mindestens so viele Stunden mit unverändertem Stand …
STILLSTAND_MIN_STUNDEN = 2
#: … und danach eine Stunde, in der mindestens so viele Zähler Menge tragen.
STILLSTAND_MIN_ZAEHLER_MIT_MENGE = 2
#: **Alle Kontext-Bedingungen blicken nur zurück** (Präzisierung des Masters zu E-1, Korrekturrunde S1): ein einmal
#: festgestelltes Fenster ändert sich durch spätere Zeilen nicht mehr.
#: «erfasst»: der Zähler hat mindestens eine Zeile in so vielen Sekunden VOR dem Beginn des Laufs.
ERFASST_RUECK_S = 30 * 86400
#: Grob-Sperre: in den 30 Tagen VOR der Nachtragsstunde (diese eingeschlossen) ≥ ``GROB_MIN_POSITIVE`` positive Δ eines
#: Zählers, alle Vielfache von ``GROB_AUFLOESUNG_KWH``.
GROB_RUECK_S = 30 * 86400
GROB_MIN_POSITIVE = 5
GROB_AUFLOESUNG_KWH = 0.1
#: Häufigkeits-Sperre: mehr als ``HAEUFIG_MAX_FENSTER`` Fenster in den 60 Tagen VOR der Nachtragsstunde (dieses
#: eingeschlossen) ⇒ dieses nicht markiert. Von einer Serie bleiben so die ersten fünf markiert, jedes weitere nicht.
#: Die «fünf» ist eine Setzung (Bauplan E-1): Produktiv höchstens 2, grober Netzzähler ≈ 9, einfrierende Erfassung 60.
HAEUFIG_RUECK_S = 60 * 86400
HAEUFIG_MAX_FENSTER = 5
#: Wie weit ein Fenster zurückblickt: Häufigkeit 60 Tage über Fenster, deren eigene Kernbedingung («erfasst») und
#: Grob-Prüfung weitere 30 Tage zurückblicken — wer so viel Rand vor seinem Bereich mitliest, bekommt dieselben Fenster
#: wie jeder andere Leser (Treffer = Kaltlauf).
RUECKBLICK_S = HAEUFIG_RUECK_S + max(ERFASST_RUECK_S, GROB_RUECK_S)
SPERRE_GROB = "grob"
SPERRE_HAEUFIG = "haeufig"
_STUNDE_S = 3600
_EPS = 1e-9


@dataclass(frozen=True)
class ZaehlerReihe:
    """Ein Zähler für die Stillstands-Erkennung: seine Rolle (``STILLSTAND_ROLLE_JE_KATEGORIE`` bzw. die Achse einer
    Nebenachse) und je belegter Stunde ``(start_ts, delta, spanne_s)`` aufsteigend — HAs ``change`` und der Abstand zum
    vorigen Stand in Sekunden (``None`` ohne vorigen Stand)."""

    rolle: str
    werte: tuple[tuple[int, Optional[float], Optional[int]], ...]


@dataclass(frozen=True)
class StillstandFenster:
    """Ein Erfassungs-Stillstand in echten Stunden: ``k`` Stunden ``[von_ts, nachtrag_ts)`` mit unverändertem Stand
    jedes erfassten Bilanz-Zählers, danach die Nachtragsstunde ``nachtrag_ts``. ``achsen``: die Achsen, die die Marke
    tragen (die Bilanz-Achsen der erfassten Zähler, dazu erbende Nebenachsen); ``sperre``: ``None`` = wird markiert,
    sonst ``SPERRE_GROB``/``SPERRE_HAEUFIG`` (erkannt, aber nicht markiert — der Befund nennt die Lage)."""

    von_ts: int
    nachtrag_ts: int
    k: int
    achsen: frozenset[str]
    sperre: Optional[str] = None

    @property
    def n(self) -> int:
        """Die Spanne der Nachtragszeile (E-2): die k Stunden des Stillstands und die Nachtragsstunde selbst."""
        return self.k + 1


def _je_stunde(reihen: Mapping[str, ZaehlerReihe]) -> tuple[dict[int, dict[str, tuple]], dict[str, list[int]]]:
    """``{start_ts: {zaehler: (delta, spanne)}}`` und je Zähler seine belegten Stunden (aufsteigend)."""
    stunden: dict[int, dict[str, tuple]] = {}
    belegt: dict[str, list[int]] = {}
    for key, r in reihen.items():
        belegt[key] = [ts for ts, _d, _sp in r.werte]
        for ts, delta, sp in r.werte:
            stunden.setdefault(ts, {})[key] = (delta, sp)
    return stunden, belegt


def _erfasst(belegt: Mapping[str, list[int]], beginn: int) -> tuple[str, ...]:
    """Die Zähler, die für einen Lauf ab ``beginn`` erfasst sind: mindestens eine Zeile in den ``ERFASST_RUECK_S`` vor
    ``beginn`` — nur rückwärts, damit eine spätere Pause (ein Zähler ohne Zeilen) kein früheres Fenster kippt."""
    out = []
    for key, ts_liste in belegt.items():
        i = bisect_left(ts_liste, beginn)
        if i > 0 and ts_liste[i - 1] >= beginn - ERFASST_RUECK_S:
            out.append(key)
    return tuple(out)


def _eingefroren(zeile: Mapping[str, tuple], erfasst: Sequence[str]) -> bool:
    """Jeder erfasste Zähler hat in der Stunde eine Zeile (lückenlos) mit unverändertem Stand."""
    if len(erfasst) < STILLSTAND_MIN_ZAEHLER_MIT_MENGE:
        return False
    for key in erfasst:
        w = zeile.get(key)
        if w is None or w[0] is None or w[1] != _STUNDE_S or abs(w[0]) > _EPS:
            return False
    return True


def _ist_nachtrag(zeile: Mapping[str, tuple], erfasst: Sequence[str]) -> bool:
    """Jeder erfasste Zähler hat in der Stunde eine lückenlose Zeile, mindestens zwei tragen Menge (Δ > 0)."""
    menge = 0
    for key in erfasst:
        w = zeile.get(key)
        if w is None or w[0] is None or w[1] != _STUNDE_S:
            return False
        menge += w[0] > _EPS
    return menge >= STILLSTAND_MIN_ZAEHLER_MIT_MENGE


def _vorbedingung(rollen: set[str], speicher_aktiv: bool) -> bool:
    """E-1: Netzbezug und ein weiterer Bilanz-Zähler sind erfasst; mit aktivem Speicher auch Ladung und Entladung."""
    if "netzbezug" not in rollen or len(rollen) < 2:
        return False
    return not speicher_aktiv or {"ladung", "entladung"} <= rollen


def _fenster_des_laufs(reihen: Mapping[str, ZaehlerReihe], beginn: int, ts: int, erfasst: tuple[str, ...],
                       speicher_aktiv: Callable[[int], bool]) -> Optional[StillstandFenster]:
    """Das Fenster eines Laufs ``[beginn, ts)`` mit Nachtrag in ``ts`` — ``None``, wenn die Vorbedingung fehlt."""
    rollen = {reihen[key].rolle for key in erfasst}
    if not _vorbedingung(rollen, speicher_aktiv(ts)):
        return None
    achsen = frozenset(_ACHSE_DER_ROLLE[r] for r in rollen if r in _ACHSE_DER_ROLLE)
    return StillstandFenster(beginn, ts, (ts - beginn) // _STUNDE_S, achsen)


def _kandidaten(reihen: Mapping[str, ZaehlerReihe],
                speicher_aktiv: Callable[[int], bool]) -> list[tuple[StillstandFenster, tuple[str, ...]]]:
    """Die Fenster nach E-1 ohne Sperren, je mit den für den Lauf erfassten Zählern (``_erfasst`` am Laufbeginn). Eine
    Stunde ohne Zeile (Lücke) beendet den Lauf — dafür gibt es das Lücken-Bündel."""
    stunden, belegt = _je_stunde(reihen)
    out: list[tuple[StillstandFenster, tuple[str, ...]]] = []
    beginn: Optional[int] = None
    erfasst: tuple[str, ...] = ()
    vorige = None
    for ts in sorted(stunden):
        zeile = stunden[ts]
        if beginn is not None and ts - vorige != _STUNDE_S:
            beginn = None
        if beginn is not None and _eingefroren(zeile, erfasst):
            vorige = ts
            continue
        if beginn is not None and (ts - beginn) // _STUNDE_S >= STILLSTAND_MIN_STUNDEN and _ist_nachtrag(zeile, erfasst):
            f = _fenster_des_laufs(reihen, beginn, ts, erfasst, speicher_aktiv)
            if f is not None:
                out.append((f, erfasst))
        beginn, erfasst = None, ()
        kandidat = _erfasst(belegt, ts)
        if _eingefroren(zeile, kandidat):
            beginn, erfasst = ts, kandidat
        vorige = ts
    return out


def _grob_index(reihe: ZaehlerReihe) -> tuple[list[int], list[int]]:
    """Je Zähler die Stunden mit positivem Δ und die laufende Zahl der Δ, die KEIN Vielfaches der Auflösung sind."""
    ts_pos: list[int] = []
    nicht_vielfach = [0]
    for ts, delta, _sp in reihe.werte:
        if delta is None or delta <= _EPS:
            continue
        ts_pos.append(ts)
        q = delta / GROB_AUFLOESUNG_KWH
        nicht_vielfach.append(nicht_vielfach[-1] + (abs(q - round(q)) > 1e-6))
    return ts_pos, nicht_vielfach


def _grob(f: StillstandFenster, zaehler: Sequence[str], index: Mapping[str, tuple[list[int], list[int]]]) -> bool:
    """Grob-Sperre: ein erfasster Zähler mit ≥ ``GROB_MIN_POSITIVE`` positiven Δ in den 30 Tagen VOR der Nachtragsstunde
    (diese eingeschlossen), alle Vielfache von 0,1 kWh — ein Zähler in ganzen oder Zehntel-kWh friert in schwachen
    Stunden ein, ohne dass die Erfassung steht."""
    for key in zaehler:
        ts_pos, nicht_vielfach = index[key]
        lo = bisect_left(ts_pos, f.nachtrag_ts - GROB_RUECK_S)
        hi = bisect_right(ts_pos, f.nachtrag_ts)
        if hi - lo >= GROB_MIN_POSITIVE and nicht_vielfach[hi] == nicht_vielfach[lo]:
            return True
    return False


def stillstand_fenster(reihen: Mapping[str, ZaehlerReihe], *,
                       speicher_aktiv: Callable[[int], bool] = lambda _ts: False) -> list[StillstandFenster]:
    """**Die Erfassungs-Stillstände** aus den Bilanz-Zählern (Bauplan N-799 E-1, präzisiert in der Korrekturrunde S1),
    aufsteigend nach Nachtragsstunde.

    Ein Fenster: ``k ≥ 2`` aufeinanderfolgende Stunden, in denen jeder erfasste Bilanz-Zähler (PV, Einspeisung,
    Netzbezug, Ladung, Entladung — getrennt) eine Zeile mit unverändertem Stand hat, und die Stunde danach, in der jeder
    von ihnen eine Zeile hat und ≥ 2 Menge tragen. **Erfasst** ist ein Zähler, der in den 30 Tagen vor dem Laufbeginn
    eine Zeile hat. **Vorbedingung** (an der Nachtragsstunde): Netzbezug und ein weiterer Zähler sind erfasst; mit
    aktivem Speicher (``speicher_aktiv(ts)``) auch Ladung und Entladung — sonst kein Fenster. **Grob-Sperre** (30 Tage vor
    der Nachtragsstunde) ⇒ ``sperre = "grob"``. **Häufigkeits-Sperre**: liegen in den 60 Tagen vor der Nachtragsstunde
    (dieses eingeschlossen) mehr als fünf Fenster ⇒ ``sperre = "haeufig"``; gezählt werden die Fenster der Kernbedingung,
    gleich ob selbst häufig gesperrt, **ohne die grob gesperrten** — ein grober Zähler ist kein Stillstand der Erfassung,
    und seine Fenster sind schon gesperrt; zählten sie mit, sperrten sie den ersten echten Stillstand nach dem Wechsel auf
    einen feinen Zähler. Markiert wird nur ``sperre is None``.

    **Nur rückwärts:** das Ergebnis eines Fensters hängt nur von den Zeilen bis zu seiner Nachtragsstunde ab, höchstens
    ``RUECKBLICK_S`` zurück — ein späteres Fenster oder eine spätere Pause ändert ein früheres nie, und wer so viel Rand vor
    seinem Bereich mitliest, bekommt dieselben Fenster wie jeder andere Leser (Treffer = Kaltlauf)."""
    kandidaten = _kandidaten(reihen, speicher_aktiv)
    if not kandidaten:
        return []
    index = {key: _grob_index(r) for key, r in reihen.items()}
    gepruft = [(f, _grob(f, zaehler, index)) for f, zaehler in kandidaten]
    ende = [f.nachtrag_ts for f, grob in gepruft if not grob]
    out: list[StillstandFenster] = []
    for f, grob in gepruft:
        if grob:
            out.append(_mit_sperre(f, SPERRE_GROB))
            continue
        dichte = bisect_right(ende, f.nachtrag_ts) - bisect_left(ende, f.nachtrag_ts - HAEUFIG_RUECK_S)
        out.append(_mit_sperre(f, SPERRE_HAEUFIG) if dichte > HAEUFIG_MAX_FENSTER else f)
    return out


def _mit_sperre(f: StillstandFenster, sperre: str) -> StillstandFenster:
    return StillstandFenster(f.von_ts, f.nachtrag_ts, f.k, f.achsen, sperre)


def erbt_marke(f: StillstandFenster, reihen: Iterable[ZaehlerReihe]) -> bool:
    """E-2: erbt eine Nebenachse (Wallbox, Wärmepumpe, Sonstige, V2H) die Marke? — wenn jeder ihrer im Fenster erfassten
    Zähler in jeder Stunde ``[von_ts, nachtrag_ts)`` eine lückenlose Zeile mit unverändertem Stand hat (mindestens einer).
    ``reihen``: die Zähler der Achse."""
    stunden = range(f.von_ts, f.nachtrag_ts, _STUNDE_S)
    gesehen = False
    for r in reihen:
        if not r.werte or r.werte[0][0] > f.von_ts or r.werte[-1][0] < f.nachtrag_ts:
            continue
        je_ts = {ts: (d, sp) for ts, d, sp in r.werte if f.von_ts <= ts < f.nachtrag_ts}
        for ts in stunden:
            w = je_ts.get(ts)
            if w is None or w[0] is None or w[1] != _STUNDE_S or abs(w[0]) > _EPS:
                return False
        gesehen = True
    return gesehen


def marke_der_stunde(fenster: Iterable[StillstandFenster], stunden_ts: Iterable[int]) -> Optional[tuple[int, frozenset]]:
    """Die Marke einer Stundenzeile, die die echten Stunden ``stunden_ts`` trägt (eine; am Herbst-Umstellungstag zwei):
    ``(k + 1, achsen)`` für die Nachtragsstunde, ``(0, achsen)`` für eine Stunde im Fenster, sonst ``None``. Nur
    markierbare Fenster (``sperre is None``)."""
    ts_menge = set(stunden_ts)
    for f in fenster:
        if f.sperre is not None:
            continue
        if f.nachtrag_ts in ts_menge:
            return f.n, f.achsen
        if any(f.von_ts <= ts < f.nachtrag_ts for ts in ts_menge):
            return 0, f.achsen
    return None
