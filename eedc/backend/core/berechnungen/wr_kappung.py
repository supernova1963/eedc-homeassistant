"""Wechselrichter-Kappung (AC-Grenze) auf Prognose-Stundenprofile.

**Warum stündlich und nicht als kWp-Deckel.** Ein überbelegtes System — der
Normalfall beim Balkonkraftwerk (3 × 420 Wp an einem 600-W-Wechselrichter,
#347) wie beim Dach (22 × 440 Wp an einem 7-kW-Gerät, #354) — erreicht die
AC-Grenze nur um die Mittagsspitze. Morgens und abends liefert es weit
darunter, dort begrenzt der Wechselrichter gar nicht. Wer stattdessen die
Nennleistung auf die AC-Grenze deckelte (1,26 → 0,6 kWp), kürzte die
Randstunden mit und läge systematisch zu niedrig — bei starker Überbelegung
deutlich.

**Warum über Orientierungsgruppen hinweg.** Die Grenze gehört dem
Wechselrichter, nicht der Himmelsrichtung: an einem 7-kW-Gerät können ein
Ost- und ein West-String hängen, und die 7 kW gelten für deren **Summe**
(#354, kingcap1 — „Fronius2-Carport und Nord-7kW"). Der Fan-out der Prognose
gruppiert aber nach Neigung/Ausrichtung, die beiden Strings liegen also in
verschiedenen Gruppen. Eine Kappung, die nur innerhalb einer Gruppe rechnet,
ließe denselben Wechselrichter zweimal bis an seine Grenze liefern — bei zwei
Strings also 14 kW. Deshalb nehmen die Funktionen hier **alle** Gruppen
zusammen entgegen und geben alle zusammen zurück.

Umgekehrt darf nicht über die Grenze hinweg zusammengefasst werden: in einer
Gruppe können ein ungekappter PV-String und ein gekapptes BKW nebeneinander
liegen (`min(a+b, grenze) ≠ min(a,∞) + min(b,grenze)`). Maßgeblich ist also
weder die Gruppe noch die Komponente, sondern die **geteilte Grenze** —
`Mitglied.grenz_id`.

Die Aufteilung auf Mitglieder ist zulässig, weil die Ertragsformel in kWp
**strikt linear** ist (`solar_forecast_service.berechne_pv_ertrag`: kWp ist
reiner Multiplikator, Temperatur- und Schnee-Korrektur hängen nicht davon ab)
— der Stundenwert einer Gruppe lässt sich also verlustfrei auf ihre Mitglieder
herunterrechnen. Greift eine geteilte Grenze, werden die beteiligten Mitglieder
**anteilig** gekürzt: der Wechselrichter riegelt seine Summe ab, er entscheidet
nicht, welcher String zuerst verliert.

Ohne gepflegte Grenze wird **nicht** gekappt (`None`, kein Default) — ein
Default machte aus „nicht gepflegt" eine Zahl, die wie eine Messung aussieht.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from backend.core.investition_kennwerte import get_wr_grenze_kw


@dataclass(frozen=True)
class Mitglied:
    """Eine Erzeuger-Komponente innerhalb einer Orientierungsgruppe.

    Attributes:
        kwp: Nennleistung der Komponente.
        grenze_kw: AC-Grenze in kW, oder `None` = unbegrenzt.
        grenz_id: Kennung der Grenze. Mitglieder mit **derselben** `grenz_id`
            teilen sich `grenze_kw` (mehrere Strings an einem Wechselrichter);
            `None` heißt „gehört keiner geteilten Grenze an" und wird — sofern
            `grenze_kw` gesetzt ist — für sich allein gekappt.
    """

    kwp: float
    grenze_kw: Optional[float] = None
    grenz_id: Optional[str] = None


def zuordne_grenzen(
    erzeuger: Sequence[Any], wechselrichter: Sequence[Any],
) -> dict[Any, tuple[Optional[float], Optional[str]]]:
    """`{erzeuger.id: (grenze_kw, grenz_id)}` für eine Bestandsliste.

    EIN Weg, auf dem ein Erzeuger an seine AC-Grenze kommt — sonst baut jeder
    Prognose-Pfad seine eigene Zuordnung und sie driften auseinander (die
    Klasse, die der vierte ADR-001-Nachtrag benennt).

    Zwei Fälle, und die Reihenfolge ist wichtig:

    1. **Eigene Grenze** (`balkonkraftwerk`): das Gerät ist Erzeuger und
       Wechselrichter in einem, seine Grenze teilt es mit niemandem. Sie
       gewinnt auch dann, wenn das BKW zusätzlich einem Wechselrichter
       zugeordnet wäre — das eigene Gerät ist das nähere.
    2. **Geteilte Grenze über den Parent** (`pv-module` → `wechselrichter`):
       alle Strings desselben Wechselrichters bekommen dieselbe `grenz_id` und
       werden gemeinsam gekappt.

    Ein Erzeuger ohne Grenze bekommt `(None, None)` — der Aufrufer nimmt dann
    den unveränderten Pfad, und die Rechnung bleibt bitgleich zu vorher.
    """
    wr_grenzen = {
        wr.id: get_wr_grenze_kw(wr)
        for wr in wechselrichter
        if getattr(wr, "id", None) is not None
    }

    zuordnung: dict[Any, tuple[Optional[float], Optional[str]]] = {}
    for erz in erzeuger:
        erz_id = getattr(erz, "id", None)
        if erz_id is None:
            continue
        eigene = get_wr_grenze_kw(erz)
        if eigene is not None:
            zuordnung[erz_id] = (eigene, f"inv:{erz_id}")
            continue
        parent_id = getattr(erz, "parent_investition_id", None)
        parent_grenze = wr_grenzen.get(parent_id) if parent_id is not None else None
        if parent_grenze is not None:
            zuordnung[erz_id] = (parent_grenze, f"wr:{parent_id}")
        else:
            zuordnung[erz_id] = (None, None)
    return zuordnung


def hat_kappung(mitglieder_je_gruppe: Sequence[Sequence[Mitglied]]) -> bool:
    """Trägt mindestens ein Mitglied irgendeiner Gruppe eine AC-Grenze?

    Der Aufrufer nimmt sonst den unveränderten Pfad — ohne Grenze soll die
    Rechnung **bitgleich** zu vorher bleiben (keine zusätzliche Multiplikation,
    keine Rundungsdrift).
    """
    return any(
        m.grenze_kw is not None and m.grenze_kw > 0
        for gruppe in mitglieder_je_gruppe
        for m in gruppe
    )


def kappe_stunde(
    gruppen_kw: Sequence[float],
    gruppen_kwp: Sequence[float],
    mitglieder_je_gruppe: Sequence[Sequence[Mitglied]],
) -> list[float]:
    """Stundenwerte aller Orientierungsgruppen nach AC-Kappung.

    Args:
        gruppen_kw: unbegrenzter Stundenwert je Gruppe (kW).
        gruppen_kwp: kWp, auf die der jeweilige Stundenwert gerechnet wurde.
        mitglieder_je_gruppe: Komponenten je Gruppe, gleiche Reihenfolge.

    Returns:
        Gekappter Stundenwert je Gruppe, in derselben Reihenfolge.

    Eine Gruppe **ohne** Mitgliederliste bleibt unverändert — sie ist nicht
    „ohne Erzeuger", sondern „nicht aufgeschlüsselt"; sie stillschweigend auf 0
    zu setzen wäre die 0-Werte-Falle in ihrer teuersten Form.
    """
    anteile: list[list[float]] = []
    for idx, mitglieder in enumerate(mitglieder_je_gruppe):
        kw = gruppen_kw[idx] if idx < len(gruppen_kw) else 0.0
        kwp = gruppen_kwp[idx] if idx < len(gruppen_kwp) else 0.0
        kw = max(0.0, kw or 0.0)
        if not mitglieder or kwp <= 0 or kw <= 0:
            anteile.append([])
            continue
        pro_kwp = kw / kwp
        anteile.append([pro_kwp * m.kwp for m in mitglieder])

    # Pools bilden: gleiche `grenz_id` = gemeinsame Grenze. Ein Mitglied mit
    # Grenze, aber ohne `grenz_id`, bekommt einen Pool für sich allein.
    pools: dict[str, list[tuple[int, int]]] = {}
    pool_grenze: dict[str, float] = {}
    for g, mitglieder in enumerate(mitglieder_je_gruppe):
        if not anteile[g]:
            continue
        for i, m in enumerate(mitglieder):
            if m.grenze_kw is None or m.grenze_kw <= 0:
                continue
            key = m.grenz_id or f"__einzeln:{g}:{i}"
            pools.setdefault(key, []).append((g, i))
            # Bei geteilter Grenze ist der Wert je Mitglied derselbe; das `min`
            # ist die konservative Auflösung, falls doch zwei verschiedene
            # Zahlen unter einer Kennung ankommen.
            vorher = pool_grenze.get(key)
            pool_grenze[key] = (
                m.grenze_kw if vorher is None else min(vorher, m.grenze_kw)
            )

    for key, positionen in pools.items():
        grenze = pool_grenze[key]
        summe = sum(anteile[g][i] for g, i in positionen)
        if summe <= grenze or summe <= 0:
            continue
        faktor = grenze / summe
        for g, i in positionen:
            anteile[g][i] *= faktor

    ergebnis: list[float] = []
    for g in range(len(mitglieder_je_gruppe)):
        if not anteile[g]:
            kw = gruppen_kw[g] if g < len(gruppen_kw) else 0.0
            ergebnis.append(max(0.0, kw or 0.0))
        else:
            ergebnis.append(sum(anteile[g]))
    return ergebnis


def kappe_profile(
    stunden_je_gruppe: Sequence[Sequence[float]],
    gruppen_kwp: Sequence[float],
    mitglieder_je_gruppe: Sequence[Sequence[Mitglied]],
) -> list[list[float]]:
    """`kappe_stunde` über ganze Tagesprofile — Ergebnis je Gruppe."""
    laenge = max((len(s or []) for s in stunden_je_gruppe), default=0)
    gekappt: list[list[float]] = [[] for _ in stunden_je_gruppe]
    for h in range(laenge):
        werte = [
            (s[h] or 0.0) if s is not None and h < len(s) else 0.0
            for s in stunden_je_gruppe
        ]
        for g, v in enumerate(kappe_stunde(werte, gruppen_kwp, mitglieder_je_gruppe)):
            gekappt[g].append(v)
    return gekappt


def kappungs_faktoren(
    stunden_je_gruppe: Sequence[Sequence[float]],
    gruppen_kwp: Sequence[float],
    mitglieder_je_gruppe: Sequence[Sequence[Mitglied]],
) -> list[float]:
    """Verhältnis gekappte zu ungekappter Tagessumme je Gruppe (1.0 = nichts).

    Damit lässt sich der **Tageswert** einer Gruppe kappen, ohne ihn aus dem
    Stundenprofil neu zu bilden: der Tageswert der Prognose ist nicht
    zwangsläufig die Σ der Stundenwerte (eigene Rundung, teils andere Quelle),
    und ihn hier neu zu erfinden wäre eine zweite Wahrheit.
    """
    gekappt = kappe_profile(stunden_je_gruppe, gruppen_kwp, mitglieder_je_gruppe)
    faktoren: list[float] = []
    for g, stunden in enumerate(stunden_je_gruppe):
        roh = sum(v or 0.0 for v in (stunden or []))
        faktoren.append(sum(gekappt[g]) / roh if roh > 0 else 1.0)
    return faktoren
