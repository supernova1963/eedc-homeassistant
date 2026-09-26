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
  `loese_pv_tageswerte_auf` nur im Aggregat-Fall, E4 BKW-Rest.

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
from backend.services.snapshot.komponenten_beitraege import (
    loese_pv_tageswerte_auf,
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
    Ziel-Key (R5b); der PV-Aggregat-Fall ist über `loese_pv_tageswerte_auf`
    aufgelöst. ``pv_marken``: #406-Herkunftsmarken. ``verworfen``:
    ``{achse: kWh}`` verworfener Mengen (R4) — ``{}`` heißt „nichts verworfen".
    """
    stunden: dict[int, dict[str, Optional[float]]]
    komponenten_kwh: dict[str, float] = field(default_factory=dict)
    pv_marken: dict[str, str] = field(default_factory=dict)
    verworfen: dict[str, float] = field(default_factory=dict)


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

    def _verwerfe(achse: str, kwh: float) -> None:
        verworfen[achse] = verworfen.get(achse, 0.0) + abs(kwh)

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
                elif pv_quelle == QUELLE_EINZEL:
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

        # ── 7. komponenten_kwh aus denselben Werten (R5b) ────────────────
        for beitraege in je_achse.values():
            for target, wert, _n in beitraege:
                if target in ohne_ziel:
                    continue
                komponenten[target] = komponenten.get(target, 0.0) + wert

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
        komponenten, pv_marken = loese_pv_tageswerte_auf(komponenten, investitionen_by_id, datum)
    else:
        komponenten.pop(PV_AGGREGAT_BASIS_FELD, None)

    return TagesTabelle(
        stunden=stunden,
        komponenten_kwh=komponenten,
        pv_marken=pv_marken,
        verworfen={k: round(v, 3) for k, v in verworfen.items()},
    )


