"""Die Verteilung **eines Tages** je Gerät — und ihre 24 Stunden (WK-16c).

**Was hier entsteht:** für jeden Tag die Mengen je Gerät (die Eingabe des
Verteilungs-Layers) **und** dieselben Segmente je Stunde.

⭐ **Die Stunde verteilt den Tag, sie misst ihn nicht** (Konzept Kap. 6.2). Jede
Stundenreihe entsteht aus einer **Tagesmenge** und einer **gemessenen Form** —
nie aus einer Glättung und nie über Gerätegrenzen hinweg. Was keine Form hat,
wird **genannt** (``ohne_stundenform_kwh``), nicht gleichmäßig verteilt
(ADR-002/**P4**).

⭐ **Zwei Familien, zwei Formen-Quellen — und beide stehen schon im Baum:**

* Die **Teilmengen** (Betriebsart/Modus) verteilt
  ``verteile_tages_stapel_auf_stunden`` seit Bauschnitt 5; seit WK-16c gibt sie
  ihr Zwischenergebnis **je Gerät** heraus (``StundenVerteilung.je_geraet``)
  statt es sofort zu addieren. Es ist dieselbe Rechnung, eine Stufe früher.
* Die **Summanden** (``strom_heizen_kwh``/``strom_warmwasser_kwh``) bekommen die
  Form **ihres eigenen Zählers** aus derselben Standreihe
  (``lade_stundenformen``) — wie die Wärme- und Kältelinien des
  Stunden-Verlaufs. Ihr Rest (*System/Standby*) fällt auf die **Restform** des
  Geräts: Gesamtform minus der Formen, die schon erklärt sind — die Bauform von
  Zweig 1 in ``verteile_tages_stapel_auf_stunden``, über die öffentlich
  gemachte ``gesamt_form``.

⛔ **Kein Segment bekommt die Form eines anderen.** Warmwasser läuft morgens,
Heizen abends; beide über die Geräteform zu verteilen hieße, eine Form zu
erfinden, die niemand gemessen hat — und sie sähe aus wie eine Messung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import waermepumpe_kwh_je_investition
from backend.core.berechnungen.tages_stapel import (
    STUNDEN,
    StundenFormen,
    beitraege_des_tages,
    gesamt_form,
    verteile_menge,
    verteile_tages_stapel_auf_stunden,
)
from backend.core.berechnungen.waerme_verteilung import (
    FAMILIE_SUMMANDEN,
    FUNKTION_ENTFEUCHTEN,
    FUNKTION_HEIZEN,
    FUNKTION_KUEHLEN,
    FUNKTION_LUEFTEN,
    FUNKTION_OHNE_MODUS,
    FUNKTION_SYSTEM,
    FUNKTION_WARMWASSER,
    GeraetStromEingabe,
    verteile_geraet_strom,
)
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil import lade_modus_split_tag, lade_modus_stunden_tag
from backend.services.snapshot.aggregator import (
    get_betriebsart_strom_tageswerte,
    get_tagesdetail_kwh,
    get_wp_strom_stufe_je_investition,
)
from backend.services.snapshot.boundary_range import tageszeile_ist_rueckwaerts
from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
from backend.services.snapshot.komponenten_beitraege import investition_beitraege
from backend.services.snapshot.reader import mqtt_zaehler_keys
from backend.services.snapshot.stunden_leser import lade_stundenformen

#: Die Mapping-Felder der beiden Summanden-Achsen — Ausgabe-Keys des
#: Tagesdetails daneben. Zwei Namen für dieselbe Achse gibt es nur, weil der
#: Aggregator zwischen Mapping-Feld und Ausgabe-Key übersetzt.
_ACHSEN: tuple[tuple[str, str, str], ...] = (
    (FUNKTION_HEIZEN, "strom_heizen_kwh", "wp_strom_heizen_kwh"),
    (FUNKTION_WARMWASSER, "strom_warmwasser_kwh", "wp_strom_warmwasser_kwh"),
)

#: Die Teilmengen-Segmente, so wie sie im ``TagesStapel`` heißen.
_TEILMENGEN: tuple[tuple[str, str], ...] = (
    (FUNKTION_HEIZEN, "heizen_kwh"),
    (FUNKTION_WARMWASSER, "warmwasser_kwh"),
    (FUNKTION_KUEHLEN, "kuehlen_kwh"),
    (FUNKTION_LUEFTEN, "lueften_kwh"),
    (FUNKTION_ENTFEUCHTEN, "entfeuchten_kwh"),
    (FUNKTION_OHNE_MODUS, "nicht_aufgeteilt_kwh"),
)
#: Die funktionsfremden Teilmengen, die **neben** den Summanden stehen (W-16/K4).
_FUNKTIONSFREMD: tuple[tuple[str, str], ...] = (
    (FUNKTION_KUEHLEN, "kuehlen_kwh"),
    (FUNKTION_LUEFTEN, "lueften_kwh"),
    (FUNKTION_ENTFEUCHTEN, "entfeuchten_kwh"),
)


@dataclass(frozen=True)
class TagesVerteilung:
    """Ein Tag: die Mengen je Gerät und dieselben Segmente je Stunde."""

    #: ``{inv_id: GeraetStromEingabe}`` — die Verteilung des **Tages**.
    je_geraet: dict[str, GeraetStromEingabe] = field(default_factory=dict)
    #: ``{inv_id: {funktion: [24 kWh]}}`` — der Verlauf derselben Segmente.
    stunden_je_geraet: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    #: Was keiner Stunde zuzuordnen war — über alle Geräte und Segmente (P4).
    ohne_stundenform_kwh: float = 0.0


async def lade_tages_verteilung(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> TagesVerteilung:
    """Tag und Stunden in **einem** Durchgang — dieselben Eingänge wie ``tag-detail``.

    ⚠ Gelesen wird im Fenster der **Tageszeile** (N-434/N-435): Trägt sie ihren
    Wärmepumpen-Strom aus den HA-Langzeitstatistiken, laufen auch die
    Betriebsart-Zähler und die Summanden-Achsen von 23 Uhr bis 23 Uhr. Ohne das
    nennte diese Sicht andere Zahlen als *Cockpit → Tag* für denselben Tag.
    """
    from backend.services.waerme_verteilung import eingabe_aus_tageswerten

    tz_zeile = (await db.execute(
        select(
            TagesZusammenfassung.komponenten_kwh,
            TagesZusammenfassung.source_provenance,
            TagesZusammenfassung.verworfen,
        ).where(
            TagesZusammenfassung.anlage_id == anlage.id,
            TagesZusammenfassung.datum == datum,
        )
    )).one_or_none()
    rueckwaerts = tageszeile_ist_rueckwaerts(
        tz_zeile[1] if tz_zeile else None, tz_zeile[2] if tz_zeile else None,
    )
    menge_je_inv = waermepumpe_kwh_je_investition(
        (tz_zeile[0] if tz_zeile else None) or {},
    )
    if not menge_je_inv:
        return TagesVerteilung()

    gemessen_je_inv = await get_betriebsart_strom_tageswerte(
        db, anlage, investitionen_by_id, datum, rueckwaerts=rueckwaerts,
    )
    beitraege = beitraege_des_tages(
        gemessen_je_inv, menge_je_inv,
        await lade_modus_split_tag(db, anlage.id, datum),
        investitionen_by_id, datum,
        stufe_je_inv=await get_wp_strom_stufe_je_investition(
            db, anlage, investitionen_by_id,
        ),
    )
    beitrag_je_inv = {b.inv_id: b for b in beitraege}
    detail = await get_tagesdetail_kwh(
        db, anlage, investitionen_by_id, datum,
        tageszeile_rueckwaerts=rueckwaerts,
    )

    # ── Die Mengen des Tages je Gerät ────────────────────────────────────
    je_geraet: dict[str, GeraetStromEingabe] = {}
    for inv_id_str, menge in menge_je_inv.items():
        inv = investitionen_by_id.get(inv_id_str)
        if inv is None or not inv.ist_aktiv_an(datum):
            continue
        je_geraet[inv_id_str] = eingabe_aus_tageswerten(
            inv,
            menge_kwh=float(menge or 0.0),
            strom_heizen_kwh=(
                detail.werte_je_inv.get("wp_strom_heizen_kwh", {}).get(inv_id_str)
            ),
            strom_warmwasser_kwh=(
                detail.werte_je_inv.get("wp_strom_warmwasser_kwh", {}).get(inv_id_str)
            ),
            beitrag=beitrag_je_inv.get(inv_id_str),
        )
    if not je_geraet:
        return TagesVerteilung()

    # ── Die Formen ───────────────────────────────────────────────────────
    zaehler, gesamt_felder = _zaehler_des_tages(
        anlage, investitionen_by_id, beitraege, je_geraet,
        quellen_energy=extract_quellen_energy(anlage),
        mqtt_keys=await mqtt_zaehler_keys(db, anlage.id),
    )
    formen_je_key = await lade_stundenformen(db, anlage, datum, list(zaehler.values()))

    def _summe_je_slot(keys: list[str]) -> list[Optional[float]]:
        reihen = [formen_je_key[k] for k in keys if k in formen_je_key]
        if not reihen:
            return [None] * STUNDEN
        return [
            (sum(r[h] for r in reihen if r[h] is not None)
             if any(r[h] is not None for r in reihen) else None)
            for h in range(STUNDEN)
        ]

    modus_stunden, _ = await lade_modus_stunden_tag(db, anlage.id, datum)
    formen = StundenFormen(
        felder_je_inv={
            b.inv_id: {
                feld: formen_je_key.get(f"inv:{b.inv_id}:{feld}", [None] * STUNDEN)
                for feld in b.felder
            }
            for b in beitraege if b.gemessen
        },
        gesamt_je_inv={
            inv_id: _summe_je_slot([f"inv:{inv_id}:{f}" for f in felder])
            for inv_id, felder in gesamt_felder.items()
        },
        modus_stunden_je_inv=modus_stunden,
    )
    verteilung = verteile_tages_stapel_auf_stunden(beitraege, formen)

    # ── Die Stunden je Gerät und Segment ─────────────────────────────────
    stunden: dict[str, dict[str, list[float]]] = {}
    ohne = 0.0
    for inv_id_str, eingabe in je_geraet.items():
        reihen, fehlt = _stunden_eines_geraets(
            inv_id_str, eingabe, verteilung.je_geraet.get(inv_id_str),
            formen, formen_je_key,
        )
        if reihen:
            stunden[inv_id_str] = reihen
        ohne += fehlt
    return TagesVerteilung(
        je_geraet=je_geraet,
        stunden_je_geraet=stunden,
        ohne_stundenform_kwh=ohne if ohne > 1e-6 else 0.0,
    )


def _zaehler_des_tages(
    anlage, investitionen_by_id: dict, beitraege, je_geraet, *,
    quellen_energy, mqtt_keys,
) -> tuple[dict[str, tuple[str, object]], dict[str, list[str]]]:
    """Welche Zähler eine Stundenform liefern können — und die Gesamtform-Felder.

    ⚠ **Ein Leser, keine Regel.** Ob ein Feld einen Zähler hat, beantwortet
    ``feld_hat_zaehler``; welche Felder ein Gerät überhaupt in die Bilanz gibt,
    ``investition_beitraege``. Hier steht nur, welche davon für diesen Tag
    gebraucht werden.
    """
    mapping = (anlage.sensor_mapping or {}).get("investitionen", {}) or {}

    def _zaehler(inv_id: str, feld: str):
        cfg = ((mapping.get(inv_id) or {}).get("felder") or {}).get(feld)
        key = f"inv:{inv_id}:{feld}"
        if not feld_hat_zaehler(cfg, key, quellen_energy, mqtt_keys):
            return None
        return key, (cfg.get("sensor_id") if isinstance(cfg, dict) else None)

    zaehler: dict[str, tuple[str, object]] = {}
    gesamt_felder: dict[str, list[str]] = {}
    for inv_id_str in je_geraet:
        inv = investitionen_by_id.get(inv_id_str)
        felder_cfg = (mapping.get(inv_id_str) or {}).get("felder") or {}
        gesamt_felder[inv_id_str] = [
            beitrag.feld for beitrag in investition_beitraege(
                inv, mapping.get(inv_id_str) or {},
                ist_verfuegbar=lambda f, _c=felder_cfg, _i=inv_id_str: feld_hat_zaehler(
                    _c.get(f), f"inv:{_i}:{f}", quellen_energy, mqtt_keys,
                ),
            )
        ]
        for _funktion, feld, _key in _ACHSEN:
            z = _zaehler(inv_id_str, feld)
            if z:
                zaehler[z[0]] = z
        for feld in gesamt_felder[inv_id_str]:
            z = _zaehler(inv_id_str, feld)
            if z:
                zaehler[z[0]] = z
    for b in beitraege:
        if not b.gemessen:
            continue
        for feld in b.felder:
            z = _zaehler(b.inv_id, feld)
            if z:
                zaehler[z[0]] = z
    return zaehler, gesamt_felder


def _stunden_eines_geraets(
    inv_id: str,
    eingabe: GeraetStromEingabe,
    teilmengen_stunden,
    formen: StundenFormen,
    formen_je_key: dict,
) -> tuple[dict[str, list[float]], float]:
    """Die 24 Slots **eines** Geräts je Segment — und was keine Form hatte.

    Die Familie entscheidet der Layer (``verteile_geraet_strom``); hier wird
    jedem seiner Segmente die Form gegeben, die zu ihm gehört.
    """
    v = verteile_geraet_strom(eingabe)
    if not v.hat_aufteilung:
        return {}, 0.0

    reihen: dict[str, list[float]] = {}
    ohne = 0.0

    if v.familie != FAMILIE_SUMMANDEN:
        # Teilmengen: schon verteilt — dieselben Zahlen wie im Stapel daneben.
        if teilmengen_stunden is None:
            return {}, v.aufgeteilt_kwh
        for funktion, feld in _TEILMENGEN:
            if funktion not in v.je_funktion:
                continue
            reihe = [getattr(teilmengen_stunden[h], feld) for h in range(STUNDEN)]
            reihen[funktion] = reihe
            ohne += max(0.0, v.je_funktion[funktion] - sum(reihe))
        return reihen, ohne

    # ── Summanden: je Achse ihre eigene Zählerform ───────────────────────
    roh: list[list[float]] = []
    for funktion, feld, _key in _ACHSEN:
        if funktion not in v.je_funktion:
            continue
        form = formen_je_key.get(f"inv:{inv_id}:{feld}", [None] * STUNDEN)
        werte, fehlt = verteile_menge(v.je_funktion[funktion], form)
        reihen[funktion] = werte
        ohne += fehlt
        roh.append([float(x) if x is not None else 0.0 for x in form])
    # Die gemessenen funktionsfremden Teilmengen stehen NEBEN den Achsen (K4) —
    # sie sind oben schon je Gerät verteilt worden.
    if teilmengen_stunden is not None:
        for funktion, feld in _FUNKTIONSFREMD:
            if funktion not in v.je_funktion:
                continue
            reihe = [getattr(teilmengen_stunden[h], feld) for h in range(STUNDEN)]
            reihen[funktion] = reihe
            ohne += max(0.0, v.je_funktion[funktion] - sum(reihe))
            roh.append(reihe)
    if FUNKTION_SYSTEM in v.je_funktion:
        # Die **Restform** — dieselbe Bauform wie in Zweig 1 von
        # `verteile_tages_stapel_auf_stunden`: was die Gesamtform mehr zeigt als
        # die erklärten Formen zusammen. Nur dort kann Standby liegen.
        gesamt = gesamt_form(inv_id, formen)
        rest_form = [
            max(
                0.0,
                (float(gesamt[h]) if h < len(gesamt) and gesamt[h] is not None else 0.0)
                - sum(r[h] for r in roh),
            )
            for h in range(STUNDEN)
        ]
        werte, fehlt = verteile_menge(v.je_funktion[FUNKTION_SYSTEM], rest_form)
        reihen[FUNKTION_SYSTEM] = werte
        ohne += fehlt
    return reihen, ohne


__all__ = ["TagesVerteilung", "lade_tages_verteilung"]
