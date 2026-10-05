"""Baustein des Symmetrie-Wächters „Kanal-Δ je Tag ≡ Bestand" (HA-Bauform E2, Auftrag Punkt 6).

Die Proben stehen in ``test_kanal_symmetrie.py``; dieses Modul ist ihr Baustein (kein ``test``-Präfix,
dieselbe Regel wie ``ha_lts_helfer.py``).

**Was verglichen wird (Familie Spiegel).** Für jede Tageszeile (``TagesZusammenfassung``) und jeden
Schlüssel ihres ``komponenten_kwh``: der gespeicherte Tageswert gegen das Δ der Kanäle, aus denen er
besteht, über das Tagesfenster des Bestands ``[Vortag 23:00, 23:00)``
(``slot_konvention.tagesfenster_start_ts``, eine Umrechnung an einer Stelle).

* **Woraus ein Schlüssel besteht**, sagt DIESELBE Funktion, die der HA-Tagespfad fragt:
  ``lts_aggregator._lts_eintraege`` (Beitragsschicht: Whitelist · Either-Or · Parent · K3 · Wallbox-Regel)
  samt ``resolve_either_or_eintraege``. ``Σ vorzeichen × Δ(inv:<id>:<feld>)`` — so entstehen etwa
  ``batterie_<id>`` (−Ladung + Entladung) und ``waermepumpe_<id>`` (Heizen + Warmwasser).
* **Lese-Schicht (E3):** ``services/kanal/lesen.py::zeitraum_stapel`` über ``fenster.tagesfenster`` — dieselbe
  Schicht und dieselben Fenster-Helfer, die E4 benutzt (Auftrag E3: „der Symmetrie-Wächter läuft jetzt über die neue
  Schicht"). Ein Kanal-Δ zählt nur bei voller Abdeckung (``Zeitraum.voll``).
* **Toleranz 0,005 kWh** (+ Rechenrauschen): ``komponenten_kwh`` wird beim Schreiben auf 0,01 gerundet
  (``energie_profil/aggregator.py::baue_zusammenfassung``, ``round(v, 2)``) — die halbe Rundungsstufe.

**Benannte Ausnahmeklassen statt stiller Auslassung** — je Klasse gezählt, nie verglichen:

* ``verworfen`` — die Tageszeile trägt einen Befund auf der Achse dieses Schlüssels (R3-Deckel / R4
  negativ): der Bestand hat eine Stunde verworfen, die der Spiegel (HAs ``sum``) enthält.
* ``ohne_regelmarke`` — ``verworfen IS NULL``: Altbestand, dessen Stunden die Lückenenergie noch verloren
  haben (R9/N-92); dort weiß ein Spiegel mehr.
* ``zerlegung`` — ``komponenten_kwh.<key>`` trägt die Marke ``kwp_anteil`` (#406): der Wert ist der
  kWp-Anteil am Anlagen-Zähler, keine Messung dieses Geräts.
* ``ohne_kanal`` — ein beitragender Zähler hat (noch) keinen Kanal oder deckt das Tagesfenster nicht voll
  (Regel ``lesen.py``: Stand vor dem Fenster, Stand am Ende, keine Spanne über das Fenster hinaus).

Die dritte Klasse des Auftrags, **Stunden mit geleertem ``komponenten``**, hätte nur eine Familie Bestand
betroffen (aus den Stundenzeilen gebildet) — die bleibt unbelegt (Bauplan §3b, 06.10.), und der Spiegel liest
``komponenten`` nicht. Die Klasse entfällt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.erzeuger_traeger import bkw_restwerte
from backend.core.berechnungen.spannen import achse_der_kategorie
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.lesen import zeitraum_stapel
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.snapshot.komponenten_beitraege import resolve_either_or_eintraege
from backend.services.snapshot.lts_aggregator import _lts_eintraege

#: Halbe Rundungsstufe von ``komponenten_kwh`` (0,01 kWh) plus Rechenrauschen.
TOLERANZ_KWH = 0.005 + 1e-9

KLASSEN = ("verworfen", "ohne_regelmarke", "zerlegung", "ohne_kanal")

#: Die Matrix-Tage liegen alle in der Vergangenheit; ``jetzt`` weit danach ⇒ jedes Tagesfenster ist abgeschlossen
#: (kein Schreibverzug im Spiel, keine echte Uhr).
_NACH_ALLEM = 4_102_444_800   # 2100-01-01


@dataclass
class Bericht:
    tage: int = 0
    verglichen: int = 0
    klassen: Counter = field(default_factory=Counter)
    abweichungen: list[tuple] = field(default_factory=list)   # (datum, key, bestand, kanal_delta)
    groesste: float = 0.0


async def symmetrie_spiegel(db: AsyncSession, anlage_id: int) -> Bericht:
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    invs = {str(i.id): i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()}
    kanaele = {k.key: k for k in (await db.execute(
        select(Kanal).where(Kanal.anlage_id == anlage_id))).scalars().all()}
    tz_zeilen = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage_id).order_by(TagesZusammenfassung.datum))).scalars().all()
    b = Bericht()
    for tz in tz_zeilen:
        werte = tz.komponenten_kwh or {}
        if not werte:
            continue
        b.tage += 1
        von, bis = tagesfenster(tz.datum)
        roh = _lts_eintraege(anlage, invs, tz.datum)
        mit_kanal = [kanaele[sk] for sk in dict.fromkeys(e.sensor_key for e in roh) if sk in kanaele]
        lese = await zeitraum_stapel(db, mit_kanal, von, bis, jetzt=_NACH_ALLEM) if mit_kanal else {}
        deltas: dict[str, float | None] = {sk: (z.delta if z.voll else None) for sk, z in lese.items()}
        eintraege = resolve_either_or_eintraege(
            roh, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: deltas.get(e.sensor_key) is not None,
        )
        je_key: dict[str, list] = {}
        for e in eintraege:
            je_key.setdefault(e.target_key, []).append(e)
        # Ein Balkonkraftwerk mit gemessenen Kindern trägt nur den Rest (N-536, „Zählerlücken wie HA" E4):
        # dieselbe Funktion wie der Tagespfad (`tages_tabelle.baue_tagestabelle` → `bkw_restwerte`), hier
        # auf dem Tages-Δ statt je Slot — gleich, solange kein Slot den Rest unter 0 drückt.
        pv_einzel = {e.sensor_key.split(":", 2)[1]: deltas.get(e.sensor_key) for e in eintraege
                     if e.kategorie == "pv" and e.sensor_key.startswith("inv:")}
        rest = bkw_restwerte(list(invs.values()), {i: d for i, d in pv_einzel.items() if d is not None})
        prov = tz.source_provenance or {}
        for key, ist in sorted(werte.items()):
            beitraege = je_key.get(key, [])
            if (prov.get(f"komponenten_kwh.{key}") or {}).get("abgeleitet") == ABGELEITET_KWP_ANTEIL:
                b.klassen["zerlegung"] += 1
                continue
            if tz.verworfen is None:
                b.klassen["ohne_regelmarke"] += 1
                continue
            achsen = {achse_der_kategorie(e.kategorie) for e in beitraege}
            if any(a in (tz.verworfen or {}) for a in achsen):
                b.klassen["verworfen"] += 1
                continue
            if not beitraege or any(deltas.get(e.sensor_key) is None for e in beitraege):
                b.klassen["ohne_kanal"] += 1
                continue
            soll = sum(
                e.vorzeichen * rest.get(e.sensor_key.split(":", 2)[1], deltas[e.sensor_key])
                if e.kategorie == "pv" and e.sensor_key.startswith("inv:") else e.vorzeichen * deltas[e.sensor_key]
                for e in beitraege
            )
            b.verglichen += 1
            abw = abs(soll - float(ist))
            b.groesste = max(b.groesste, abw)
            if abw > TOLERANZ_KWH:
                b.abweichungen.append((tz.datum, key, float(ist), round(soll, 6)))
    return b
