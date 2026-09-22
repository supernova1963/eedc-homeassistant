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


# ─────────────────────────────────────────────────────────────────────────────
# Wie eedc eine Stunde beschriftet (N-544, 22.09.2026)
# ─────────────────────────────────────────────────────────────────────────────
# **Jede Zeitangabe zu einem Slot sagt, ob sie Beginn oder Ende meint.** Das ist
# eine Regel über die Kategorie *Zeitangabe eines Slots*, nicht über einzelne
# Attribute:
#
#   Beginn-Angaben : `ab` · `seit` · `stunden` · `stunde_von`
#   End-Angaben    : `bis` · `*_um` · `frist` · `stand` · `stunde_bis`
#
# Alle Slots dieses Moduls sind **backward** (#144): Slot `h` deckt `[h−1, h)`.
# Ein Slot „14" beginnt also um 13:00 und endet um 14:00 — bis zum 22.09.2026
# schrieb dieses Modul für beide Bedeutungen `f"{h:02d}:00"`, und damit lagen
# vier Beginn-Angaben eine Stunde zu spät (E2 `seit`, E5 `stunde_max_mittel`,
# P2 `fenster[].ab/bis`, P7 `guenstige_heizstunden`) und `stand` eine Stunde
# voraus. Ein `stunde`-Attribut ohne Beginn/Ende-Angabe („h:00") war schlicht
# nicht entscheidbar.


def _hhmm(stunde: int) -> str:
    """Eine **Uhrzeit** als „HH:00" — nicht für Slots, s. die beiden darunter."""
    return f"{stunde:02d}:00"


def _hhmm_beginn(slot: int) -> str:
    """Der **Beginn** des Backward-Slots `slot` als „HH:00" — Slot `h` beginnt `(h−1):00`."""
    return f"{(slot - 1) % SLOTS_JE_TAG:02d}:00"


def _hhmm_ende(slot: int) -> str:
    """Das **Ende** des Backward-Slots `slot` als „HH:00" — Slot `h` endet `h:00`."""
    return f"{slot % SLOTS_JE_TAG:02d}:00"


def _iso(tag: date, slot: int) -> str:
    """Der **Beginn** eines Achsen-Slots als ISO-Zeitstempel — s. `FensterKontext.slot_iso`.

    Dieselbe Rechnung, derselbe SoT (`zeittarif.uhrzeit_des_slots`): Slot `s`
    beginnt `(s−1)` Stunden nach Mitternacht von `tag`. Sie steht hier, weil
    zwei Stellen einen Zeitstempel ohne Fenster-Kontext brauchen (E3 und die
    neuen Sim-Sensoren); der Kontext baut keinen zweiten.
    """
    from backend.core.berechnungen.zeittarif import uhrzeit_des_slots

    return uhrzeit_des_slots(tag, slot).astimezone().isoformat()


