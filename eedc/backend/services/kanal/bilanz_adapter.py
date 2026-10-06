"""Adapter der Bilanz-Gruppe — Tages- und Monatssummen aus den Kanälen in der Datenform der heutigen Leser
(HA-Bauform E4a, Teil 1; Bauplan §6/§6a „Bilanz-Gruppe", §3b; Auftrag ``plans/auftrag-ha-bauform-e4a1.md``).

**Stand E4a-1: gebaut und gegen den Bestand geprüft, von NIEMANDEM benutzt** (kein Umschalten; Wächter
``test_kanal_lesen_waechter.py`` — außerhalb ``services/kanal/`` importiert niemand die Schicht oder diese Adapter).

**Bilanz-Gruppe** = die gemeinsamen Eingänge der Bilanz-Formel (``verbrauch.berechne_verbrauchs_kennzahlen``):
Netz (Einspeisung, Netzbezug), PV und Balkonkraftwerk (samt Anlagenzähler), Speicher (Ladung, Entladung) und die
Erzeuger hinter dem Zähler (Kategorie ``erzeugung_sonstiges``). Achsen ``BILANZ_ACHSEN``.

Drei Rückgabeformen, je die des Lesers, den der Adapter ersetzt — und dessen Fenster:

* ``tage_aus_kanaelen`` → je Tag ``KanalTag``: ``komponenten_kwh`` · ``pv_marken`` · ``verworfen`` wie
  ``TagesZusammenfassung``, dazu die ``TagesBilanz`` wie ``bilanz_aus_stundenrows`` sie für die Tages-Leser
  (``tage_werte.py``, ``energie_profil/tag.py``/``monat.py``) bildet. Fenster ``fenster.tagesfenster``.
* ``monats_summen_aus_kanaelen`` → je Monat ``TagesMonatsSumme`` wie ``lade_monats_summen_aus_tagen`` — über
  DIESELBE Faltung (``monats_aus_tagen.falte_monat``), Σ der Tage im Monat = ``fenster.monatsfenster``.
* ``sensor_monatswerte_aus_kanaelen`` → ``MonatswertResponse`` wie ``HAStatisticsService.get_monatswerte``
  (Kalendermonat, ``fenster.kalendermonatsfenster``) — die Nutzer von ``get_sensor_monatswert``.

**Zwei benannte Fassungen** (Auftrag Punkt 2):

* ``FASSUNG_WIE_BESTAND`` (a) — dieselben Regeln je Stunde wie der heutige Leser: R4 (Rücksprung verworfen), R3
  (Deckel × Fenster), Either-Or, PV-Tages-Präzedenz, BKW-Rest je Slot, Aggregat-Auflösung (N-623) und R6. **Keine
  Regel ist hier nachgebaut:** die Kanal-Zeilen werden dem UNVERÄNDERTEN HA-Leser vorgelegt (``KanalAlsHaQuelle``
  — der WebSocket-Zweig von ``HAStatisticsService`` liest Zeilen, hier sind es die Kanal-Zeilen), und die Tagesrechnung
  ist ``tages_tabelle.baue_tagestabelle`` selbst; die Stundenzeile entsteht über
  ``energie_profil.aggregator.zaehlerwerte_der_stunde`` + ``rund`` wie beim Schreiben der Stundenzeile. Gebraucht
  für die Gleichheitsprobe und als Rückfall für Nicht-HA-Quellen.
* ``FASSUNG_WIE_HA`` (b) — reines Kanal-Δ über das Fenster des Lesers, ohne Deckel und ohne Rücksprung-Regel (das
  Ziel für den HA-Spiegel nach Teil 2). Komponiert wird mit denselben Layer-Funktionen auf dem Δ: Either-Or
  (``resolve_either_or_eintraege``, „Kanal hat Δ"), BKW-Rest (``bkw_restwerte`` auf dem Tages-Δ), Aggregat-Auflösung
  (``loese_aggregat_tag_auf``); die Bilanz über ``bilanz_aus_stundenrows`` (Regel R7, Mengen = Σ). ⚑ **Zwei Regeln
  gehen nicht an Δ** — sie fragen je STUNDE, ob ein Erzeuger seinen Slot hatte: die PV-Tages-Präzedenz
  (``waehle_pv_quelle`` → ``einzel_deckt_den_tag``) und ``gemessene_tageswerte`` (N-623, „Dämmerungsrest"). (b) ruft
  beide unverändert mit den ungefilterten Stunden-Slots der Kanäle (derselbe HA-Leser, ohne R3/R4), und nur an Tagen
  mit Anlagenzähler UND Einzelzähler — Halt-Punkt H1 im Bericht E4a-1, nicht still entschieden. Ohne Anlagenzähler
  entscheidet das Vorhandensein allein (EIN Pseudo-Slot, wie ``waehle_pv_quelle`` es für den Tagespfad vorsieht).

Ohne Sprung und ohne Rücksprung sind (a) und (b) gleich (Probe ``test_kanal_bilanz_gleichheit.py``).

**Auswahl der Zähler** (dieselbe wie der Tagespfad, keine eigene): die HA-Auswahl ``lts_aggregator._lts_eintraege``,
wenn die Anlage HA-Zähler zugeordnet hat; sonst die MQTT-/Snapshot-Auswahl ``snapshot.aggregator._snapshot_eintraege``.
Filter (aktiv · Anschaffung · Stilllegung) je Tag über ``Investition.ist_aktiv_an`` — dieselbe Grenze wie
``aktiv_am_tag`` im Tagespfad (``utils/investition_filter.py`` nennt die Gleichheit).

Schwesterdateien: ``bilanz_quellenwahl.py`` (Quellenwahl der Gruppe), ``lesen.py``, ``fenster.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
from bisect import bisect_left, bisect_right
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.erzeuger_traeger import bkw_restwerte, ergaenze_kinder_deckung
from backend.core.berechnungen.pv_tages_praezedenz import (
    QUELLE_AGGREGAT,
    QUELLE_EINZEL,
    erwartete_erzeuger_ids,
    gemessene_tageswerte,
    loese_aggregat_tag_auf,
    waehle_pv_quelle,
)
from backend.core.berechnungen.spannen import achse_der_kategorie
from backend.core.berechnungen.tagesbilanz import TagesBilanz, bilanz_aus_stundenrows
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import ART_SUM, FAMILIE_SPIEGEL, Kanal, KanalQuelle
from backend.services.energie_profil.monats_aus_tagen import (
    MonatsSchluessel,
    TagesMonatsSumme,
    TagesZeile,
    falte_monat,
)
from backend.services.ha_statistics_service import (
    HAStatisticsService,
    MonatswertResponse,
    SensorMeta,
    SensorMonatswert,
)
from backend.services.kanal.fenster import kalendermonatsfenster, monate, tagesfenster
from backend.services.kanal.lesen import kanaele_laden, soll_ende, stunden_stapel, zeitraum_stapel
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.snapshot.keys import PV_AGGREGAT_BASIS_FELD
from backend.services.snapshot.komponenten_beitraege import _TYP_KEY_PREFIX, resolve_either_or_eintraege
from backend.services.snapshot.tages_tabelle import TabellenEintrag, TagesTabelle, baue_tagestabelle

FASSUNG_WIE_BESTAND = "wie_bestand"
FASSUNG_WIE_HA = "wie_ha"
FASSUNGEN = (FASSUNG_WIE_BESTAND, FASSUNG_WIE_HA)

#: Die Achsen der Bilanz-Gruppe (``spannen.achse_der_kategorie``): PV inkl. Balkonkraftwerk und Erzeuger hinter dem
#: Zähler, Einspeisung, Netzbezug, Speicher.
BILANZ_ACHSEN: frozenset[str] = frozenset({"pv", "einspeisung", "netzbezug", "batterie"})

_STUNDE = 3600


# ── Kanal-Zeilen als HA-Quelle (für Fassung (a) und die Stunden von N-623) ──


class KanalAlsHaQuelle(HAStatisticsService):
    """Der UNVERÄNDERTE HA-Leser über Kanal-Zeilen statt über HAs Recorder.

    ``HAStatisticsService`` liest im WebSocket-Zweig (``conn is None``) Zeilen ``{start_ts, sum, state}`` über
    ``_ws_zeilen`` und rechnet daraus Slot-Tabelle (``get_hourly_slots_for_day``: Anker, Index, Spanne n,
    Herbst/Frühjahr) und Monatswert (``get_sensor_monatswert``: R4, R3 × Fenster, N-567). Diese Klasse gibt ihm
    die Kanal-Zeilen — „Sensor" ist der Kanal-Schlüssel, Einheit kWh (der Kanal führt kWh), ``sum`` = Kanalwert
    (``sum + offset``). So steht keine Regel ein zweites Mal im Baum. Synchron wie der Leser selbst; die Zeilen
    werden vorher geladen (``_zeilen_laden``).
    """

    def __init__(self, zeilen: dict[str, list[dict]]):
        super().__init__()
        self._kanal_zeilen = {k: sorted(v, key=lambda z: z["start_ts"]) for k, v in zeilen.items()}
        self._kanal_ts = {k: [z["start_ts"] for z in v] for k, v in self._kanal_zeilen.items()}
        self._kanal_ids = {key: i + 1 for i, key in enumerate(sorted(zeilen))}

    @property
    def is_available(self) -> bool:  # noqa: D102 — keine Verbindung nötig, die Zeilen liegen vor
        return True

    @contextmanager
    def _verbindung(self):
        yield None   # ⇒ der Zweig ohne Datenbank: alles läuft über `_ws_zeilen`

    def get_metadata(self, conn, sensor_id: str) -> Optional[SensorMeta]:
        i = self._kanal_ids.get(sensor_id)
        return SensorMeta(id=i, unit="kWh", has_sum=True) if i is not None else None

    def _ws_zeilen(self, sensor_ids, ts_von, ts_bis, *, short_term=False, types=None) -> dict[str, list[dict]]:
        # Beidseitig inklusiv wie das Original (Docstring `HAStatisticsService._ws_zeilen`).
        out = {}
        for sid in sensor_ids:
            if sid in self._kanal_zeilen:
                ts = self._kanal_ts[sid]
                out[sid] = self._kanal_zeilen[sid][bisect_left(ts, ts_von):bisect_right(ts, ts_bis)]
        return out


async def _zeilen_laden(
    db: AsyncSession, kanaele: Sequence[Kanal], von: int, bis: int, *, jetzt: Optional[int],
) -> dict[str, list[dict]]:
    """Die Zeilen ``start_ts ∈ [von, bis)`` je Kanal samt dem Stand davor — eine Anweisung (``stunden_stapel``)."""
    for k in kanaele:
        if k.art != ART_SUM:
            raise ValueError(f"Kanal {k.key}: die Bilanz-Gruppe kennt nur Mengen-Kanäle (Art sum), nicht {k.art}")
    if not kanaele:
        return {}
    out: dict[str, list[dict]] = {}
    for key, st in (await stunden_stapel(db, list(kanaele), von, bis, jetzt=jetzt)).items():
        zeilen: list[dict] = []
        if st.werte and st.werte[0].change is not None:
            w0 = st.werte[0]   # der Stand davor (HAs Anker): Wert und Zeit aus Zuwachs und Spanne der ersten Zeile
            zeilen.append({"start_ts": float(w0.start_ts - w0.spanne), "sum": w0.wert - w0.change,
                           "state": w0.wert - w0.change})
        zeilen.extend({"start_ts": float(w.start_ts), "sum": w.wert, "state": w.wert} for w in st.werte)
        out[key] = zeilen
    return out


# ── Auswahl der Zähler (dieselbe wie der Tagespfad) ─────────────────────────


async def zaehler_eintraege(db: AsyncSession, anlage, invs_by_id: dict, datum: date) -> list[TabellenEintrag]:
    """Die zugeordneten Zähler des Tages, mit ``schluessel`` = Kanal-Schlüssel (``sensor_key``).

    HA-Auswahl (``_lts_eintraege``), wenn die Anlage HA-Zähler zugeordnet hat — so wählt der Tagespfad bei
    erreichbarem HA; sonst die Snapshot-/MQTT-Auswahl (``_snapshot_eintraege``)."""
    from backend.services.snapshot.aggregator import _snapshot_eintraege
    from backend.services.snapshot.lts_aggregator import _lts_eintraege

    roh = _lts_eintraege(anlage, invs_by_id, datum)
    if not roh:
        roh, _entity, _quellen = await _snapshot_eintraege(db, anlage, invs_by_id, datum)
    return [dataclasses.replace(e, schluessel=e.sensor_key) for e in roh]


def bilanz_eintraege(eintraege: Iterable[TabellenEintrag]) -> list[TabellenEintrag]:
    """Nur die Einträge der Bilanz-Gruppe (``BILANZ_ACHSEN``)."""
    return [e for e in eintraege if achse_der_kategorie(e.kategorie) in BILANZ_ACHSEN]


# ── Ergebnisform Tag ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KanalTag:
    """Ein Tag aus den Kanälen in der Form, die die Tages-Leser aus Tages- und Stundenzeilen lesen."""

    datum: date
    fassung: str
    #: wie ``TagesZusammenfassung.komponenten_kwh`` (Zähler-Teil, ``round(v, 2)`` wie ``baue_zusammenfassung``).
    komponenten_kwh: dict[str, float]
    #: #406-Marken wie ``TagesTabelle.pv_marken`` (``source_provenance`` der Tageszeile).
    pv_marken: dict[str, str]
    #: wie ``TagesZusammenfassung.verworfen`` — die Regelmarke; ``{}`` ohne Befund. In (b) immer ``{}``.
    verworfen: dict[str, float]
    #: wie ``bilanz_aus_stundenrows(Stundenzeilen, verworfen=…)``.
    bilanz: TagesBilanz
    #: Zahl der Stundenzeilen, die die Bilanz trägt (Belegdichte wie im Bestand; (b) rechnet ohne Stunden: 0).
    stunden: int = 0
    nachtrag: dict[str, float] = field(default_factory=dict)

    @property
    def source_provenance(self) -> dict:
        """Die Marken in der Form, in der ``TagesZusammenfassung.source_provenance`` sie trägt (gelesen wird nur
        ``abgeleitet``, ``core/berechnungen/energie.py::bkw_gemessen_kwh_je_investition``)."""
        return {f"komponenten_kwh.{k}": {"abgeleitet": v} for k, v in self.pv_marken.items()}


def _stundenzeilen(tabelle: TagesTabelle) -> list[SimpleNamespace]:
    """Die Stundenzeilen, wie ``aggregate_day`` sie aus der Tagestabelle schreibt — über dieselben Funktionen
    (``zaehlerwerte_der_stunde`` + ``rund``), nur nicht in die Datenbank."""
    from backend.services.energie_profil.aggregator import rund, zaehlerwerte_der_stunde

    kontext = SimpleNamespace(kwh_pro_stunde=tabelle.stunden)
    zeilen = []
    for h in range(24):
        z = zaehlerwerte_der_stunde(h, kontext)
        zeilen.append(SimpleNamespace(
            stunde=h, pv_kw=rund(z.pv_kw, 3), verbrauch_kw=rund(z.verbrauch_kw, 3),
            einspeisung_kw=rund(z.einspeisung_kw, 3), netzbezug_kw=rund(z.netzbezug_kw, 3),
            batterie_kw=rund(z.batterie_kw, 3), waermepumpe_kw=rund(z.waermepumpe_kw, 3),
            wallbox_kw=rund(z.wallbox_kw, 3), spannen=z.spannen,
        ))
    return zeilen


def _tag_wie_bestand(anlage, invs_by_id: dict, datum: date, eintraege: list[TabellenEintrag],
                     quelle: KanalAlsHaQuelle) -> Optional[KanalTag]:
    """(a) Slot-Tabelle aus dem unveränderten HA-Leser, Tagesrechnung ``baue_tagestabelle`` — wie
    ``lts_aggregator.lts_tagestabelle``."""
    eigene = list(dict.fromkeys(e.schluessel for e in eintraege))
    reihen = quelle.get_hourly_slots_for_day(eigene, datum)
    if not reihen or not any(k in eigene for k in reihen):
        return None
    tabelle = baue_tagestabelle(
        anlage, invs_by_id, datum, eintraege,
        {k: {h: (s.delta, s.n) for h, s in r.slots.items()} for k, r in reihen.items() if k in eigene},
    )
    zeilen = _stundenzeilen(tabelle)
    return KanalTag(
        datum=datum, fassung=FASSUNG_WIE_BESTAND,
        komponenten_kwh={k: round(v, 2) for k, v in tabelle.komponenten_kwh.items()},
        pv_marken=dict(tabelle.pv_marken), verworfen=dict(tabelle.verworfen),
        bilanz=bilanz_aus_stundenrows(zeilen, verworfen=tabelle.verworfen),
        stunden=len(zeilen), nachtrag=dict(tabelle.nachtrag),
    )


def _tag_wie_ha(anlage, invs_by_id: dict, datum: date, eintraege: list[TabellenEintrag],
                deltas: dict[str, Optional[float]], quelle: KanalAlsHaQuelle) -> Optional[KanalTag]:
    """(b) Kanal-Δ über das Tagesfenster, komponiert mit den Layer-Funktionen; kein R3, kein R4."""
    eintraege = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=lambda e: deltas.get(e.schluessel) is not None,
    )
    mit = [e for e in eintraege if deltas.get(e.schluessel) is not None]
    if not mit:
        return None
    alle_invs = list(invs_by_id.values())
    aggregat_key = f"basis:{PV_AGGREGAT_BASIS_FELD}"
    pv_aggregat: Optional[float] = None
    einzel_eintraege: dict[str, list[tuple[TabellenEintrag, float]]] = {}
    for e in mit:
        if e.kategorie != "pv":
            continue
        if e.sensor_key == aggregat_key:
            pv_aggregat = (pv_aggregat or 0.0) + deltas[e.schluessel]
        else:
            einzel_eintraege.setdefault(e.sensor_key.split(":", 2)[1], []).append((e, deltas[e.schluessel]))
    # ⚑ H1: die PV-Tages-Präzedenz fragt je STUNDE, ob jeder erwartete Erzeuger einen Slot hat
    # (`einzel_deckt_den_tag`). Sie bekommt deshalb die ungefilterten Stunden-Slots derselben Kanäle (kein R3/R4) —
    # nur wenn Aggregat UND Einzelzähler da sind; sonst entscheidet das Vorhandensein allein (dann ist die Wahl
    # stundenunabhängig).
    if einzel_eintraege and pv_aggregat is not None:
        reihen = quelle.get_hourly_slots_for_day(
            [aggregat_key, *[e.schluessel for lst in einzel_eintraege.values() for e, _d in lst]], datum)
        agg = reihen.get(aggregat_key)
        gedeckt: dict[int, set[str]] = {}
        for inv_id, lst in einzel_eintraege.items():
            for e, _d in lst:
                for h in (reihen[e.schluessel].slots if e.schluessel in reihen else ()):
                    gedeckt.setdefault(h, set()).add(inv_id)
        stunden = set(gedeckt) | set(agg.slots if agg else ())
        pv_quelle = waehle_pv_quelle(
            erwartete_ids=erwartete_erzeuger_ids(alle_invs, datum),
            gedeckte_ids_je_slot={h: ergaenze_kinder_deckung(gedeckt.get(h, set()), alle_invs) for h in stunden},
            aggregat_je_slot={h: (agg.slots[h].delta if agg and h in agg.slots else None) for h in stunden},
        )
    else:
        pv_quelle = waehle_pv_quelle(
            erwartete_ids=erwartete_erzeuger_ids(alle_invs, datum),
            gedeckte_ids_je_slot={0: ergaenze_kinder_deckung(einzel_eintraege.keys(), alle_invs)},
            aggregat_je_slot={0: pv_aggregat},
        )
    komponenten: dict[str, float] = {}
    kat_summe: dict[str, float] = {}

    def _nimm(kat: str, target: str, wert: float) -> None:
        kat_summe[kat] = kat_summe.get(kat, 0.0) + wert
        komponenten[target] = komponenten.get(target, 0.0) + wert

    for e in mit:
        if e.kategorie == "pv":
            if e.sensor_key == aggregat_key and pv_quelle == QUELLE_AGGREGAT:
                _nimm("pv", e.target_key, deltas[e.schluessel])
            continue
        _nimm(e.kategorie, e.target_key, e.vorzeichen * deltas[e.schluessel])

    eigen_kwh: dict[str, float] = {}
    if einzel_eintraege and pv_quelle in (QUELLE_EINZEL, QUELLE_AGGREGAT):
        einzel = {inv_id: sum(d for _e, d in lst) for inv_id, lst in einzel_eintraege.items()}
        rest = bkw_restwerte(alle_invs, einzel)
        for inv_id, lst in einzel_eintraege.items():
            wert = rest.get(inv_id, einzel[inv_id])
            if pv_quelle == QUELLE_AGGREGAT:
                eigen_kwh[inv_id] = wert
            else:
                _nimm("pv", lst[0][0].target_key, wert)

    pv_marken: dict[str, str] = {}
    if pv_quelle == QUELLE_AGGREGAT and PV_AGGREGAT_BASIS_FELD in komponenten:
        aggregat = komponenten.pop(PV_AGGREGAT_BASIS_FELD)
        # ⚑ H1: `gemessene_tageswerte` fragt je STUNDE — die ungefilterten Slots derselben Kanäle (kein R3/R4).
        schluessel_je_inv = {inv_id: [e.schluessel for e, _d in lst] for inv_id, lst in einzel_eintraege.items()}
        reihen = quelle.get_hourly_slots_for_day(
            [aggregat_key, *[s for lst in schluessel_je_inv.values() for s in lst]], datum)
        agg_reihe = reihen.get(aggregat_key)
        aggregat_je_stunde = {h: s.delta for h, s in (agg_reihe.slots.items() if agg_reihe else ())}
        eigen_stunden: dict[str, set[int]] = {}
        eigen_buendel: dict[str, float] = {}
        for inv_id, keys in schluessel_je_inv.items():
            for k in keys:
                for h, s in (reihen[k].slots.items() if k in reihen else ()):
                    eigen_stunden.setdefault(inv_id, set()).add(h)
                    if s.n > 1:
                        eigen_buendel[inv_id] = eigen_buendel.get(inv_id, 0.0) + abs(s.delta)
        gemessen = gemessene_tageswerte(
            aggregat_kwh=aggregat, aggregat_je_stunde=aggregat_je_stunde, eigen_kwh=eigen_kwh,
            eigen_stunden=eigen_stunden, eigen_buendel_kwh=eigen_buendel, gesperrt=set(),
        )
        aufloesung = loese_aggregat_tag_auf(
            aggregat_kwh=aggregat, gemessen=gemessen, mit_zaehler=set(eigen_kwh),
            investitionen=alle_invs, datum=datum,
        )
        typ_je_id = {inv.id: getattr(inv, "typ", None) for inv in alle_invs}
        for inv_id, wert in aufloesung.werte.items():
            praefix = _TYP_KEY_PREFIX.get(typ_je_id.get(inv_id))
            if praefix is None:
                continue
            komponenten[f"{praefix}{inv_id}"] = wert
            if inv_id in aufloesung.verteilt:
                pv_marken[f"{praefix}{inv_id}"] = ABGELEITET_KWP_ANTEIL
    else:
        komponenten.pop(PV_AGGREGAT_BASIS_FELD, None)

    # Die Bilanz: dieselbe Layer-Funktion wie am Tag (Regel R7 — Mengen Σ, Gesamtverbrauch nach der HA-Formel,
    # EV = Direktverbrauch + Entladung). Ladung und Entladung tragen getrennte Zeilen, damit das Vorzeichen je
    # Zeile (``batterie_kw``) sie nicht verrechnet; Stundengrößen (Direktverbrauch, Überschuss, Defizit) bleiben 0
    # — sie sind stundengepaart und gehören nicht zur Bilanz-Gruppe (Bauplan §2: abgeleitete Kanäle, S3).
    pv_total = None
    if "pv" in kat_summe or "erzeugung_sonstiges" in kat_summe:
        pv_total = kat_summe.get("pv", 0.0) + kat_summe.get("erzeugung_sonstiges", 0.0)
    ladung = -kat_summe["ladung_batterie"] if "ladung_batterie" in kat_summe else None
    entladung = kat_summe.get("entladung_batterie")
    zeilen = [SimpleNamespace(
        pv_kw=pv_total, verbrauch_kw=None, einspeisung_kw=kat_summe.get("einspeisung"),
        netzbezug_kw=kat_summe.get("netzbezug"), batterie_kw=entladung,
        waermepumpe_kw=kat_summe.get("verbrauch_wp"),
    )]
    if ladung is not None:
        zeilen.append(SimpleNamespace(pv_kw=None, verbrauch_kw=None, einspeisung_kw=None, netzbezug_kw=None,
                                      batterie_kw=-ladung, waermepumpe_kw=None))
    return KanalTag(
        datum=datum, fassung=FASSUNG_WIE_HA,
        komponenten_kwh={k: round(v, 2) for k, v in komponenten.items()},
        pv_marken=pv_marken, verworfen={}, bilanz=bilanz_aus_stundenrows(zeilen, verworfen={}), stunden=0,
    )


# ── Laden einer Tagesfolge ──────────────────────────────────────────────────


@dataclass
class _Lauf:
    anlage: Any
    invs: list
    eintraege_je_tag: dict[date, list[TabellenEintrag]]
    kanaele: dict[str, Kanal]
    quelle: KanalAlsHaQuelle
    deltas_je_tag: dict[date, dict[str, Optional[float]]]


def _tage(von: date, bis: date) -> list[date]:
    out, d = [], von
    while d <= bis:
        out.append(d)
        d += timedelta(days=1)
    return out


async def _lauf_laden(db: AsyncSession, anlage_id: int, tage: list[date], *, fassung: str,
                      jetzt: Optional[int]) -> _Lauf:
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    invs = list((await db.execute(select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all())
    eintraege_je_tag: dict[date, list[TabellenEintrag]] = {}
    for tag in tage:
        invs_by_id = {str(i.id): i for i in invs if i.ist_aktiv_an(tag)}
        eintraege_je_tag[tag] = await zaehler_eintraege(db, anlage, invs_by_id, tag)
    keys = list(dict.fromkeys(e.schluessel for lst in eintraege_je_tag.values() for e in lst))
    kanaele = await kanaele_laden(db, anlage_id, keys)
    mengen = [k for k in kanaele.values() if k.art == ART_SUM]
    zeilen: dict[str, list[dict]] = {}
    deltas_je_tag: dict[date, dict[str, Optional[float]]] = {t: {} for t in tage}
    if mengen and tage:
        von = tagesfenster(tage[0])[0] - _STUNDE   # die Zeile, die Slot 23 des Vortags schließt (Index −1)
        bis = tagesfenster(tage[-1])[1]
        zeilen = await _zeilen_laden(db, mengen, von, bis, jetzt=jetzt)
        if fassung == FASSUNG_WIE_HA:
            from backend.services.kanal.lesen import reihe_stapel

            grenzen = [tagesfenster(t)[0] for t in tage] + [tagesfenster(tage[-1])[1]]
            if all(b > a for a, b in zip(grenzen, grenzen[1:])):
                je = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt)
                for key, liste in je.items():
                    for tag, z in zip(tage, liste):
                        deltas_je_tag[tag][key] = z.delta if z.voll else None
    return _Lauf(anlage, invs, eintraege_je_tag, kanaele, KanalAlsHaQuelle(zeilen), deltas_je_tag)


def _tage_bis_soll_ende(tage: list[date], jetzt: Optional[int]) -> list[date]:
    """Nur Tage, deren Fenster vor dem Soll-Ende des Stundenlaufs begonnen hat — ein Tag ohne fällige Stunde hat
    noch keine Tageszeile (der Bestand schreibt den laufenden Tag erst mit seiner ersten Stunde)."""
    if jetzt is None:
        import time as _t
        jetzt = int(_t.time())
    se = soll_ende(jetzt)
    return [t for t in tage if tagesfenster(t)[0] < se]


async def tage_aus_kanaelen(
    db: AsyncSession, anlage_id: int, von: date, bis: date, *, fassung: str = FASSUNG_WIE_HA,
    jetzt: Optional[int] = None,
) -> dict[date, KanalTag]:
    """Je Tag ``von`` … ``bis`` (inklusive, nur Tage mit fälliger Stunde) ein ``KanalTag`` aus den Kanälen.

    Liest jeden Kanal einmal (``stunden_stapel`` über alle Tage; in (b) dazu ``reihe_stapel`` über die
    Tagesgrenzen). Ein Tag ohne Kanalwert fehlt (keine Aussage — wie ein Tag ohne Tageszeile). Wählt NICHT die
    Quelle — das ist ``bilanz_quellenwahl``; die Adapter rechnen, was die Kanäle sagen.
    """
    if fassung not in FASSUNGEN:
        raise ValueError(f"unbekannte Fassung {fassung!r}")
    tage = _tage_bis_soll_ende(_tage(von, bis), jetzt)
    if not tage:
        return {}
    lauf = await _lauf_laden(db, anlage_id, tage, fassung=fassung, jetzt=jetzt)
    out: dict[date, KanalTag] = {}
    for tag in tage:
        invs_by_id = {str(i.id): i for i in lauf.invs if i.ist_aktiv_an(tag)}
        eintraege = [e for e in lauf.eintraege_je_tag[tag] if e.schluessel in lauf.kanaele]
        if not eintraege:
            continue
        if fassung == FASSUNG_WIE_BESTAND:
            erg = _tag_wie_bestand(lauf.anlage, invs_by_id, tag, eintraege, lauf.quelle)
        else:
            erg = _tag_wie_ha(lauf.anlage, invs_by_id, tag, eintraege, lauf.deltas_je_tag[tag], lauf.quelle)
        if erg is not None:
            out[tag] = erg
    return out


# ── Monat (Tagesfenster-Monat, wie `lade_monats_summen_aus_tagen`) ──────────


def _letzter_tag(jahr: int, monat: int) -> date:
    return (date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)) - timedelta(days=1)


def monats_summe_aus_tagen(tage: Iterable[KanalTag]) -> TagesMonatsSumme:
    """Ein Monat aus seinen Kanal-Tagen — DIESELBE Faltung wie der Bestand (``monats_aus_tagen.falte_monat``)."""
    tage = sorted(tage, key=lambda t: t.datum)
    return falte_monat(
        stunden_tage=[(t.datum, t.bilanz, t.stunden) for t in tage],
        tageszeilen=[TagesZeile(datum=t.datum, komponenten_kwh=t.komponenten_kwh,
                                source_provenance=t.source_provenance) for t in tage],
    )


async def monats_summen_aus_kanaelen(
    db: AsyncSession, anlage_id: int, *, von: MonatsSchluessel, bis: MonatsSchluessel,
    fassung: str = FASSUNG_WIE_HA, jetzt: Optional[int] = None,
) -> dict[MonatsSchluessel, TagesMonatsSumme]:
    """Je Monat ``von`` … ``bis`` (inklusive) eine ``TagesMonatsSumme`` aus den Kanälen — Fenster
    ``fenster.monatsfenster`` (Σ der Tagesfenster), Faltung ``falte_monat``. Die E-Mobilitäts-Aufteilung
    (``emob_ladung_*_abgeleitet_kwh``) ist NICHT Teil der Bilanz-Gruppe und bleibt hier leer (U5, Auftrag E4c);
    ``tage``/``stunden`` sind die Tage mit Kanalwert bzw. deren Stundenzeilen ((b): 0)."""
    liste = monate(von, bis)
    if not liste:
        return {}
    tage = await tage_aus_kanaelen(db, anlage_id, date(*liste[0], 1), _letzter_tag(*liste[-1]),
                                   fassung=fassung, jetzt=jetzt)
    je_monat: dict[MonatsSchluessel, list[KanalTag]] = {}
    for t in tage.values():
        je_monat.setdefault((t.datum.year, t.datum.month), []).append(t)
    return {m: monats_summe_aus_tagen(je_monat[m]) for m in liste if m in je_monat}


# ── Kalendermonat je Sensor (wie `get_monatswerte`) ─────────────────────────


async def kanal_je_sensor(db: AsyncSession, anlage_id: int) -> dict[str, str]:
    """``{HA-Entity: Kanal-Schlüssel}`` der Spiegel-Kanäle (geltende Quelle = die jüngste ``kanal_quelle``)."""
    zeilen = (await db.execute(
        select(Kanal.key, KanalQuelle.statistic_id, KanalQuelle.familie, KanalQuelle.gueltig_ab)
        .join(KanalQuelle, KanalQuelle.kanal_id == Kanal.id)
        .where(and_(Kanal.anlage_id == anlage_id, Kanal.art == ART_SUM))
        .order_by(Kanal.key, KanalQuelle.gueltig_ab)
    )).all()
    juengste: dict[str, tuple[Optional[str], str]] = {}
    for key, sid, familie, _ab in zeilen:
        juengste[key] = (sid, familie)
    return {sid: key for key, (sid, familie) in juengste.items() if familie == FAMILIE_SPIEGEL and sid}


async def sensor_monatswerte_aus_kanaelen(
    db: AsyncSession, anlage_id: int, sensor_ids: Sequence[str], jahr: int, monat: int, *,
    deckel_je_sensor: Optional[dict[str, float]] = None, fassung: str = FASSUNG_WIE_HA,
    jetzt: Optional[int] = None,
) -> MonatswertResponse:
    """Wie ``HAStatisticsService.get_monatswerte`` (Kalendermonat ``fenster.kalendermonatsfenster``), aus den
    Spiegel-Kanälen der genannten Entities. Ein Sensor ohne Kanal fehlt im Ergebnis (wie ein Sensor, den HA nicht
    kennt). (a) ist der unveränderte ``get_sensor_monatswert`` über die Kanal-Zeilen (R4, R3 × Fenster, N-567);
    (b) ist das Kanal-Δ (``zeitraum``) ohne Regel — nur bei voller Abdeckung."""
    if fassung not in FASSUNGEN:
        raise ValueError(f"unbekannte Fassung {fassung!r}")
    zuordnung = await kanal_je_sensor(db, anlage_id)
    gefragt = {sid: zuordnung[sid] for sid in sensor_ids if sid in zuordnung}
    kanaele = await kanaele_laden(db, anlage_id, list(gefragt.values()))
    von, bis = kalendermonatsfenster(jahr, monat)
    sensoren: list[SensorMonatswert] = []
    if fassung == FASSUNG_WIE_BESTAND:
        zeilen = await _zeilen_laden(db, [kanaele[k] for k in gefragt.values() if k in kanaele], von, bis, jetzt=jetzt)
        quelle = KanalAlsHaQuelle(zeilen)
        deckel = {gefragt[sid]: d for sid, d in (deckel_je_sensor or {}).items() if sid in gefragt}
        # Wie jeder Aufruf des HA-Lesers aus einer async-Funktion: im Thread (Wächter `test_ha_last_und_index.py`).
        # Hier liest er keine Recorder-Datei, sondern die vorab geladenen Kanal-Zeilen — reine Rechnung.
        antwort = await asyncio.to_thread(
            quelle.get_monatswerte, list(gefragt.values()), jahr, monat, deckel_je_sensor=deckel)
        zurueck = {key: sid for sid, key in gefragt.items()}
        sensoren = [w.model_copy(update={"sensor_id": zurueck[w.sensor_id]}) for w in antwort.sensoren]
    else:
        je = await zeitraum_stapel(db, [kanaele[k] for k in gefragt.values() if k in kanaele], von, bis, jetzt=jetzt)
        for sid, key in gefragt.items():
            z = je.get(key)
            if z is None or not z.voll:
                continue
            sensoren.append(SensorMonatswert(
                sensor_id=sid, start_wert=round(z.wert_von, 3), end_wert=round(z.wert_bis, 3),
                differenz=round(z.delta, 2), verworfen_kwh=0.0, nachtrag_kwh=0.0,
                # Stunden des gedeckten Zeitraums (≥ 1) — N-585 liest nur „0 = keine Messung" daraus.
                intervalle=max(1, round((z.gedeckt_bis - z.gedeckt_von) / _STUNDE)),
            ))
    return MonatswertResponse(jahr=jahr, monat=monat, monat_name=HAStatisticsService.MONAT_NAMEN[monat],
                              sensoren=sensoren, abfrage_zeitpunkt=datetime.now())


__all__ = [
    "BILANZ_ACHSEN", "FASSUNGEN", "FASSUNG_WIE_BESTAND", "FASSUNG_WIE_HA", "KanalAlsHaQuelle", "KanalTag",
    "bilanz_eintraege", "kanal_je_sensor", "monats_summe_aus_tagen", "monats_summen_aus_kanaelen",
    "sensor_monatswerte_aus_kanaelen", "tage_aus_kanaelen", "zaehler_eintraege",
]
