"""eedc-eigene PV-Prognose-Werte für den HA-Export (#150 Slice A).

Liefert die Vorausschau-Sensoren für `calculate_anlage_sensors()`:
  - Tagesprognose heute — der **kanonische** eedc-Tageswert (= persistierter
    `pv_prognose_kwh` = Cockpit/Aussicht/Kurzfrist/Vergleich-eedc), rollt
    intraday mit OpenMeteo mit. **Ein Wert überall** (Prognose-Kanon-Fix V3):
    der frühere MQTT-„heute" (IST bisher + Rest) war genau die Inkonsistenz
    aus Rainers PN 2026-06-26 (MQTT 76,8 ≠ Anzeige 75,3) und entfällt.
  - Rest-Ertrag heute (NUR Σ Prognose der verbleibenden Stunden) — aus
    DEMSELBEN Kanon-Helper wie „heute", damit beide synchron mit OM rollen.
  - Tagesprognose morgen / übermorgen / in 3 Tagen
  - „Speicher voll um" (SoC-Simulation ab AKTUELLEM Speicherstand)
  - die eedc-Stundenprofile heute + Tag+1/2/3 (als Sensor-Attribut, kein
    eigenes Topic)
  - seit eedc@ha Teil 1 (S3/P1, 21.09.2026) die **Verbrauchs**-Stundenreihe von Modell A samt
    ihrem WP-Anteil und der Temperaturvorhersage — der Rohstoff der
    Überschuss-Prognose (§5/P2) und der Fenster-Sensoren
  - seit N-591 (01.10.2026) die Verbrauchsprognose für **morgen** (Modell A, Wochentag und
    Temperaturvorhersage von morgen) samt Stundenreihe und Datum

Prognose-Basis: ``services/prognose_kanon.py`` (Multi-String-Fan-out +
eedc-Korrektur pro Energie-Slot), Tageswert = Σ korrigierte Stunden-Slots
(Invariante: Sensor-State == Σ Attribut-Slots). Identischer Kanon wie die
„eedc"-Spalte im Prognosen-Vergleich und der Live-/Persistenz-Pfad.

Quellen-Regel (Export-Rahmen): es wird IMMER nur die **eedc-eigene** Prognose
exportiert — nie Solcast/SFML, die liegen via eigene HA-Integration schon in
HA. Die gewählte Anzeige-Quelle der Anlage ist hier deshalb bewusst
irrelevant.

Robustheit: fehlende Koordinaten / keine PV / Netzwerkfehler → ``None``; die
Sensoren entfallen dann lautlos (Export bleibt für die übrigen Sensoren grün).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.core.investition_kennwerte import aggregiere_speicher_basis
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


async def berechne_prognose_export(db, anlage, *, skip_jitter: bool = False) -> Optional[dict]:
    """Berechnet die eedc-eigenen PV-Prognose-Exportwerte einer Anlage.

    ``skip_jitter`` (N-531, 18.09.2026): der Prognose-Kanon schläft vor jedem Open-Meteo-Abruf
    ``random.uniform(1, 30)`` Sekunden, um Lastspitzen zu verteilen — bei parallelem Fan-out je
    Orientierungsgruppe wartet der Aufrufer auf das Maximum, gemessen 26 s bei kaltem Cache. Jede
    Sicht mit Bedienoberfläche überspringt das; der HA-Export war der einzige Aufrufer ohne den
    Schalter. On-Demand-Wege (REST-Sichten, Publish-Knopf) übergeben ``True``; der zeitgesteuerte
    Publish-Job behält den Jitter, weil er bei allen Installationen zur selben Minute läuft.

    Returns:
        dict mit ``heute_kwh`` (kanonische eedc-Tagesprognose, rollt mit den
        OpenMeteo-Aktualisierungen — **nicht** IST bisher + Rest),
        ``rest_today_kwh`` (verbleibende Stunden ab jetzt, laufende Stunde
        anteilig nach verstrichenen Minuten, #339), ``day_plus_1_kwh``,
        ``day_plus_2_kwh``, ``day_plus_3_kwh``, ``speicher_voll_um``
        (str "HH:00" | None), ``speicher_verbrauch_profil`` (die Verbrauchsannahme
        dieser Simulation als Attribut-Dict, s. ``_speicher_verbrauch_profil``; None,
        solange nicht simuliert wurde), ``verbrauch_heute_kwh`` (Σ des Live-Verbrauchsprofils,
        nur aus einem individuellen Profil — sonst None, #395), ``verbrauch_morgen_kwh`` samt
        ``verbrauch_morgen_*`` (dieselbe Rechnung für morgen, N-591), ``stundenprofil_heute`` und
        ``stundenprofil_day_plus_1/2/3`` (je 24 kWh-Slots) — oder ``None``.
    """
    try:
        from backend.services.prognose_kanon import kanon_tagesprognose
        from backend.services.verbrauch_prognose_service import get_verbrauch_prognose
        from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

        heute = date.today()

        prognose = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=skip_jitter)
        if not prognose:
            return None

        def _tageswert(offset: int) -> Optional[float]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            return tag.eedc_kwh if tag else None

        def _haelften(offset: int) -> tuple[Optional[float], Optional[float]]:
            """Vormittag/Nachmittag desselben Tages — am **Solar Noon** (#395/3).

            ⛔ **Die öffentliche Zusage in #395 nannte einen festen 13-Uhr-Schnitt
            und behauptete, das sei „die Aufteilung, die auf deinem Bildschirm
            steht". Beides ist am Code falsch** (Fund N-331, gemessen 27.08.):
            eedc schneidet an **allen** drei rechnenden Stellen am Solar Noon —
            `solar_forecast_service:829`, `prognose_kanon::vm_nm_split` und
            `prognosen.py::_berechne_tageshaelfte` (für alle vier Quellen).
            Quelle des Irrtums war ein veralteter Feldkommentar
            (`prognosen.py:95`, „0:00–12:59"), der drei Zeilen über der Funktion
            steht, die es anders macht.

            **Der Sensor folgt der Anzeige, nicht der Zusage** — sonst stünden
            wieder zwei Zahlen für dieselbe Größe auf einer Seite, genau die
            Klasse, die der Prognose-Kanon in v4.0.1 beseitigt hat.

            ⭐ **Der Einwand aus der Zusage bleibt trotzdem beantwortet:** dass
            eine bewegliche Grenze eine Automation an zwei Tagen verschieden
            entscheiden lässt, stimmt — deshalb reist die Grenze als Attribut
            `solar_noon` mit, statt geraten werden zu müssen.
            """
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            if tag is None:
                return None, None
            return tag.vm_kwh, tag.nm_kwh

        def _stundenprofil(offset: int) -> Optional[list]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            if tag is None or tag.profil is None:
                return None
            return list(tag.profil.stundenprofil_export_kwh)

        heute_tag = prognose.tage[0] if prognose.tage else None
        stunden_kwh_heute = (
            list(heute_tag.profil.stunden_kwh)
            if heute_tag and heute_tag.profil
            else [0.0] * 24
        )

        # „heute" = kanonischer eedc-Tageswert (= Anzeige/Persistenz, rollt mit
        # OM). „Rest heute" + „heute" aus DEMSELBEN Kanon-Helper (§5.4).
        now = datetime.now(_BERLIN_TZ)
        heute_kwh = heute_tag.eedc_kwh if heute_tag else None
        # Rest NUR aus dem Kanon (#339: laufende Stunde anteilig). Ohne Profil ist
        # `stunden_kwh_heute` ohnehin [0.0]*24 — eine zweite Rest-Formel hier wäre
        # eine zweite Wahrheit, die beim nächsten Konventionswechsel driftet.
        rest_today = prognose.rest_heute_kwh if prognose.rest_heute_kwh is not None else 0.0

        # „Speicher voll um" — Simulation ab aktuellem SoC (nicht Mitternacht).
        speicher_voll_um = None
        speicher_verbrauch_profil = None
        speicher_voll_um_slot: Optional[int] = None
        speicher_soc_pro_stunde: Optional[dict] = None
        speicher_end_soc_prozent: Optional[float] = None
        speicher_sim_start: Optional[int] = None
        speicher_sim_anteil: Optional[float] = None
        speicher_kap, speicher_eta, akt_soc, soc_datum, soc_stunde = (
            await _aktueller_speicher(db, anlage.id, heute)
        )
        sim_start, sim_anteil = _sim_start(soc_datum, soc_stunde, heute)
        if speicher_kap > 0 and akt_soc is not None and sim_start is not None:
            vp = await get_verbrauch_prognose(anlage.id, heute, db)
            verbrauch_stunden = vp["stunden_kw"] if vp else [0.0] * 24
            sim = simuliere_speicher_tag(
                pv_stunden=stunden_kwh_heute,
                verbrauch_stunden=verbrauch_stunden,
                speicher_kap_kwh=speicher_kap,
                start_soc_prozent=akt_soc,
                start_stunde=sim_start,
                wirkungsgrad_prozent=speicher_eta,
                start_anteil=sim_anteil,
            )
            speicher_voll_um = sim.speicher_voll_um
            speicher_soc_pro_stunde = dict(sim.soc_pro_stunde)
            speicher_end_soc_prozent = round(float(sim.end_soc_prozent), 1)
            speicher_sim_start = sim_start
            speicher_sim_anteil = sim_anteil
            speicher_verbrauch_profil = _speicher_verbrauch_profil(vp, verbrauch_stunden)
            # E3 (S2): derselbe Zeitpunkt als Slot — der ISO-Zeitstempel entsteht
            # erst beim Sensor, damit die Zonen-Frage genau einmal beantwortet wird.
            if speicher_voll_um:
                try:
                    speicher_voll_um_slot = int(str(speicher_voll_um).split(":")[0])
                except ValueError:
                    speicher_voll_um_slot = None

        # #395 (OB73-gif): die Verbrauchsprognose des Tages — dieselbe Zahl wie
        # die Kachel in Cockpit → Live, aus demselben Dienst. `None` ohne
        # individuelles Profil (kein Sensor aus einem Standardprofil, N-332).
        from backend.services.verbrauchsprognose_heute import (
            verbrauchsprognose_heute,
            verbrauchsprognose_morgen,
        )
        verbrauch = await verbrauchsprognose_heute(anlage, db)
        # N-591 (#420, OB73-gif): dieselbe Rechnung für morgen — Wochentag und
        # Temperaturvorhersage von morgen. NACH dem Kanon gerufen: dessen Abruf
        # hat den Forecast-Eintrag gewärmt, aus dem die Temperaturen kommen.
        # Die Speicher-Simulation bleibt, wie sie ist (endet um Mitternacht;
        # Modell (c) war nicht gewählt).
        verbrauch_morgen = await verbrauchsprognose_morgen(
            anlage, db, skip_jitter=skip_jitter,
        )

        return {
            "heute_kwh": heute_kwh,
            "rest_today_kwh": rest_today,
            # rapahl-PN 2026-08-23: IST bisher + Rest — die nachgeführte
            # Tageszahl. Sie steht NEBEN `heute_kwh`, nicht an dessen Stelle:
            # jener bleibt der kanonische Wert, der in App, MQTT und Persistenz
            # dieselbe Zahl trägt (Prognose-Kanon-Fix V3). Wer die beiden
            # verwechselt, hat wieder zwei Wahrheiten — deshalb heißt der Sensor
            # ausdrücklich „(nachgeführt)".
            "heute_rollend_kwh": prognose.heute_rollend_kwh,
            "ist_bisher_kwh": prognose.ist_bisher_kwh,
            # N-544: bis wohin die IST-Summe reicht (hoechster gemessener
            # Backward-Slot). P6 summiert das SOLL bis genau dorthin — eine
            # Quelle statt zweier Grenzen.
            "ist_bisher_bis_slot": prognose.ist_bisher_bis_slot,
            "heute_vormittag_kwh": _haelften(0)[0],
            "heute_nachmittag_kwh": _haelften(0)[1],
            "morgen_vormittag_kwh": _haelften(1)[0],
            "morgen_nachmittag_kwh": _haelften(1)[1],
            # Die Schnittgrenze selbst — als „HH:MM" für heute. Sie ist die
            # Antwort auf „wann genau teilt ihr?", und ohne sie müsste eine
            # Automation sie schätzen.
            "solar_noon_heute": _solar_noon_text(heute, anlage.longitude),
            "solar_noon_morgen": _solar_noon_text(heute + timedelta(days=1), anlage.longitude),
            "day_plus_1_kwh": _tageswert(1),
            "day_plus_2_kwh": _tageswert(2),
            "day_plus_3_kwh": _tageswert(3),
            "speicher_voll_um": speicher_voll_um,
            "speicher_verbrauch_profil": speicher_verbrauch_profil,
            "verbrauch_heute_kwh": verbrauch.summe_kwh if verbrauch else None,
            "verbrauch_profil_typ": verbrauch.profil_typ if verbrauch else None,
            "verbrauch_profil_tage": verbrauch.profil_tage if verbrauch else None,
            "verbrauch_profil_slots": verbrauch.profil_slots if verbrauch else None,
            # ── S3/P1: die Stundenreihen von Modell A ───────────────────────
            # Sie verlassen den Dienst seit S3/P1 als Attribut; die Tagessumme
            # daneben bleibt unveraendert. ⚠ Ohne individuelles Profil ist
            # `verbrauch` None — dann gibt es KEINE Reihe und keinen Sensor
            # (N-332), nicht eine Reihe aus Nullen.
            "verbrauch_stundenprofil_kwh": verbrauch.stunden_kwh if verbrauch else None,
            "verbrauch_wp_stundenprofil_kwh": (
                verbrauch.wp_stunden_kwh if verbrauch else None
            ),
            "verbrauch_temperatur_c": verbrauch.temperatur_c if verbrauch else None,
            # N-544: das Stunden-Label je Position der drei Reihen darüber. Der
            # Fenster-Kontext ordnet danach auf seine Slot-Achse ein, statt
            # „Position i = Stunde i" anzunehmen. (Die Begründung „an DST-Tagen
            # 23 bzw. 25 Einträge" ist für OpenMeteo widerlegt — 24 Einträge mit
            # fester Verschiebung, s. `VerbrauchsprognoseHeute.stunden_label`.)
            "verbrauch_stunden_label": verbrauch.stunden_label if verbrauch else None,
            # ── N-591: die Verbrauchsprognose für morgen (eigener Sensor) ────
            # ⚠ Ohne individuelles Profil für den Tagestyp von morgen ist sie
            # None — dann kein Sensor (N-332), auch wenn es „heute" gibt.
            "verbrauch_morgen_kwh": verbrauch_morgen.summe_kwh if verbrauch_morgen else None,
            "verbrauch_morgen_profil_typ": (
                verbrauch_morgen.profil_typ if verbrauch_morgen else None
            ),
            "verbrauch_morgen_profil_tage": (
                verbrauch_morgen.profil_tage if verbrauch_morgen else None
            ),
            "verbrauch_morgen_profil_slots": (
                verbrauch_morgen.profil_slots if verbrauch_morgen else None
            ),
            "verbrauch_morgen_stundenprofil_kwh": (
                verbrauch_morgen.stunden_kwh if verbrauch_morgen else None
            ),
            "verbrauch_morgen_wp_stundenprofil_kwh": (
                verbrauch_morgen.wp_stunden_kwh if verbrauch_morgen else None
            ),
            "verbrauch_morgen_datum": verbrauch_morgen.datum if verbrauch_morgen else None,
            # ── S2: was die Steuerungs-Sensoren aus derselben Rechnung brauchen ──
            "speicher_voll_um_slot": speicher_voll_um_slot,
            # ── S3b: derselbe Sim-Lauf, zwei weitere Groessen ───────────────
            # ⭐ **EIN Lauf, nicht zwei.** „Voll um", „leer um" und „reicht bis
            # Mitternacht" sind drei Fragen an **denselben** simulierten Tag;
            # eine zweite Simulation daneben koennte zu einem anderen Ergebnis
            # kommen (anderer Start-SoC, andere Uhr) und stuende dann mit einer
            # zweiten Wahrheit neben der ersten.
            "speicher_soc_pro_stunde": speicher_soc_pro_stunde,
            "speicher_end_soc_prozent": speicher_end_soc_prozent,
            "speicher_sim_start_stunde": speicher_sim_start,
            # V1: die **Start**-Annahme der Simulation als fertiges
            # Attribut-Paar — Slot und Anteil. Die S3b-Regel „jeder Sensor
            # nennt sein Modell" galt bis 22.09.2026 nur für das
            # Verbrauchsmodell daneben; die Start-Annahme blieb stumm, obwohl
            # genau sie den Wert um bis zu eine halbe Stunde verschiebt.
            "speicher_sim_annahme": (
                {
                    "sim_start_stunde": speicher_sim_start,
                    "sim_start_anteil": speicher_sim_anteil,
                }
                if speicher_sim_start is not None else None
            ),
            "speicher_kap_kwh": speicher_kap or None,
            "speicher_eta_prozent": speicher_eta,
            "speicher_soc_prozent": akt_soc,
            "stundenprofil_heute": [round(v, 2) for v in stunden_kwh_heute],
            # ── S3b: die Abregelung von heute, in der Skala der Kappung ─────
            "abregelung_om_kwh": heute_tag.abregelung_om_kwh if heute_tag else None,
            "abregelung_om_stundenprofil_kwh": (
                heute_tag.abregelung_om_stundenprofil_kwh if heute_tag else None
            ),
            "abregelung_grenzen_kw": heute_tag.grenzen_kw if heute_tag else None,
            # Der **Rest des Tages** aus derselben Verlust-Reihe — dieselbe
            # `rest_aus_slots`-Rechnung wie beim Ertrag (#339: laufende Stunde
            # anteilig), damit „noch abzuregeln" und „noch zu erwarten" nicht
            # zwei verschiedene Tagesreste meinen.
            "abregelung_rest_heute_kwh": _abregelung_rest(heute_tag, now),
            "stundenprofil_day_plus_1": _stundenprofil(1),
            "stundenprofil_day_plus_2": _stundenprofil(2),
            "stundenprofil_day_plus_3": _stundenprofil(3),
        }
    except Exception as e:  # Export bleibt für die übrigen Sensoren grün
        logger.warning(
            "HA-Export PV-Prognose fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        return None


def _sim_start(
    soc_datum: Optional[date], soc_stunde: Optional[int], heute: date
) -> tuple[Optional[int], float]:
    """Aus der gelesenen SoC-Zeile den Start-Slot der Simulation und seinen Anteil (V1).

    ⭐ **Zwei Umrechnungen in einer Funktion, und beide waren vorher geraten.**

    1. **Konvention.** ``TagesEnergieProfil.soc_prozent`` liegt **forward**
       (N-387, `core/berechnungen/slot_konvention.py`): Zeile ``stunde = s``
       trägt das Mittel über ``[s:00, s+1:00)``. Die Simulation rechnet
       **backward** (Slot ``h`` = ``[h-1, h)``, wie die PV-Reihe, die sie
       bekommt). Dasselbe Wanduhr-Intervall heißt dort ``s + 1``.
    2. **Anteil.** Ein **Mittel** beschreibt den Ladestand etwa zur **Mitte**
       seines Intervalls, nicht an dessen Beginn ⇒ von diesem einen Slot steht
       noch die **halbe** Stunde aus (``0.5``).

    Bis 22.09.2026 stand hier ``start_stunde = now.hour``, ganz. Im verdichteten
    Normalfall (HA schreibt gegen :12) traf das denselben Slot — und rechnete
    dessen erste Hälfte ein zweites Mal. Hinkt HA nach, war zusätzlich die
    **Stunde** falsch; jetzt startet die Rechnung bei der zuletzt gemessenen
    Stunde und simuliert die Lücke bis jetzt mit **ganzen** Slots mit. Das ist
    kein Sonderfall im Code, sondern fällt hier von selbst an.

    **Stammt der SoC von gestern** (die Abfrage lässt ``datum >= heute − 1`` zu):

    * ``stunde = 23`` ist der **Normalfall kurz nach Mitternacht** und gar
      nicht veraltet — ``[gestern 23:00, 00:00)`` **ist** der Backward-Slot 0
      von heute. Also Slot 0, Anteil ``0.5``.
    * jede frühere Stunde heißt „heute liegt noch gar kein SoC vor". Dann wird
      der **ganze** Tag ab Slot 0 durchsimuliert (Anteil ``1.0``) — der
      Startwert ist dann älter als der Slot, und das ist die kleinere
      Ungenauigkeit als ein übersprungener Vormittag.

    Returns:
        ``(start_slot | None, anteil)``. ``None`` heißt „keine Simulation" —
        entweder gibt es keine SoC-Zeile, oder ihr Slot liegt hinter dem
        Tagesende (``heute``/``stunde = 23``; erreichbar nur, wenn die Uhr des
        Aufrufers hinter der letzten verdichteten Stunde zurückliegt).
    """
    from backend.core.berechnungen.slot_konvention import forward_stunde_zu_backward_slot

    if soc_datum is None or soc_stunde is None:
        return None, 1.0
    slot = forward_stunde_zu_backward_slot(int(soc_stunde))   # s + 1, SoT der Konvention
    if soc_datum == heute:
        return (slot, 0.5) if slot < 24 else (None, 1.0)
    return (0, 0.5) if slot >= 24 else (0, 1.0)


def _abregelung_rest(heute_tag, jetzt) -> Optional[float]:
    """Der noch bevorstehende Kappungsverlust von heute — `None` ohne Kappung."""
    if heute_tag is None or not heute_tag.abregelung_om_stundenprofil_kwh:
        return None
    from backend.services.prognose_kanon import rest_aus_slots

    rest = rest_aus_slots(heute_tag.abregelung_om_stundenprofil_kwh, jetzt)
    return None if rest is None else round(rest, 2)


def _speicher_verbrauch_profil(
    vp: Optional[dict], verbrauch_stunden: Sequence[float]
) -> dict:
    """Die Verbrauchsannahme der Speicher-Simulation als Sensor-Attribute (N-392).

    ⚠ **Zwei Verbrauchsmodelle stehen im selben Export nebeneinander**, und
    das ist bekannt und bleibt so: `eedc_verbrauchsprognose_heute_kwh` trägt
    das 7-Tage-Profil der Live-Kachel (``verbrauchsprognose_heute``), die
    Simulation hinter `eedc_speicher_voll_um` rechnet mit dem gewichteten
    8-Wochen-Profil (``verbrauch_prognose_service``). Bis 2026-09-18 nannte
    nur der Nachbar seine Grundlage (``profil_typ``/``profil_tage``) — eine
    Automation, die beide verrechnet, mischte zwei Modelle ohne ein Attribut,
    das es sagt. Deshalb trägt jetzt jeder Sensor seine Annahme; die
    Algorithmen werden hier **nicht** zusammengeführt.

    Dieselben Feldnamen wie beim Nachbarn, wo dieselbe Bedeutung dahintersteht
    (``profil_typ``, ``profil_tage``); die Kennwerte des Modells kommen aus dem
    Ergebnis des Dienstes — nichts wird hier ein zweites Mal hergeleitet.

    ``verbrauch_annahme_kwh`` ist die Σ genau der Liste, die die Simulation
    bekommen hat — auch dann, wenn kein Profil vorlag: dann rechnet sie mit
    **0 kWh Verbrauch** (``profil_typ: "kein_profil"``), und das ist die
    Annahme mit der größten Überraschung für den Anwender; sie darf am
    wenigsten stumm bleiben.
    """
    return {
        "profil_typ": vp["profil_typ"] if vp else "kein_profil",
        "profil_wochen": vp["wochen"] if vp else None,
        "profil_halbwertszeit_tage": vp["halbwertszeit_tage"] if vp else None,
        "profil_stufe": vp["basis"] if vp else None,
        "profil_tage": vp["daten_tage"] if vp else None,
        "verbrauch_annahme_kwh": round(sum(float(v or 0.0) for v in verbrauch_stunden), 1),
    }


def _solar_noon_text(tag: date, longitude: Optional[float]) -> Optional[str]:
    """Solar Noon dieses Tages als „HH:MM" — dieselbe Quelle wie der Schnitt.

    Bewusst über `_solar_noon_hour` und nicht über eine eigene Formel: die
    Grenze im Attribut MUSS dieselbe sein, an der die beiden Zahlen daneben
    getrennt wurden. Eine zweite Berechnung wäre die nächste zweite Wahrheit.
    """
    if longitude is None:
        return None
    from backend.services.solar_forecast_service import _solar_noon_hour

    noon = _solar_noon_hour(tag.isoformat(), longitude)
    h = int(noon)
    return f"{h:02d}:{int((noon - h) * 60):02d}"


async def _aktueller_speicher(
    db, anlage_id: int, heute: date
) -> tuple[float, float, Optional[float], Optional[date], Optional[int]]:
    """(Speicher-Kapazität kWh, Wirkungsgrad %, aktueller SoC %, Datum, Stunde).

    Der „aktuelle SoC" ist der zuletzt gespeicherte Stunden-SoC (heute, sonst
    gestern) aus ``TagesEnergieProfil`` — robust und ohne Live-Abhängigkeit.

    ⭐ **Seit V1 (22.09.2026) reist mitzurück, WO dieser Wert steht** (Datum +
    `stunde`-Spalte). Der Aufrufer hat die Start-Stunde der Simulation bis
    dahin aus `now.hour` **geraten**; das stimmte nur, solange HA pünktlich
    verdichtet hatte, und sagte nichts über den Anteil des Slots, der noch
    bevorsteht. `None`/`None` heißt „keine SoC-Zeile gefunden" — dann ist auch
    der SoC `None`.

    ⚠ **`soc_prozent` liegt forward** (`core/berechnungen/slot_konvention.py`,
    N-387): Zeile `stunde = s` trägt das Mittel über `[s:00, s+1:00)`. Die
    Simulation rechnet **backward** (Slot `h` = `[h-1, h)`). Dasselbe
    Wanduhr-Intervall heißt dort also `s + 1` — die Umrechnung macht der
    Aufrufer, diese Funktion liefert die Rohspalte.
    """
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
            Investition.aktiv.is_(True),
        )
    )
    speicher = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    # A31-2/E18: NETTO wie im Planungs-Tab. Der Sensor `eedc_speicher_voll_um`
    # und die KPI-Kachel „Speicher voll" tragen denselben Namen und dieselbe
    # Simulation — sie dürfen nicht auf verschiedenen Kapazitäten laufen. Seit
    # N-238 gilt das auch für den **Wirkungsgrad**, deshalb der geteilte Helper
    # statt zweier gleichlautender Faltungen.
    # (Der abweichende Start-SoC und die abweichende Start-Stunde bleiben
    # bewusst, s. Modul-Docstring von `speicher_simulation`.)
    kap, eta = aggregiere_speicher_basis(speicher)
    if not kap:
        return 0.0, eta, None, None, None

    soc_res = await db.execute(
        select(
            TagesEnergieProfil.soc_prozent,
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
        ).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= heute - timedelta(days=1),
            TagesEnergieProfil.soc_prozent.isnot(None),
        ).order_by(
            TagesEnergieProfil.datum.desc(), TagesEnergieProfil.stunde.desc()
        ).limit(1)
    )
    zeile = soc_res.first()
    if zeile is None:
        return float(kap), eta, None, None, None
    return float(kap), eta, zeile[0], zeile[1], int(zeile[2])
