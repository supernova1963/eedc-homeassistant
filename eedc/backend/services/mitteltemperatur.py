"""Die Außentemperatur als Mittelwert je Tag und je Monat — mit Vorrangkette.

**Warum es diesen Dienst gibt.** Der Wärme/Klima-Verlauf (Konzept §8) zeigt die
Außentemperatur als zweite Linie: Ein kalter Monat braucht mehr Strom, ohne dass
die Anlage schlechter arbeitet. Der naheliegende Ort dafür — das Feld
``Monatsdaten.durchschnittstemperatur`` — ist seit dem IA-V4-Flip **leer**: Sein
Auto-Fill lag in der gelöschten V3-Seite (**N-426**). Die Größe selbst ist
trotzdem da, nur an einer anderen Stelle.

⭐ **Und die überlebt sogar länger als gedacht.** Bis 4.3.1 löschte der Nachtlauf
(`scheduler_jobs.py`) Stundenzeilen (``TagesEnergieProfil``) älter als 730 Tage; seit dem
Nachtrag zu Fund-Päckchen G löscht eedc keine Stundenzeilen mehr von selbst. Schon
gelöschte Tage haben keine Stundenwerte — ``TagesZusammenfassung`` mit ihrem
Tages-Min/Max wurde **nie** beschnitten.

**Die Vorrangkette, von genau nach ungenau:**

1. **Stundenwerte** (``TagesEnergieProfil.temperatur_c``) — das echte Mittel über
   die gemessenen Stunden. Reicht so weit zurück wie die Stundenzeilen (Tage, deren
   Stunden bis 4.3.1 nach zwei Jahren gelöscht wurden, haben keine).
2. **Tages-Min/Max** (``TagesZusammenfassung``) — ``(min + max) / 2``, die
   klimatologische Näherung. Sie greift für ältere Monate und für Tage, deren
   Stundenzeilen fehlen.
3. **Gepflegter Monatswert** (``Monatsdaten.durchschnittstemperatur``) — wer ihn
   von Hand einträgt, hat Vorrang vor **nichts**: Er kommt zuletzt, weil die
   gemessenen Reihen der Anlage näher sind als ein Wert aus einem Archiv.

⛔ **Kein Netzabruf.** Die Wetter-Route könnte jeden vergangenen Monat liefern,
aber zwölf Abrufe für eine Hilfslinie sind unverhältnismäßig — und sie träfen
das Wetter am Anlagenstandort nicht besser als die eigene Messreihe.

⚠ **Ø und Kd sind zwei Größen aus derselben Tagesreihe — nicht dieselbe.**
Der **Monats-Ø** ordnet ein und wird **angezeigt** (Verlauf, Monatstabelle). Die
**Heizgradtage** werden **gerechnet** und sind der Nenner des wetternormierten
Vergleichs (``lade_heizgradtage_je_monat``, SOLL Wärme/Klima §4.1). Bis zum
12.09.2026 stand hier, eine Wetternormierung brauche „eine eigene, dokumentierte
Definition — die Frage ist offen"; sie ist es nicht mehr, die Definition steht
im Layer (``core/berechnungen/heizgradtage.py``, Heizgrenze 15 °C).

⛔ **Und die beiden teilen die Reihe, nicht die Vorrangkette.** Für die
Heizgradtage gilt **nur Stufe 1+2** (Tagesmittel); der gepflegte Monats-Ø ist
dort **kein** Eingang — Begründung samt Messung im Docstring von
``lade_heizgradtage_je_monat``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.heizgradtage import (
    HeizgradtageMonat,
    heizgradtage_je_monat,
)
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung


async def lade_tagesmittel_temperatur(
    db: AsyncSession,
    anlage_id: int,
    von: "object" = None,
    bis: "object" = None,
) -> dict[object, float]:
    """Tagesmittel der Außentemperatur je Datum (Vorrang 1 vor 2).

    ``von``/``bis`` sind ``date``-Grenzen (einschließlich); ``None`` heißt
    „unbegrenzt". Rückgabe: ``{datum: °C}`` — Tage ohne jede Temperaturspur
    fehlen, statt mit 0 dazustehen.
    """
    # 1 — echtes Mittel über die Stundenzeilen des Tages.
    #
    # ⭐ Summe und Anzahl holt die Datenbank je Tag (`GROUP BY datum`), geteilt
    # wird weiter in Python. Vorher kamen alle Stundenzeilen einzeln herüber —
    # an einer Anlage mit zwei Jahren Historie 16.391 Tupel je Anfrage, für 685
    # Mittelwerte. ⛔ **Nicht auf `AVG()` umstellen:** Die Division hier bleibt
    # dieselbe Rechnung wie bisher, `AVG` wäre eine andere (und die Rundung auf
    # eine Nachkommastelle im Monatsmittel darüber ist nah genug an der Kante,
    # dass das sichtbar werden könnte).
    q = select(
        TagesEnergieProfil.datum,
        func.sum(TagesEnergieProfil.temperatur_c),
        func.count(TagesEnergieProfil.temperatur_c),
    ).where(
        TagesEnergieProfil.anlage_id == anlage_id,
        TagesEnergieProfil.temperatur_c.is_not(None),
    )
    if von is not None:
        q = q.where(TagesEnergieProfil.datum >= von)
    if bis is not None:
        q = q.where(TagesEnergieProfil.datum <= bis)
    q = q.group_by(TagesEnergieProfil.datum)
    je_tag = {
        datum: float(summe) / int(anzahl)
        for datum, summe, anzahl in (await db.execute(q)).all()
        if anzahl and int(anzahl) > 0
    }

    # 2 — Näherung aus Min/Max, nur wo Stufe 1 nichts hat.
    q2 = select(
        TagesZusammenfassung.datum,
        TagesZusammenfassung.temperatur_min_c,
        TagesZusammenfassung.temperatur_max_c,
    ).where(TagesZusammenfassung.anlage_id == anlage_id)
    if von is not None:
        q2 = q2.where(TagesZusammenfassung.datum >= von)
    if bis is not None:
        q2 = q2.where(TagesZusammenfassung.datum <= bis)
    for datum, tmin, tmax in (await db.execute(q2)).all():
        if datum in je_tag or tmin is None or tmax is None:
            continue
        je_tag[datum] = (float(tmin) + float(tmax)) / 2.0
    return je_tag


async def lade_monatsmittel_temperatur(
    db: AsyncSession,
    anlage_id: int,
    gepflegt_je_monat: Optional[dict[tuple[int, int], Optional[float]]] = None,
    von: "object" = None,
    bis: "object" = None,
) -> dict[tuple[int, int], float]:
    """Monatsmittel je ``(jahr, monat)`` — über die ganze Historie oder ein Fenster.

    ⚠ **Gemittelt wird über die TAGE, nicht über die Stunden des Monats.** Ein
    Monat, von dem nur wenige Tage Stundenwerte tragen, bekäme sonst das Gewicht
    dieser Tage — das Mittel kippte in Richtung der besser erfassten Zeit. Über
    Tagesmittel gemittelt zählt jeder erfasste Tag gleich viel.

    Args:
        gepflegt_je_monat: von Hand gepflegte Monatswerte
            (``Monatsdaten.durchschnittstemperatur``). Sie füllen **nur Lücken** —
            Stufe 3 der Vorrangkette.
        von/bis: ``date``-Grenzen (einschließlich); ``None`` heißt „unbegrenzt".
            ⭐ Das Fenster gilt für **beide** Eingänge — die Tagesreihe *und* die
            gepflegten Monatswerte. Ein Fenster, das nur die halbe Funktion
            beträfe, wäre eine Falle: der Aufrufer, der einen Monat anfragt,
            bekäme fremde Monate zurück, sobald er Stufe 3 mitgibt.

    ⭐ **Wozu das Fenster (N-426, 13.09.2026).** Die Wetter-Route beantwortet
    „welche Ø-Temperatur hatte DIESER eine Monat?" für das Auto-Fill des
    Monatsformulars. Ohne Fenster läse sie dafür die komplette Historie der
    Anlage — dieselbe Antwort, nur teurer.
    """
    je_tag = await lade_tagesmittel_temperatur(db, anlage_id, von=von, bis=bis)
    summe: dict[tuple[int, int], float] = defaultdict(float)
    tage: dict[tuple[int, int], int] = defaultdict(int)
    for datum, temp in je_tag.items():
        schluessel = (datum.year, datum.month)
        summe[schluessel] += temp
        tage[schluessel] += 1
    ergebnis = {k: round(summe[k] / tage[k], 1) for k in summe if tage[k] > 0}

    for schluessel, wert in (gepflegt_je_monat or {}).items():
        if wert is None or schluessel in ergebnis:
            continue
        if not _monat_im_fenster(schluessel, von, bis):
            continue
        ergebnis[schluessel] = round(float(wert), 1)
    return ergebnis


def _monat_im_fenster(
    schluessel: tuple[int, int], von: "object", bis: "object"
) -> bool:
    """Überlappt der Monat ``(jahr, monat)`` das ``von``/``bis``-Fenster?

    Ein Monat zählt, sobald **ein** Tag von ihm im Fenster liegt — dieselbe
    Großzügigkeit, mit der die Tagesreihe gefiltert wird (dort fällt der
    Randmonat ja auch nicht ganz weg, sondern nur seine Tage außerhalb).
    """
    jahr, monat = schluessel
    if von is not None and (jahr, monat) < (von.year, von.month):
        return False
    if bis is not None and (jahr, monat) > (bis.year, bis.month):
        return False
    return True


async def lade_heizgradtage_je_monat(
    db: AsyncSession,
    anlage_id: int,
    von: "object" = None,
    bis: "object" = None,
) -> dict[tuple[int, int], HeizgradtageMonat]:
    """Heizgradtage je Monat — Tagesmittel (Stufe 1+2) durch die Layer-Formel.

    Der Eingabe-Builder zur Wetternormierung: dieselbe Tagesreihe wie die
    Ø-Anzeige, aber **je Tag** in die Gradtag-Formel gegeben und erst dann
    summiert.

    ⛔ **Stufe 3 (gepflegter ``Monatsdaten.durchschnittstemperatur``) ist KEIN
    Eingang** (Entscheid K-2, 12.09.2026, SOLL §4.1). ``max(0; 15 − T)`` ist
    **konvex**: In einem Übergangsmonat mit Tagen beidseits der Heizgrenze
    unterschätzt der Weg über den Monatsmittelwert die Summe — an der
    Demo-Anlage im Mai 2026 gemessene **−26,6 %** (22,1 statt 30,1 Kd). Ein
    Monat, der nur einen gepflegten Ø trägt, bekommt deshalb **keine** Kd,
    sondern den Grund (S3). Dass hier keine dritte Stufe einsickert, hält
    ``test_mitteltemperatur.py`` fest.

    Args:
        von/bis: ``date``-Grenzen (einschließlich); ``None`` heißt „unbegrenzt".

    Returns:
        ``{(jahr, monat): HeizgradtageMonat}`` — ein Monat ohne einen einzigen
        Temperaturtag **fehlt**, statt mit 0 Kd dazustehen.
    """
    je_tag = await lade_tagesmittel_temperatur(db, anlage_id, von=von, bis=bis)
    return heizgradtage_je_monat(je_tag)
