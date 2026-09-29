"""Der Lückenschluss: kein abgeschlossener Monat bleibt ohne Wetterwerte.

**Warum es ihn gibt (Paket „Die Wetterreihe geradeziehen", #395 Punkt 1).** Er
ist Gernots Bedingung für die Freigabe: *„nur wenn sichergestellt ist, dass
zukünftig kein Monat ohne diese Daten entstehen kann."* Ohne ihn wäre B2 ein
Rückschritt — heute steht (falsch) der Vormonatswert im Feld, danach stünde
**nichts** darin, solange niemand den Knopf drückt.

⚠ **Täglich, nicht am Monatswechsel.** Der vorhandene Monats-Job läuft am 1. um
00:01 — eine Minute nach Monatsende, da liefert kein Archiv den Monat.
Open-Meteo hinkt laut eigenem Kommentar **2–5 Tage** nach (N-388). Ein täglicher
Versuch klappt irgendwann, und er fängt zugleich jede andere Ursache: Ausfall,
kein Netz, ein später nachgetragener Monat.

⛔ **Nur Lücken, nie überschreiben.** Das Umlegen einer ganzen Reihe bleibt die
vom Anwender **angeordnete** Aktion (Reparatur-Werkbank, ``WETTER_BACKFILL``).
Ein Hintergrundjob ändert keinen vorhandenen Wert — auch keinen, den er selbst
geschrieben hat.

⛔ **PVGIS-TMY wird NIE automatisch geschrieben.** Ein langjähriges Mittel ist
keine Messung *dieses* Monats; es automatisch einzutragen machte ein schwaches
Jahr unsichtbar — genau der Fehler, gegen den dieses Paket gebaut ist. Liefert
kein messendes Archiv, **bleibt die Lücke**, und der Daten-Checker nennt sie.
PVGIS-TMY bleibt, was es ist: die letzte Stufe des **manuellen** Knopfs, mit
``datenquelle`` ausgewiesen.

⭐ **Die Reichweite der Zusage, ehrlich benannt.** „Kein Monat ohne Daten" gilt,
**solange ein messendes Archiv den Ort erreicht**. An 8 DACH-Orten gemessen
(Juli 2025): 8 von 8 mit Abdeckung 100 % — sieben über Bright Sky, Zürich über
Open-Meteo. Für DACH ist die Zusage damit praktisch lückenlos; der Rest ist
**sichtbar statt still**, und das ist der Unterschied zu heute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.services.provenance import write_with_provenance
from backend.services.wetter.monatswerte import (
    WETTER_MONATSFELDER,
    loese_monats_wetter,
    provenance_label,
)

logger = logging.getLogger(__name__)

#: Der Schreiber-Name im Audit-Log — er soll im Protokoll vom angeordneten
#: Nachzug (`wetter_backfill`) unterscheidbar sein.
WRITER = "wetter_luecken"


@dataclass
class LueckenErgebnis:
    """Was ein Lauf für EINE Anlage getan hat."""

    anlage_id: int
    monate_mit_luecke: int = 0
    monate_gefuellt: int = 0
    felder_gefuellt: int = 0
    abrufe: int = 0
    ohne_messende_quelle: list[str] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)


def _offene_felder(md: Monatsdaten) -> list[str]:
    return [f for f in WETTER_MONATSFELDER if getattr(md, f, None) is None]


async def monate_mit_luecke(
    db: AsyncSession, anlage_id: int, heute: date | None = None
) -> list[Monatsdaten]:
    """Die abgeschlossenen Monatszeilen, in denen ein Wetterfeld leer ist.

    ⛔ **Der laufende Monat bleibt draußen** — dieselbe Begründung wie beim
    angeordneten Nachzug: ``fetch_brightsky_month`` fragt nur bis gestern und
    setzt ``tage_gesamt`` dann auf den *gestrigen* Tag; die Abdeckung läse sich
    als ~100 %, obwohl der Monat halb ist.

    ⭐ **Erst DB, dann Netz.** Das ist der ganze Grund, warum diese Funktion
    getrennt steht: im Normalbetrieb ist der Job ein SELECT pro Nacht und kein
    einziger Abruf.
    """
    heute = heute or date.today()
    zeilen = (await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )).scalars().all()
    return [
        md for md in zeilen
        if (md.jahr, md.monat) < (heute.year, heute.month) and _offene_felder(md)
    ]


async def schliesse_wetter_luecken(
    db: AsyncSession, anlage: Anlage, heute: date | None = None
) -> LueckenErgebnis:
    """Füllt die Wetter-Lücken einer Anlage — und nur die.

    Returns:
        `LueckenErgebnis`. ``abrufe`` zählt die Monate, für die überhaupt eine
        Quelle gefragt wurde; **ohne Lücke ist sie 0**, und das prüft eine
        Probe ausdrücklich (Idempotenz).
    """
    ergebnis = LueckenErgebnis(anlage_id=anlage.id)

    if not anlage.latitude or not anlage.longitude:
        return ergebnis

    offen = await monate_mit_luecke(db, anlage.id, heute)
    ergebnis.monate_mit_luecke = len(offen)
    if not offen:
        return ergebnis

    for md in offen:
        felder = _offene_felder(md)
        try:
            data = await loese_monats_wetter(db, anlage, md.jahr, md.monat)
        except Exception as e:  # noqa: BLE001 — ein Monat darf den Lauf nicht töten
            ergebnis.fehler.append(f"{md.jahr}-{md.monat:02d}: {type(e).__name__}: {e}")
            continue
        ergebnis.abrufe += 1

        label = provenance_label(data.get("datenquelle"))
        temperatur_aus_messung = data.get("temperatur_herkunft") == "messung"
        if label is None and not temperatur_aus_messung:
            # Weder ein messendes Archiv noch die eigene Reihe — die Lücke
            # bleibt, und der Daten-Checker nennt sie.
            ergebnis.ohne_messende_quelle.append(f"{md.jahr}-{md.monat:02d}")
            continue

        vorher = ergebnis.felder_gefuellt
        for feld in felder:
            if feld == "durchschnittstemperatur":
                wert = data.get("durchschnittstemperatur_c")
                quelle = "manual:form" if temperatur_aus_messung else label
            else:
                wert = data.get(feld)
                quelle = label
            if wert is None or quelle is None:
                continue
            # ⚠ Null Sonnenstunden sind keine Messung, sondern eine Station
            # ohne Sonnenschein-Fühler (#386 zählt Tage mit `solar`, nicht mit
            # `sunshine`). Eine Lücke bleibt eine Lücke.
            if feld == "sonnenstunden" and not wert > 0:
                continue
            # ⛔ KEIN `benutzer_override`. Das Feld ist leer — es gibt nichts zu
            # durchbrechen, und ein Hintergrundjob darf es auch nicht.
            schreib = await write_with_provenance(
                db, md, feld, float(wert), source=quelle, writer=WRITER,
            )
            if schreib.applied:
                ergebnis.felder_gefuellt += 1
        if ergebnis.felder_gefuellt > vorher:
            ergebnis.monate_gefuellt += 1

    return ergebnis
