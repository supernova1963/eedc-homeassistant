"""
EEDC Community Service

Bereitet Anlagendaten für die anonyme Übertragung an den Community-Server vor.
"""

from datetime import date, datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition
from backend.core.berechnungen import (
    PV_ERZEUGER_TYPEN,
    bkw_kwp_aus_kindern,
    erzeuger_traeger,
)
from backend.core.config import settings
from backend.core.investition_kennwerte import get_speicher_kapazitaet_kwh
from backend.services.pv_orientation import get_pv_neigung
from backend.core.investition_parameter import (
    PARAM_WALLBOX,
    PARAM_BALKONKRAFTWERK,
    PARAM_WAERMEPUMPE,
)
from typing import Mapping, Sequence

from backend.core.berechnungen.waermepumpe_kennzahl import abgrenzungs_grund
from backend.services.monats_fakten import MonatsFakt, lade_monats_fakten
from backend.services.monats_co2 import co2_bilanz_aus_fakt
from backend.services.pvgis_soll import (
    SollQuelle,
    lade_erzeuger,
    lade_soll_quelle,
    soll_fuer_monat,
)
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

    # Speicherkapazität summieren — NUR die heute vorhandenen Geräte (F-24).
    #
    # Der Datensatz beschreibt die **aktuelle Ausstattung** der Anlage; der
    # Server rechnet nichts nach. Ohne den Stilllegungs-Filter meldete jede
    # Anlage nach einem Speicher-Tausch oder einer Erweiterung nach dem
    # Zwei-Datensatz-Weg die **Summe aus altem und neuem** Gerät — an einer
    # Kopie des Dev-Bestands gemessen (11.08.2026): 15,4 kWh + 30,8 kWh =
    # **46,2 kWh** statt 30,8. Damit stand die Anlage im öffentlichen
    # Benchmark mit einer Ausstattung, die es nie gab, und verzerrte die
    # Größenklassen für alle anderen mit.
    #
    # `ist_aktiv_an(heute)` statt `aktiv`: Wer ein Gerät ersetzt, setzt das
    # **Stilllegungsdatum** — den `aktiv`-Haken zu entfernen würde es auch aus
    # der Historie nehmen (`models/investition.py::ist_aktiv_an`).
    heute_ = date.today()
    speicher_kwh = sum(
        get_speicher_kapazitaet_kwh(inv) or 0
        for inv in investitionen
        if inv.typ == "speicher" and inv.ist_aktiv_an(heute_)
    )

    # Wallbox Ladeleistung — Bug #6 v3.25.0: vorher 'ladeleistung_kw' (toter Key,
    # weder Form noch Wizard noch Schema → Community-Datensatz lieferte immer wallbox_kw=None).
    #
    # N-617: nur die heute vorhandenen Wallboxen — dieselbe Regel wie der
    # Speicher darüber (F-24). Bis 04.10.2026 lief das Maximum über jede je
    # erfasste: nach einem Tausch 22 kW → 11 kW stand im Benchmark 22 kW, auch
    # wenn die alte Box stillgelegt oder deaktiviert war (gemessen über
    # `prepare_community_data`).
    wallbox_kw = None
    wallboxen = [inv for inv in investitionen if inv.typ == "wallbox" and inv.ist_aktiv_an(heute_)]
    if wallboxen:
        wallbox_kw = max(
            (inv.parameter or {}).get(PARAM_WALLBOX["MAX_LADELEISTUNG_KW"], 0) or 0
            for inv in wallboxen
        )
        if wallbox_kw == 0:
            wallbox_kw = None

    # Balkonkraftwerk Leistung (Wp pro Modul × Anzahl Module)
    #
    # ⚠ **N-266, Handarbeit-Stelle 1 von 2.** Diese Zeile liest das
    # `parameter`-JSON **roh** und erreicht `get_bkw_kwp` von sich aus nie — die
    # Ableitung aus den Modul-Kindern (E5) kommt hier also nicht an. Sie wird
    # deshalb hier ausdrücklich nachgezogen: hängen `pv-module` am BKW, ist
    # deren Σ kWp seine Leistung, und die eigene Pflege ist Altbestand aus der
    # Zeit vor der Zuordnung. Das ist die einzige N-266-Stelle, deren Zahl das
    # Haus verlässt — sie bestimmt im öffentlichen Benchmark die
    # Vergleichsgruppe, und der Server rechnet nichts nach.
    #
    # N-617: nur heute vorhandene Balkonkraftwerke und, für die Ableitung, nur
    # heute vorhandene Modul-Kinder — wie Speicher und Wallbox. Bis 04.10.2026
    # zählte ein stillgelegtes altes BKW neben dem neuen mit (600 + 800 =
    # 1.400 Wp) und ein erst künftig angeschafftes schon heute (800 Wp statt
    # keins). Ein Kind mit Anschaffung in der Zukunft hat die Leistung heute
    # noch nicht übernommen; dann gilt die eigene Pflege des BKW.
    bkw_wp = None
    investitionen_heute = [inv for inv in investitionen if inv.ist_aktiv_an(heute_)]
    bkws = [inv for inv in investitionen_heute if inv.typ == "balkonkraftwerk"]
    if bkws:
        bkw_wp = 0.0
        for inv in bkws:
            aus_kindern = bkw_kwp_aus_kindern(inv, investitionen_heute)
            if aus_kindern:
                bkw_wp += aus_kindern * 1000
                continue
            bkw_wp += (
                ((inv.parameter or {}).get(PARAM_BALKONKRAFTWERK["LEISTUNG_WP"], 0) or 0)
                * ((inv.parameter or {}).get(PARAM_BALKONKRAFTWERK["ANZAHL"], 1) or 1)
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
    #
    # N-266: `erzeuger_traeger` — ein Balkonkraftwerk mit Modul-Kindern hat seine
    # Ausrichtung abgetreten. Bliebe es drin, ginge seine EINE (alte) Ausrichtung
    # als zusätzlicher Summand in den Ø ein und verschöbe die Vergleichsgruppe
    # genau gegen die Module, deren Ausrichtungen der Melder erst erfassen wollte.
    #
    # ⛔ N-617: erst der Zeitfilter (`ist_aktiv_an(heute)`), dann der Selektor —
    # wie Speicher, Wallbox und BKW-Leistung darüber und wie jede andere
    # Jetzt-Menge vor `erzeuger_traeger` (ADR-002/P11, Abgrenzung a). Bis
    # 04.10.2026 gingen stillgelegte, künftige und deaktivierte Erzeuger in den
    # Ø ein: ein stillgelegter Ost-String machte aus „30°, süd" ein „20°,
    # gemischt" (gemessen über `prepare_community_data`). Der Datensatz
    # beschreibt die heutige Ausstattung; der Server rechnet nichts nach.
    pv_module = erzeuger_traeger(
        [inv for inv in investitionen_heute if inv.typ in PV_ERZEUGER_TYPEN]
    )
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
    # SOLL §4.1/§7 A5: Passive Kühlung erreicht ein Vielfaches der Effizienz
    # aktiver — die eigene Kennzahl ist korrekt, ein **Vergleich** gegen aktiv
    # gekühlte Anlagen wäre die Falschaussage. Der Server braucht die Markierung,
    # um sie aus dem Ranking zu nehmen; **rechnen** tut er damit nichts.
    #
    # ⚠ Wie `wp_art`: die erste Wärmepumpe steht für die Anlage. Das ist eine
    # bekannte Vereinfachung des Anlagen-Datensatzes, keine neue.
    kuehlung_art = None
    if hat_waermepumpe:
        wps = [inv for inv in investitionen if inv.typ == "waermepumpe"]
        if wps:
            wp_art = (wps[0].parameter or {}).get(PARAM_WAERMEPUMPE["WP_ART"])
            kuehlung_art = (wps[0].parameter or {}).get(
                PARAM_WAERMEPUMPE["KUEHLUNG_ART"]
            )

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
        "kuehlung_art": kuehlung_art,
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
    # Der Maßstab (PVGIS) und die CO₂-Eingaben werden EINMAL geladen, nicht je
    # Monat — beides sind Anlagen-Eigenschaften. `soll_quelle is None` heißt
    # „keine aktive Prognose": dann trägt der Datensatz keine SOLL-Felder und
    # der Server fällt auf seine eigene Kaskade zurück (#387).
    soll_quelle = await lade_soll_quelle(db, anlage_id)
    erzeuger = await lade_erzeuger(db, anlage_id) if soll_quelle else []
    eauto_parameter = {
        inv.id: inv.parameter for inv in investitionen if inv.typ == "e-auto"
    }
    data["soll_jahr_kwh"] = (
        round(soll_quelle.jahr_kwh, 1)
        if soll_quelle and soll_quelle.jahr_kwh
        else None
    )

    if include_monatswerte:
        for fakt in await lade_monats_fakten(db, anlage_id):
            monatswert_data = _monatswert(
                fakt,
                soll_quelle=soll_quelle,
                erzeuger=erzeuger,
                eauto_parameter=eauto_parameter,
            )
            if monatswert_data is not None:
                data["monatswerte"].append(monatswert_data)

    return data


def _monatswert(
    fakt: MonatsFakt,
    *,
    soll_quelle: SollQuelle | None = None,
    erzeuger: Sequence = (),
    eauto_parameter: Mapping[int, dict | None] | None = None,
) -> dict | None:
    """Ein Community-Monatswert aus einem ``MonatsFakt`` — oder ``None``.

    Drei Filter, die ersten beiden aus dem Bestand übernommen und bewusst
    beibehalten:

    - **ohne Zählerzeile nichts** — Einspeisung und Netzbezug wären 0 und die
      Autarkie damit eine Behauptung ohne Messung (P4). Die alte Fassung lief
      über die ``Monatsdaten``-Zeilen und hatte den Filter dadurch implizit.
    - **ohne PV nichts** — der Benchmark vergleicht PV-Anlagen. Ein Monat vor
      der Inbetriebnahme (oder eine reine BHKW-Anlage) gehört nicht hinein.
    - **kein angefangener Monat** (F-48, neu 2026-08-19) — siehe unten.

    ⛔ **Der laufende Kalendermonat wird nicht geteilt (F-48).** Bis dahin ging
    jeder Monat mit Zählerzeile und PV > 0 raus, also auch ein halber. Wer den
    Abschluss des laufenden Monats schon anlegt (das Formular lässt es zu) oder
    ihn importiert, schickte ein Bruchstück in einen Bestand voller ganzer
    Monate. **Live gemessen am 19.08.2026:** ``/api/statistics/monthly-averages``
    wies für 08/2026 **46,3 kWh/kWp bei n = 5** aus — kein August, sondern fünf
    halbe —, und der Client benutzt genau diese Reihe als Monats-Vergleichswert.

    ⚠ **„Zu Ende" heißt Kalendermonat vorbei, NICHT „Monatsabschluss
    erledigt".** Sonst hinge die Vergleichbarkeit an der Pflegedisziplin des
    Einzelnen: wer früh abschließt, wäre drin, wer spät abschließt, fehlte —
    und beides wäre unsichtbar. Der Kalender ist für alle derselbe.

    **Was verloren geht, ehrlich:** der eigene neueste Datenpunkt fehlt in der
    Gemeinschaftssicht bis zum Monatsende. Kein Verlust — eedc zeigt ihn lokal,
    vergleichbar war er dort nie.
    """
    heute = date.today()
    if (fakt.jahr, fakt.monat) >= (heute.year, heute.month):
        return None

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

    # N-632 (05.10.2026, Regel N-585): eine gemessene 0 bleibt 0 — bis dahin stand hier
    # `round(x, 1) if x else None`, und ein Monat ohne Netzbezug ging als „kein Wert" hinaus,
    # während dieselbe Nutzlast eine Autarkie von 100 % aus genau dieser 0 meldete. „Erfasst" ist
    # hier die Zählerzeile (`meta.hat_zaehlerzeile`, Filter oben): ihre beiden Spalten sind
    # `NOT NULL` (`models/monatsdaten.py`), die Schicht trägt also für beide Größen einen Wert,
    # nie eine Lücke. Der Server nimmt die 0 an (`MonatswertInput`: `ge=0`, `None` erlaubt), der
    # Benchmark zählt sie über `is not None` als Datenpunkt, die Statistik summiert ohnehin mit
    # `coalesce(…, 0)` — keine Server-Änderung.
    monatswert_data = {
        "jahr": fakt.jahr,
        "monat": fakt.monat,
        "ertrag_kwh": round(pv_erzeugung, 1),
        "einspeisung_kwh": round(einspeisung, 1),
        "netzbezug_kwh": round(netzbezug, 1),
        "autarkie_prozent": round(autarkie, 1) if autarkie is not None else None,
        "eigenverbrauch_prozent": round(ev_quote, 1) if ev_quote is not None else None,
        # Der Eigenverbrauch in kWh, nicht nur als Quote (F-47): der Server hat
        # ihn bis dahin als `Erzeugung − Einspeisung` rekonstruiert — falsch,
        # sobald ein weiterer Erzeuger hinter demselben Zähler sitzt oder der
        # Speicher mitspielt. Hier ist es die kanonische Größe aus der Schicht.
        "eigenverbrauch_kwh": round(kennzahlen.eigenverbrauch_kwh, 1),
    }

    # Der Maßstab dieses Monats (#387) — tagesgenau gekürzt, siehe
    # `services/pvgis_soll.py`. Ohne aktive PVGIS-Prognose bleibt das Feld weg;
    # der Server hat dann keinen anlagenindividuellen Maßstab und sagt es.
    soll_kwh = soll_fuer_monat(soll_quelle, erzeuger, fakt.jahr, fakt.monat)
    if soll_kwh is not None and soll_kwh > 0:
        monatswert_data["soll_ertrag_kwh"] = soll_kwh

    # CO₂ nach eedcs einzigem Kanon (ADR-001/DI-2, F-47) — inklusive Wärmepumpe
    # und E-Mobilität. Der Server rechnete `Eigenverbrauch × 0,38` und ließ
    # beides aus; allein die Wärmepumpen fehlten mit rund 22 % der Summe.
    co2 = co2_bilanz_aus_fakt(fakt, eauto_parameter or {})
    if co2.co2_gesamt_kg > 0:
        monatswert_data["co2_vermieden_kg"] = round(co2.co2_gesamt_kg, 1)

    speicher = fakt.speicher
    if speicher.ladung_kwh > 0 or speicher.entladung_kwh > 0:
        monatswert_data["speicher_ladung_kwh"] = round(speicher.ladung_kwh, 1)
        monatswert_data["speicher_entladung_kwh"] = round(speicher.entladung_kwh, 1)
        if speicher.netzladung_kwh > 0:
            monatswert_data["speicher_ladung_netz_kwh"] = round(speicher.netzladung_kwh, 1)

    wp = fakt.wp
    if wp.strom_kwh > 0:
        monatswert_data["wp_stromverbrauch_kwh"] = round(wp.strom_kwh, 1)
        # ⭐ **N-391 (14.09.2026): die Gesamtwärme erreicht das Feld, wenn es
        # keinen Heiz-Einzelwert gibt.** Wer Heizung und Warmwasser über EINEN
        # Wärmemengenzähler misst, trägt seinen Wert unter *Wärme gesamt* ein —
        # ohne diese Zeile käme im Payload gar keine Wärme an, und der Server
        # sähe eine Anlage mit Strom und ohne Wärme (Arbeitszahl gesperrt,
        # Mengen fehlend).
        #
        # ⚠ **Kein neues Payload-Feld, und das ist gemessen, nicht bequem:**
        # `wp_heizwaerme_kwh` wird serverseitig ausschließlich **in der Summe**
        # mit `wp_warmwasser_kwh` gelesen (`core/wp_jaz.py`, `api/stats.py`,
        # `api/statistics.py`, `api/benchmark.py`); kein `.tsx` rendert es
        # allein. Ein eigenes Feld kostete sieben Query-Stellen, eine Spalte,
        # eine Migration und einen koordinierten Deploy — für eine Zahl, die
        # der Server ohnehin nur summiert. Die **Bedeutung** steht im Docstring
        # von `MonatswertInput` (Community-Repo): bei gemeinsamem Zähler trägt
        # das Feld die Gesamtwärme.
        #
        # ⚠ **Gesendet wird die Aufteilung der KANONISCHEN Wärme** (D1), nicht
        # die Rohspalte: `wp_heizwaerme_kwh` trägt, was von `wp.waerme_kwh` neben
        # dem Warmwasser übrig bleibt. Ohne Gesamtzähler ist das bitgleich der
        # bisherige Wert (dort IST die Wärme Heizung + Warmwasser); mit
        # Gesamtzähler kommt seine Menge vollständig an, auch wenn nur EINE der
        # beiden Achsen daneben gepflegt ist. Ein blankes „sonst die
        # Gesamtwärme" verlöre in dieser Lage die Differenz.
        _ww_gesendet = wp.warmwasser_kwh if wp.warmwasser_kwh > 0 else 0.0
        _heiz_gesendet = max(wp.waerme_kwh - _ww_gesendet, 0.0)
        if _heiz_gesendet > 0:
            monatswert_data["wp_heizwaerme_kwh"] = round(_heiz_gesendet, 1)
        if _ww_gesendet > 0:
            monatswert_data["wp_warmwasser_kwh"] = round(_ww_gesendet, 1)
        # ⭐ **ADR-002/P12 (02.09.2026): Darf aus diesem Monat eine Arbeitszahl
        # gebildet werden?** Lokal entscheidet das seit dem 26.08. der Layer;
        # der Server bildet seinen JAZ aber selbst — an **vier** Stellen
        # (`core/wp_jaz.py::anlagen_jaz` als SoT für Benchmark-Kachel, Ranking
        # und beide `components.py`-Sichten; dazu `stats.py` je Region,
        # `statistics.py` global und `benchmark.py` je Monatswert).
        # ⚠ Hier stand bis zum 13.09.2026 eine andere Aufzählung („`components.py`
        # zweimal, `statistics.py` fürs Ranking") — die stimmte bis zum 06.09.,
        # seit `85c75a2` hängen beide am SoT. Am 13.09. im zweiten Repo neu
        # erhoben. Er hat die Geräte
        # nie gesehen und kann die Abgrenzung nicht prüfen; ohne dieses Flag
        # ginge eine Anlage mit Wärmepumpe **und** Split-Klimaanlage mit dem
        # Strom zweier Geräte und der Wärme von einem in **fremde**
        # Vergleichswerte ein.
        #
        # ⛔ Es sperrt die **Kennzahl**, nicht die **Mengen**: Strom, Heizwärme
        # und Warmwasser bleiben additiv richtig und werden weiter gesendet und
        # ausgewertet (E1 — Mengen summiert, Kennzahlen getrennt).
        #
        # ⚠ Dieselben drei Lagen wie in jeder lokalen Sicht, über **einen**
        # SoT-Aufruf. `zeitraum_versetzt` gehört nicht dazu: Der Payload liest
        # eine Quelle (die Monats-Fakten), Q und E stammen aus demselben
        # Zeitraum.
        #
        # ⭐ **ZWEITE HÄLFTE (06.09.2026, rapahl per PN):** `abgrenzungs_grund`
        # allein ist NICHT die ganze Sperre. Es gibt zwei Gründe, aus denen
        # lokal keine Arbeitszahl entsteht, und dieser Payload kannte nur einen:
        #
        #   • **Abgrenzung** — Q und E messen verschiedene Dinge (die drei Lagen
        #     oben). Antwort: `abgrenzungs_grund(...) is None`.
        #   • **Herkunft** — die Wärme ist *gerechnet*, nicht gemessen
        #     (`Strom × gepflegte JAZ`, kein Wärmemengenzähler). Antwort:
        #     `WpFakten.jaz_belastbar`, also `waerme_abgeleitet_kwh <= 0`.
        #
        # `arbeitszahl()` sperrt beide hart (`waermepumpe_kennzahl.py`:
        # „Wärme ist gerechnet, nicht gemessen"). Der Payload meldete den
        # zweiten Fall als **belastbar** — und damit ging eine Zahl in fünf
        # Server-Vergleichswerte ein, die gar keine Messung ist: Wärme aus
        # `Strom × JAZ` geteilt durch denselben Strom ergibt **exakt die
        # gepflegte JAZ** zurück. Der Community-Schnitt spiegelte an dieser
        # Stelle ein Einstellungsfeld. Wir haben die Zahl dem Besitzer
        # verweigert und sie allen anderen gemeldet.
        #
        # ⛔ Wieder nur die **Kennzahl**, nie die **Mengen** (E1): Strom,
        # Heizwärme und Warmwasser bleiben additiv richtig und werden weiter
        # gesendet — auch der abgeleitete Anteil, denn als *Menge* ist er die
        # beste verfügbare Auskunft.
        monatswert_data["wp_jaz_belastbar"] = (
            abgrenzungs_grund(
                abgrenzung_stoerung=wp.abgrenzung_stoerung,
                bauarten_gemischt=wp.bauarten_gemischt,
                geraete_ohne_waerme=wp.waerme_deckt_nicht_alle_geraete,
                # N-441: die Gegenrichtung. Waerme von Geraet A und Strom von
                # Geraet B ergaben bis zum 12.09.2026 `1 == 1` — der Monat ging
                # als **belastbar** hinaus, und der Server bildete daraus einen
                # Regionalwert fuer fremde Anlagen.
                geraete_verschieden=wp.geraete_verschieden,
            ) is None
            and wp.jaz_belastbar
        )
        # **W-14 — der Server bekommt die Größe, weil er sie selbst nicht bilden kann.**
        # ⛔ **Hier stand bis zum 02.09.2026 „Der Server rechnet nichts nach, also
        # bekommt er die Größe."** Das ist falsch und war es immer: Er rechnet an
        # den Stellen aus dem Block darüber — er bekam nur nicht die Information,
        # ob er darf. Der Satz hat die Lücke elf Tage lang plausibel aussehen
        # lassen. (Seit WK-06b bekommt er sie, s. das Abzug-Feld unten.)
        # Sein JAZ ist `(Heizwärme + Warmwasser) / (Stromverbrauch − Abzug)`; ohne
        # diesen Wert stünde der Kühlstrom im Nenner und die Kältemenge nirgends.
        # Eine kühlende Anlage stand damit systematisch schlechter da als eine,
        # die es nicht tut — und zwar unabhängig davon, ob aktiv oder passiv
        # gekühlt wird (SOLL §4.2 Fall 4).
        #
        # ⚠ **Immer mitgeschickt, auch als 0.** Ein fehlendes Feld heißt beim
        # Server „alter Client, unbekannt"; eine 0 heißt „gemessen, es gab
        # keinen Kühlbetrieb". Das ist derselbe Unterschied, den P4 überall
        # sonst verlangt — und der Server darf ihn nicht raten.
        #
        # ⛔ **Diese Zahl bleibt die MENGE und behält ihren Vertrag** — der Name
        # `wp_strom_kuehlen_kwh` darf NICHT umgedeutet werden (Docstring von
        # `MonatswertInput`, Community-Repo). Der Server zieht sie nur noch dann
        # ab, wenn das Abzug-Feld darunter fehlt (älterer Client).
        monatswert_data["wp_strom_kuehlen_kwh"] = round(
            wp.modus_strom_kuehlen_kwh, 1
        )
        # ⭐ **Und daneben die ENTSCHEIDUNG: wieviel davon der Server abziehen
        # darf** (WK-06b, 13.09.2026; SOLL Wärme/Klima §4.1 „Ergänzung zu E7",
        # Option A). Das neue Feld `wp_strom_funktionsfremd_abzug_kwh` schließt
        # **zwei** Lücken auf einmal:
        #
        # 1. **Lüften und Entfeuchten** (offen seit E4, 26.08.2026): Lokal zieht
        #    die Arbeitszahl *Kühlen · Lüften · Entfeuchten* ab, der Server kannte
        #    nur den Kühlstrom. Wer diese Zähler getrennt führt, sah dort eine
        #    andere Zahl als im eigenen Cockpit. ⇒ Der Abzug trägt die **volle**
        #    Definition, deshalb heißt er nicht `…kuehlen_abzug…`.
        # 2. **Option A** (die neuere und die größere): Ein aus dem Betriebsmodus
        #    **abgeleiteter** Anteil kürzt einen **gemessenen** F5-Nenner nicht —
        #    er ist eine Verteilung genau der Zähler, die den Nenner bilden. Der
        #    Server kann diese Bedingung nicht selbst bilden; sie hängt an
        #    `getrennte_strommessung` und daran, ob der Split gemessen ist, und
        #    Geräte hat er nie gesehen. Ohne das Feld stand dieselbe Anlage dort
        #    mit **4,24** und hier mit **3,79** (N-454, rund 12 %) — und die
        #    höhere Zahl ging in **fremde** Vergleichswerte.
        #
        # ⚠ **`modus_strom_funktionsfremd_abzug_kwh`, nicht
        # `modus_strom_funktionsfremd_kwh`.** Der ältere Vermerk an dieser Stelle
        # nannte die Menge — er stammt von **vor** Option A, die die beiden
        # Größen erst getrennt hat (K1: die Menge bleibt die Menge). Wer hier die
        # Menge einsetzte, baute den behobenen Fehler im zweiten Repo nach.
        #
        # ⚠ **Immer mitgeschickt, auch als 0.0** — dieselbe P4-Regel wie oben:
        # fehlt das Feld, liest der Server „älterer Client" und fällt auf die
        # Menge zurück; eine 0.0 heißt „entschieden, nichts abzuziehen".
        monatswert_data["wp_strom_funktionsfremd_abzug_kwh"] = round(
            wp.modus_strom_funktionsfremd_abzug_kwh, 1
        )

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

    # ⭐ N-555 Stufe 2 (Konzept Heimladung/Fahrverbrauch 7.2, Community E3): das
    # Wallbox-Feld trägt, was sein Vertrag verlangt — nur die **private** Ladung
    # („nur privat genutzte Fahrzeuge", `eedc-community/backend/schemas.py`). Der Server
    # ändert sich nicht.
    # * kWh und PV um die gemessenen Dienstwagen gekürzt (sonst bildete der Server aus
    #   gekürzter kWh und ungekürzter PV einen PV-Anteil über 100 %);
    # * ≤ 0 ⇒ Feld weglassen (ein negativer Wert scheiterte am Schema `ge=0` und wiese
    #   den ganzen Submit ab);
    # * ein Dienstwagen ohne eigene Messung neben einer privaten Wallbox in Betrieb ⇒
    #   Wallbox-Feld weglassen (wo er lädt, ist nicht feststellbar);
    # * Ladevorgänge weglassen, sobald ein Dienstwagen an der privaten Wallbox geladen
    #   haben kann (in Betrieb, keine dienstliche Wallbox) — nicht aufteilbar.
    # Die E-Auto-Seite oben bleibt unverändert (nur private Messwerte, keine Schätzung).
    wallbox = emob.wallbox_summe_gemessen
    dienst_pv = emob.dienstlich_gemessen_pv_kwh
    dienst_gesamt = dienst_pv + emob.dienstlich_gemessen_netz_kwh
    wb_privat = wallbox.ladung_kwh - dienst_gesamt
    wb_privat_pv = min(max(0.0, wallbox.pv_kwh - dienst_pv), max(0.0, wb_privat))
    dienstwagen_unbekannt = bool(emob.dienstwagen_ungemessen) and emob.wallbox_in_betrieb
    if wb_privat > 0 and not dienstwagen_unbekannt:
        monatswert_data["wallbox_ladung_kwh"] = round(wb_privat, 1)
        if wb_privat_pv > 0:
            monatswert_data["wallbox_ladung_pv_kwh"] = round(wb_privat_pv, 1)
        dienstwagen_kann_laden = (
            emob.dienstwagen_in_betrieb and not emob.dienstliche_wallbox_in_betrieb
        )
        if wallbox.ladevorgaenge > 0 and not dienstwagen_kann_laden:
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
