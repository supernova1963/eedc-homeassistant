"""HA-Export, Stufe 3b — Preise und Speicher (acht anlagenweite Sensoren).

Phase von ``calculate_anlage_sensors``, **nach** ``steuerungs_sensoren``. Sie
rechnet nur; die Eingänge (Bezugspreis-Reihen, Wirkungsgrade je Speicher) hat
der Orchestrator vorher geholt und reicht sie als Parameter herein — denn
``steuerungs_sensoren`` braucht dieselben (P3 den Wirkungsgrad, der
Fenster-Kontext die Preisreihe). Zwei Beschaffungen wären zwei Wahrheiten über
denselben Moment und eine zweite Runde Abfragen.

⭐ **Der IMD-Lader liegt hier, wird aber vom Orchestrator gerufen.** Er steht in
diesem Modul, weil er fachlich zu dieser Phase gehört (η je Speicher); gerufen
wird er **vor** ``steuerungs_sensoren``, weil P3 den Wirkungsgrad dort schon
braucht. ⛔ Hier stand in Fassung 3 der Vorlage, die Zeilen kämen aus
``calculate_investition_sensors`` — der läuft **nach** dem Anlagen-Rechner
(``sensoren.py:49/103``) und erreicht eine anlagenweite Phase nie.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import select

from backend.models.investition import Investition, InvestitionMonatsdaten

logger = logging.getLogger(__name__)


async def lade_speicher_wirkungsgrade(
    db, anlage, *, heute: date
) -> dict[int, "WirkungsgradInfo"]:
    """Der Wirkungsgrad **je aktivem Speicher** — gemessen, gepflegt oder keiner.

    ⚠ **ADR-002/P10-Ausnahme, gelistet als `P10_PER_INVESTITION`.** Dieser Lader
    greift selbst auf ``InvestitionMonatsdaten`` zu, und das ist eine bewusste
    Ausnahme derselben Art wie ``roi_pv.py::pv_einsparung_und_speicher_ist``:
    was hier entsteht, ist ein **Geräteaggregat** (Lade-/Entlademengen über die
    Lebensdauer **eines** Speichers), keine Monatszeilen-Faltung. Die
    Monats-Fakten-Schicht liefert anlagenweite Monate; aus einem aufbereiteten
    Anlagenmonat lässt sich η eines einzelnen Geräts nicht zurückrechnen.

    Der Filter ist derselbe wie bei den Bestandsaufrufern
    (``Investition.ist_aktiv_im_monat``, #236), die Periode reicht von der
    ältesten Anschaffung bis heute — genau wie in ``roi_pv``, damit beide
    Sichten dieselbe Zahl nennen.
    """
    from backend.core.investition_kennwerte import get_speicher_wirkungsgrad_gepflegt
    from backend.services.speicher_wirtschaftlichkeit import wirkungsgrad_ist_fuer_speicher

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
    if not speicher:
        return {}

    imd_res = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([s.id for s in speicher])
        )
    )
    je_inv: dict[int, list] = {}
    for imd in imd_res.scalars().all():
        je_inv.setdefault(imd.investition_id, []).append(imd)

    anschaffungen = [s.anschaffungsdatum for s in speicher if s.anschaffungsdatum]
    periode_von = min(anschaffungen) if anschaffungen else None

    out: dict[int, WirkungsgradInfo] = {}
    for sp in speicher:
        gepflegt = get_speicher_wirkungsgrad_gepflegt(sp)
        gemessen = None
        if periode_von is not None:
            try:
                gemessen = await wirkungsgrad_ist_fuer_speicher(
                    db,
                    anlage_id=anlage.id,
                    speicher=sp,
                    verbrauch_daten_je_monat=[
                        (imd.verbrauch_daten or {})
                        for imd in je_inv.get(sp.id, [])
                        if sp.ist_aktiv_im_monat(imd.jahr, imd.monat)
                    ],
                    von=periode_von,
                    bis=heute,
                )
            except Exception as e:      # ein fehlender η darf den Export nicht kippen
                logger.warning(
                    "HA-Export η-IST fehlgeschlagen (Speicher %s): %s: %s",
                    sp.id, type(e).__name__, e,
                )
        out[sp.id] = _aufloesen(sp, gemessen, gepflegt)
    return out


class WirkungsgradInfo:
    """Der aufgelöste Wirkungsgrad eines Speichers samt Begründung.

    ⭐ **Drei Stufen, und die dritte ist „kein Sensor".** Der Kanon-Default
    (95 %) kommt hier bewusst **nicht** vor: er ist für eine Ertragsrechnung
    über Jahre richtig, als Nenner eines ct-Betrags in einer HA-Automation aber
    eine Behauptung über *dieses* Gerät.

    ``messung`` nennt immer, was die Messung ergeben hat — auch wenn sie
    gescheitert ist. Ein stummer Rückfall auf den Parameter wäre die „stille
    Ersetzung", gegen die KONZEPT-FLEX-TARIFE §8 steht.
    """

    __slots__ = ("wirkungsgrad", "quelle", "messung", "laedt_aus_netz")

    def __init__(self, wirkungsgrad, quelle, messung, laedt_aus_netz):
        self.wirkungsgrad: Optional[float] = wirkungsgrad
        self.quelle: Optional[str] = quelle          # "gemessen" | "parameter" | None
        self.messung: str = messung
        self.laedt_aus_netz: bool = laedt_aus_netz

    def als_attribut(self) -> dict:
        return {
            "wirkungsgrad": self.wirkungsgrad,
            "quelle": self.quelle,
            "messung": self.messung,
        }


def _aufloesen(speicher: Any, gemessen, gepflegt: Optional[float]) -> WirkungsgradInfo:
    """gemessen › gepflegt › keiner — und der Grund reist mit."""
    laedt = bool((getattr(speicher, "parameter", None) or {}).get("laedt_aus_netz"))

    if gemessen is None:
        # `aggregiere_speicher_ist` gab `None`: zu wenige Monate ODER gar keine
        # erfasste Entladung. Der SoT trennt die beiden nicht — der Text auch nicht.
        messung = "zu-wenig-monate"
    elif gemessen.wirkungsgrad_prozent is not None:
        return WirkungsgradInfo(
            round(float(gemessen.wirkungsgrad_prozent), 1), "gemessen", gemessen.quelle, laedt
        )
    else:
        # `fenster-zu-kurz` · `keine-ladung` · `nicht-ermittelbar`
        messung = gemessen.quelle

    if gepflegt is not None:
        return WirkungsgradInfo(round(float(gepflegt), 1), "parameter", messung, laedt)
    return WirkungsgradInfo(None, None, messung, laedt)


# ═════════════════════════════════════════════════════════════════════════════
# Die Phase — neun anlagenweite Sensoren
# ═════════════════════════════════════════════════════════════════════════════

def _sensor(key: str):
    from backend.services.ha_sensors_export import STEUERUNG_SENSOREN

    for d in STEUERUNG_SENSOREN:
        if d.key == key:
            return d
    raise KeyError(key)


def _anhaengen(sensor_values: list, key: str, wert, zusatz: Optional[dict] = None,
               berechnung: Optional[str] = None) -> None:
    """Einen Sensor anhängen — **nur mit Wert** (ADR-002/P4).

    ``None`` heißt „diesen Sensor gibt es in dieser Lage nicht", nie „der Wert
    ist 0". Ein `False` dagegen IST ein Wert. Dieselbe Regel und dieselbe
    Bauform wie in ``anlage_steuerung.py``.
    """
    from backend.services.ha_sensors_export import SensorValue

    if wert is None:
        return
    sensor_values.append(SensorValue(
        definition=_sensor(key), value=wert,
        zusatz_attribute={k: v for k, v in (zusatz or {}).items() if v is not None},
        berechnung=berechnung,
    ))


def _jetzt_preis(reihe, jetzt_slot: int) -> Optional[float]:
    """Der Preis der **laufenden** Stunde aus einer Slot-Reihe."""
    if reihe is None:
        return None
    preise = getattr(reihe, "preis_cent", reihe)
    if 0 <= jetzt_slot < len(preise):
        return preise[jetzt_slot]
    return None


def _tagesteil(reihe, von: int, bis: int) -> Optional[list]:
    """Ein Tagesausschnitt einer Achsen-Reihe als Attribut — oder `None`.

    ⚠ Die Stundenreihen-Attribute tragen **24 Backward-Slots je Tag**, wie
    ``stundenprofil_kwh`` überall sonst: Slot 0 ist gestern 23 Uhr, Slot 23 ist
    heute 22–23 Uhr. Die interne Achse ist länger (25 bzw. 48) — sie muss die
    Stunde 23–24 Uhr tragen, damit ein Fenster dort gefunden wird. Für das
    Attribut wird auf die Tageskonvention geschnitten.
    """
    if reihe is None:
        return None
    teil = list(reihe[von:bis])
    return teil if any(v is not None for v in teil) else None


def _leer_um_und_reicht(
    soc_pro_stunde: Optional[dict], start_stunde: Optional[int]
) -> tuple[Optional[int], Optional[bool], Optional[float], Optional[int]]:
    """„Leer um" und „reicht bis Mitternacht" aus **einer** Regel auf **einem** Lauf.

    ⭐ **Die Regel ist ein ÜBERGANG, kein Zustand:** „leer um" ist das Ende des
    ersten Slots **nach dem Start-Slot**, in dem der Ladestand in den Leerstand
    übergeht (vorher > ``SOC_LEER_PROZENT``, jetzt ≤). „Reicht" ist genau dann
    AN, wenn es diesen Übergang nicht gibt **und** der End-Ladestand über der
    Schwelle liegt.

    ⛔ **Hier stand in Fassung 3 der Vorlage „erster Slot ab jetzt ≤ 2 %".** Das
    hätte den häufigsten Abendfall falsch gemeldet: Der Start-Slot der
    Simulation ist die **abgelaufene** Stunde, und sein SoC ist der
    Ausgangswert. Ein jetzt leerer Speicher, den die PV bis 11 Uhr wieder füllt,
    hätte „leer um" in der Vergangenheit gemeldet und daneben „reicht: AUS" —
    während „voll um 11:00" danebensteht. Mit der Übergangsregel: kein Übergang
    ⇒ kein „leer um", und „reicht" ist AN, wenn er über der Schwelle endet.

    ⚠ Der **12-Uhr-Filter** der Simulation (`speicher_leer_um`) bleibt dem
    Planungs-Tab: er ist dort richtig, weil jene Simulation um Mitternacht
    startet und morgendliche Niedrigstände keine Aussage über den Abend sind.
    Diese hier startet **jetzt** und braucht ihn nicht.

    Returns:
        ``(leer_slot | None, reicht | None, end_soc | None, min_slot | None)``
        — alles `None`, wenn es keinen Lauf gab (kein Speicher, kein SoC).
    """
    from backend.core.berechnungen.speicher_simulation import SOC_LEER_PROZENT

    if not soc_pro_stunde:
        return None, None, None, None
    slots = sorted(int(h) for h in soc_pro_stunde)
    if not slots:
        return None, None, None, None

    werte = {int(h): float(v) for h, v in soc_pro_stunde.items()}
    start = int(start_stunde) if start_stunde is not None else slots[0]

    leer_slot: Optional[int] = None
    vorher = werte[slots[0]]
    for h in slots:
        if h <= start:
            vorher = werte[h]
            continue
        if vorher > SOC_LEER_PROZENT and werte[h] <= SOC_LEER_PROZENT:
            leer_slot = h
            break
        vorher = werte[h]

    end_soc = werte[slots[-1]]
    reicht = leer_slot is None and end_soc > SOC_LEER_PROZENT
    min_slot = min(slots, key=lambda h: werte[h])
    return leer_slot, reicht, round(end_soc, 1), min_slot


async def preise_speicher_sensoren(
    *,
    anlage,
    sensor_values: list,
    prognose: Optional[dict],
    preis: Optional[dict],
    fenster_ctx,
    bezugspreise,
    speicher_eta: dict,
    heute: date,
    jetzt_stunde: int,
) -> dict:
    """Die neun Sensoren der Stufe 3b — Preise, Speicherkosten, Abregelung, §51.

    ⛔ **Diese Phase lädt nichts.** Alle Eingänge kommen als Parameter; der
    Orchestrator hat sie vor ``steuerungs_sensoren`` geholt, weil P3 sie dort
    schon braucht. Eine zweite Beschaffung wäre eine zweite Wahrheit über
    denselben Moment.
    """
    from backend.core.berechnungen.preis_reihe import wert_je_kwh
    from backend.core.berechnungen.speicher_kosten import eta_anlage, speicher_kwh_kosten
    from backend.api.routes.ha_export.anlage_steuerung import _hhmm_beginn, _iso, _iso_ende

    prognose = prognose or {}
    preis = preis or {}
    jetzt_slot = jetzt_stunde + 1          # backward: die laufende Stunde

    # ── 1 · Bezugspreis jetzt ───────────────────────────────────────────────
    bezug_jetzt: Optional[float] = None
    ev_grund: Optional[str] = None
    speicher_grund: Optional[str] = None
    if bezugspreise is not None:
        reihe = bezugspreise.allgemein
        bezug_jetzt = _jetzt_preis(reihe, jetzt_slot)
        aufschlag = bezugspreise.aufschlag
        wp = bezugspreise.waermepumpe
        wp_eigen = bezugspreise.wp_eigener_tarif and wp.hat_preis
        if not reihe.ist_vollstaendig:
            ev_grund = (
                "dynamischer Tarif ohne ableitbaren Aufschlag — die nackte Börse "
                "gegen eine Vertragsvergütung wäre keine Näherung, sondern eine "
                "Differenz aus zwei Preisebenen"
            )
        _anhaengen(
            sensor_values, "eedc_bezugspreis_jetzt_cent", bezug_jetzt,
            {
                "preisquelle": reihe.quelle,
                "aufschlag_cent": aufschlag.cent if aufschlag else None,
                "aufschlag_quelle": aufschlag.quelle if aufschlag else (
                    "keiner" if reihe.quelle == "boersenpreis" else None
                ),
                "aufschlag_basis": aufschlag.basis if aufschlag else None,
                "ust_prozent": bezugspreise.ust_prozent if aufschlag else None,
                "tarif": getattr(bezugspreise.tarif_heute, "vertragsart", None) or "fest",
                "gueltig_ab": (
                    getattr(bezugspreise.tarif_heute, "gueltig_ab", None).isoformat()
                    if getattr(bezugspreise.tarif_heute, "gueltig_ab", None) else None
                ),
                "markt": preis.get("markt") if reihe.quelle in
                         ("boersenpreis", "boerse_plus_aufschlag") else None,
                "slot_konvention": "backward",
                "stundenprofil_cent": _tagesteil(reihe.preis_cent, 0, 24),
                "stundenprofil_morgen_cent": _tagesteil(reihe.preis_cent, 24, 48),
                "waermepumpe_cent": _jetzt_preis(wp, jetzt_slot) if wp_eigen else None,
                "waermepumpe_preisquelle": wp.quelle if wp_eigen else None,
                "zeitfenster_ignoriert": bezugspreise.zeitfenster_ignoriert or None,
                "eigenverbrauch_wert_grund": ev_grund,
                "verguetung_grund": bezugspreise.verguetung_grund,
            },
            berechnung=_bezug_berechnung(reihe, aufschlag, bezugspreise.ust_prozent),
        )

        # ── 2 · Einspeisevergütung ──────────────────────────────────────────
        _anhaengen(
            sensor_values, "eedc_einspeiseverguetung_cent", bezugspreise.verguetung_cent,
            {
                "verguetung_quelle": bezugspreise.verguetung_quelle,
                "tarif": getattr(bezugspreise.tarif_heute, "vertragsart", None) or "fest",
                "einspeisung_variabel": bezugspreise.einspeisung_variabel,
            },
        )

        # ── 3 · Was der Eigenverbrauch wert ist ─────────────────────────────
        #
        # ⚠ **Nur mit VOLLSTÄNDIGEM Bezugspreis** (Flex P-5): „nackte Börse
        # minus Vertragsvergütung" wäre keine Näherung, sondern eine Differenz
        # aus zwei verschiedenen Preisebenen.
        if reihe.ist_vollstaendig:
            _anhaengen(
                sensor_values, "eedc_eigenverbrauch_wert_cent",
                wert_je_kwh(bezug_jetzt, bezugspreise.verguetung_cent),
                {
                    "preisquelle": reihe.quelle,
                    "verguetung_quelle": bezugspreise.verguetung_quelle,
                    "aufschlag_quelle": aufschlag.quelle if aufschlag else None,
                    "slot_konvention": "backward",
                    "stundenprofil_cent": _ev_profil(reihe.preis_cent, bezugspreise.verguetung_cent, 0, 24),
                    "stundenprofil_morgen_cent": _ev_profil(reihe.preis_cent, bezugspreise.verguetung_cent, 24, 48),
                },
                berechnung=(
                    f"{bezug_jetzt} ct Bezug − {bezugspreise.verguetung_cent} ct Vergütung"
                    if bezug_jetzt is not None and bezugspreise.verguetung_cent is not None
                    else None
                ),
            )

    # ── 4+5 · Was Speicherstrom kostet ──────────────────────────────────────
    eta = eta_anlage([i.wirkungsgrad for i in speicher_eta.values()])
    je_speicher = {str(k): v.als_attribut() for k, v in speicher_eta.items()}
    if speicher_eta and eta is None:
        speicher_grund = (
            "für mindestens einen Speicher gibt es weder einen gemessenen noch "
            "einen gepflegten Wirkungsgrad — eine anlagenweite Zahl wäre für "
            "einen Teil der Kapazität erfunden"
        )
    eine_quelle = {i.quelle for i in speicher_eta.values() if i.wirkungsgrad is not None}
    eine_messung = {i.messung for i in speicher_eta.values() if i.wirkungsgrad is not None}
    eta_attribute = {
        "wirkungsgrad_prozent": eta,
        "wirkungsgrad_quelle": eine_quelle.pop() if len(eine_quelle) == 1 else None,
        "wirkungsgrad_messung": eine_messung.pop() if len(eine_messung) == 1 else None,
        "je_speicher": je_speicher or None,
        "speicher_kosten_grund": speicher_grund,
    }

    if bezugspreise is not None:
        _anhaengen(
            sensor_values, "eedc_speicher_strom_kosten_cent",
            speicher_kwh_kosten(bezugspreise.verguetung_cent, eta),
            {
                **eta_attribute,
                "verguetung_cent": bezugspreise.verguetung_cent,
                "verguetung_quelle": bezugspreise.verguetung_quelle,
            },
            berechnung=(
                f"{bezugspreise.verguetung_cent} ct entgangene Vergütung ÷ {eta} % Wirkungsgrad"
                if bezugspreise.verguetung_cent is not None and eta is not None else None
            ),
        )

        # Netzladen gibt es nur, wo überhaupt aus dem Netz geladen wird —
        # dasselbe Gate wie bei P3 (`laedt_aus_netz`, der Erfassungs-Schalter
        # seit #264; `arbitrage_faehig` wäre enger und schlösse jeden aus, der
        # den Handels-Haken nie gesetzt hat).
        if any(i.laedt_aus_netz for i in speicher_eta.values()):
            reihe = bezugspreise.allgemein
            _anhaengen(
                sensor_values, "eedc_speicher_netzladen_kosten_cent",
                speicher_kwh_kosten(bezug_jetzt, eta),
                {
                    **eta_attribute,
                    "preisquelle": reihe.quelle,
                    "slot_konvention": "backward",
                    "stundenprofil_cent": _eta_profil(reihe.preis_cent, eta, 0, 24),
                    "stundenprofil_morgen_cent": _eta_profil(reihe.preis_cent, eta, 24, 48),
                },
                berechnung=(
                    f"{bezug_jetzt} ct Bezug ÷ {eta} % Wirkungsgrad"
                    if bezug_jetzt is not None and eta is not None else None
                ),
            )

    # ── 6+7 · Leer um / reicht bis Mitternacht ──────────────────────────────
    leer_slot, reicht, end_soc, min_slot = _leer_um_und_reicht(
        prognose.get("speicher_soc_pro_stunde"), prognose.get("speicher_sim_start_stunde"),
    )
    if end_soc is not None:
        modell_b = prognose.get("speicher_verbrauch_profil") or {}
        if leer_slot is not None:
            _anhaengen(
                sensor_values, "eedc_speicher_leer_um_ts", _iso_ende(heute, leer_slot),
                {
                    "quelle": "simulation",
                    "regel": "Übergang in den Leerstand nach der laufenden Stunde",
                    "end_soc_prozent": end_soc,
                    **modell_b,
                },
                berechnung=(
                    f"erste Stunde nach jetzt, in der der Ladestand unter die "
                    f"Leer-Schwelle fällt (Simulation ab {jetzt_stunde:02d}:00)"
                ),
            )
        _anhaengen(
            sensor_values, "eedc_speicher_reicht_bis_mitternacht", bool(reicht),
            {
                "min_soc_prozent": round(
                    min((prognose.get("speicher_soc_pro_stunde") or {}).values()), 1
                ),
                "min_soc_um": _iso_ende(heute, min_slot) if min_slot is not None else None,
                "end_soc_prozent": end_soc,
                **modell_b,
            },
        )

    # ── 8 · Abregelung heute ────────────────────────────────────────────────
    #
    # **0 ist ein Wert** (ADR-002/P4): „heute wird nichts abgeregelt" ist eine
    # Aussage, „an dieser Anlage wird gar nicht gekappt" ist keine — dann fehlt
    # der Sensor. Der Kanon unterscheidet beides über `None`.
    _anhaengen(
        sensor_values, "eedc_abregelung_heute_kwh", prognose.get("abregelung_om_kwh"),
        {
            "skala": "openmeteo_roh_vor_korrektur",
            "slot_konvention": "backward",
            "stundenprofil_kwh": prognose.get("abregelung_om_stundenprofil_kwh"),
            "rest_heute_kwh": prognose.get("abregelung_rest_heute_kwh"),
            "grenzen_kw": prognose.get("abregelung_grenzen_kw"),
        },
        berechnung=(
            "Σ(Rohprognose − an der Wechselrichter-Grenze gekappt) je Stunde — "
            "in der Skala der Rohprognose, weil die Kappung nichtlinear ist"
        ),
    )

    # ── 9 · Einspeisung unerwünscht (§51 EEG) ───────────────────────────────
    #
    # ⛔ **Nicht tarifgebunden.** §51 trifft jede Anlage in der Direktvermarktung,
    # unabhängig davon, was sie für den Bezug zahlt; und auch für jede andere ist
    # „der Markt zahlt gerade nichts" die Information, aus der eine Automation
    # ihren Eigenverbrauch hochfährt. Deshalb steht hier die **Börse**, nicht der
    # Bezugspreis.
    rang_jetzt = next(
        (e for e in (preis.get("rang_profil") or []) if e.get("stunde") == jetzt_stunde), None,
    )
    if rang_jetzt is not None and rang_jetzt.get("preis_cent") is not None:
        boerse = float(rang_jetzt["preis_cent"])
        pv_reihe = prognose.get("stundenprofil_heute") or []
        pv_jetzt = pv_reihe[jetzt_slot] if jetzt_slot < len(pv_reihe) else None
        negative = [
            e["stunde"] for e in (preis.get("rang_profil") or [])
            if e.get("preis_cent") is not None and float(e["preis_cent"]) < 0
        ]
        naechste = next((h for h in sorted(negative) if h >= jetzt_stunde), None)
        _anhaengen(
            sensor_values, "eedc_einspeisung_unerwuenscht",
            bool(boerse < 0 and (pv_jetzt or 0) > 0),
            {
                "boersenpreis_cent": boerse,
                "pv_prognose_kwh": round(float(pv_jetzt), 2) if pv_jetzt is not None else None,
                "ueberschuss_prognose_kwh": (
                    round(fenster_ctx.ueberschuss_kwh[jetzt_slot], 2)
                    if fenster_ctx is not None and jetzt_slot < len(fenster_ctx.ueberschuss_kwh)
                    else None
                ),
                "negative_stunden_heute": len(negative),
                # Beginn-Angabe: ab wann die nächste negative Stunde läuft.
                "naechste_negative_ab": (
                    _hhmm_beginn(naechste + 1) if naechste is not None else None
                ),
                **(fenster_ctx.profil_attribute if fenster_ctx is not None else {}),
            },
        )
    return {}


def _bezug_berechnung(reihe, aufschlag, ust) -> Optional[str]:
    if reihe.quelle == "boerse_plus_aufschlag" and aufschlag is not None:
        return f"(1 + {ust:.0f} % USt) × Börsenpreis + {aufschlag.cent} ct Aufschlag ({aufschlag.quelle})"
    if reihe.quelle == "boersenpreis":
        return "Börsenpreis der laufenden Stunde — Näherung ohne ableitbaren Aufschlag"
    if reihe.quelle == "zeitfenster":
        return "Arbeitspreis des Zeitfensters, das die laufende Stunde deckt"
    return "Arbeitspreis des Tarifs"


def _ev_profil(preise, verguetung, von: int, bis: int) -> Optional[list]:
    """Der Eigenverbrauchs-Wert je Slot — dieselbe Formel wie für die laufende Stunde."""
    from backend.core.berechnungen.preis_reihe import wert_je_kwh

    if verguetung is None:
        return None
    return _tagesteil([wert_je_kwh(p, verguetung) for p in preise], von, bis)


def _eta_profil(preise, eta, von: int, bis: int) -> Optional[list]:
    """Die Netzladekosten je Slot — Bezugspreis ÷ η."""
    from backend.core.berechnungen.speicher_kosten import speicher_kwh_kosten

    if eta is None:
        return None
    return _tagesteil([speicher_kwh_kosten(p, eta) for p in preise], von, bis)
