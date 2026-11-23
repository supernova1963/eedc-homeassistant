"""Abruf-Spalten eines Tages: was der Abruf nicht liefert, bleibt wie gespeichert (Fund-Päckchen G, 23.11.2026).

Wetter (Open-Meteo) und Börsenpreis (aWATTar/EPEX) kommen aus einem **Abruf**, nicht aus einer Quelle mit Historie in Home
Assistant. ``aggregate_day`` löscht beide Tageszeilen und schreibt sie neu (``rette_und_loesche``); bis hierher gewann dabei
auch ein **leerer** Abruf — ohne Netz, bei einem Fehler oder einer Begrenzung des Dienstes standen Temperatur, Einstrahlung,
GTI, Performance Ratio, Börsenpreis und negative Preisstunden danach leer (gemessen 23.11.2026 an der Produktiv-Kopie,
«Zeitraum neu aggregieren» ohne Netz). Ein gescheiterter Abruf ist keine Aussage der Quelle.

**Regel (je Feld):** liefert der Abruf einen Wert, gewinnt er (so bleibt das Archiv-Upgrade des Wetters erhalten); liefert er
nichts, bleibt der gespeicherte Wert. Die Stundenwerte gehen **als Eingang** in den Lauf, nicht nachträglich auf die
Zeilen — damit rechnet ``aggregate_day`` das Abgeleitete (§51-Menge, Performance Ratio, auch an einem Kanal-Tag über
``Weiche.tageszeile``) aus denselben Zahlen wie die Stundenzeilen. Das GTI je Stunde speichert eedc nicht: liefert der
Abruf an keiner Stunde GTI, gilt die gespeicherte Tagessumme (die Performance Ratio entsteht dann aus ihr und dem neuen
PV-Ertrag — wie im Korrektur-Lauf des Sensorwechsels, ``zuordnung_wechsel/korrektur_lauf._performance_ratio``). Lieferte
ein Abruf des Tages gar nichts, stehen seine Tageswerte (Temperatur min/max, Strahlungssumme bzw. Börse Ø/min, negative
Preisstunden) wie gespeichert in der neuen Tageszeile (``AbrufLauf.tageswerte``).

Gilt für **jeden** Weg, der den Tag neu schreibt, weil alle über ``aggregate_day`` laufen: Nachtlauf, 15-Minuten-Lauf,
«Tag neu aggregieren», «Zeitraum neu aggregieren», «Aus Home Assistant neu übernehmen», Daten-Checker-Knöpfe, Vollbackfill,
Monatsabschluss-Nachlauf, Archiv-Nachzug, Korrektur-Lauf. Felder aus Zählern und HA-Statistik (Quelle mit Historie) folgen
weiter der Quelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._helpers import StrompreisStunden

#: Wetter je Stunde — Schlüssel des Abrufs (``_get_wetter_ist``) = Spalte der Stundenzeile.
WETTER_STUNDE: tuple[str, ...] = (
    "temperatur_c", "globalstrahlung_wm2", "bewoelkung_prozent", "niederschlag_mm", "wetter_code",
)
BOERSE_STUNDE = "boersenpreis_cent"
#: Klasse (d) des Wächters K3 (``test_konformitaet_tep_felder.py``): Stundenspalten aus einem Abruf, die bleiben, wenn
#: der Abruf nichts liefert. Der Wächter liest DIESE Konstante.
ABRUF_FELDER_BEHALTEN: tuple[str, ...] = (*WETTER_STUNDE, BOERSE_STUNDE)


#: Tageswerte aus genau einem Abruf. Liefert der Abruf des Tages GAR NICHTS, bleiben sie wie gespeichert (die gespeicherten
#: Stunden können weniger sein als die des früheren Abrufs — ein Ø über sie wäre eine andere Zahl).
TAG_WETTER: tuple[str, ...] = ("temperatur_min_c", "temperatur_max_c", "strahlung_summe_wh_m2")
TAG_BOERSE: tuple[str, ...] = ("boersenpreis_avg_cent", "boersenpreis_min_cent", "negative_preis_stunden")


@dataclass(frozen=True)
class AbrufBestand:
    """Die gespeicherten Abruf-Werte eines Tages, gelesen VOR dem Löschen (nur Werte, keine ORM-Objekte)."""
    wetter: dict[int, dict] = field(default_factory=dict)     # {stunde: {spalte: wert}} — nur gesetzte Werte
    boerse: dict[int, float] = field(default_factory=dict)    # {stunde: ct/kWh}
    gti_summe: Optional[float] = None                         # Tageszeile ``gti_summe_wh_m2``
    tag: dict = field(default_factory=dict)                   # Tageszeile ``TAG_WETTER`` + ``TAG_BOERSE``


async def lese_abruf_bestand(anlage_id: int, datum: date, db: AsyncSession) -> AbrufBestand:
    """Wetter, Börsenpreis und GTI-Tagessumme des Tages, wie gespeichert."""
    tep, tz = TagesEnergieProfil, TagesZusammenfassung
    spalten = [getattr(tep, f) for f in ABRUF_FELDER_BEHALTEN]
    zeilen = (await db.execute(
        select(tep.stunde, *spalten).where(and_(tep.anlage_id == anlage_id, tep.datum == datum))
    )).all()
    wetter: dict[int, dict] = {}
    boerse: dict[int, float] = {}
    for stunde, *werte in zeilen:
        je_feld = dict(zip(ABRUF_FELDER_BEHALTEN, werte))
        w = {k: je_feld[k] for k in WETTER_STUNDE if je_feld[k] is not None}
        if w:
            wetter[stunde] = w
        if je_feld[BOERSE_STUNDE] is not None:
            boerse[stunde] = je_feld[BOERSE_STUNDE]
    tag_spalten = ("gti_summe_wh_m2", *TAG_WETTER, *TAG_BOERSE)
    tag = (await db.execute(
        select(*[getattr(tz, f) for f in tag_spalten]).where(and_(tz.anlage_id == anlage_id, tz.datum == datum))
    )).first()
    tagwerte = dict(zip(tag_spalten, tag)) if tag is not None else {}
    return AbrufBestand(wetter=wetter, boerse=boerse, gti_summe=tagwerte.pop("gti_summe_wh_m2", None), tag=tagwerte)


@dataclass(frozen=True)
class AbrufLauf:
    """Der Abruf eines Laufs, ergänzt um den Bestand — die Eingänge für ``aggregate_day``."""
    bestand: AbrufBestand
    wetter_stunden: dict
    strompreis: StrompreisStunden
    wetter_leer: bool
    boerse_leer: bool

    def gti(self, akku) -> None:
        """Trug keine Stunde des Abrufs GTI, gilt die gespeicherte Tagessumme (``akku`` = ``TagesAkkumulator``)."""
        if akku.gti_stunden_count == 0 and self.bestand.gti_summe is not None:
            akku.gti_summe = self.bestand.gti_summe

    def tageswerte(self, zusammenfassung) -> None:
        """Lieferte ein Abruf gar nichts, stehen seine Tageswerte wie gespeichert in der neuen Tageszeile."""
        for leer, felder in ((self.wetter_leer, TAG_WETTER), (self.boerse_leer, TAG_BOERSE)):
            for f in felder if leer else ():
                if self.bestand.tag.get(f) is not None:
                    setattr(zusammenfassung, f, self.bestand.tag[f])

    def stunden_ohne_menge(self, geschrieben: set[int]) -> list[int]:
        """Stunden, deren gespeicherte Zeile Abruf-Werte trug und die der Lauf nicht schreibt (keine Menge) — Fund-Päckchen H.

        ``aggregate_day`` schreibt nur Stunden mit Leistungspunkt oder Zählerwert. Fehlt einer Stunde beim Neuaufbau jede
        Menge, verschwand bis hierher ihre Zeile samt Wetter und Börsenpreis (gemessen 23.11.2026 an der Produktiv-Kopie,
        «Tag neu aggregieren» 31.10.2025: 24 → 11 Zeilen). Regel Gernot 23.11.2026: Werte aus einer Quelle ohne Historie
        werden nicht gelöscht. Es entsteht nie eine Zeile, die vorher nicht da war (``schreibe_stunde_ohne_menge``).
        """
        return sorted((self.bestand.wetter.keys() | self.bestand.boerse.keys()) - geschrieben)


def schreibe_stunde_ohne_menge(h: int, kontext, db: AsyncSession, auto_writer: str) -> None:
    """Die Zeile einer Stunde ohne Menge (``AbrufLauf.stunden_ohne_menge``) — gebaut von ``aggregator.baue_stundenzeile``,
    derselben Stelle wie jede Stundenzeile, nur ohne Zählerwerte und ohne Beitrag zum Tages-Akkumulator.

    Sie trägt, was eine geschriebene Stunde ohne Menge trüge: die Abruf-Spalten (je Feld der neue Abruf, sonst der
    gespeicherte Wert) und die Felder der N-595-Rettung — Betriebsart, Ladestand, Endkundenpreis: die Quelle gewinnt, wo sie
    liefert, sonst der gerettete Wert mit seiner alten Herkunft (``fuehre_gerettete_stunden_zusammen``, dieselbe Bedingung
    wie an jeder Stunde). Alle Mengen sind leer (Zähler-kWh, Leistungsverlauf, Spannen, Starts und Betriebsstunden der
    Zähler). Die Tageszeile rechnet ohne sie (Stundenzahl, Wetter-Tageswerte, Vollzyklen, PR, §51 wie ohne die Zeile).
    """
    from backend.services.energie_profil import aggregator as ag

    leer = ag.Zaehlerstunde(None, None, None, None, None, None, None, None)
    sp = kontext.strompreis_stunden
    profil = ag.baue_stundenzeile(h, {}, leer, ag.wetter_der_stunde(h, kontext), None, None, kontext.soc_stunden.get(h),
                                  sp.sensor.get(h), sp.boerse.get(h), kontext)
    profil.wp_starts_anzahl = profil.wp_betriebsstunden = None      # Zählerwerte, keine Werte dieser Stunde
    db.add(profil)
    ag.seed_tep_provenance(profil, writer=auto_writer, source=kontext.kwh_source_label)
    if kontext.gerettete_herkunft.get(h):
        ag.setze_gerettete_herkunft(profil, kontext.gerettete_herkunft[h])


async def abruf_mit_bestand(anlage_id: int, datum: date, db: AsyncSession, wetter_stunden: dict,
                            strompreis: StrompreisStunden) -> AbrufLauf:
    """Vor dem Löschen: den Bestand lesen und je Feld mit dem Abruf zusammenführen."""
    bestand = await lese_abruf_bestand(anlage_id, datum, db)
    return AbrufLauf(bestand=bestand, wetter_stunden=wetter_mit_bestand(wetter_stunden, bestand),
                     strompreis=boerse_mit_bestand(strompreis, bestand),
                     wetter_leer=not wetter_stunden, boerse_leer=not strompreis.boerse)


def wetter_mit_bestand(wetter_stunden: dict, bestand: AbrufBestand) -> dict:
    """Je Stunde und Spalte der Abrufwert, sonst der gespeicherte."""
    if not bestand.wetter:
        return wetter_stunden
    ergebnis = {h: dict(w) for h, w in wetter_stunden.items()}
    for h, alt in bestand.wetter.items():
        neu = ergebnis.setdefault(h, {})
        for k, v in alt.items():
            if neu.get(k) is None:
                neu[k] = v
    return ergebnis


def boerse_mit_bestand(strompreis: StrompreisStunden, bestand: AbrufBestand) -> StrompreisStunden:
    """Je Stunde der abgerufene Börsenpreis, sonst der gespeicherte; der Sensor-Endpreis bleibt unberührt."""
    if not bestand.boerse:
        return strompreis
    boerse = {**bestand.boerse, **{h: v for h, v in strompreis.boerse.items() if v is not None}}
    return StrompreisStunden(sensor=strompreis.sensor, boerse=boerse)
