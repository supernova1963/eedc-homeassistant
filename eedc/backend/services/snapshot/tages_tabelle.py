"""Die Tagestabelle — Stunden und Tag aus EINER Slot-Tabelle (Zählerlücken wie HA).

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7, R2–R6. Beide
Aggregatoren — HA-Langzeitstatistik (`lts_aggregator`) und Snapshot/MQTT
(`snapshot/aggregator`, Standalone) — liefern je Zähler eine Folge belegter
Slots ``{h: (delta, n)}``; **ab hier ist die Rechnung dieselbe**:

* Either-Or je Tag, R4 (negatives Delta ⇒ verworfen), R3 (Deckel × Spanne je
  Sensor-Slot und auf die Achsensumme der Stunde),
* PV-Präzedenz je Tag und BKW-Rest je Slot (#406, N-536),
* Achsen-Spanne (max n der verwendeten Sensor-Slots) und R6-Verbrauch,
* `komponenten_kwh` = Σ der in den Stunden verwendeten Gerätewerte (R5b),
  E4 BKW-Rest.
* **Aggregat-Fall (N-623, Bauplan Fassung 2):** die Stundenachse ist die
  Aggregat-Summe; ein Erzeuger mit eigenem Zähler behält seinen **Tageswert**
  (Σ seiner brauchbaren Slots, in keiner Stunde), wenn er gemessen ist
  (`pv_tages_praezedenz.gemessene_tageswerte`), die übrigen Träger teilen den
  Rest nach kWp (`pv_tages_praezedenz.loese_aggregat_tag_auf`). Σ Keys ==
  Σ Stunden. Bis 04.10.2026 (seit v4.0.51) verwarf dieser Fall die Messungen
  und gab jedem Erzeuger den kWp-Anteil.

⛔ Eine zweite Fassung dieser Rechnung im Snapshot-Pfad wäre die F-56-Klasse,
die bis 29.08.2026 schon einmal mit der Verbrauchsformel entstanden war.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from backend.core.berechnungen.erzeuger_traeger import (
    bkw_restwerte,
    ergaenze_kinder_deckung,
)
from backend.core.berechnungen.pv_tages_praezedenz import (
    QUELLE_AGGREGAT,
    QUELLE_EINZEL,
    erwartete_erzeuger_ids,
    gemessene_tageswerte,
    loese_aggregat_tag_auf,
    waehle_pv_quelle,
)
from backend.core.berechnungen.spannen import (
    ACHSEN_MIT_DECKEL,
    achse_der_kategorie,
    deckel_fenster_je_slot,
    verbrauch_spannen_passen,
)
from backend.core.berechnungen.stundenbilanz import (
    berechne_batterie_netto_kwh,
    stunden_verbrauch_kwh,
)
from backend.services.snapshot.keys import PV_AGGREGAT_BASIS_FELD
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.snapshot.komponenten_beitraege import (
    _TYP_KEY_PREFIX,
    resolve_either_or_eintraege,
)
from backend.services.snapshot.plausibility import (
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)

logger = logging.getLogger(__name__)

#: Energie-Kategorien je Achse, die ein gemessener Wert auf dieser Achse trägt.
_PV_KATEGORIEN = ("pv", "erzeugung_sonstiges")


@dataclass(frozen=True)
class TabellenEintrag:
    """Ein zugeordneter Zähler: woher (``schluessel`` — HA-Entity im LTS-Pfad,
    `sensor_key` im Snapshot-Pfad), wohin (Kategorie → Achse) und in welchen
    `komponenten_kwh`-Schlüssel mit welchem Vorzeichen."""
    schluessel: str
    kategorie: str
    gruppe: Optional[str]
    sensor_key: str
    target_key: str
    vorzeichen: int


@dataclass
class TagesTabelle:
    """Stunden und Tag eines Tages aus EINER Slot-Tabelle (`baue_tagestabelle`).

    ``stunden``: ``{h: {pv, erzeugung_sonstiges, einspeisung, netzbezug,
    batterie_netto, wp, wallbox, verbrauch_sonstiges, verbrauch, spannen}}`` —
    dasselbe Format wie bisher, dazu ``spannen`` (``{achse: n}`` nur für n > 1).
    ``komponenten_kwh``: Σ der in den Stunden verwendeten Gerätewerte je
    Ziel-Key (R5b); im PV-Aggregat-Fall die Auflösung auf Träger-Ebene
    (N-623: gemessene Erzeuger mit ihrem Tageswert, die übrigen mit dem
    kWp-Anteil am Rest). ``pv_marken``: #406-Herkunftsmarken. ``verworfen``:
    ``{achse: kWh}`` verworfener Mengen (R4) — ``{}`` heißt „nichts verworfen".
    ``nachtrag``: ``{achse: kWh}`` der Stunden, die **nur durch das Deckel-Fenster**
    passiert sind (N-567) — Menge über Schwelle × n, aber nicht über Schwelle × Fenster
    (Nullstunden davor, R3 Nachträge II). Sie zählen wie in HA; das Feld benennt sie nur.
    """
    stunden: dict[int, dict[str, Optional[float]]]
    komponenten_kwh: dict[str, float] = field(default_factory=dict)
    pv_marken: dict[str, str] = field(default_factory=dict)
    verworfen: dict[str, float] = field(default_factory=dict)
    nachtrag: dict[str, float] = field(default_factory=dict)
    #: N-555 Stufe 3 (Konzept 7.2 Anhang D, D-6): die Slots ``{h: (delta, n)}`` der
    #: **zusätzlich** gelesenen Zähler (Heimlade-Zähler je Auto), roh aus demselben
    #: Lesezugriff. Sie gehen in keine Achse und in keinen Tageswert — die Rechnung der
    #: Tabelle sieht sie nicht; nur der Ladeblock-Hook liest sie.
    zusatz_slots: dict[str, dict[int, tuple[float, int]]] = field(default_factory=dict)


def baue_tagestabelle(
    anlage,
    investitionen_by_id: dict,
    datum: date,
    eintraege: list[TabellenEintrag],
    slots_je_schluessel: dict[str, dict[int, tuple[float, int]]],
    *,
    ohne_tageswert: frozenset[str] = frozenset(),
) -> TagesTabelle:
    """Die gemeinsame Rechnung beider Aggregatoren (R2–R6, E3, E4).

    Args:
        eintraege: die zugeordneten Zähler des Tages (eine Auswahl für Stunde
            und Tag, Beitragsschicht).
        slots_je_schluessel: je ``schluessel`` die **belegten** Slots
            ``{h: (delta, n)}`` — Rohdelta inklusive Vorzeichen; ein negatives
            Delta verwirft diese Funktion (R4).
        ohne_tageswert: Schlüssel, deren Tageswert abgelehnt ist, obwohl ihre
            Stunden zählen — der Snapshot-Tagesreset (R4: in der Stunde eine
            Menge; Rücksprung-Entscheid 28.08.: am Tag keine Aussage). Ihre
            Slots gehen in die Stunden, nicht in `komponenten_kwh`.
    """

    def _hat_tagesdaten(e: TabellenEintrag) -> bool:
        return bool(slots_je_schluessel.get(e.schluessel))

    eintraege = resolve_either_or_eintraege(
        eintraege, gruppe_fn=lambda e: e.gruppe, hat_tagesdaten_fn=_hat_tagesdaten,
    )

    kwp = getattr(anlage, "leistung_kwp", None)
    verworfen: dict[str, float] = {}
    nachtrag: dict[str, float] = {}

    def _verwerfe(achse: str, kwh: float) -> None:
        verworfen[achse] = verworfen.get(achse, 0.0) + abs(kwh)

    # N-623: Zähler mit einem verworfenen Slot tragen am Aggregat-Tag keinen Tageswert.
    verworfene_schluessel: set[str] = set()

    # ── 3. Sensor-Slots filtern (R4 negativ, R3 je Sensor-Slot) ─────────────
    # je Stunde: Liste (eintrag, delta, n) der brauchbaren Sensor-Slots
    brauchbar: dict[int, list[tuple[TabellenEintrag, float, int]]] = {h: [] for h in range(24)}
    # R3, Nachträge II: Deckel-Fenster = Zeit seit der letzten Änderung des
    # Standes (Nullzeilen eines eingefrorenen Zählers zählen mit), nicht n.
    fenster_je: dict[tuple[str, int], int] = {}
    for e in eintraege:
        slots = slots_je_schluessel.get(e.schluessel)
        if not slots:
            continue
        achse = achse_der_kategorie(e.kategorie)
        _fenster = deckel_fenster_je_slot((h, d, n) for h, (d, n) in slots.items())
        for h, (delta, n) in slots.items():
            fenster_je[(e.schluessel, h)] = _fenster.get(h, n)
            if not 0 <= h <= 23:
                continue
            if delta < 0:
                logger.warning(
                    f"Anlage {anlage.id}, {datum} h={h} {e.schluessel}: "
                    f"negatives Zähler-Delta {delta:.3f} — verworfen (R4)"
                )
                _verwerfe(achse, delta)
                verworfene_schluessel.add(e.schluessel)
                continue
            if achse in ACHSEN_MIT_DECKEL:
                schwelle = schwelle_pv_einspeisung_stunde_kwh(
                    kwp, spanne=fenster_je[(e.schluessel, h)],
                )
                if cap_pv_einspeisung_stunde(
                    delta, schwelle, anlage_id=anlage.id, datum=datum,
                    stunde=h, kategorie=f"{achse}:{e.schluessel}",
                ) is None:
                    _verwerfe(achse, delta)
                    verworfene_schluessel.add(e.schluessel)
                    continue
            brauchbar[h].append((e, delta, n))

    # ── 4. PV-Präzedenz je Tag (#406, N-536) ──────────────────────────────
    pv_aggregat_je_slot: dict[int, Optional[float]] = {}
    pv_einzel_je_slot: dict[int, dict[str, float]] = {}
    for h in range(24):
        pv_aggregat_je_slot[h] = None
        pv_einzel_je_slot[h] = {}
        for e, delta, _n in brauchbar[h]:
            if e.kategorie != "pv":
                continue
            if e.sensor_key == f"basis:{PV_AGGREGAT_BASIS_FELD}":
                pv_aggregat_je_slot[h] = (pv_aggregat_je_slot[h] or 0.0) + delta
            else:
                inv_id = e.sensor_key.split(":", 2)[1]
                pv_einzel_je_slot[h][inv_id] = pv_einzel_je_slot[h].get(inv_id, 0.0) + delta
    _alle_invs = list(investitionen_by_id.values())
    pv_quelle = waehle_pv_quelle(
        erwartete_ids=erwartete_erzeuger_ids(investitionen_by_id.values(), datum),
        gedeckte_ids_je_slot={
            h: ergaenze_kinder_deckung(ids.keys(), _alle_invs)
            for h, ids in pv_einzel_je_slot.items()
        },
        aggregat_je_slot=pv_aggregat_je_slot,
    )

    komponenten: dict[str, float] = {}
    # Tagesreset (Snapshot): die Ziel-Keys der abgelehnten Zähler tragen keinen
    # Tageswert. Ein Ziel mit einem abgelehnten Zähler ist als GANZES ohne
    # Aussage — eine Teilsumme der übrigen Summanden wäre eine Behauptung.
    ohne_ziel = {e.target_key for e in eintraege if e.schluessel in ohne_tageswert}
    stunden: dict[int, dict[str, Optional[float]]] = {}
    # N-623, Aggregat-Fall: je Erzeuger mit eigenem Zähler der Tageswert (Σ seiner
    # brauchbaren Slots, BKW mit Kindern als Rest je Slot), die Stunden mit eigenem
    # Slot, seine Bündel-Energie und seine Schlüssel; dazu die verwendeten
    # Aggregat-Slots. Nichts davon geht in eine Stunde.
    eigen_kwh: dict[str, float] = {}
    eigen_stunden: dict[str, set[int]] = {}
    eigen_buendel: dict[str, float] = {}
    eigen_schluessel: dict[str, set[str]] = {}
    aggregat_je_stunde: dict[int, float] = {}
    for h in range(24):
        # Verwendete Gerätewerte dieser Stunde je Achse: [(target_key, wert, n)]
        je_achse: dict[str, list[tuple[str, float, int]]] = {}
        kat_summe: dict[str, float] = {}
        fenster_achse: dict[str, int] = {}

        def _nimm(achse: str, kat: str, target: str, wert: float, n: int, fenster: int) -> None:
            je_achse.setdefault(achse, []).append((target, wert, n))
            kat_summe[kat] = kat_summe.get(kat, 0.0) + wert
            fenster_achse[achse] = max(fenster_achse.get(achse, 1), fenster)

        einzel_eintraege = {}
        for e, delta, n in brauchbar[h]:
            achse = achse_der_kategorie(e.kategorie)
            if e.kategorie == "pv":
                if e.sensor_key == f"basis:{PV_AGGREGAT_BASIS_FELD}":
                    if pv_quelle == QUELLE_AGGREGAT:
                        _nimm("pv", "pv", e.target_key, delta, n, fenster_je[(e.schluessel, h)])
                elif pv_quelle in (QUELLE_EINZEL, QUELLE_AGGREGAT):
                    inv_id = e.sensor_key.split(":", 2)[1]
                    einzel_eintraege.setdefault(inv_id, []).append((e, delta, n))
                continue
            _nimm(achse, e.kategorie, e.target_key, e.vorzeichen * delta, n,
                  fenster_je[(e.schluessel, h)])

        if einzel_eintraege:
            einzel = {inv_id: sum(d for _e, d, _n in lst) for inv_id, lst in einzel_eintraege.items()}
            rest = bkw_restwerte(_alle_invs, einzel)       # E4: je Slot ≥ 0 geklemmt
            for inv_id, lst in einzel_eintraege.items():
                wert = rest.get(inv_id, einzel[inv_id])
                if pv_quelle == QUELLE_AGGREGAT:
                    # N-623: Tageswert des eigenen Zählers — geht in KEINE Stunde.
                    eigen_kwh[inv_id] = eigen_kwh.get(inv_id, 0.0) + wert
                    eigen_stunden.setdefault(inv_id, set()).add(h)
                    eigen_schluessel.setdefault(inv_id, set()).update(_e.schluessel for _e, _d, _n in lst)
                    eigen_buendel[inv_id] = eigen_buendel.get(inv_id, 0.0) + sum(
                        abs(_d) for _e, _d, _n in lst if _n > 1
                    )
                    continue
                n_max = max(n for _e, _d, n in lst)
                f_max = max(fenster_je[(_e.schluessel, h)] for _e, _d, _n in lst)
                _nimm("pv", "pv", lst[0][0].target_key, wert, n_max, f_max)

        # ── 5. Deckel auf die Achsensumme (R3) ────────────────────────────
        for achse in ACHSEN_MIT_DECKEL:
            beitraege = je_achse.get(achse)
            if not beitraege:
                continue
            summe = sum(w for _t, w, _n in beitraege)
            # R3, Nachträge II: das Fenster der Achse ist das längste ihrer Sensoren.
            schwelle = schwelle_pv_einspeisung_stunde_kwh(kwp, spanne=fenster_achse[achse])
            if cap_pv_einspeisung_stunde(
                summe, schwelle, anlage_id=anlage.id, datum=datum, stunde=h, kategorie=achse,
            ) is None:
                _verwerfe(achse, summe)
                je_achse.pop(achse)
                for kat in ((_PV_KATEGORIEN) if achse == "pv" else (achse,)):
                    kat_summe.pop(kat, None)
                continue
            # N-567: passiert, aber nur dank des Fensters? Dann ist es ein Nachtrag nach
            # Nullstunden (eingefrorener Zähler — oder ein Sprung nach einer Nacht mit echten
            # Nullen, den eedc nicht unterscheiden kann). Er zählt wie in HA; hier wird er
            # nur BENANNT, damit der Daten-Checker ihn zeigen kann — vorher (Fenster n) stand
            # er in `verworfen`, seit dem Fenster wäre er sonst nirgends sichtbar.
            # (Über Schwelle × n und trotzdem durch den Deckel ⇒ das Fenster war größer als n.)
            n_achse = max(n for _t, _w, n in beitraege)
            schwelle_n = schwelle_pv_einspeisung_stunde_kwh(kwp, spanne=n_achse)
            if schwelle_n is not None and abs(summe) > schwelle_n:
                nachtrag[achse] = nachtrag.get(achse, 0.0) + abs(summe)

        # ── 7. komponenten_kwh aus denselben Werten (R5b) ────────────────
        for beitraege in je_achse.values():
            for target, wert, _n in beitraege:
                if target in ohne_ziel:
                    continue
                komponenten[target] = komponenten.get(target, 0.0) + wert

        for target, wert, _n in je_achse.get("pv", []):
            if target == PV_AGGREGAT_BASIS_FELD:
                aggregat_je_stunde[h] = aggregat_je_stunde.get(h, 0.0) + wert

        # ── 6. Spannen + Stundenwerte ─────────────────────────────────────
        spannen = {
            achse: n_max
            for achse, beitraege in je_achse.items()
            if (n_max := max(n for _t, _w, n in beitraege)) > 1
        }
        pv = kat_summe.get("pv") if "pv" in je_achse else None
        sonst_erz = kat_summe.get("erzeugung_sonstiges") if "pv" in je_achse else None
        pv_total = None
        if pv is not None or sonst_erz is not None:
            pv_total = (pv or 0.0) + (sonst_erz or 0.0)
        einsp = kat_summe.get("einspeisung") if "einspeisung" in je_achse else None
        bez = kat_summe.get("netzbezug")
        # Vorzeichen der Beitragsschicht zurücknehmen: Ladung trägt −1.
        ladung_batt = -kat_summe["ladung_batterie"] if "ladung_batterie" in kat_summe else None
        entladung_batt = kat_summe.get("entladung_batterie")
        wp = kat_summe.get("verbrauch_wp")
        wallbox = kat_summe.get("ladung_wallbox")
        eauto = kat_summe.get("verbrauch_eauto")
        sonst_verbr = kat_summe.get("verbrauch_sonstiges")

        batt_netto = berechne_batterie_netto_kwh(
            ladung_kwh=ladung_batt, entladung_kwh=entladung_batt,
        )
        verbrauch = (
            stunden_verbrauch_kwh(
                pv_kwh=pv_total, netzbezug_kwh=bez, einspeisung_kwh=einsp,
                batterie_netto_kwh=batt_netto,
            )
            if verbrauch_spannen_passen(spannen, batterie_da=batt_netto is not None)
            else None
        )
        stunden[h] = {
            "pv": pv_total,
            # Sonstiges-Erzeuger-Anteil separat (für PV-reine Performance-Ratio;
            # `pv` enthält ihn bewusst für die Bilanz) — symmetrisch zu
            # snapshot/aggregator.py.
            "erzeugung_sonstiges": sonst_erz,
            "einspeisung": einsp,
            "netzbezug": bez,
            "batterie_netto": batt_netto,
            "wp": wp,
            "wallbox": (wallbox or 0.0) + (eauto or 0.0) if (wallbox is not None or eauto is not None) else None,
            "verbrauch_sonstiges": sonst_verbr,
            "verbrauch": verbrauch,
            "spannen": spannen or None,
        }

    pv_marken: dict[str, str] = {}
    if pv_quelle == QUELLE_AGGREGAT and PV_AGGREGAT_BASIS_FELD in komponenten:
        aggregat = komponenten.pop(PV_AGGREGAT_BASIS_FELD)
        gesperrte_schluessel = verworfene_schluessel | set(ohne_tageswert)
        gemessen = gemessene_tageswerte(
            aggregat_kwh=aggregat,
            aggregat_je_stunde=aggregat_je_stunde,
            eigen_kwh=eigen_kwh,
            eigen_stunden=eigen_stunden,
            eigen_buendel_kwh=eigen_buendel,
            gesperrt={i for i, s in eigen_schluessel.items() if s & gesperrte_schluessel},
        )
        aufloesung = loese_aggregat_tag_auf(
            aggregat_kwh=aggregat, gemessen=gemessen, mit_zaehler=set(eigen_kwh),
            investitionen=_alle_invs, datum=datum,
        )
        typ_je_id = {inv.id: getattr(inv, "typ", None) for inv in _alle_invs}
        for inv_id, wert in aufloesung.werte.items():
            praefix = _TYP_KEY_PREFIX.get(typ_je_id.get(inv_id))
            if praefix is None:
                continue
            komponenten[f"{praefix}{inv_id}"] = wert
            if inv_id in aufloesung.verteilt:
                pv_marken[f"{praefix}{inv_id}"] = ABGELEITET_KWP_ANTEIL
    else:
        komponenten.pop(PV_AGGREGAT_BASIS_FELD, None)

    return TagesTabelle(
        stunden=stunden,
        komponenten_kwh=komponenten,
        pv_marken=pv_marken,
        verworfen={k: round(v, 3) for k, v in verworfen.items()},
        nachtrag={k: round(v, 3) for k, v in nachtrag.items()},
    )


