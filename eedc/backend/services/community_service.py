"""
EEDC Community Service

Bereitet Anlagendaten für die anonyme Übertragung an den Community-Server vor.
"""

import hashlib
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition
from backend.core.berechnungen import PV_ERZEUGER_TYPEN
from backend.core.config import settings
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.services.pv_orientation import get_pv_neigung
from backend.core.investition_parameter import (
    PARAM_WALLBOX,
    PARAM_BALKONKRAFTWERK,
    PARAM_WAERMEPUMPE,
)
from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.services.plz_to_state import PLZ_TO_STATE


# Community Server URL
COMMUNITY_SERVER_URL = "https://energy.raunet.eu"


def get_region_from_plz(plz: str | None, land: str | None = None) -> str | None:
    """
    Ermittelt die Region aus PLZ und Land.
    Für AT und CH wird direkt das Länderkürzel zurückgegeben.
    Für DE wird das Bundesland-Kürzel aus der PLZ ermittelt.
    """
    # AT/CH/IT direkt zurückgeben — keine PLZ-Auflösung nötig
    if land in ("AT", "CH", "IT"):
        return land

    if not plz:
        return None

    # Exakte PLZ-Zuordnung aus vollständiger PLZ-Tabelle
    return PLZ_TO_STATE.get(plz)


def generate_anlage_hash(anlage: Anlage, secret: str) -> str:
    """
    Generiert einen eindeutigen aber anonymen Hash für eine Anlage.
    """
    raw = f"{anlage.leistung_kwp:.1f}:{anlage.installationsdatum}:{anlage.standort_plz[:2] if anlage.standort_plz else 'XX'}:{secret}"
    return hashlib.sha256(raw.encode()).hexdigest()


# Mapping: Ausrichtungs-Text → Kompass-Azimut (0=Nord, 90=Ost, 180=Süd, 270=West)
_AUSRICHTUNG_ZU_KOMPASS = {
    "süd": 180, "south": 180, "s": 180,
    "südost": 135, "southeast": 135, "so": 135,
    "ost": 90, "east": 90, "o": 90,
    "nordost": 45, "northeast": 45, "no": 45,
    "nord": 0, "north": 0, "n": 0,
    "nordwest": 315, "northwest": 315, "nw": 315,
    "west": 270, "w": 270,
    "südwest": 225, "southwest": 225, "sw": 225,
    "ost-west": 180,  # Sonderfall: wird als "gemischt" behandelt
}


def _ausrichtung_roh(inv) -> str:
    """Ausrichtungs-String einer Investition: Spalte → ``parameter`` → ``""``.

    Kleingeschrieben zurückgegeben, damit die Aufrufer nicht jeder für sich
    `.lower()` rufen (und einer es vergisst). Der `parameter`-Zweig ist für das
    Balkonkraftwerk nötig: ``PARAM_BALKONKRAFTWERK["AUSRICHTUNG"]`` schreibt
    dorthin, das Formular zusätzlich in die Spalte — bei Import und Altbestand
    kann also nur das JSON gefüllt sein (dieselbe #229-Lage wie bei der kWp).

    Bewusst **kein** ``get_pv_azimut``: der arbeitet in der PVGIS-Konvention
    (0 = Süd), die Community-Payload in der Kompass-Konvention (180 = Süd).
    Die beiden zu mischen wäre genau die Vokabular-Drift, gegen die
    ``project_backend_client_vokabular`` geschrieben ist.
    """
    direkt = getattr(inv, "ausrichtung", None)
    if isinstance(direkt, str) and direkt.strip():
        return direkt.strip().lower()
    param = (getattr(inv, "parameter", None) or {}).get("ausrichtung")
    if isinstance(param, str) and param.strip():
        return param.strip().lower()
    return ""


def _ausrichtung_zu_kompass(ausrichtung: str | None) -> int:
    """Konvertiert Ausrichtungs-Text in Kompass-Azimut (0=Nord, 180=Süd)."""
    if not ausrichtung:
        return 180  # Default: Süd
    return _AUSRICHTUNG_ZU_KOMPASS.get(ausrichtung.lower(), 180)


