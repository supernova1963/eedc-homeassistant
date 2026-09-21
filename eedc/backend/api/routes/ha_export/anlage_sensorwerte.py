"""HA-Export, Anlagen-Sensoren — die Sensorwerte: `grundlast_sensorwert` (#395, hier umgezogen), die Energie-, Investitions-,
Speicher- und Letzter-Import-Sensoren aus den berechneten Größen sowie die Prognose- (#150 A) und Börsenpreis-Sensoren
(#150 B).
"""
# Vorlage 8b des Refactorings grosser Dateien (18.09.2026): Phasen des Rechners
# `ha_export/anlage_sensoren.py::calculate_anlage_sensors` byte-identisch als Funktionen, Schnittstelle als
# Schluesselwort-Parameter und Rueckgabe-Dict; der Rechner orchestriert. Kein Verhaltenswechsel —
# Gate ist `plans/skript-golden-master-ha-export.py` (alte gegen neue Antworten, bitgleich).

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date
from backend.core.berechnungen.kapitalrechnung import (
    annahme_dauer_text,
    erklaerung_jahres_ersparnis,
)
from backend.services.ha_sensors_export import (
    SensorValue,
    ANLAGE_SENSOREN,
    INVESTITION_SENSOREN,
    SPEICHER_SENSOREN,
    LETZTER_IMPORT_SENSOREN,
    PROGNOSE_SENSOREN,
    PREIS_SENSOREN,
)
from backend.services.ha_export_prognose import berechne_prognose_export
from backend.services.ha_export_preis import berechne_preis_export


async def grundlast_sensorwert(
    db: AsyncSession, anlage_id: int, heute: date
) -> tuple[Optional[float], Optional[str]]:
    """Die **gemessene** Grundlast des laufenden Monats für den HA-Sensor (#395/5).

    ⛔ **Bewusst NICHT der Live-Wert.** „Grundlast" bezeichnet in eedc zwei
    verschiedene Zahlen (Fund N-332): Cockpit → Live zeigt den Median über das
    Verbrauchs-**Profil** — ohne eigene Historie ist das ein BDEW-H0-Modellwert
    mit 0,3 kW Default. Hier zählt der Median der **gemessenen** Nachtstunden,
    dieselbe Quelle und derselbe Layer-SoT wie die Kachel in Cockpit → Monat.
    Ein Modellwert, der als Sensor in eine Automation läuft, ist die teuerste
    Sorte Zahl: er sieht aus wie eine Messung.

    ⭐ **`heute` ist ein Parameter und kein `date.today()` in dieser Funktion** —
    dasselbe Muster wie `core/hub_leer_grund.py`. Sonst müsste jede Probe die
    Prozessuhr lesen und damit auf die Stunde ihres Laufs wetten (N-167: vier
    von 24 Stunden rot ohne Code-Änderung). Der Aufrufer setzt die Uhr ein, die
    Funktion rechnet.

    Returns:
        ``(kW, Rechenweg)`` — ``(None, None)``, wenn keine Nachtstunde gemessen
        ist. Dann entsteht **kein** Sensor.
    """
    from backend.api.routes.aktueller_monat import _load_grundlast_nacht_kw
    from backend.core.berechnungen import berechne_grundlast

    nacht = await _load_grundlast_nacht_kw(anlage_id, heute.year, heute.month, db)
    if not nacht:
        return None, None
    kennzahlen = berechne_grundlast(
        nacht_verbrauch_kw=nacht, gesamtverbrauch_kwh=None, tage=heute.day,
    )
    if kennzahlen.grundlast_kw is None:
        return None, None
    return kennzahlen.grundlast_kw, (
        f"Median über {len(nacht)} gemessene Nachtstunden (0–5 Uhr) im laufenden Monat"
    )

