"""HA-Export, Stufe 2 + 3 anlagenweit — die Entscheidungs- und Plan-Sensoren (S2/S3).

Phase von ``calculate_anlage_sensors`` (Vorlage-8b-Bauform: Schlüsselwort-Parameter
hinein, Rückgabe-Dict heraus). Sie hängt an die schon gebaute Sensorliste an:

* **E1 · E2 · E4 · E5** — Zustandsgrößen aus dem Tagesprofil (`TagesEnergieProfil`
  je Stunde, `TagesZusammenfassung` je Tag). Das sind **Exporte, keine Formeln**:
  Überschuss, Defizit und Netzbezugs-Spitze rechnet der Aggregator längst.
* **E3** — derselbe Zeitpunkt wie `eedc_speicher_voll_um`, als ISO-Zeitstempel.
* **P2 · P3 · P5 · P6** — die anlagenweiten Plan-Größen; die Fenster-Rechnung
  kommt aus dem Layer (`core/berechnungen/fenster.py`), der gemeinsame Eingang
  aus `services/ha_export_fenster.py`.

⛔ **Diese Phase holt nichts, was schon geholt wurde.** Prognose und Preis
reicht die Vorgänger-Phase durch (`prognose_und_preis_sensoren`); das
Tagesprofil kommt in **einem** Query. Eine zweite Beschaffung wäre nicht nur
langsam, sie wäre die zweite Wahrheit — derselbe Sensor stünde dann auf zwei
Momentaufnahmen.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import select

from backend.core.berechnungen.fenster import (
    arbitrage_vorschlag,
    bestes_fenster,
    ueberschuss_bloecke,
)
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.ha_export_fenster import P5_DAUERN_H, SLOTS_JE_TAG
from backend.services.ha_sensors_export import STEUERUNG_SENSOREN, SensorValue

#: Ab diesem Ladestand gilt der Speicher als voll (E2). Dieselbe Schwelle wie
#: in der Tages-Simulation (`speicher_simulation.py`: „erste Stunde mit SoC ≥ 98 %")
#: wäre zu früh für eine Ampel, die „ist er JETZT voll?" beantwortet — deshalb
#: 99 %: ein Speicher, der die letzte Stunde noch nachlädt, ist nicht voll.
SPEICHER_VOLL_AB_PROZENT = 99.0

#: P6 schweigt, bis der Tag genug Substanz hat. Vor der dritten vollen
#: Sonnenstunde misst jede Abweichung vor allem die Zufälligkeit einer einzigen
#: bewölkten Stunde — eine Ampel, die morgens um sieben Alarm schlägt, wird
#: abgeschaltet und ist dann auch mittags nicht mehr da.
P6_MINDEST_SONNENSTUNDEN = 3

#: Die Abweichung gilt als auffällig ab dem Doppelten des mittleren Fehlers der
#: letzten 30 Tage (Fachentscheid, abgenommen 21.09.2026). ⚠ Die Schwelle ist
#: **anlagenspezifisch**: eine Anlage mit 8 % MAE schlägt bei 16 % an, eine mit
#: 25 % erst bei 50 %. Ein fester Prozentwert hätte je nach Anlage entweder
#: dauernd oder nie ausgelöst.
P6_SCHWELLE_FAKTOR = 2.0


def _sensor(key: str):
    for d in STEUERUNG_SENSOREN:
        if d.key == key:
            return d
    raise KeyError(key)


def _anhaengen(sensor_values: list, key: str, wert, zusatz: Optional[dict] = None,
               berechnung: Optional[str] = None) -> None:
    """Einen Sensor anhängen — **nur mit Wert** (ADR-002/P4).

    ``None`` heißt hier immer „diesen Sensor gibt es in dieser Lage nicht", nie
    „der Wert ist 0". Ein `False` dagegen IST ein Wert: ein `binary_sensor`,
    der AUS ist, sagt etwas.
    """
    if wert is None:
        return
    sensor_values.append(SensorValue(
        definition=_sensor(key), value=wert,
        zusatz_attribute={k: v for k, v in (zusatz or {}).items() if v is not None},
        berechnung=berechnung,
    ))


def _hhmm(stunde: int) -> str:
    return f"{stunde:02d}:00"


def _iso(tag: date, slot: int) -> str:
    """Ein Slot als ISO-8601-Zeitstempel mit Zone — s. `FensterKontext.slot_iso`."""
    return datetime.combine(
        tag + timedelta(days=slot // SLOTS_JE_TAG), time(hour=slot % SLOTS_JE_TAG)
    ).astimezone().isoformat()


async def _lade_tagesprofil(db, anlage_id: int, heute: date):
    """Die Stundenzeilen von heute **und** die Tageszeile — ein Query je Tabelle."""
    stunden_res = await db.execute(
        select(TagesEnergieProfil)
        .where(TagesEnergieProfil.anlage_id == anlage_id,
               TagesEnergieProfil.datum == heute)
        .order_by(TagesEnergieProfil.stunde)
    )
    tag_res = await db.execute(
        select(TagesZusammenfassung)
        .where(TagesZusammenfassung.anlage_id == anlage_id,
               TagesZusammenfassung.datum == heute)
    )
    return list(stunden_res.scalars().all()), tag_res.scalar_one_or_none()


def _ueberschuss_jetzt_kw(zeile) -> Optional[float]:
    """Überschuss der letzten vollen Stunde; **negativ = Defizit**.

    ⚠ **Eine Größe, nicht zwei.** Das Tagesprofil führt `ueberschuss_kw` und
    `defizit_kw` getrennt (sie sind nie beide > 0). Für eine Automation ist
    „wie viel steht zur Verfügung" aber **eine** Zahl mit Vorzeichen; zwei
    Sensoren, von denen immer einer 0 ist, wären die schlechtere Antwort auf
    dieselbe Frage. Der Defizit-Betrag reist als Attribut mit.
    """
    ueber = zeile.ueberschuss_kw
    defizit = zeile.defizit_kw
    if ueber is None and defizit is None:
        return None
    return round(float(ueber or 0.0) - float(defizit or 0.0), 2)


def _ueberschuss_seit(zeilen: list, bis_index: int) -> Optional[str]:
    """Seit wann läuft der aktuelle Überschuss-Lauf? (Attribut von E2)"""
    start = None
    for zeile in zeilen[: bis_index + 1]:
        wert = _ueberschuss_jetzt_kw(zeile)
        if wert is not None and wert > 0:
            start = zeile.stunde if start is None else start
        else:
            start = None
    return _hhmm(start) if start is not None else None


async def steuerungs_sensoren(
    *,
    anlage,
    db,
    sensor_values: list,
    prognose: Optional[dict],
    preis: Optional[dict],
    fenster_ctx,
    heute: date,
    jetzt_stunde: int,
):
    """E1–E5, P2, P3, P5 und P6 an die Sensorliste anhängen.

    ``heute``/``jetzt_stunde`` sind Parameter und keine Uhrzeit-Griffe in
    dieser Funktion (N-167-Muster) — der Orchestrator setzt die Uhr ein.
    """
    prognose = prognose or {}
    preis = preis or {}

    zeilen, tageszeile = await _lade_tagesprofil(db, anlage.id, heute)

    # ── E1 · Überschuss heute + letzte volle Stunde ──────────────────────────
    if tageszeile is not None and tageszeile.ueberschuss_kwh is not None:
        _anhaengen(
            sensor_values, "eedc_ueberschuss_heute_kwh", tageszeile.ueberschuss_kwh,
            {
                "defizit_heute_kwh": tageszeile.defizit_kwh,
                "stand": _hhmm(zeilen[-1].stunde) if zeilen else None,
            },
            berechnung="Σ der Stundenüberschüsse heute (aus dem 15-Minuten-Takt aggregiert)",
        )

    letzte = None
    letzte_index = -1
    for i, zeile in enumerate(zeilen):
        if _ueberschuss_jetzt_kw(zeile) is not None:
            letzte, letzte_index = zeile, i
    if letzte is not None:
        jetzt_kw = _ueberschuss_jetzt_kw(letzte)
        _anhaengen(
            sensor_values, "eedc_ueberschuss_jetzt_kw", jetzt_kw,
            {"stunde": _hhmm(letzte.stunde), "defizit_kw": letzte.defizit_kw},
            # ⚠ Der Sensor heißt „letzte Stunde" und nicht „jetzt", weil er
            # genau das ist: ein Stundenmittel, bis zu 15 Minuten alt. Einen
            # Live-Überschuss gibt es in eedc als Größe nicht (gemessen 21.09.).
            berechnung=f"Stundenmittel der Stunde {_hhmm(letzte.stunde)} — kein Live-Wert",
        )
        # ── E2 · Überschuss verfügbar ───────────────────────────────────────
        _anhaengen(
            sensor_values, "eedc_ueberschuss_verfuegbar", bool(jetzt_kw and jetzt_kw > 0),
            {"seit": _ueberschuss_seit(zeilen, letzte_index)},
        )

    # ── E2 · günstige Stunde ────────────────────────────────────────────────
    if fenster_ctx is not None and fenster_ctx.hat_preis:
        slot = jetzt_stunde
        if 0 <= slot < len(fenster_ctx.guenstig):
            _anhaengen(
                sensor_values, "eedc_guenstige_stunde", bool(fenster_ctx.guenstig[slot]),
                {
                    "schwelle_cent": preis.get("guenstig_schwelle_cent"),
                    "preis_cent": fenster_ctx.preis_cent[slot],
                },
            )

    # ── E4 · Ladestand + E2 · Speicher voll ─────────────────────────────────
    soc = prognose.get("speicher_soc_prozent")
    if soc is None:
        # Der Prognose-Pfad kann ausgefallen sein (kein Netz); die Zahl liegt
        # dann trotzdem in der Stundenzeile, die wir ohnehin geladen haben.
        soc = next((z.soc_prozent for z in reversed(zeilen) if z.soc_prozent is not None), None)
    if soc is not None:
        je_speicher = next(
            (z.soc_je_speicher for z in reversed(zeilen) if z.soc_je_speicher), None
        )
        _anhaengen(
            sensor_values, "eedc_speicher_soc_prozent", round(float(soc), 1),
            {"je_speicher": je_speicher},
            berechnung="Kapazitätsgewichteter Ladestand über alle Speicher der Anlage",
        )
        _anhaengen(
            sensor_values, "eedc_speicher_voll",
            bool(float(soc) >= SPEICHER_VOLL_AB_PROZENT),
            {"soc_prozent": round(float(soc), 1),
             "schwelle_prozent": SPEICHER_VOLL_AB_PROZENT},
        )

    # ── E3 · „Speicher voll um" als Zeitstempel ─────────────────────────────
    voll_slot = prognose.get("speicher_voll_um_slot")
    if voll_slot is not None:
        # Die Simulation läuft ab der laufenden Stunde bis Mitternacht; eine
        # frühere Stunde als „jetzt" kann sie nicht liefern. Sollte sie es
        # doch (Uhrensprung zwischen Simulation und Export), meint sie morgen.
        slot = voll_slot if voll_slot >= jetzt_stunde else voll_slot + SLOTS_JE_TAG
        _anhaengen(
            sensor_values, "eedc_speicher_voll_um_ts", _iso(heute, slot),
            {"quelle": "eedc_speicher_voll_um",
             **(prognose.get("speicher_verbrauch_profil") or {})},
        )

    # ── E5 · Netzbezugs-Spitze ──────────────────────────────────────────────
    if tageszeile is not None and tageszeile.peak_netzbezug_kw is not None:
        mittel = [(z.stunde, z.netzbezug_kw) for z in zeilen if z.netzbezug_kw is not None]
        grundlast = next(
            (sv.value for sv in sensor_values if sv.definition.key == "eedc_grundlast_kw"),
            None,
        )
        _anhaengen(
            sensor_values, "eedc_netzbezug_spitze_heute_kw", tageszeile.peak_netzbezug_kw,
            {
                # ⚠ Andere Größe als der Wert daneben — s. die Definition.
                "stunde_max_mittel": _hhmm(max(mittel, key=lambda x: x[1])[0]) if mittel else None,
                "max_mittel_kw": round(max(m[1] for m in mittel), 2) if mittel else None,
                "grundlast_kw": grundlast,
            },
        )

    # ── P2 · Überschuss-Prognose heute ──────────────────────────────────────
    if fenster_ctx is not None and prognose.get("verbrauch_stundenprofil_kwh"):
        pv = list(prognose.get("stundenprofil_heute") or [])
        verbrauch = list(prognose["verbrauch_stundenprofil_kwh"])
        n = min(len(pv), len(verbrauch))
        ueber = [round(max(0.0, pv[i] - verbrauch[i]), 2) for i in range(n)]
        defizit = [round(max(0.0, verbrauch[i] - pv[i]), 2) for i in range(n)]
        bloecke = ueberschuss_bloecke(pv[:n], verbrauch[:n])
        _anhaengen(
            sensor_values, "eedc_ueberschuss_prognose_heute_kwh", round(sum(ueber), 1),
            {
                "stundenprofil_kwh": ueber,
                "defizit_stundenprofil_kwh": defizit,
                "fenster": [
                    {"ab": _iso(heute, b.ab), "bis": _iso(heute, b.bis),
                     "stunden": b.stunden, "min_kw": b.min_kw, "summe_kwh": b.summe_kwh}
                    for b in bloecke
                ],
                **fenster_ctx.profil_attribute,
            },
            berechnung="Σ max(0; PV-Prognose − Verbrauchsprognose) je Stunde (Modell A)",
        )

    # ── P3 · Arbitrage-Vorschlag ────────────────────────────────────────────
    await _arbitrage_sensor(
        anlage=anlage, db=db, sensor_values=sensor_values,
        prognose=prognose, fenster_ctx=fenster_ctx, heute=heute,
    )

    # ── P5 · bestes Fenster ─────────────────────────────────────────────────
    if fenster_ctx is not None:
        _bestes_fenster_sensor(sensor_values, fenster_ctx)

    # ── P6 · Abweichungs-Ampel ──────────────────────────────────────────────
    await _abweichungs_ampel(
        anlage=anlage, db=db, sensor_values=sensor_values,
        prognose=prognose, heute=heute, jetzt_stunde=jetzt_stunde,
    )
    return {}


async def _arbitrage_sensor(*, anlage, db, sensor_values, prognose, fenster_ctx, heute):
    """P3 — nur bei einem Speicher, der **aus dem Netz laden darf**.

    ⭐ **Das Gate ist `laedt_aus_netz`, nicht `arbitrage_faehig`** (Konzept §5/P3):
    `laedt_aus_netz` ist der Erfassungs-Schalter seit #264 und sagt, ob das
    Gerät überhaupt Netzstrom aufnimmt; `arbitrage_faehig` sagt zusätzlich, ob
    der Anwender **Handel** damit treiben will — es impliziert den ersten
    (`bedingungen.py`). Das engere Flag als Gate hätte jeden Speicher
    ausgeschlossen, der aus dem Netz lädt, ohne dass jemand den Handels-Haken
    gesetzt hat; der Vorschlag ist aber genau für den gedacht.
    """
    if fenster_ctx is None or not fenster_ctx.hat_preis:
        return
    kap = prognose.get("speicher_kap_kwh")
    soc = prognose.get("speicher_soc_prozent")
    if not kap or soc is None:
        return

    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "speicher",
            Investition.aktiv.is_(True),
        )
    )
    speicher = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    laedt = [i for i in speicher if (i.parameter or {}).get("laedt_aus_netz")]
    if not laedt:
        return
    arbitrage_faehig = any((i.parameter or {}).get("arbitrage_faehig") for i in laedt)

    frei = max(0.0, float(kap) * (1.0 - float(soc) / 100.0))
    eta = prognose.get("speicher_eta_prozent") or 90.0
    ergebnis = arbitrage_vorschlag(
        fenster_ctx.kosten,
        # Das Defizit der Prognose ist die Menge, die eine Entladung ersetzen
        # kann — dieselbe Reihe, die P2 als Attribut ausweist.
        [max(0.0, fenster_ctx.verbrauch_kwh[i] - _pv(prognose, i))
         for i in range(len(fenster_ctx.kosten))],
        frei_kwh=frei,
        wirkungsgrad_prozent=eta,
        guenstig=fenster_ctx.guenstig,
        ab_h=fenster_ctx.jetzt_slot,
    )
    if ergebnis is None:
        return
    _anhaengen(
        sensor_values, "eedc_arbitrage_vorschlag_kwh", ergebnis.menge_kwh,
        {
            "stunden": [_hhmm(h % SLOTS_JE_TAG) for h in ergebnis.lade_stunden],
            "ersparnis_cent": round(ergebnis.ersparnis_cent),
            "soc_prozent": round(float(soc), 1),
            "frei_kwh": round(frei, 1),
            "wirkungsgrad_prozent": eta,
            "arbitrage_faehig": arbitrage_faehig,
            "preisquelle": fenster_ctx.preisquelle,
            # N-392: die Simulation hinter „Speicher voll um" rechnet mit
            # Modell B — dieser Vorschlag sitzt auf denselben Eingängen und
            # nennt deshalb dasselbe Modell.
            **(prognose.get("speicher_verbrauch_profil") or {}),
        },
        berechnung=(
            f"Laden in {len(ergebnis.lade_stunden)} günstigen Stunden, Entladung "
            f"gegen das teuerste Defizit danach (Wirkungsgrad {eta:.0f} %)"
        ),
    )


def _pv(prognose: dict, slot: int) -> float:
    reihe = prognose.get("stundenprofil_heute") or []
    return float(reihe[slot]) if slot < len(reihe) else 0.0


def _bestes_fenster_sensor(sensor_values: list, ctx) -> None:
    """P5 — vier kanonische Dauern und ein mengenneutrales Kostenprofil."""
    dauern: dict[str, dict] = {}
    for dauer in P5_DAUERN_H:
        f = bestes_fenster(
            ctx.kosten, dauer_h=dauer, ab_h=ctx.jetzt_slot, frist_h=ctx.frist_slot
        )
        if f is not None:
            dauern[f"dauer_{dauer}h"] = ctx.fenster_attribute(f)
    if not dauern:
        return
    zwei = dauern.get("dauer_2h") or next(iter(dauern.values()))
    _anhaengen(
        sensor_values, "eedc_bestes_fenster_ab", zwei["ab"],
        {
            **dauern,
            # ⚠ mengenneutral: der Wert je Slot gilt für **eine** kWh. Wer
            # mehr fahren will, als der Überschuss deckt, rechnet mit dem
            # Slot-Preis — deshalb steht der daneben.
            "kosten_profil_cent_kwh": [
                None if k is None else round(k, 2) for k in ctx.kosten
            ],
            "preis_profil_cent_kwh": [
                None if p is None else round(p, 2) for p in ctx.preis_cent
            ],
            "frist": ctx.slot_iso(ctx.frist_slot + 1) if ctx.frist_slot is not None else None,
            "preisquelle": ctx.preisquelle,
            **ctx.profil_attribute,
        },
        berechnung=(
            "Günstigstes zusammenhängendes 2-Stunden-Fenster ab jetzt — Kosten je "
            "kWh, in Überschuss-Stunden um den Überschussanteil gemindert"
        ),
    )


async def _abweichungs_ampel(*, anlage, db, sensor_values, prognose, heute, jetzt_stunde):
    """P6 — die Abweichung von heute und, wenn eine Schwelle existiert, die Ampel.

    ⛔ **Nichts wird hier neu summiert.** IST und rollende Prognose liegen im
    Export-Dict (`ha_export_prognose.py`, `ist_bisher_kwh`/`heute_rollend_kwh`).
    Eine eigene Summe wäre eine zweite Wahrheit über denselben Tag.
    """
    ist = prognose.get("ist_bisher_kwh")
    stundenprofil = prognose.get("stundenprofil_heute") or []
    if ist is None or not stundenprofil:
        return

    # Prognose bis zur letzten VOLLEN Stunde — dieselbe Grenze wie beim IST.
    bis_stunde = max(0, jetzt_stunde)
    soll = sum(float(v or 0.0) for v in stundenprofil[:bis_stunde])
    if soll <= 0:
        return   # vor Sonnenaufgang ist jede Prozentzahl eine Division durch fast 0

    abweichung = (float(ist) - soll) / soll * 100

    # Die Ampel braucht eine anlagenspezifische Schwelle — ohne
    # Genauigkeits-Tracking gibt es keine, und dann gibt es sie nicht (P4).
    # Die Zahl selbst gibt es trotzdem; sie trägt den mittleren Fehler als
    # Einordnung mit, wo er existiert.
    from backend.services.prognose_genauigkeit_service import eedc_mae_prozent

    mae, tage = await eedc_mae_prozent(db, anlage.id, heute=heute)

    _anhaengen(
        sensor_values, "eedc_prognose_abweichung_heute_prozent", round(abweichung, 1),
        {
            "ist_kwh": round(float(ist), 1),
            "prognose_kwh": round(soll, 1),
            "bis_stunde": _hhmm(bis_stunde),
            "mae_30_tage_prozent": mae,
        },
        berechnung=f"({ist:.1f} − {soll:.1f}) ÷ {soll:.1f} × 100",
    )

    if mae is None:
        return
    sonnenstunden = sum(1 for v in stundenprofil[:bis_stunde] if float(v or 0.0) > 0)
    schwelle = P6_SCHWELLE_FAKTOR * mae
    genug = sonnenstunden >= P6_MINDEST_SONNENSTUNDEN
    _anhaengen(
        sensor_values, "eedc_prognose_auffaellig",
        bool(genug and abs(abweichung) > schwelle),
        {
            "schwelle_prozent": round(schwelle, 1),
            "mae_30_tage_prozent": mae,
            "mae_tage": tage,
            "sonnenstunden_bisher": sonnenstunden,
            "grund": None if genug else (
                f"noch keine {P6_MINDEST_SONNENSTUNDEN} vollen Sonnenstunden "
                f"({sonnenstunden}) — die Abweichung ist noch nicht aussagekräftig"
            ),
        },
    )