def _iso_ende(tag: date, slot: int) -> str:
    """Das **Ende** eines Achsen-Slots — der Beginn des nächsten."""
    return _iso(tag, slot + 1)


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
    """Seit wann läuft der aktuelle Überschuss-Lauf? (Attribut von E2)

    ⭐ **`seit` ist eine Beginn-Angabe** (N-544): Der Lauf beginnt mit dem
    **Anfang** des ersten Überschuss-Slots, nicht mit seinem Ende. Bis zum
    22.09.2026 stand hier `_hhmm(start)` — für Slot 11 (= 10–11 Uhr) also
    „11:00", obwohl der Überschuss um **10:00** einsetzte. Eine Stunde zu spät,
    und zwar genau in der Zahl, auf die eine Automation „läuft schon lange
    genug" stützt.
    """
    start = None
    for zeile in zeilen[: bis_index + 1]:
        wert = _ueberschuss_jetzt_kw(zeile)
        if wert is not None and wert > 0:
            start = zeile.stunde if start is None else start
        else:
            start = None
    return _hhmm_beginn(start) if start is not None else None


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
    speicher_eta: Optional[dict] = None,
):
    """E1–E5, P2, P3, P5 und P6 an die Sensorliste anhängen.

    ``heute``/``jetzt_stunde`` sind Parameter und keine Uhrzeit-Griffe in
    dieser Funktion (N-167-Muster) — der Orchestrator setzt die Uhr ein.
    """
    prognose = prognose or {}
    preis = preis or {}

    zeilen, tageszeile = await _lade_tagesprofil(db, anlage.id, heute)

    # Die letzte Stundenzeile **mit Wert** — nicht einfach `zeilen[-1]`.
    #
    # ⭐ **N-544/W9: die laufende Stunde hat schon eine Zeile, aber noch keine
    # Zählerwerte.** `live_tagesverlauf_service` rastert bis `now`, der
    # Aggregator legt den Bucket an und schreibt die Zeile — um 14:30 existiert
    # also Zeile `stunde=15` mit `ueberschuss_kw`/`defizit_kw` = `None`
    # (`verrechne_stunde` setzt sie leer, wenn `pv_kw`/`verbrauch_kw` fehlen).
    # `_ueberschuss_jetzt_kw` überspringt sie deshalb richtig — `stand` nahm
    # dagegen `zeilen[-1]` und meldete damit das Ende einer Stunde, die noch
    # gar nicht gemessen ist: **eine Stunde voraus**.
    letzte = None
    letzte_index = -1
    for i, zeile in enumerate(zeilen):
        if _ueberschuss_jetzt_kw(zeile) is not None:
            letzte, letzte_index = zeile, i

    # ── E1 · Überschuss heute + letzte volle Stunde ──────────────────────────
    if tageszeile is not None and tageszeile.ueberschuss_kwh is not None:
        _anhaengen(
            sensor_values, "eedc_ueberschuss_heute_kwh", tageszeile.ueberschuss_kwh,
            {
                "defizit_heute_kwh": tageszeile.defizit_kwh,
                # End-Angabe: „bis wann ist gerechnet" = Ende des letzten Slots
                # mit Wert.
                "stand": _hhmm_ende(letzte.stunde) if letzte is not None else None,
            },
            berechnung="Σ der Stundenüberschüsse heute (aus dem 15-Minuten-Takt aggregiert)",
        )

    if letzte is not None:
        jetzt_kw = _ueberschuss_jetzt_kw(letzte)
        _anhaengen(
            sensor_values, "eedc_ueberschuss_jetzt_kw", jetzt_kw,
            {
                # ⛔ Hier stand bis 22.09.2026 ein einzelnes `stunde: "h:00"` —
                # nicht entscheidbar, ob Beginn oder Ende gemeint war. Die
                # **Entfernung** dieses Attributs ist die einzige des Pakets
                # (S3b/B5, Golden Master `--erwartete-entfernungen`).
                "stunde_von": _hhmm_beginn(letzte.stunde),
                "stunde_bis": _hhmm_ende(letzte.stunde),
                "defizit_kw": letzte.defizit_kw,
            },
            # ⚠ Der Sensor heißt „letzte Stunde" und nicht „jetzt", weil er
            # genau das ist: ein Stundenmittel, bis zu 15 Minuten alt. Einen
            # Live-Überschuss gibt es in eedc als Größe nicht (gemessen 21.09.).
            berechnung=(
                f"Stundenmittel der Stunde {_hhmm_beginn(letzte.stunde)}–"
                f"{_hhmm_ende(letzte.stunde)} — kein Live-Wert"
            ),
        )
        # ── E2 · Überschuss verfügbar ───────────────────────────────────────
        _anhaengen(
            sensor_values, "eedc_ueberschuss_verfuegbar", bool(jetzt_kw and jetzt_kw > 0),
            {"seit": _ueberschuss_seit(zeilen, letzte_index)},
        )

    # ── E2 · günstige Stunde ────────────────────────────────────────────────
    #
    # ⭐ **Dieser Sensor liest die BÖRSE, nicht den Fenster-Kontext** (S3b).
    # Er ist seit v4.0.27 die Markierung, die `eedc_preis_rang` trägt — „ist
    # diese Stunde am Markt billig?" —, und seine Attribute sind Vertrag. Der
    # Kontext daneben beantwortet ab S3b eine **andere** Frage (er rechnet mit
    # dem Bezugspreis des Haushalts, bei Festtarif also mit einer Reihe ohne
    # Tal). Läse dieser Sensor ihn weiter, hätte ein Festtarif-Haushalt ab S3b
    # dauerhaft „nicht günstig" stehen — eine stille Bedeutungsänderung an
    # einem released Sensor.
    #
    # `rang_profil` ist **forward** (`strompreis_markt_service`), die laufende
    # Stunde dort also `jetzt.hour` — genau der Index, den dieser Sensor
    # immer hatte. Er bleibt damit bitgleich.
    rang_jetzt = next(
        (e for e in (preis.get("rang_profil") or []) if e.get("stunde") == jetzt_stunde),
        None,
    )
    if rang_jetzt is not None:
        _anhaengen(
            sensor_values, "eedc_guenstige_stunde", bool(rang_jetzt.get("unter_schwelle")),
            {
                "schwelle_cent": preis.get("guenstig_schwelle_cent"),
                "preis_cent": rang_jetzt.get("preis_cent"),
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
        # N-544: `*_um` ist eine **End**-Angabe. Der Sim-Slot `h` ist voll, wenn
        # die Stunde `[h−1, h)` durchgerechnet ist — der Zeitpunkt ist `h:00`,
        # also das ENDE des Slots. Bis 22.09.2026 kam dieselbe Zahl aus
        # `_iso(heute, slot)` heraus, weil `_iso` damals den forward-Index nahm;
        # mit der backward-Achse ist `_iso_ende` die richtige Funktion **und**
        # benennt, was gemeint ist. Der Wert bleibt bitgleich.
        _anhaengen(
            sensor_values, "eedc_speicher_voll_um_ts", _iso_ende(heute, slot),
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
                # N-544: Beginn-Angabe (die Stunde, in der das Maximum lag).
                "stunde_max_mittel": (
                    _hhmm_beginn(max(mittel, key=lambda x: x[1])[0]) if mittel else None
                ),
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
                # N-544: `ab` ist der Beginn des ersten Slots, `bis` der Beginn
                # des ersten Slots NACH dem Block — also sein Ende. `b.ab`/`b.bis`
                # sind Backward-Slot-Indizes des heutigen Tages und liegen damit
                # auf derselben Achse wie der Fenster-Kontext.
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
        speicher_eta=speicher_eta,
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


async def _arbitrage_sensor(*, anlage, db, sensor_values, prognose, fenster_ctx, heute,
                            speicher_eta=None):
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
    # ⭐ **S3b: derselbe Resolver wie die Speicherkosten-Sensoren** — gemessen
    # › gepflegt › **kein Vorschlag**. Bis zum 22.09.2026 stand hier
    # `prognose.get("speicher_eta_prozent") or 90.0`: eine Kaskade aus zwei
    # Defaults übereinander (`aggregiere_speicher_basis` liefert selbst schon
    # den Kanon-Default 95, das `or 90.0` greift also nur, wenn gar kein
    # Speicher da ist). Die genannte Cent-Ersparnis stand damit auf einer
    # Herstellerangabe, die niemand bestätigt hat — an der Demo-Anlage sind es
    # **gemessen 85,0 %** statt der gepflegten 95.
    from backend.core.berechnungen.speicher_kosten import eta_anlage

    eta_info = speicher_eta or {}
    eta = eta_anlage([i.wirkungsgrad for i in eta_info.values()]) if eta_info else None
    if eta is None:
        # Ohne belastbaren Wirkungsgrad gibt es keinen Vorschlag: die Ersparnis
        # ist eine Differenz zweier Preise ÜBER η, und ein geratenes η
        # verschiebt sie um zweistellige Prozente (ADR-002/P4).
        return
    _quellen = {i.quelle for i in eta_info.values() if i.wirkungsgrad is not None}
    _messungen = {i.messung for i in eta_info.values() if i.wirkungsgrad is not None}
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
            # N-544: `stunden` ist eine Beginn-Angabe — „laden ab".
            "stunden": [_hhmm_beginn(h) for h in ergebnis.lade_stunden],
            "ersparnis_cent": round(ergebnis.ersparnis_cent),
            "soc_prozent": round(float(soc), 1),
            "frei_kwh": round(frei, 1),
            "wirkungsgrad_prozent": eta,
            "wirkungsgrad_quelle": _quellen.pop() if len(_quellen) == 1 else None,
            "wirkungsgrad_messung": _messungen.pop() if len(_messungen) == 1 else None,
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

    # ⭐ **Dieselbe Grenze wie beim IST — und die kommt aus derselben Quelle**
    # (N-544). Bis 22.09.2026 stand hier `bis_stunde = max(0, jetzt_stunde)`:
    # die Uhr als Grenze für eine Summe, die der Kanon aus **gemessenen Zeilen**
    # bildet. Gemessen, wann die beiden auseinanderlaufen:
    #
    #   * zwischen :00 und ~:12 — HA hat die eben abgelaufene LTS-Stunde noch
    #     nicht geschrieben. IST endet bei Slot `jetzt.hour`, die Uhr-Summe
    #     `[:jetzt_stunde]` ebenfalls bei Slot `jetzt.hour − 1` … beide bei
    #     derselben Stunde. **Gleich.**
    #   * ab ~:12 bis zur vollen Stunde — die Zeile ist da. IST endet jetzt bei
    #     Slot `jetzt.hour + 1`, die Uhr-Summe weiterhin eine Stunde davor:
    #     **eine gemessene Stunde mehr als prognostizierte**. Der Sensor meldete
    #     dann drei Viertel jeder Stunde eine Abweichung, die aus der Grenze
    #     stammte und nicht aus der Anlage — bei einer Vormittagsstunde mit
    #     1 kWh über einer 7-kWh-Summe sind das rund +14 %.
    #
    # Der Kanon sagt jetzt selbst, bis wohin er gemessen hat.
    #
    # `ist_bisher_bis_slot` ist der **höchste Slot mit Wert** und wird deshalb
    # INKLUSIVE summiert. Fehlt er (ältere Prognose-Dicts, keine Messzeile),
    # bleibt es beim bisherigen Uhr-Schnitt.
    bis_slot = prognose.get("ist_bisher_bis_slot")
    if bis_slot is None:
        bis_index = max(0, jetzt_stunde)
    else:
        bis_index = max(0, int(bis_slot) + 1)
    soll = sum(float(v or 0.0) for v in stundenprofil[:bis_index])
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
            # End-Angabe (N-544): bis wann gerechnet wurde = Ende des
            # letzten einbezogenen Slots.
            "bis_stunde": _hhmm_ende(bis_index - 1) if bis_index > 0 else None,
            "mae_30_tage_prozent": mae,
        },
        berechnung=f"({ist:.1f} − {soll:.1f}) ÷ {soll:.1f} × 100",
    )

    if mae is None:
        return
    sonnenstunden = sum(1 for v in stundenprofil[:bis_index] if float(v or 0.0) > 0)
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