async def sensorwerte_erstellen(
    *,
    amortisation_jahre,
    anlage,
    autarkie,
    batterie_entladung,
    batterie_ladung,
    betriebskosten_ges,
    co2_ersparnis,
    db,
    direktverbrauch,
    eigenverbrauch,
    einspeise_erloes,
    einspeisung,
    ersparnis_posten,
    erzeugung_bilanz,
    ev_ersparnis,
    ev_quote,
    gesamtverbrauch,
    investition_gesamt,
    investitionen,
    jahres_ersparnis,
    jahres_ertraege_ges,
    kapitaleinsatz,
    monatsdaten,
    netto_ertrag,
    netzbezug,
    pv_erzeugung,
    relevante_kosten,
    roi_prozent,
    sonstige_ausgaben_gesamt,
    sonstige_ertraege_gesamt,
    sonstige_netto_gesamt,
    speicher_effizienz,
    speicher_kapazitaet,
    speicher_zyklen,
    spez_ertrag,
    strompreis,
):
    """Je Sensor der Anlagen-Registry der Wert aus den berechneten Größen (Energie, Investitionen, Speicher, letzter Import);
    die Grundlast über `grundlast_sensorwert`.

    Aus `calculate_anlage_sensors` Zeilen 864-1048 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # Sensor-Werte erstellen
    sensor_values = []

    # Energie-Sensoren
    for sensor in ANLAGE_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "pv_erzeugung_gesamt_kwh":
            value = pv_erzeugung
            berechnung = f"Summe aus {len(monatsdaten)} Monaten"
        elif sensor.key == "direktverbrauch_gesamt_kwh":
            value = direktverbrauch
            berechnung = f"PV direkt verbraucht (ohne Speicher)"
        elif sensor.key == "eigenverbrauch_gesamt_kwh":
            value = eigenverbrauch
        elif sensor.key == "einspeisung_gesamt_kwh":
            value = einspeisung
        elif sensor.key == "netzbezug_gesamt_kwh":
            value = netzbezug
        elif sensor.key == "gesamtverbrauch_kwh":
            value = gesamtverbrauch
            berechnung = f"{eigenverbrauch:.0f} + {netzbezug:.0f}"
        elif sensor.key == "autarkie_prozent":
            value = autarkie
            berechnung = f"{eigenverbrauch:.0f} ÷ {gesamtverbrauch:.0f} × 100"
        elif sensor.key == "eigenverbrauch_quote_prozent":
            value = ev_quote
            # DI-2-B: Nenner = Netzpunkt-Erzeugung (PV inkl. BKW + sonstige
            # Erzeuger), deckungsgleich mit der Cockpit-EV-Quote.
            berechnung = f"{eigenverbrauch:.0f} ÷ {erzeugung_bilanz:.0f} × 100"
        elif sensor.key == "spezifischer_ertrag_kwh_kwp":
            value = spez_ertrag if spez_ertrag else None
            if value is not None:
                berechnung = (
                    f"{pv_erzeugung:.0f} kWh annualisiert "
                    f"(saisonal gewichtet, wie Cockpit)"
                )
        elif sensor.key == "netto_ertrag_euro":
            value = netto_ertrag
            berechnung = f"{einspeise_erloes:.2f} + {ev_ersparnis:.2f} + {sonstige_netto_gesamt:.2f} (sonstige)"
        elif sensor.key == "einspeise_erloes_euro":
            value = einspeise_erloes
            if strompreis and getattr(strompreis, "einspeisung_variabel", False):
                # #392: der €-Wert daneben ist je Monat mit dem gepflegten
                # Monatssatz gerechnet — ein einzelner Satz im Text wäre
                # eine Behauptung, die die Zahl nicht deckt.
                berechnung = (
                    f"{einspeisung:.0f} kWh × Monatssatz "
                    f"(variable Vergütung, je Monat aufgelöst)"
                )
            elif strompreis:
                berechnung = f"{einspeisung:.0f} × {strompreis.einspeiseverguetung_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "eigenverbrauch_ersparnis_euro":
            value = ev_ersparnis
            if strompreis:
                berechnung = f"{eigenverbrauch:.0f} × {strompreis.netzbezug_arbeitspreis_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "co2_ersparnis_kg":
            value = co2_ersparnis
            berechnung = "PV-Eigenverbrauch + Wärmepumpe + E-Mobilität (vermiedenes CO₂)"
        elif sensor.key == "eedc_grundlast_kw":
            value, berechnung = await grundlast_sensorwert(db, anlage.id, date.today())

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Investitions-Sensoren
    for sensor in INVESTITION_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "investition_gesamt_euro":
            if investition_gesamt > 0:
                value = investition_gesamt
                berechnung = f"Summe aus {len(investitionen)} Investitionen"
        elif sensor.key == "jahres_ersparnis_euro":
            if jahres_ersparnis > 0:
                value = jahres_ersparnis
                # N-212: der Rechenweg nennt jetzt jeden Posten mit SEINER
                # Monatszahl **und** den Betriebskosten-Abzug. Vorher stand
                # hier `(Σ ÷ Anlagenmonate) × 12` — das ergab einen um exakt
                # die Betriebskosten größeren Wert als der Sensor daneben.
                berechnung = erklaerung_jahres_ersparnis(
                    ersparnis_posten,
                    betriebskosten_jahr_euro=betriebskosten_ges,
                    jahres_ertraege_euro=jahres_ertraege_ges,
                )
        elif sensor.key == "roi_prozent":
            if roi_prozent is not None:
                value = roi_prozent
                berechnung = f"{jahres_ersparnis:.2f} ÷ {kapitaleinsatz:.2f} × 100"
        elif sensor.key == "amortisation_jahre":
            if amortisation_jahre is not None:
                value = amortisation_jahre
                # F-19: der Nenner ist der Kapitaleinsatz. Er wird ausgeschrieben,
                # solange sonstige Positionen ihn von den relevanten Kosten
                # unterscheiden — sonst bliebe die Differenz unerklärt (N-212).
                if sonstige_ausgaben_gesamt or sonstige_ertraege_gesamt:
                    _nenner = f"{relevante_kosten:.2f}"
                    if sonstige_ausgaben_gesamt:
                        _nenner += f" + {sonstige_ausgaben_gesamt:.2f} sonstige Ausgaben"
                    # Bauschritt 7: die Erträge mindern den Nenner und werden
                    # deshalb genauso ausgeschrieben — sonst bliebe die
                    # Differenz zum Ergebnis unerklärt (N-212).
                    if sonstige_ertraege_gesamt:
                        _nenner += f" − {sonstige_ertraege_gesamt:.2f} sonstige Erträge"
                    berechnung = f"({_nenner}) ÷ {jahres_ersparnis:.2f}"
                else:
                    berechnung = f"{kapitaleinsatz:.2f} ÷ {jahres_ersparnis:.2f}"
                # Konzept §5/§8-6: die Annahme steht im selben Attribut wie der
                # Rechenweg. Ein HA-Sensor hat keinen Tooltip — wer die Zahl in
                # ein Dashboard hängt, sieht sonst eine Dauer ohne jede
                # Voraussetzung.
                berechnung += f" — {annahme_dauer_text(betriebskosten_jahr_euro=betriebskosten_ges)}"

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Speicher-Sensoren (nur wenn Speicher vorhanden)
    if speicher_kapazitaet > 0 or batterie_ladung > 0:
        for sensor in SPEICHER_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "speicher_zyklen":
                if speicher_zyklen is not None:
                    value = speicher_zyklen
                    berechnung = f"{batterie_entladung:.0f} ÷ {speicher_kapazitaet:.1f}"
            elif sensor.key == "speicher_effizienz_prozent":
                if speicher_effizienz is not None:
                    value = speicher_effizienz
                    berechnung = f"{batterie_entladung:.0f} ÷ {batterie_ladung:.0f} × 100"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    # Letzter Import Sensoren (Status)
    if monatsdaten:
        # Finde den neuesten Monat (sortiert nach Jahr, dann Monat)
        sorted_md = sorted(monatsdaten, key=lambda m: (m.jahr, m.monat), reverse=True)
        letzter = sorted_md[0]

        # Monatsnamen
        monatsnamen = [
            "", "Januar", "Februar", "März", "April", "Mai", "Juni",
            "Juli", "August", "September", "Oktober", "November", "Dezember"
        ]
        monatsname = monatsnamen[letzter.monat] if 1 <= letzter.monat <= 12 else str(letzter.monat)

        for sensor in LETZTER_IMPORT_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "letzter_import_jahr":
                value = letzter.jahr
                berechnung = f"Neuester Datensatz: {monatsname} {letzter.jahr}"
            elif sensor.key == "letzter_import_monat":
                value = letzter.monat
                berechnung = f"Monat {letzter.monat} ({monatsname})"
            elif sensor.key == "letzter_import_monat_name":
                value = f"{monatsname} {letzter.jahr}"
                berechnung = f"Formatiert aus {letzter.monat}/{letzter.jahr}"
            elif sensor.key == "anzahl_monate_erfasst":
                value = len(monatsdaten)
                berechnung = f"Erfasste Monatsdaten in der Datenbank"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))
    _loc = locals()  # nur gebundene Namen zurueckgeben — ein bedingt gesetzter Name bleibt sonst UnboundLocal
    return {k: _loc[k] for k in ("sensor_values",) if k in _loc}


async def prognose_und_preis_sensoren(*, anlage, db, sensor_values, skip_jitter):
    """Die eedc-Prognose-Sensoren (#150 A, `berechne_prognose_export`) und die Börsenpreis-Sensoren (#150 B) an die Liste
    anhängen.

    Aus `calculate_anlage_sensors` Zeilen 1049-1171 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 8b.
    """
    # #150 A: eedc-eigene PV-Prognose (OpenMeteo × Lernfaktor) — anlage-weit,
    # koordinaten-/PV-gated, netzwerk-tolerant (None → Sensoren entfallen).
    # Stundenprofil reist als Attribut mit (kein eigenes Topic).
    # N-531: On-Demand-Wege überspringen den Open-Meteo-Jitter (bis 30 s je Aufruf), der Cron-Job nicht.
    prognose = await berechne_prognose_export(db, anlage, skip_jitter=skip_jitter)
    if prognose:
        for sensor in PROGNOSE_SENSOREN:
            value = None
            zusatz: dict = {}
            if sensor.key == "eedc_prognose_heute_kwh":
                value = prognose["heute_kwh"]
                if prognose.get("stundenprofil_heute"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_heute"]}
            elif sensor.key == "eedc_prognose_heute_rollend_kwh":
                value = prognose["heute_rollend_kwh"]
            elif sensor.key == "eedc_prognose_rest_today_kwh":
                value = prognose["rest_today_kwh"]
            elif sensor.key == "eedc_prognose_day_plus_1_kwh":
                value = prognose["day_plus_1_kwh"]
                if prognose.get("stundenprofil_day_plus_1"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_1"]}
            elif sensor.key == "eedc_prognose_day_plus_2_kwh":
                value = prognose["day_plus_2_kwh"]
                if prognose.get("stundenprofil_day_plus_2"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_2"]}
            elif sensor.key == "eedc_prognose_day_plus_3_kwh":
                value = prognose["day_plus_3_kwh"]
                if prognose.get("stundenprofil_day_plus_3"):
                    zusatz = {"stundenprofil_kwh": prognose["stundenprofil_day_plus_3"]}
            elif sensor.key == "eedc_prognose_heute_vormittag_kwh":
                value = prognose.get("heute_vormittag_kwh")
                if prognose.get("solar_noon_heute"):
                    zusatz = {"solar_noon": prognose["solar_noon_heute"]}
            elif sensor.key == "eedc_prognose_heute_nachmittag_kwh":
                value = prognose.get("heute_nachmittag_kwh")
                if prognose.get("solar_noon_heute"):
                    zusatz = {"solar_noon": prognose["solar_noon_heute"]}
            elif sensor.key == "eedc_prognose_morgen_vormittag_kwh":
                value = prognose.get("morgen_vormittag_kwh")
                if prognose.get("solar_noon_morgen"):
                    zusatz = {"solar_noon": prognose["solar_noon_morgen"]}
            elif sensor.key == "eedc_prognose_morgen_nachmittag_kwh":
                value = prognose.get("morgen_nachmittag_kwh")
                if prognose.get("solar_noon_morgen"):
                    zusatz = {"solar_noon": prognose["solar_noon_morgen"]}
            elif sensor.key == "eedc_speicher_voll_um":
                value = prognose["speicher_voll_um"]
                # Die Verbrauchsannahme der Simulation reist mit (N-392) — ein
                # ANDERES Modell als beim Nachbarn darunter (8-Wochen-Profil
                # statt 7-Tage-Profil); das Attribut `profil_typ` sagt es.
                if value is not None and prognose.get("speicher_verbrauch_profil"):
                    zusatz = dict(prognose["speicher_verbrauch_profil"])
            elif sensor.key == "eedc_verbrauchsprognose_heute_kwh":
                value = prognose.get("verbrauch_heute_kwh")
                if value is not None:
                    # Die Grundlage reist mit — dieselben drei Angaben, die der
                    # Tooltip der Kachel nennt (Profiltyp, Tage, belegte Slots).
                    zusatz = {
                        "profil_typ": prognose.get("verbrauch_profil_typ"),
                        "profil_tage": prognose.get("verbrauch_profil_tage"),
                        "profil_slots": prognose.get("verbrauch_profil_slots"),
                    }
                    # ── S3/P1 (21.09.2026): die Reihe, aus der die Summe wird ──
                    #
                    # ⭐ Sie lag intern laengst vor und wurde nur nie exportiert.
                    # Erst mit ihr ist die **Ueberschuss-Prognose je Stunde**
                    # rechenbar — die Groesse, die eine Wallbox, eine Waermepumpe
                    # und eine Speicher-Arbitrage brauchen und keines dieser
                    # Systeme selbst bilden kann. Slot-Konvention wie bei der
                    # PV-Reihe daneben (Index = Stunde der Prozesszone).
                    #
                    # ⚠ `wp_stundenprofil_kwh` ist eine **Teilmenge** von
                    # `stundenprofil_kwh`, kein Summand daneben — wer beide
                    # addiert, zaehlt den Waermepumpenstrom doppelt. Derselbe
                    # Satz wie bei den Modus-Sensoren der Waermepumpe.
                    if prognose.get("verbrauch_stundenprofil_kwh"):
                        zusatz["stundenprofil_kwh"] = prognose["verbrauch_stundenprofil_kwh"]
                    if prognose.get("verbrauch_wp_stundenprofil_kwh"):
                        zusatz["wp_stundenprofil_kwh"] = prognose["verbrauch_wp_stundenprofil_kwh"]

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor, value=value, zusatz_attribute=zusatz
                ))

    # #150 B: Börsenpreis-Trigger (Rang je Tag-/Nacht-Fenster) — Rang-Profil als Attribut.
    preis = await berechne_preis_export(db, anlage)
    if preis:
        for sensor in PREIS_SENSOREN:
            value = None
            zusatz = {}
            if sensor.key == "eedc_preis_rang":
                value = preis["preis_rang"]
                if preis.get("rang_profil"):
                    zusatz = {"rang_profil": preis["rang_profil"]}
                if preis.get("guenstig_schwelle_cent") is not None:
                    zusatz["guenstig_schwelle_cent"] = preis["guenstig_schwelle_cent"]
                # Die Bezugsgröße der Schwelle reist mit: ohne sie ist im
                # Rang-Profil keine eigene Schwelle rechenbar (#335/N-105).
                if preis.get("optimierter_durchschnitt_cent") is not None:
                    zusatz["optimierter_durchschnitt_cent"] = preis["optimierter_durchschnitt_cent"]
                # Der Kalendertag des Profils (N-104). Ohne ihn ist ein
                # stehengebliebenes Profil nach Mitternacht nicht von einem
                # aktuellen zu unterscheiden.
                if preis.get("datum"):
                    zusatz["datum"] = preis["datum"]
                # Morgen — sobald die Day-Ahead-Auktion veröffentlicht hat
                # (N-104, Melder rapahl). `morgen_verfuegbar` ist immer gesetzt,
                # damit eine Automation „noch nicht da" von „gibt es nicht"
                # unterscheiden kann, statt auf ein fehlendes Attribut zu prüfen.
                zusatz["morgen_verfuegbar"] = bool(preis.get("morgen_verfuegbar"))
                for schluessel in (
                    "datum_morgen",
                    "rang_profil_morgen",
                    "guenstig_schwelle_cent_morgen",
                    "optimierter_durchschnitt_cent_morgen",
                ):
                    if preis.get(schluessel) is not None:
                        zusatz[schluessel] = preis[schluessel]
            elif sensor.key == "eedc_preis_guenstige_stunden_anzahl":
                value = preis["guenstige_stunden_anzahl"]
            elif sensor.key == "eedc_preis_guenstige_stunden_tag":
                value = preis["guenstige_stunden_tag"]
            elif sensor.key == "eedc_preis_guenstige_stunden_nacht":
                value = preis["guenstige_stunden_nacht"]
            elif sensor.key == "eedc_preis_aktuell_cent":
                value = preis["preis_aktuell_cent"]
            elif sensor.key == "eedc_preis_tages_durchschnitt_cent":
                value = preis["tages_durchschnitt_cent"]
            elif sensor.key == "eedc_preis_optimierter_durchschnitt_cent":
                value = preis["optimierter_durchschnitt_cent"]
            elif sensor.key == "eedc_preis_abstand_prozent":
                value = preis["abstand_prozent"]
            elif sensor.key == "eedc_preis_abstand_cent":
                value = preis["abstand_cent"]

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor, value=value, zusatz_attribute=zusatz
                ))
    # S2/S3: beide Ergebnisse gehen an die Steuerungs-Phase weiter — sie darf
    # weder Preis noch Prognose ein zweites Mal holen. Ein zweiter Abruf waere
    # nicht nur langsam (Open-Meteo, Markt-API), er waere eine zweite
    # Momentaufnahme: derselbe Sensor und sein Fenster-Attribut stuenden dann
    # auf verschiedenen Staenden desselben Tages.
    return {"prognose": prognose, "preis": preis}

