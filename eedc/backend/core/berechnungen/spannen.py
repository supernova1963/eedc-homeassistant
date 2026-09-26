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

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Mapping, Optional

#: Die Achsen einer Stundenzeile, in der Reihenfolge der Spalten
#: (`pv_kw` · `einspeisung_kw` · `netzbezug_kw` · `batterie_kw` ·
#: `waermepumpe_kw` · `wallbox_kw` · `verbrauch_sonstiges`).
ACHSEN: tuple[str, ...] = (
    "pv", "einspeisung", "netzbezug", "batterie", "waermepumpe", "wallbox", "sonstige",
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
    """n der Achse in einer Zeile — 1, wenn die Zeile keine Spanne für sie trägt."""
    if not spannen:
        return 1
    n = spannen.get(achse)
    return int(n) if n and n > 1 else 1


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
    """**Stunde gegen Stunde:** trägt diese Zeile auf der Achse mehr als eine
    reale Stunde? Dann ist sie keine Stichprobe dieser Stunde (Korrekturprofil,
    Verbrauchsprofil, Speicher-Stundenrechnungen, Spitzen …) — ihre Energie
    zählt trotzdem in jeder Summe."""
    return spanne(getattr(row, "spannen", None), achse) > 1


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