def get_ausrichtung_label(azimut: int | None) -> str:
    """Konvertiert Azimut-Winkel in Ausrichtungs-Label."""
    if azimut is None:
        return "unbekannt"

    # Normalisiere auf 0-360
    azimut = azimut % 360

    if 337.5 <= azimut or azimut < 22.5:
        return "nord"
    elif 22.5 <= azimut < 67.5:
        return "nord-ost"
    elif 67.5 <= azimut < 112.5:
        return "ost"
    elif 112.5 <= azimut < 157.5:
        return "süd-ost"
    elif 157.5 <= azimut < 202.5:
        return "süd"
    elif 202.5 <= azimut < 247.5:
        return "süd-west"
    elif 247.5 <= azimut < 292.5:
        return "west"
    elif 292.5 <= azimut < 337.5:
        return "nord-west"

    return "gemischt"


async def prepare_community_data(
    db: AsyncSession,
    anlage_id: int,
    include_monatswerte: bool = True,
) -> dict | None:
    """
    Bereitet die Anlagendaten für die Community-Übertragung vor.

    Returns:
        dict mit anonymisierten Daten oder None wenn Anlage nicht gefunden
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        return None

    # Region aus Land + PLZ ermitteln
    region = get_region_from_plz(anlage.standort_plz, getattr(anlage, 'standort_land', None))
    if not region:
        region = "XX"  # Unbekannt

    # Investitionen laden für Ausstattung
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    # Ausstattung ermitteln (Typ-Namen aus InvestitionTyp Enum)
    hat_speicher = any(inv.typ == "speicher" for inv in investitionen)
    hat_waermepumpe = any(inv.typ == "waermepumpe" for inv in investitionen)
    hat_eauto = any(inv.typ == "e-auto" for inv in investitionen)
    hat_wallbox = any(inv.typ == "wallbox" for inv in investitionen)
    hat_balkonkraftwerk = any(inv.typ == "balkonkraftwerk" for inv in investitionen)
    hat_sonstiges = any(inv.typ == "sonstiges" for inv in investitionen)

    # Speicherkapazität summieren
    speicher_kwh = sum(
        get_speicher_kapazitaet_kwh(inv) or 0
        for inv in investitionen
        if inv.typ == "speicher"
    )

    # Wallbox Ladeleistung — Bug #6 v3.25.0: vorher 'ladeleistung_kw' (toter Key,
    # weder Form noch Wizard noch Schema → Community-Datensatz lieferte immer wallbox_kw=None).
    wallbox_kw = None
    wallboxen = [inv for inv in investitionen if inv.typ == "wallbox"]
    if wallboxen:
        wallbox_kw = max(
            (inv.parameter or {}).get(PARAM_WALLBOX["MAX_LADELEISTUNG_KW"], 0) or 0
            for inv in wallboxen
        )
        if wallbox_kw == 0:
            wallbox_kw = None

    # Balkonkraftwerk Leistung (Wp pro Modul × Anzahl Module)
    bkw_wp = None
    bkws = [inv for inv in investitionen if inv.typ == "balkonkraftwerk"]
    if bkws:
        bkw_wp = sum(
            ((inv.parameter or {}).get(PARAM_BALKONKRAFTWERK["LEISTUNG_WP"], 0) or 0)
            * ((inv.parameter or {}).get(PARAM_BALKONKRAFTWERK["ANZAHL"], 1) or 1)
            for inv in bkws
        )
        if bkw_wp == 0:
            bkw_wp = None

    # Sonstiges Bezeichnung
    sonstiges_bezeichnung = None
    sonstige = [inv for inv in investitionen if inv.typ == "sonstiges"]
    if sonstige:
        bezeichnungen = [inv.bezeichnung for inv in sonstige if inv.bezeichnung]
        sonstiges_bezeichnung = ", ".join(bezeichnungen[:3]) if bezeichnungen else None

    # Durchschnittliche Neigung und Ausrichtung aus den PV-ERZEUGERN (F-10).
    #
    # Bis 2026-08-07 filterte diese Zeile hart auf `pv-module`. Eine reine
    # Balkonkraftwerk-Anlage fiel damit in den `else`-Zweig unten und meldete dem
    # Community-Server **erfundene** Stammdaten: 30° Neigung und Ausrichtung
    # „süd" — obwohl das BKW beides als eigenes Formularfeld trägt. Der Server
    # rechnet nichts nach (er hat die Rohdaten nie gesehen), also wurde die
    # Anlage still gegen die falsche Vergleichsgruppe gemessen. Von allen
    # F-10-Stellen die einzige, deren falscher Wert das Haus verlässt.
    pv_module = [inv for inv in investitionen if inv.typ in PV_ERZEUGER_TYPEN]
    if pv_module:
        # Über den SoT-Helper (Spalte → `parameter`): beim BKW kann die Neigung
        # aus Import/Altbestand nur im `parameter`-JSON stehen, dann lieferte der
        # Spalten-Direktzugriff still die 30°-Annahme statt des gepflegten Werts.
        neigungen = [get_pv_neigung(inv, default=30) for inv in pv_module]
        neigung_grad = int(sum(neigungen) / len(neigungen))

        # Sonderfall: Einzelner Erzeuger mit "Ost-West" → direkt übernehmen.
        # Gilt für das BKW genauso: es kennt „Ost-West (gemischt)" als Option.
        if len(pv_module) == 1 and _ausrichtung_roh(pv_module[0]) == "ost-west":
            ausrichtung = "ost-west"
        else:
            azimute = [_ausrichtung_zu_kompass(_ausrichtung_roh(inv)) for inv in pv_module]
            # Prüfen ob gemischt (z.B. Ost-West)
            if max(azimute) - min(azimute) > 45:
                ausrichtung = "ost-west" if any(60 <= a <= 120 for a in azimute) and any(240 <= a <= 300 for a in azimute) else "gemischt"
            else:
                ausrichtung = get_ausrichtung_label(int(sum(azimute) / len(azimute)))
    else:
        neigung_grad = 30
        ausrichtung = "süd"

    # Installation Jahr
    if anlage.installationsdatum:
        installation_jahr = anlage.installationsdatum.year
    else:
        installation_jahr = datetime.now().year

    # Wärmepumpenart ermitteln (für fairen Community-JAZ-Vergleich)
    wp_art = None
    if hat_waermepumpe:
        wps = [inv for inv in investitionen if inv.typ == "waermepumpe"]
        if wps:
            wp_art = (wps[0].parameter or {}).get(PARAM_WAERMEPUMPE["WP_ART"])

    # Basis-Daten
    data = {
        "region": region,
        "kwp": round(anlage.leistung_kwp or 0, 1),
        "ausrichtung": ausrichtung,
        "neigung_grad": neigung_grad,
        "speicher_kwh": round(speicher_kwh, 1) if speicher_kwh > 0 else None,
        "installation_jahr": installation_jahr,
        "hat_waermepumpe": hat_waermepumpe,
        "hat_eauto": hat_eauto,
        "hat_wallbox": hat_wallbox,
        "hat_balkonkraftwerk": hat_balkonkraftwerk,
        "hat_sonstiges": hat_sonstiges,
        "wp_art": wp_art,
        "wallbox_kw": wallbox_kw,
        "bkw_wp": bkw_wp,
        "sonstiges_bezeichnung": sonstiges_bezeichnung,
        "monatswerte": [],
        # N18-2: Der Payload enthält ALLE teilbaren Monate (Voll-Submit) — der
        # Server darf serverseitig vorhandene Monate, die hier fehlen (Monat
        # gelöscht bzw. vom PV-0-Filter aussortiert), rückwirkend löschen.
        # Alt-Server ignorieren das Feld folgenlos.
        "monate_vollstaendig": bool(include_monatswerte),
    }

    # Monatswerte aus den Monats-Fakten (ADR-002/P10, S6 des Bauplans).
    # Vorher faltete diese Sicht die `InvestitionMonatsdaten` selbst — und
    # verlor dabei drei Achsen: die P7-Auflösung der PV (eine Anlage, die ihre
    # Erzeugung als Anlagen-Aggregat statt je Modul pflegt, konnte GAR NICHTS
    # teilen — `monatswerte` blieb leer und `/community/share` brach mit HTTP
    # 400 ab), den Erzeuger hinter dem Zähler + V2H in der Autarkie (F-1) und
    # den Dienstwagen-Filter.
    if include_monatswerte:
        for fakt in await lade_monats_fakten(db, anlage_id):
            monatswert_data = _monatswert(fakt)
            if monatswert_data is not None:
                data["monatswerte"].append(monatswert_data)

    return data


def _monatswert(fakt: MonatsFakt) -> dict | None:
    """Ein Community-Monatswert aus einem ``MonatsFakt`` — oder ``None``.

    Zwei Filter, beide aus dem Bestand übernommen und bewusst beibehalten:

    - **ohne Zählerzeile nichts** — Einspeisung und Netzbezug wären 0 und die
      Autarkie damit eine Behauptung ohne Messung (P4). Die alte Fassung lief
      über die ``Monatsdaten``-Zeilen und hatte den Filter dadurch implizit.
    - **ohne PV nichts** — der Benchmark vergleicht PV-Anlagen. Ein Monat vor
      der Inbetriebnahme (oder eine reine BHKW-Anlage) gehört nicht hinein.
    """
    if not fakt.meta.hat_zaehlerzeile:
        return None

    # Die PV-Achse des Benchmarks: Module (P7-aufgelöst) + BKW — NICHT
    # `hinter_zaehler_kwh`. Der Server rechnet daraus den spezifischen Ertrag
    # je kWp; ein BHKW dort hineinzurechnen würde die Kennzahl verfälschen.
    pv_erzeugung = fakt.erzeugung.pv_kwh
    if pv_erzeugung <= 0:
        return None

    einspeisung = fakt.zaehler.einspeisung_kwh
    netzbezug = fakt.zaehler.netzbezug_kwh

    # #294: kanonische SoT-Formel (inkl. Speicher), deckungsgleich mit
    # Cockpit/HA-Export. Seit S6 kommt sie aus der Schicht und trägt damit
    # zusätzlich V2H und den Erzeuger hinter dem Zähler (F-1) — die
    # Bezugsgröße ist `erzeugung_hinter_zaehler_kwh`, nicht `pv_kwh`: an EINEM
    # Netzanschluss messen die Zähler die Summe aller Erzeuger dahinter.
    kennzahlen = fakt.kennzahlen
    autarkie = (
        kennzahlen.autarkie_prozent if kennzahlen.gesamtverbrauch_kwh > 0 else None
    )
    ev_quote = kennzahlen.eigenverbrauchsquote_prozent

    monatswert_data = {
        "jahr": fakt.jahr,
        "monat": fakt.monat,
        "ertrag_kwh": round(pv_erzeugung, 1),
        "einspeisung_kwh": round(einspeisung, 1) if einspeisung else None,
        "netzbezug_kwh": round(netzbezug, 1) if netzbezug else None,
        "autarkie_prozent": round(autarkie, 1) if autarkie is not None else None,
        "eigenverbrauch_prozent": round(ev_quote, 1) if ev_quote is not None else None,
    }

    speicher = fakt.speicher
    if speicher.ladung_kwh > 0 or speicher.entladung_kwh > 0:
        monatswert_data["speicher_ladung_kwh"] = round(speicher.ladung_kwh, 1)
        monatswert_data["speicher_entladung_kwh"] = round(speicher.entladung_kwh, 1)
        if speicher.netzladung_kwh > 0:
            monatswert_data["speicher_ladung_netz_kwh"] = round(speicher.netzladung_kwh, 1)

    wp = fakt.wp
    if wp.strom_kwh > 0:
        monatswert_data["wp_stromverbrauch_kwh"] = round(wp.strom_kwh, 1)
        if wp.heizung_kwh > 0:
            monatswert_data["wp_heizwaerme_kwh"] = round(wp.heizung_kwh, 1)
        if wp.warmwasser_kwh > 0:
            monatswert_data["wp_warmwasser_kwh"] = round(wp.warmwasser_kwh, 1)

    # E-Auto und Wallbox bleiben GETRENNT (der Server führt beide Felder) —
    # deshalb die Quellen-Summen der Schicht statt des Heimladungs-Pools, der
    # genau eine der beiden Quellen wählt. Beide sind dienstwagen- und
    # laufzeitgefiltert; ein dienstlich gefahrenes Fahrzeug ist keine Aussage
    # über diese Anlage. [[feedback_dienstwagen_alle_checks]]
    #
    # ⚠ **Die `*_gemessen`-Variante, und zwar als einzige Sicht (F-16).** Seit
    # der PV-Anteil der Heimladung aus der Tagesebene abgeleitet wird, tragen
    # `eauto_summe`/`wallbox_summe` eine Schätzung. Der Server hat die Rohdaten
    # nie gesehen und rechnet nichts nach — eine Schätzung wäre dort in einem
    # Benchmark nicht mehr als solche erkennbar, und der Anlagen-Hash bewegte
    # sich ohne neue Messung. Der Payload trägt Messwerte, keine Bewertung
    # (dieselbe Linie wie beim BKW-Eigenverbrauch weiter unten).
    emob = fakt.emob
    eauto = emob.eauto_summe_gemessen
    eauto_ladung_gesamt = eauto.ladung_kwh + eauto.extern_kwh
    if eauto_ladung_gesamt > 0:
        monatswert_data["eauto_ladung_gesamt_kwh"] = round(eauto_ladung_gesamt, 1)
        if eauto.pv_kwh > 0:
            monatswert_data["eauto_ladung_pv_kwh"] = round(eauto.pv_kwh, 1)
        if eauto.extern_kwh > 0:
            monatswert_data["eauto_ladung_extern_kwh"] = round(eauto.extern_kwh, 1)
        if emob.km > 0:
            monatswert_data["eauto_km"] = round(emob.km, 1)
        if emob.v2h_entladung_kwh > 0:
            monatswert_data["eauto_v2h_kwh"] = round(emob.v2h_entladung_kwh, 1)

    wallbox = emob.wallbox_summe_gemessen
    if wallbox.ladung_kwh > 0:
        monatswert_data["wallbox_ladung_kwh"] = round(wallbox.ladung_kwh, 1)
        if wallbox.pv_kwh > 0:
            monatswert_data["wallbox_ladung_pv_kwh"] = round(wallbox.pv_kwh, 1)
        if wallbox.ladevorgaenge > 0:
            monatswert_data["wallbox_ladevorgaenge"] = int(wallbox.ladevorgaenge)

    # BKW: der GEMESSENE Eigenverbrauch, nicht der aus der Hausbilanz
    # abgeleitete Anteil (S5). Der Payload trägt Messwerte, keine Bewertung.
    bkw = fakt.bkw
    if bkw.erzeugung_kwh > 0:
        monatswert_data["bkw_erzeugung_kwh"] = round(bkw.erzeugung_kwh, 1)
        if bkw.eigenverbrauch_gemessen_kwh > 0:
            monatswert_data["bkw_eigenverbrauch_kwh"] = round(bkw.eigenverbrauch_gemessen_kwh, 1)
        if bkw.speicher_ladung_kwh > 0:
            monatswert_data["bkw_speicher_ladung_kwh"] = round(bkw.speicher_ladung_kwh, 1)
        if bkw.speicher_entladung_kwh > 0:
            monatswert_data["bkw_speicher_entladung_kwh"] = round(bkw.speicher_entladung_kwh, 1)

    if fakt.sonstiges.verbrauch_kwh > 0:
        monatswert_data["sonstiges_verbrauch_kwh"] = round(fakt.sonstiges.verbrauch_kwh, 1)

    return monatswert_data


async def get_community_preview(db: AsyncSession, anlage_id: int) -> dict | None:
    """
    Gibt eine Vorschau der zu teilenden Daten zurück.
    """
    data = await prepare_community_data(db, anlage_id)
    if not data:
        return None

    return {
        "vorschau": data,
        "anzahl_monate": len(data.get("monatswerte", [])),
        "community_url": COMMUNITY_SERVER_URL,
    }
