"""
Live Wetter — die Phasen der Antwort von ``GET /api/live/{anlage_id}/wetter``.

Ausgelagert aus ``live_wetter.py::get_live_wetter`` (RF-7, Serie „Funktion vor
Datei"): die Route lag kognitiv bei 197, die Datei netto über 1 000 Zeilen.
Der Orchestrator bleibt in ``live_wetter.py`` und ruft dort weiter jeden Namen,
den Proben **am Modul ``live_wetter``** ersetzen (``_lade_forecast_gecached``,
``_get_lernfaktor``, ``_speichere_prognose``, ``_error_cache_set``) — ein
Aufruf von hier aus liefe an diesen Patches vorbei. Hier stehen nur Phasen:
sie bekommen, was der Orchestrator geladen hat, und rufen ihre Dienste über
dieselben lokalen Importe wie vorher (Patch-Ziel ist das Quellmodul).
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from backend.services.korrekturprofil_lookup import lookup_korrekturfaktor
from backend.services.solar_forecast_service import _solar_noon_hour
from backend.services.wetter.utils import (
    klassifiziere_stunde,
    wetter_symbol_aus_tag,
)

# Derselbe Kanal wie die Route: die Debug-Zeilen dieser Phasen standen bis
# RF-7 in `get_live_wetter` und tragen weiter deren Logger-Namen — wer
# `backend.api.routes.live_wetter` filtert, sieht dieselben Zeilen wie vorher.
logger = logging.getLogger("backend.api.routes.live_wetter")


def _extract_time(values: Optional[list]) -> Optional[str]:
    """Extrahiert HH:MM aus Open-Meteo ISO-Zeitstring (z.B. '2026-03-23T06:15')."""
    if not values or not values[0]:
        return None
    try:
        return values[0].split("T")[1][:5]
    except (IndexError, AttributeError):
        return None


def _format_solar_noon(longitude: Optional[float]) -> Optional[str]:
    """Solar Noon als 'HH:MM' String für heute."""
    if longitude is None:
        return None
    noon = _solar_noon_hour(date.today().isoformat(), longitude)
    h = int(noon)
    m = int((noon - h) * 60)
    return f"{h:02d}:{m:02d}"


# ── Zustand zwischen den Phasen ──────────────────────────────────────────────


@dataclass
class _Sonnenstunden:
    gesamt_s: Optional[float]
    bisher_s: Optional[float]
    rest_s: Optional[float]


@dataclass
class _PrognoseZahlen:
    """Tageswert, Rest, rollend, IST — aus dem Kanon; der Rest-Schritt der
    gewählten Quelle überschreibt ``rest``/``rollend``."""
    kanon_heute: object
    pv_prognose: Optional[float]
    rest: Optional[float]
    rollend: Optional[float]
    ist_bisher: Optional[float]


@dataclass
class _QuellenStand:
    """Was SFML und Solcast geliefert haben — **in place** gefüllt.

    Die Phasen schreiben Feld für Feld hinein, wie vorher die lokalen
    Variablen; bricht ein Abruf mittendrin ab, bleibt stehen, was bis dahin
    gesetzt war (derselbe Stand, den der ``except`` vorher hinterließ).
    """
    sfml_kwh: Optional[float] = None
    sfml_tomorrow: Optional[float] = None
    sfml_uebermorgen: Optional[float] = None
    sfml_accuracy: Optional[float] = None
    sfml_stundenprofil_heute: Optional[list] = None  # 24 Backward-Slots (kWh), für Persistenz
    # Mehrtages-Profile der gewählten Quelle (evcc `forecast` liefert 3 Tage).
    # Bis 2026-08-30 wurde nur tage[0] gelesen und der Rest verworfen — Morgen/
    # Übermorgen fielen im Block still auf den eedc-Kanon zurück (Burkard #401).
    quelle_tagesprofile: Optional[list] = None
    solcast_kwh: Optional[float] = None
    solcast_p10: Optional[float] = None
    solcast_p90: Optional[float] = None
    solcast_stundenprofil: Optional[list] = None
    # Tageswerte der Folgetage — dasselbe Objekt trägt sie längst mit, der
    # Live-Pfad hat sie nur nie ausgelesen (der Vergleichs-Endpoint tut es
    # über `solcast.tage_voraus`). Ohne sie fiel Solcast im Block für BEIDE
    # Folgetage auf eedc zurück, weil Solcast hier nur HEUTE stündlich
    # liefert. Gleiche Klasse wie `sfml_uebermorgen` oben.
    solcast_tage_voraus: Optional[list] = None


@dataclass
class _PersistenzAuftrag:
    om_prognose: Optional[float]
    om_stundenprofil: Optional[list]
    pv_final_sonne_unter: bool
    lern_stundenprofil: Optional[list]
    lern_kwh: Optional[float]


# ── Stunden ──────────────────────────────────────────────────────────────────


def _gti_werte(hourly: dict, multi_gti) -> list:
    """GTI je Stunde der Haupt- bzw. Multi-String-Abfrage."""
    # GTI-Werte: Bei Single-String aus Haupt-Request, bei Multi-String aus gewichtetem Ergebnis
    if multi_gti:
        return multi_gti
    return hourly.get("global_tilted_irradiance", [])


async def _wetter_stunden(
    db, anlage, anlage_id: int, hourly: dict, times: list, gti_values: list,
    pq, skalar_fallback: Optional[float],
) -> tuple[list[dict], list[dict]]:
    """Die Stunden des Tages: ``(alle_stunden, stunden)`` — 0-23 und 6-20."""
    alle_stunden = []  # 0-23 für Verbrauchsprofil
    stunden = []       # 6-20 für Wetter-Timeline
    for i, t in enumerate(times):
        h = int(t[11:13])

        code = hourly.get("weather_code", [None] * len(times))[i]
        gti = gti_values[i] if i < len(gti_values) else None
        bewoelkung_h = hourly.get("cloud_cover", [None] * len(times))[i]
        niederschlag_h = hourly.get("precipitation", [None] * len(times))[i]

        # Korrekturfaktor auf GTI anwenden (skaliert die Strahlung, nicht den Ertrag,
        # damit Temperaturkorrektur weiterhin korrekt greift). Pro-Stunde-Lookup mit
        # Fallback-Kaskade (sonnenstand_wetter -> stunde -> sonnenstand -> Skalar -> Legacy).
        if gti is not None and pq.ist_eedc:
            gti = await _korrigiertes_gti(
                db, anlage, anlage_id, t, h, gti,
                bewoelkung_h, niederschlag_h, code, skalar_fallback,
            )
        stunde = {
            "zeit": f"{h:02d}:00",
            "temperatur_c": hourly.get("temperature_2m", [None] * len(times))[i],
            "wetter_code": code,
            "wetter_symbol": wetter_symbol_aus_tag(
                code, bewoelkung_h, niederschlag_h,
                niederschlag_threshold_mm=0.05,
            ),
            "bewoelkung_prozent": bewoelkung_h,
            "niederschlag_mm": niederschlag_h,
            "globalstrahlung_wm2": hourly.get("shortwave_radiation", [None] * len(times))[i],
            "gti_wm2": gti,
        }
        alle_stunden.append(stunde)
        if 6 <= h <= 20:
            stunden.append(stunde)
    return alle_stunden, stunden


async def _korrigiertes_gti(
    db, anlage, anlage_id: int, t: str, h: int, gti: float,
    bewoelkung_h, niederschlag_h, code, skalar_fallback: Optional[float],
) -> float:
    """GTI einer Stunde × Korrekturfaktor (Profil vor Skalar) — oder unverändert."""
    klasse_h = klassifiziere_stunde(bewoelkung_h, niederschlag_h, code)
    forecast_datum = date.fromisoformat(t[:10])
    kp = await lookup_korrekturfaktor(
        db,
        anlage_id=anlage_id,
        lat=anlage.latitude,
        lon=anlage.longitude,
        datum=forecast_datum,
        stunde=h,
        klasse=klasse_h,
    )
    faktor_h = kp.faktor if kp is not None else skalar_fallback
    if faktor_h is not None:
        gti = gti * faktor_h
    return gti


def _aktuelle_stunde(alle_stunden: list[dict], now) -> Optional[dict]:
    """Die letzte Stunde bis einschließlich der laufenden — dasselbe Dict, das
    auch in ``stunden`` steht (eine spätere Temperatur-Übernahme wirkt dort mit)."""
    aktuelle_stunde = None
    for s in alle_stunden:
        h = int(s["zeit"].split(":")[0])
        if h <= now.hour:
            aktuelle_stunde = s
    return aktuelle_stunde


def _sonnenstunden(hourly: dict, now) -> _Sonnenstunden:
    """Sonnenscheindauer in Sekunden: Tag, bis jetzt, ab jetzt."""
    # Sonnenstunden: Tagessumme + Ist (bis jetzt) + Rest (ab jetzt)
    # Aktuelle Stunde wird anteilig nach Minuten aufgeteilt (Minuten-Präzision)
    hourly_sunshine = hourly.get("sunshine_duration", [])
    sunshine_s = sum(s for s in hourly_sunshine if s is not None) if hourly_sunshine else None
    sunshine_bisher_s = None
    sunshine_remaining_s = None
    if hourly_sunshine:
        current_h = now.hour
        minute_fraction = now.minute / 60  # Anteil der aktuellen Stunde (0.0–1.0)
        # Vergangene vollständige Stunden
        sunshine_bisher_s = sum(
            s for i, s in enumerate(hourly_sunshine)
            if s is not None and i < current_h
        )
        # Aktuell laufende Stunde anteilig dazu
        if current_h < len(hourly_sunshine) and hourly_sunshine[current_h] is not None:
            sunshine_bisher_s += hourly_sunshine[current_h] * minute_fraction
            sunshine_remaining_s = (
                sum(s for i, s in enumerate(hourly_sunshine)
                    if s is not None and i > current_h)
                + hourly_sunshine[current_h] * (1 - minute_fraction)
            )
        else:
            sunshine_remaining_s = sum(
                s for i, s in enumerate(hourly_sunshine)
                if s is not None and i > current_h
            )
    return _Sonnenstunden(sunshine_s, sunshine_bisher_s, sunshine_remaining_s)


# ── Prognose-Kanon ───────────────────────────────────────────────────────────


async def _kanon_zahlen(db, anlage, profil: list[dict], pv_prognose: Optional[float]) -> _PrognoseZahlen:
    """Tageswert, Rest, rollend, IST aus dem Kanon; die PV-Slots des Profils
    werden dabei **in place** durch die Export-Slots ersetzt."""
    # Defaults, bevor der Kanon-Zweig sie setzt: fehlt der Kanon (kein
    # Profil, kein Netz), bleibt die Antwort bei `None` statt bei 0 —
    # „unbekannt" ist keine Null (ADR-002/P4).
    pv_prognose_rest: Optional[float] = None
    pv_prognose_rollend: Optional[float] = None
    pv_ist_bisher: Optional[float] = None

    # ── Prognose-Kanon: EINE Wahrheit für PV-Tagesprognose + Chart-Slots ──
    # Anzeige-/Persistenz-Wert + die PV-Slots der Chart-Kurve kommen aus dem
    # kanonischen Service (Multi-String-Fan-out + eedc-Korrektur pro Slot),
    # damit „heute" hier identisch ist mit Aussicht/Kurzfrist/Vergleich-eedc/
    # MQTT/persistiertem TZ-Wert. Verbrauchsprofil/Grundlast bleiben aus dem
    # lokalen GTI-Pfad; nur der PV-Anteil wird kanonisch ersetzt.
    from backend.services.prognose_kanon import kanon_tagesprognose
    # skip_jitter: interaktiver User-Request — der 1-30s-Random-Jitter ist
    # nur für Hintergrund-Abrufe gedacht (R18-13).
    kanon = await kanon_tagesprognose(db, anlage, days=4, skip_jitter=True)
    kanon_heute = kanon.tage[0] if (kanon and kanon.tage) else None
    # rapahl-PN 2026-08-23: Der Rest des Tages wird hier ohnehin schon
    # gerechnet (Σ der Prognose-Slots ab jetzt, laufende Stunde anteilig) —
    # er hat den Weg nach draußen bisher nur nicht gefunden. Die Anzeige
    # bildete deshalb „verbleibend" als Tagesprognose minus IST, also aus
    # der Differenz zweier Größen, von denen die eine die Vergangenheit als
    # *Vorhersage* enthält. Genau dieses Verfahren hat der Prognosen-
    # Vergleich mit #296 abgelegt („nicht mehr Tagesprognose − IST").
    if kanon is not None:
        pv_prognose_rest = kanon.rest_heute_kwh
        pv_prognose_rollend = kanon.heute_rollend_kwh
        pv_ist_bisher = kanon.ist_bisher_kwh
    if kanon_heute is not None:
        if kanon_heute.eedc_kwh is not None:
            pv_prognose = kanon_heute.eedc_kwh
        if kanon_heute.profil is not None:
            _export_slots_ins_profil(profil, kanon_heute.profil.stundenprofil_export_kwh)
    return _PrognoseZahlen(kanon_heute, pv_prognose, pv_prognose_rest, pv_prognose_rollend, pv_ist_bisher)


#: N-690 (ADR-002 P4): der Satz, den die Antwort trägt, wenn die eedc-Werte von
#: heute aus einem unvollständigen lokalen Fan-out stammen. Wortlaut wie N77 in
#: ``/solar-prognose`` — der Wert bleibt stehen, er wird nur beschriftet.
TEILSUMME_HINWEIS = (
    "Der Wetterabruf war unvollständig: nicht alle PV-Teilanlagen haben eine "
    "Einstrahlungsprognose geliefert. Die eedc-Werte für heute (Tagesprognose, "
    "PV-Kurve) sind deshalb unvollständig und können zu niedrig sein — bitte "
    "später erneut laden."
)


def _teilsumme_hinweis(multi_gti, multi_vollstaendig: bool, kanon_heute) -> Optional[str]:
    """P4-Hinweis, wenn Tageswert oder PV-Kurve aus einem unvollständigen
    lokalen Fan-out stehen bleiben — sonst ``None``.

    N-690: ``multi_vollstaendig`` wurde bis 11.10.2026 ausgepackt und nie
    gelesen. Der Kanon liefert bei einem Teil-Fan-out seit N-423 keinen
    Tageswert und kein Profil; dann bleibt hier der lokale Wert aus
    ``_berechne_verbrauchsprofil`` stehen — um die ausgefallenen Gruppen zu
    klein. Hat der Kanon beides ersetzt, zeigt die Antwort seine (vollständige)
    Zahl, und es gibt nichts zu sagen. ``multi_gti is None`` heißt: kein lokaler
    Fan-out (Ein-Gruppen-Anlage oder Prefetch-Eintrag ``(data, None, False)``) —
    der lokale Pfad rechnet dann mit der Globalstrahlung, eine Teilsumme ist
    das nicht.
    """
    if multi_vollstaendig or multi_gti is None:
        return None
    kanon_ersetzt = (
        kanon_heute is not None
        and kanon_heute.eedc_kwh is not None
        and kanon_heute.profil is not None
    )
    return None if kanon_ersetzt else TEILSUMME_HINWEIS


def _export_slots_ins_profil(profil: list[dict], export_slots) -> None:
    for p in profil:
        h = int(p["zeit"].split(":")[0])
        if 0 <= h < 24:
            p["pv_ertrag_kw"] = round(export_slots[h], 2)


# ── Außentemperatur ──────────────────────────────────────────────────────────


async def _ha_aussentemperatur(anlage, aktuelle_stunde: Optional[dict]) -> bool:
    """HA-Sensor statt Forecast für die laufende Stunde — ``True``, wenn übernommen."""
    # ── HA-Sensor: Außentemperatur ──
    basis_live = (anlage.sensor_mapping or {}).get("basis", {}).get("live", {})
    temp_entity = basis_live.get("aussentemperatur_c") if basis_live else None
    ha_temp_found = False

    if temp_entity:
        try:
            from backend.services.ha_state_service import get_ha_state_service
            ha_svc = get_ha_state_service()
            ha_batch = await ha_svc.get_sensor_states_batch([temp_entity])
            if ha_batch.get(temp_entity):
                ha_temp = ha_batch[temp_entity][0]
                if aktuelle_stunde is not None:
                    aktuelle_stunde["temperatur_c"] = ha_temp
                    ha_temp_found = True
        except Exception as e:
            logger.debug(f"HA-Sensor Temperatur nicht lesbar: {e}")
    return ha_temp_found


def _mqtt_aussentemperatur(anlage, aktuelle_stunde: Optional[dict], ha_temp_found: bool) -> None:
    """MQTT-Wert für die laufende Stunde, wenn HA keinen geliefert hat."""
    # ── MQTT-Fallback für Außentemperatur (Standalone / HA-Sensor nicht erreichbar) ──
    if not ha_temp_found and aktuelle_stunde is not None:
        try:
            from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
            mqtt_svc = get_mqtt_inbound_service()
            if mqtt_svc and mqtt_svc.cache.has_data(anlage.id):
                mqtt_basis = mqtt_svc.cache.get_live_basis(anlage.id)
                mqtt_temp = mqtt_basis.get("aussentemperatur_c")
                if mqtt_temp is not None:
                    aktuelle_stunde["temperatur_c"] = mqtt_temp
        except Exception:
            pass


# ── Gewählte Quelle: SFML ────────────────────────────────────────────────────


async def _sfml_quelle(pq, profil: list[dict], stand: _QuellenStand) -> None:  # noqa: ARG001
    """SFML-Werte nach ``stand`` — nur bei SFML als Quelle.

    ``profil`` liest diese Phase seit N-761 nicht mehr: die Stundenreihe der Quelle schreibt
    ``_quelle_ins_profil`` erst nach dem Rückfall (``_pq_nach_abruf``), für SFML und Solcast an einer Stelle.
    """
    # ── SFML per Auto-Discovery (wenn als aktive Quelle gewählt) ──
    if not pq.ist_sfml:
        return
    try:
        from backend.services.prognose_discovery import discover_prognose_sensoren
        sfml_disc = await discover_prognose_sensoren("sfml")
        if sfml_disc.gefunden:
            stand.sfml_kwh = sfml_disc.wert("heute_kwh")
            stand.sfml_tomorrow = sfml_disc.wert("morgen_kwh")
            # Burkard (T89667 #276, 2026-08-31): Ohne diese Zeile konnte
            # Übermorgen unter der SFML-Überschrift GAR NICHT aus SFML
            # kommen — der Tageswert wurde nie gelesen, der Block hing
            # für Tag 2 allein am Stundenprofil. Wer keins hat (oder
            # dessen Profil nicht so weit reicht), sah dort immer eedc,
            # obwohl der Sensor danebensteht. Der Vergleichs-Endpoint
            # liest alle drei Rollen seit jeher (`prognosen.py`).
            stand.sfml_uebermorgen = sfml_disc.wert("uebermorgen_kwh")
            stand.sfml_accuracy = sfml_disc.wert("genauigkeit_30d")
            _sfml_stundenprofile(sfml_disc, stand)
    except Exception as e:
        logger.debug(f"SFML-Discovery fehlgeschlagen: {e}")


def _sfml_stundenprofile(sfml_disc, stand: _QuellenStand) -> None:
    from backend.services.prognose_adapter import (
        sfml_stundenprofil_aus_hours,
        sfml_stundenprofile_aus_forecast,
    )
    # Echtes SFML-Stundenprofil bevorzugen (evcc `forecast`,
    # 3 Tage stündlich, Wh). Fallback: `prognose_heute.hours`
    # (24 h, kWh). KEINE GTI-Schmier mehr, solange ein echtes
    # Stundenprofil vorliegt — Einzelquellen-Treue (#110 „A").
    heute_d = date.today()
    forecast_attr = sfml_disc.attribut("stundenprofil")
    if forecast_attr:
        tage = sfml_stundenprofile_aus_forecast(forecast_attr, heute_d)
        if tage and any(v for v in tage[0]):
            stand.sfml_stundenprofil_heute = tage[0]
            stand.quelle_tagesprofile = tage
    if stand.sfml_stundenprofil_heute is None:
        hours_attr = sfml_disc.attribut("heute_kwh")
        if hours_attr:
            kandidat = sfml_stundenprofil_aus_hours(hours_attr)
            if any(v for v in kandidat):
                stand.sfml_stundenprofil_heute = kandidat


def _quelle_ins_profil(profil: list[dict], pq, stand: _QuellenStand) -> None:
    """Heute-Stundenreihe der EFFEKTIVEN Quelle als ``pv_ml_prognose_kw`` ins Profil (N-761, #434).

    ``pq`` ist die Quelle nach dem Rückfall (``_pq_nach_abruf``): bei eedc — gewählt oder zurückgefallen —
    bleibt das Feld leer. SFML trägt wie bisher ``sfml_stundenprofil_heute`` (aus ``stundenprofil`` oder
    ``prognose_heute.hours``), Solcast seine Heute-Slots (``solcast_stundenprofil`` = ``quelle_tagesprofile[0]``).
    Der GTI-Schmier bleibt der Rückfall für SFML ohne Stundenattribut. Ob die Kurve die Reihe zeigt, sagt
    ``prognose_quelle_hat_profil`` (``_rest_der_quelle``) — die Reihe allein ist keine Zusage.
    """
    if not profil or pq.ist_eedc:
        return
    if pq.ist_sfml:
        heute = stand.sfml_stundenprofil_heute
    elif pq.ist_solcast and stand.quelle_tagesprofile:
        heute = stand.quelle_tagesprofile[0]
    else:
        return
    if heute is not None:
        # profil-Eintrag der Uhr-Stunde h trägt Backward-Slot h
        # (wie pv_ertrag_kw, slot_konvention #297) → 1:1-Mapping.
        for p in profil:
            h = int(p["zeit"].split(":")[0])
            if 0 <= h < len(heute):
                p["pv_ml_prognose_kw"] = round(heute[h], 2)
    elif pq.ist_sfml:
        _sfml_gti_schmier(profil, stand)


def _sfml_gti_schmier(profil: list[dict], stand: _QuellenStand) -> None:
    sfml_kwh = stand.sfml_kwh
    if sfml_kwh is not None and sfml_kwh > 0:
        # Fallback (kein Stundenattribut): Tages-kWh über
        # GTI-Kurvenform schmieren — alter Pfad, jetzt geloggt.
        logger.debug(
            "SFML ohne Stundenprofil-Attribut — Fallback auf "
            "GTI-Schmier (Tages-kWh=%s)", sfml_kwh,
        )
        gti_summe = sum(p["pv_ertrag_kw"] for p in profil)
        if gti_summe > 0:
            sfml_factor = sfml_kwh / gti_summe
            for p in profil:
                p["pv_ml_prognose_kw"] = round(p["pv_ertrag_kw"] * sfml_factor, 2)


def _pq_nach_abruf(pq, stand: _QuellenStand):
    """Die effektive Quelle nach den Abrufen von SFML und Solcast.

    Eine Regel für beide Fremdquellen (HANDBUCH_PROGNOSEN §2.3/§2.5, Konzept
    Prognosequellen-Wahl „Fallback bei Sensor-unavailable"): liefert die
    gewählte Quelle für heute keinen Tageswert, gilt die eedc-Prognose — mit
    Hinweis, und die Überschrift folgt ihr. N-696: bis 11.10.2026 gab es den
    Zweig nur für SFML; lieferte Solcast nichts, stand die eedc-Zahl ohne
    Vermerk unter „(Solcast)" (`_pv_prognose_aktiv` fiel still zurück).
    """
    if pq.ist_sfml and stand.sfml_kwh is None:
        name = "SFML"
    elif pq.ist_solcast and stand.solcast_kwh is None:
        name = "Solcast"
    else:
        return pq
    from backend.services.prognose_router import PrognoseQuelleResult
    return PrognoseQuelleResult(
        quelle="eedc", ist_fallback=True,
        hinweis=f"{name} liefert aktuell keine Daten, eedc-Prognose aktiv.",
        gewuenscht=pq.quelle,
    )


# ── Solcast (immer gelesen — Persistenz; Quelle nur bei Wahl) ───────────────


async def _solcast_quelle(anlage, pq, stand: _QuellenStand) -> None:
    """Solcast-Werte nach ``stand`` — bei jeder Quelle (Persistenz)."""
    # Solcast-Prognose (fire-and-forget, parallel zum Response)
    try:
        from backend.services.solcast_service import get_solcast_forecast
        solcast = await get_solcast_forecast(anlage)
        if solcast:
            stand.solcast_kwh = solcast.daily_kwh
            stand.solcast_p10 = solcast.daily_p10_kwh
            stand.solcast_p90 = solcast.daily_p90_kwh
            stand.solcast_tage_voraus = getattr(solcast, "tage_voraus", None)
            if solcast.hourly_kw and len(solcast.hourly_kw) == 24:
                stand.solcast_stundenprofil = list(solcast.hourly_kw)
                if pq.ist_solcast:
                    # Solcast liefert im Live-Pfad nur HEUTE stündlich; die
                    # Folgetage bleiben leer und fallen sichtbar auf den
                    # Kanon zurück (s. `prognose_quelle_tage`).
                    stand.quelle_tagesprofile = [stand.solcast_stundenprofil]
    except Exception as e:
        logger.debug(f"Solcast-Fetch für Persistenz fehlgeschlagen: {e}")


# ── Zahlen der gewählten Quelle ──────────────────────────────────────────────


def _pv_stundenprofil(profil: list[dict]) -> Optional[list[float]]:
    # OpenMeteo-Stundenprofil aus dem berechneten verbrauchsprofil ableiten
    # (24 kW-Werte → kWh; profil hat genau 24 Einträge in Stundenform).
    pv_stundenprofil: list[float] | None = None
    if profil and len(profil) == 24:
        pv_stundenprofil = [round(p.get("pv_ertrag_kw", 0.0) or 0.0, 3) for p in profil]
    return pv_stundenprofil


def _pv_prognose_aktiv(pq, pv_prognose: Optional[float], stand: _QuellenStand) -> Optional[float]:
    # pv_prognose_kwh = Wert der aktiven Quelle (für KPI-Anzeige im Frontend)
    pv_prognose_aktiv = pv_prognose  # Default: EEDC (OpenMeteo × Lernfaktor)
    if pq.ist_solcast and stand.solcast_kwh is not None:
        pv_prognose_aktiv = stand.solcast_kwh
    elif pq.ist_sfml and stand.sfml_kwh is not None:
        pv_prognose_aktiv = stand.sfml_kwh
    return pv_prognose_aktiv


def _rest_der_quelle(pq, stand: _QuellenStand, zahlen: _PrognoseZahlen, now) -> bool:
    """Rest und rollend aus der gewählten Quelle nach ``zahlen`` — liefert, ob
    die Quelle ein Stundenprofil hat."""
    # ── EINE Quelle für alle Prognosezahlen dieses Blocks ────────────────
    # Bis 2026-08-30 kamen Kopfzahl und Nachbarwerte aus VERSCHIEDENEN
    # Rechenwegen: `pv_prognose_aktiv` folgte der gewählten Quelle, `rest`
    # und `rollend` aber immer dem Kanon (der laut eigenem Docstring IMMER
    # eedc rechnet). Auf einer Seite standen damit drei Zahlen, die sich
    # nicht zueinander addieren — gemeldet von Burkard (#401: 6,9 + 9,0 ≠
    # 28,7) und, aus der anderen Richtung, von rapahl (PN 91821: 23,5 kWh
    # erzeugt bei 17,6 kWh „Heute").
    #
    # Entscheid Gernot 2026-08-30: nachgeführt UND konsequent aus der
    # gewählten Quelle. Das IST bleibt Messung (quellenunabhängig), damit
    # gilt wieder `ist_bisher + rest = rollend` — die Bilanz, an der ein
    # Anwender die drei Zahlen nachrechnen kann.
    #
    # ⛔ Der Kanon wird dafür NICHT umgebaut: „Solcast/SFML sind eigene
    # Pfade" ist seine dokumentierte Entwurfsentscheidung. Gerechnet wird
    # mit SEINER Formel (`rest_aus_slots`, #339) auf FREMDEN Slots.
    quelle_tagesprofile = stand.quelle_tagesprofile
    quelle_hat_profil = bool(quelle_tagesprofile and quelle_tagesprofile[0])
    if quelle_hat_profil and not pq.ist_eedc:
        from backend.services.prognose_kanon import rest_aus_slots
        zahlen.rest = rest_aus_slots(quelle_tagesprofile[0], now)
        if zahlen.rest is not None and zahlen.ist_bisher is not None:
            zahlen.rollend = round(zahlen.ist_bisher + zahlen.rest, 1)
        else:
            zahlen.rollend = None
    elif not pq.ist_eedc:
        # Gewählte Quelle ohne Stundenprofil (z. B. SFML mit GTI-Schmier):
        # KEIN Rest. Ihn aus der Kurvenform einer anderen Quelle zu bilden
        # wäre genau die Vermischung, die dieser Block loswerden soll.
        zahlen.rest = None
        zahlen.rollend = None
    # N-761 ⚑2: nach einem Rückfall auf eedc (SFML/Solcast ohne Tageswert) kann ``quelle_tagesprofile`` noch
    # das Profil der gewünschten Quelle tragen — die Marke sagt dann trotzdem nein: Kurve und Rest folgen eedc.
    return quelle_hat_profil and not pq.ist_eedc


def _quelle_tageswert(
    i: int, tag_datum: date, pq, pv_prognose_aktiv: Optional[float],
    sfml_tomorrow: Optional[float], sfml_uebermorgen: Optional[float],
    solcast_tage_voraus: Optional[list],
) -> Optional[float]:
    """Der Tageswert der gewählten Quelle für Tag ``i`` — ``None``, wenn sie keinen liefert."""
    kwh = None
    if i == 0:
        kwh = pv_prognose_aktiv
    elif pq.ist_sfml:
        # Tageswert der Quelle VOR dem Stundenprofil — er ist die
        # Aussage der Quelle selbst; die Profilsumme ist die
        # Ableitung daraus.
        kwh = sfml_tomorrow if i == 1 else sfml_uebermorgen
    elif pq.ist_solcast and solcast_tage_voraus:
        tag_str = tag_datum.isoformat()
        kwh = next(
            (t.get("kwh") for t in solcast_tage_voraus
             if t.get("datum") == tag_str),
            None,
        )
    return kwh


def _prognose_quelle_tage(
    pq, anlage, stand: _QuellenStand, pv_prognose_aktiv: Optional[float],
) -> Optional[list[dict]]:
    # Tageszahlen der gewählten Quelle je Tag — mit VM/NM aus IHREM Profil
    # und ausgewiesenem Rückfall, wo sie nicht so weit reicht.
    prognose_quelle_tage: list[dict] | None = None
    if not pq.ist_eedc:
        from backend.services.prognose_kanon import vm_nm_split
        quelle_tagesprofile = stand.quelle_tagesprofile
        prognose_quelle_tage = []
        for i in range(3):
            tag_datum = date.today() + timedelta(days=i)
            slots = (quelle_tagesprofile[i]
                     if quelle_tagesprofile and i < len(quelle_tagesprofile)
                     else None)
            kwh = _quelle_tageswert(
                i, tag_datum, pq, pv_prognose_aktiv,
                stand.sfml_tomorrow, stand.sfml_uebermorgen, stand.solcast_tage_voraus,
            )
            if kwh is None and slots:
                kwh = round(sum(slots), 1)
            vm = nm = None
            if slots:
                vm, nm = vm_nm_split(slots, tag_datum.isoformat(), anlage.longitude)
            prognose_quelle_tage.append({
                "datum": tag_datum.isoformat(),
                "kwh": kwh,
                "vm_kwh": vm,
                "nm_kwh": nm,
                # Was die gewählte Quelle nicht liefert, sagt es — statt
                # still eine eedc-Zahl unter ihrer Überschrift zu zeigen.
                "rueckfall": None if kwh is not None else "eedc",
                # N-695: dieselbe Regel je TEILWERT. Hat die Quelle für den Tag
                # kein Stundenprofil (Solcast im Live-Pfad nur heute, SFML ohne
                # `forecast`-Attribut an keinem Tag), zeigt die Kachel VM/NM aus
                # dem eedc-Kanon — neben der Tageszahl der Quelle, die Teile
                # addieren sich dann nicht zu ihr (#401). HANDBUCH_PROGNOSEN
                # §2.3: eine Näherung bleibt stehen und wird dazugesagt.
                "vm_nm_rueckfall": None if vm is not None else "eedc",
            })
    return prognose_quelle_tage


# ── Persistenz (der Aufruf selbst steht im Orchestrator) ─────────────────────


def _persistenz_auftrag(
    anlage, now, kanon_heute, pv_stundenprofil: Optional[list], stand: _QuellenStand,
) -> Optional[_PersistenzAuftrag]:
    """Was `_speichere_prognose` bekommt — ``None``, wenn es nichts zu speichern gibt."""
    # Prognose für Lernfaktor-Berechnung + SFML + Solcast speichern (fire-and-forget).
    # #306: Den OpenMeteo-Tageswert NICHT einfrieren, wenn der Multi-String-
    # Fan-out unvollständig war — sonst klebt ein kollabierter Solo-String/
    # BKW-Wert als Tagesprognose und verzerrt das Genauigkeits-Tracking +
    # den Lernfaktor. Vollständigkeit kommt jetzt aus dem Kanon-Fan-out
    # (om_vollstaendig); kein Kanon (kein PV/Koordinaten) → nichts einfrieren.
    om_unvollstaendig = kanon_heute is None or not kanon_heute.om_vollstaendig
    # ⭐ **N-547/W1: hier stand bis 22.09.2026 `pv_prognose`** — und das ist
    # seit dem Kanon-Zweig oben (`:1315`) `kanon_heute.eedc_kwh`, also der
    # **korrigierte und gekappte** Tageswert. Der Prefetch schrieb in
    # dasselbe Feld alle 45 Minuten die **rohe, ungekappte** Σ der
    # OM-String-Tageswerte. Gleiche Provenance-Quelle, „letzter gewinnt":
    # `pv_prognose_kwh` trug je nach Tageszeit zwei verschiedene Größen,
    # und seine drei Leser (Genauigkeits-Tracking `prognosen.py:970-998`,
    # HA-Export-Schwelle `prognose_genauigkeit_service.py:69-74`,
    # Energieprofil-Tages-SOLL `energie_profil/tag.py:135-144`)
    # multiplizieren es ausnahmslos mit dem Legacy-Lernfaktor — sie
    # erwarten also die rohe Lage. Seit N-547 schreiben beide sie.
    roh_tageswert = kanon_heute.roh_kwh if kanon_heute is not None else None
    om_prognose = (
        None if (om_unvollstaendig or roh_tageswert is None or roh_tageswert <= 0)
        else roh_tageswert
    )
    # Das OpenMeteo-Stundenprofil stammt aus demselben (kollabierten) Profil —
    # bei Unvollständigkeit ebenfalls nicht einfrieren (first-write-wins).
    om_stundenprofil = None if om_unvollstaendig else pv_stundenprofil
    # N-547: das Lern-SOLL — die gekappte, UNkorrigierte Rohreihe und ihre
    # Summe. Ohne Kanon-Stundenprofil (OpenMeteo-Schätzpfad ohne Hourly)
    # gibt es keins; dann bleiben die Felder NULL, statt eine Reihe zu
    # erfinden. #306 gilt hier genauso: unvollständiger Fan-out ⇒ nichts
    # einfrieren, auch kein Lern-SOLL.
    # ⛔ **Beide Felder hängen am Stundenprofil, auch das Tages-SOLL.** Im
    # OpenMeteo-Schätzpfad (Tagessumme ohne Hourly, `prognose_kanon::_korrigierter_tag`, `else`-Zweig)
    # ist `om_kwh` die **ungekappte** Σ der Tageswerte — die Kappung wirkt
    # nur auf Stundenwerte. Als `lern_soll_kwh` wäre das auf einer Anlage
    # mit AC-Grenze eine Zahl, die die Anlage nie erreichen kann, und der
    # Skalar lernte den Deckel als Prognosefehler ein. Lieber NULL.
    hat_lern_reihe = (
        not om_unvollstaendig and kanon_heute.om_stundenprofil_kwh is not None
    )
    lern_stundenprofil = (
        kanon_heute.om_stundenprofil_kwh if hat_lern_reihe else None
    )
    lern_kwh = kanon_heute.om_kwh if hat_lern_reihe else None
    # §6: nach Sonnenuntergang ist der OM-Tageswert konvergiert → der
    # Genauigkeits-Endwert darf eingefroren werden (Anzeige bleibt rollend).
    from backend.services.solar_forecast_service import sonnenauf_unter_stunde
    try:
        _, _sunset_h = sonnenauf_unter_stunde(
            date.today().isoformat(), anlage.latitude, anlage.longitude
        )
        pv_final_sonne_unter = now.hour >= _sunset_h
    except Exception:
        pv_final_sonne_unter = False
    if (om_prognose is not None or stand.solcast_kwh is not None
            or stand.sfml_kwh is not None or stand.sfml_stundenprofil_heute is not None
            or lern_kwh is not None):
        return _PersistenzAuftrag(
            om_prognose, om_stundenprofil, pv_final_sonne_unter, lern_stundenprofil, lern_kwh,
        )
    return None


# ── Antwort ──────────────────────────────────────────────────────────────────


def _antwort(
    anlage, stunden: list[dict], aktuelle_stunde: Optional[dict], daily: dict,
    sonne: _Sonnenstunden, zahlen: _PrognoseZahlen, pv_prognose_aktiv: Optional[float],
    grundlast: Optional[float], profil: list[dict], wahl, ist_ind: bool, pq,
    prognose_quelle_tage: Optional[list[dict]], quelle_hat_profil: bool, stand: _QuellenStand,
    teilsumme_hinweis: Optional[str] = None,
) -> dict:
    sunshine_s, sunshine_bisher_s, sunshine_remaining_s = sonne.gesamt_s, sonne.bisher_s, sonne.rest_s
    sfml_kwh, sfml_tomorrow, sfml_accuracy = stand.sfml_kwh, stand.sfml_tomorrow, stand.sfml_accuracy
    # Die Stundenreihe der effektiven Quelle (nach dem Rückfall) — erst hier, weil ``pq`` erst jetzt feststeht.
    _quelle_ins_profil(profil, pq, stand)
    return {
        "anlage_id": anlage.id,
        "verfuegbar": len(stunden) > 0,
        "aktuell": aktuelle_stunde,
        "stunden": stunden,
        "temperatur_min_c": (daily.get("temperature_2m_min", [None]) or [None])[0],
        "temperatur_max_c": (daily.get("temperature_2m_max", [None]) or [None])[0],
        "sonnenstunden": round(sunshine_s / 3600, 1) if sunshine_s is not None else None,
        "sonnenstunden_bisher": round(sunshine_bisher_s / 3600, 1) if sunshine_bisher_s is not None else None,
        "sonnenstunden_rest": round(sunshine_remaining_s / 3600, 1) if sunshine_remaining_s is not None else None,
        "pv_prognose_kwh": pv_prognose_aktiv,
        # Der GEMESSENE Rest (Σ Prognose-Slots ab jetzt) — nicht die
        # Differenz zur Tagesprognose. Analog zu `sonnenstunden_rest`, das
        # es hier längst gibt. Seit 2026-08-30 aus der GEWÄHLTEN Quelle
        # (vorher immer aus dem eedc-Kanon, auch bei Solcast/SFML).
        "pv_prognose_rest_kwh": zahlen.rest,
        # IST bisher + Rest: die nachgeführte Tageszahl, seit 2026-08-30
        # aus derselben Quelle wie der Rest. `pv_prognose_kwh` bleibt
        # daneben stehen — es ist die ursprüngliche Tagesprognose, an der
        # morgens geplant und abends bewertet wird. Der Block zeigt seither
        # die nachgeführte Zahl oben und diese klein daneben.
        "pv_prognose_heute_rollend_kwh": zahlen.rollend,
        "pv_ist_bisher_kwh": zahlen.ist_bisher,
        # N-690 (P4): stammen Tageswert/PV-Kurve aus einem unvollständigen
        # lokalen Fan-out, sagt die Antwort es selbst (s. `_teilsumme_hinweis`).
        "pv_prognose_hinweis": teilsumme_hinweis,
        "grundlast_kw": grundlast,
        "verbrauchsprofil": profil,
        "profil_typ": wahl.profil_typ if ist_ind else "bdew_h0",
        # `wahl.quelle` statt der frueheren lokalen `ind_profil_data` — die
        # ist mit #395 in `waehle_verbrauchsprofil` gewandert (s. dort).
        "profil_quelle": wahl.quelle if ist_ind else None,
        "profil_tage": wahl.profil_tage,
        "profil_slots": wahl.profil_slots,
        "prognose_quelle": pq.quelle,
        "prognose_quelle_hinweis": pq.hinweis,
        # Tageszahlen der GEWÄHLTEN Quelle (None bei eedc — dann gilt der
        # Kanon, den `prognose3Tage` ohnehin liefert). Je Tag: kwh · vm_kwh
        # · nm_kwh · rueckfall. `rueckfall="eedc"` heißt: so weit reicht die
        # gewählte Quelle nicht, die Anzeige sagt es.
        "prognose_quelle_tage": prognose_quelle_tage,
        # Konnte für die gewählte Quelle ein Rest gebildet werden? False =
        # sie hat kein Stundenprofil (dann steht KEIN Rest da, statt eines
        # aus fremder Kurvenform geschätzten).
        "prognose_quelle_hat_profil": quelle_hat_profil,
        "sfml_prognose_kwh": round(sfml_kwh, 1) if sfml_kwh is not None else None,
        "sfml_tomorrow_kwh": round(sfml_tomorrow, 1) if sfml_tomorrow is not None else None,
        "sfml_accuracy_pct": round(sfml_accuracy, 1) if sfml_accuracy is not None else None,
        "solar_noon": _format_solar_noon(anlage.longitude),
        "sunrise": _extract_time(daily.get("sunrise", [None])),
        "sunset": _extract_time(daily.get("sunset", [None])),
    }
