"""Energie-Profil — Tagesprognose (Etappe 3b).

GET /api/energie-profil/{anlage_id}/tagesprognose — kombinierte Tagesprognose (Verbrauch + PV + Speicher-Simulation)
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

import asyncio
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen.kennzahlen import autarkie_prozent
from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.core.exceptions import not_found
from backend.core.investition_kennwerte import aggregiere_speicher_basis
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.models.tages_energie_profil import TagesEnergieProfil
from ._shared import StundenPrognose, TagesPrognoseResponse, logger

router = APIRouter()


# ── Tagesprognose (Etappe 3b) ──────────────────────────────────────────────


async def _pv_stunden_aus_kanon(db, anlage, datum: date) -> Optional[list[float]]:
    """Korrigierte 24 kWh-Slots des Zieltages aus dem Prognose-Kanon.

    ``None`` = der Kanon hat für diesen Tag kein Stundenprofil (kein Abruf,
    kein Treffer, Schätzpfad ohne Hourly) → der Aufrufer nutzt seinen Fallback.

    Warum überhaupt: der frühere Eigenweg holte OpenMeteo mit **einem** Abruf
    für die Gesamt-kWp und der Orientierung der zufällig ersten Investition
    (kein ``ORDER BY``) und multiplizierte den flachen Legacy-Skalar darauf.
    Beides weicht vom Kanon ab (Multi-String-Fan-out + Kaskade pro Energie-Slot)
    — dieselbe Anlage bekam so je nach Pfad verschiedene Tagessummen.

    ``days`` kommt aus ``kanon_days`` (Horizont-Formel-SoT, geteilt mit
    ``/solar-prognose``): mindestens 4, für spätere Zieltage aus dem Datum
    abgeleitet — der Picker erlaubt +14 Tage, also ``days`` ≤ 15 (OpenMeteo-
    Maximum 16). Dass dabei derselbe OpenMeteo-Snapshot gezogen wird wie im
    Prognosen-Vergleich und im HA-/MQTT-Export, hängt seit E15/A29 nicht mehr
    an diesem Horizont: der Cache-Key trägt den Modell-Snapshot, nicht die
    Anfrage (``services/wetter/cache.snapshot_days``).
    """
    tage_bis_ziel = (datum - date.today()).days
    if tage_bis_ziel < 0:
        return None

    from backend.services.prognose_kanon import kanon_days, kanon_tagesprognose

    try:
        kanon = await kanon_tagesprognose(
            db, anlage,
            days=kanon_days(tage_bis_ziel + 1),
            # Interaktiver User-Request: der 1-30s-Random-Jitter gilt nur für
            # Hintergrund-Abrufe (R18-13).
            skip_jitter=True,
        )
    except Exception as e:
        logger.warning("Kanon-Tagesprognose fehlgeschlagen: %s", e)
        return None
    if not kanon:
        return None

    ziel_iso = datum.isoformat()
    for tag in kanon.tage:
        if tag is not None and tag.datum == ziel_iso and tag.profil is not None:
            # Export-Slots (2 NK) — exakt die Werte, die auch als MQTT-Attribut
            # `stundenprofil_kwh` rausgehen. Damit gilt die Kanon-Invariante
            # `Tageswert == Σ Export-Slots` auch für die Summenzeile hier.
            return list(tag.profil.stundenprofil_export_kwh)
    return None

@router.get("/{anlage_id}/tagesprognose", response_model=TagesPrognoseResponse)
async def get_tagesprognose(
    anlage_id: int,
    datum: Optional[date] = Query(
        default=None,
        description="Ziel-Datum (Default: morgen)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Kombinierte Tagesprognose: Verbrauch + PV + Batterie-Simulation.

    Berechnet für einen Tag (Standard: morgen):
    - Verbrauchsprofil aus historischen Stundenmitteln (Wochenmuster-Basis)
    - PV-Stundenprofil aus Solar Forecast (OpenMeteo GTI oder Solcast)
    - Netto-Bilanz und optionale Batterie-SoC-Simulation

    **Ohne Verbrauchshistorie** (< 3 vollständige Tage Energieprofil, also jede
    frische Installation) liefert die Route trotzdem die PV-Hälfte — sie hängt
    nur an Wetterdienst und kWp. Die verbrauchsabhängigen Felder sind dann
    ``None`` (nicht 0, das sähe aus wie ein Messwert) und ``hinweise`` sagt es.
    Bis A28 (N122) stand hier ein HTTP 422 für den GANZEN Endpoint.
    """
    if datum is None:
        datum = date.today() + timedelta(days=1)

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten konfiguriert")

    # `hinweise` begleitet die Antwort: jede Abweichung von „das ist die volle
    # Prognose für DIESEN Tag" wird hier vermerkt und geht in die Response (P4).
    hinweise: list[str] = []

    # ── 1. Verbrauchsprognose ──
    from backend.services.verbrauch_prognose_service import get_verbrauch_prognose

    vp = await get_verbrauch_prognose(anlage_id, datum, db)
    verbrauch_stunden = vp["stunden_kw"] if vp else None
    if vp is None:
        # A28 (N122): hier stand ein HTTP 422 für den ganzen Endpoint — die
        # PV-Stundenwerte fielen mit, obwohl sie keine Historie brauchen. Jede
        # frische Installation sah in den ersten Tagen deshalb nur eine
        # Fehlermeldung statt der PV-Vorschau. Der fehlende Teil wird jetzt
        # benannt (P4), statt die ganze Antwort zu verweigern.
        hinweise.append(
            "Für die Verbrauchsprognose fehlt noch die Historie — dafür braucht "
            "eedc mindestens 3 vollständige Tage Energieprofil. Gezeigt wird "
            "deshalb nur die PV-Vorschau; Verbrauch, Netzbezug, Einspeisung, "
            "Eigenverbrauch, Autarkie und die Speicher-Vorschau bleiben leer, "
            "bis genug Tage aufgezeichnet sind."
        )

    # ── 2. PV-Stundenprofil ──
    pv_stunden = [0.0] * 24
    pv_quelle = "openmeteo"
    pv_profil_vorhanden = False

    # Versuche Solcast zuerst (wenn als Quelle gewählt)
    from backend.services.prognose_router import resolve_prognose_quelle
    pq = resolve_prognose_quelle(anlage)

    if pq.ist_solcast:
        try:
            from backend.services.solcast_service import get_solcast_forecast
            solcast = await get_solcast_forecast(anlage)
            # Seit #357 trägt Solcast ein eigenes Stundenprofil je Prognosetag
            # (HA-Integration: `detailedForecast` am Tages-Sensor; API: 168 h).
            # Wo es eins gibt, ist der Zieltag echt beantwortet — die Näherung
            # samt Kennzeichnung bleibt nur für Tage ohne eigenes Profil.
            tages_profil = solcast.profil_fuer(datum) if solcast else None
            if tages_profil is not None:
                pv_stunden = list(tages_profil.p50)
                pv_quelle = "solcast"
                pv_profil_vorhanden = True
            elif solcast and solcast.hourly_kw and len(solcast.hourly_kw) == 24:
                # `solcast.hourly_kw` ist das Stundenprofil von HEUTE. Für einen
                # anderen Zieltag ist es eine Näherung — bisher stand das nur als
                # Code-Kommentar, während die Antwort `pv_quelle = "solcast"`
                # meldete wie bei einem echten Profil dieses Tages (N79). Der Wert
                # bleibt (er ist die beste verfügbare Information), aber die
                # Antwort sagt jetzt, worauf man sieht.
                pv_stunden = list(solcast.hourly_kw)
                pv_quelle = "solcast"
                pv_profil_vorhanden = True
                if datum != date.today():
                    hinweise.append(
                        "Solcast liefert für diesen Tag nur die Tagesmenge, kein "
                        "eigenes Stundenprofil. Der Tagesverlauf ist deshalb das "
                        "heutige Profil als Näherung für den "
                        f"{datum.strftime('%d.%m.%Y')} — die Tagessumme kann "
                        "abweichen."
                    )
        except Exception as e:
            logger.warning("Solcast für Tagesprognose fehlgeschlagen: %s", e)
            hinweise.append(
                "Die Solcast-Prognose war nicht abrufbar; für den PV-Tagesverlauf "
                "liegt keine Solcast-Quelle vor."
            )

    # Fallback: OpenMeteo GTI — kanonischer Weg zuerst (Multi-String-Fan-out +
    # Korrektur pro Energie-Slot), damit Chart/Tabelle denselben Tag zeigen wie
    # Prognosen-Vergleich und HA-/MQTT-Export.
    kanon_stunden = (
        await _pv_stunden_aus_kanon(db, anlage, datum)
        if pv_quelle == "openmeteo" else None
    )
    if kanon_stunden is not None:
        pv_stunden = kanon_stunden
        pv_profil_vorhanden = True
    elif pv_quelle == "openmeteo":
        # Fallback (Kanon ohne Ergebnis: kein OpenMeteo, keine kWp, Zieltag
        # jenseits des Abrufs): eigener Abruf-Pfad, damit die Prognose nicht
        # ganz ausfällt. Seit `49954860` (P1/N51) fächert er wie der Kanon je
        # Orientierungsgruppe auf; was bleibt, ist der flache Legacy-Skalar
        # (`_get_lernfaktor`) statt der Kaskade pro Energie-Slot — deshalb
        # kann seine Tagessumme weiter leicht vom Kanon abweichen.
        try:
            from backend.services.solar_forecast_service import get_solar_prognose

            # Strings für Multi-Ausrichtung laden
            inv_result = await db.execute(
                select(Investition).where(
                    Investition.anlage_id == anlage_id,
                    Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
                    Investition.aktiv.is_(True),
                )
            )
            invs = inv_result.scalars().all()
            # Nur die am Zieltag aktiven Investitionen — Anschaffung UND
            # Stilllegung (`ist_aktiv_an`). Bis 04.10.2026 prüfte dieser Pfad nur
            # die Stilllegung: ein String mit Anschaffungsdatum nach dem Zieltag
            # ging schon mit seiner kWp in die Prognose ein (gemessen über
            # `get_tagesprognose` mit gestellter Wetterprognose: Gruppen 6 + 4
            # statt 6 kWp, der 4-kWp-String kommt erst in fünf Tagen). Der Kanon
            # darüber filtert je Tag schon so (`prognose_kanon`).
            aktive_invs = [inv for inv in invs if inv.ist_aktiv_an(datum)]

            if aktive_invs:
                # Einheitlich kWp + Neigung + Azimut aus Top-Level-Spalten ODER
                # parameter-JSON lesen — je nachdem, wo das Formular die Werte
                # gespeichert hat. Ohne den Helper fallen Prognose-Pfade stumm
                # auf Neigung=35°/Azimut=0° zurück, wenn die Werte nur in den
                # Top-Level-Spalten (Investition.neigung_grad, .ausrichtung)
                # liegen statt im parameter-JSON.
                from backend.services.pv_orientation import (
                    orientierungs_gruppen, resolve_system_losses,
                )
                from backend.services.prognose_auswahl import lade_aktive_prognose

                # P1 (N51): EIN Abruf je Orientierungsgruppe statt eines Abrufs
                # über die Gesamt-kWp mit der Orientierung der zufällig ersten
                # Investition (`aktive_invs[0]`, Query ohne `ORDER BY`). Eine
                # Ost/West-Anlage bekam so den Tagesgang EINER Himmelsrichtung
                # auf die volle Leistung gerechnet — bei ausgeglichener
                # Verteilung ein Fehler in der Summenzeile, der sich NICHT
                # herausmittelt. Der Kanon-Pfad darüber fächert längst auf; hier
                # lief der Fallback als einzige Sicht daneben.
                # Bei genau EINER Gruppe ist der eine Abruf die korrekte Form —
                # dann ist bewiesen, dass alle Module dieselbe Orientierung
                # haben (dieselbe Guard-Form wie prefetch_service/solar_prognose).
                gruppen = orientierungs_gruppen(aktive_invs)

                # system_losses aus aktuellem PVGIS-Eintrag (gleicher Pfad wie
                # solar_prognose.py und prefetch_service.py). Es gibt KEIN
                # system_losses-Attribut auf Anlage — der frühere Zugriff
                # `anlage.system_losses` warf einen AttributeError, der im
                # try/except geschluckt wurde und pv_stunden auf [0] * 24 ließ.
                pvgis = await lade_aktive_prognose(db, anlage_id)
                system_losses = resolve_system_losses(pvgis)

                # Tage bis zum Zieldatum berechnen
                tage_bis_ziel = (datum - date.today()).days
                forecast_days = max(tage_bis_ziel + 1, 2)

                ergebnisse = await asyncio.gather(*[
                    get_solar_prognose(
                        latitude=anlage.latitude,
                        longitude=anlage.longitude,
                        kwp=g.kwp,
                        neigung=g.neigung,
                        ausrichtung=g.ausrichtung,
                        days=forecast_days,
                        system_losses=system_losses,
                        # Interaktiver User-Request (Stunden-/Tagesprognose der
                        # Aussicht): der 1-30s-Random-Jitter gilt nur für
                        # Hintergrund-Abrufe (R18-13).
                        skip_jitter=True,
                    )
                    for g in gruppen
                ])

                ziel_str = datum.isoformat()
                summe = [0.0] * 24
                geliefert = 0
                for prognose in ergebnisse:
                    if not prognose:
                        continue
                    for tag in prognose.tageswerte:
                        if tag.datum == ziel_str and tag.stunden_kw:
                            for i, v in enumerate(tag.stunden_kw[:24]):
                                summe[i] += v or 0.0
                            geliefert += 1
                            break

                if geliefert:
                    pv_stunden = [round(v, 3) for v in summe]
                    pv_profil_vorhanden = True

                    # P4: eine Teilsumme sagt es selbst. Fällt eine
                    # Orientierungsgruppe aus, fehlt ihr kWp-Anteil im
                    # Tagesverlauf — der Wert bleibt (beste verfügbare
                    # Information), aber nicht ungekennzeichnet.
                    if geliefert < len(gruppen):
                        hinweise.append(
                            f"Nur {geliefert} von {len(gruppen)} Dachflächen "
                            "(Orientierungsgruppen) haben eine Prognose geliefert. "
                            "Der PV-Tagesverlauf ist deshalb eine Teilsumme und zu "
                            "niedrig — bitte später erneut laden."
                        )

                    # Lernfaktor anwenden (MOS-Kaskade)
                    from backend.api.routes.live_wetter import _get_lernfaktor
                    lernfaktor = await _get_lernfaktor(anlage_id, db)
                    if lernfaktor is not None:
                        pv_stunden = [round(v * lernfaktor, 3) for v in pv_stunden]

        except Exception as e:
            logger.warning("PV-Prognose für Tagesprognose fehlgeschlagen: %s", e)

    # P4 (N78): Bis hierher konnte die Antwort mit der Vorbelegung `[0.0] * 24`
    # herauskommen — als PV-Prognose „0 kWh", nicht als „keine Prognose". Die
    # Speicher-Simulation unten rechnet mit diesen Nullen weiter und meldet dann
    # „Speicher lädt nicht". Die Zahlen bleiben (kein geschätzter Ersatz), aber
    # die Antwort sagt jetzt, dass sie keine Prognose sind.
    if not pv_profil_vorhanden:
        hinweise.append(
            "Für diesen Tag liegt keine PV-Prognose vor — der Wetterabruf ist "
            "ausgefallen oder der Tag liegt außerhalb des Prognose-Horizonts. Die "
            "PV-Werte im Verlauf sind deshalb 0 und bedeuten NICHT, dass die "
            "Anlage nichts erzeugt; auch die Speicher-Vorschau darunter ist damit "
            "ohne Aussage."
        )

    # ── 3. Batterie-Info laden ──
    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == InvestitionTyp.SPEICHER.value,
            Investition.aktiv.is_(True),
        )
    )
    speicher_invs = [
        inv for inv in inv_result.scalars().all()
        if not inv.stilllegungsdatum or inv.stilllegungsdatum >= datum
    ]

    # A31-2/E-1: NETTO-Kapazität. Die Simulation unten fährt den Speicher von
    # 0 auf 100 % der übergebenen Zahl; mit der Brutto-Kapazität ist er
    # rechnerisch später voll als real. Stiller Brutto-Fallback (E17) — bei
    # ungepflegtem Netto-Feld bleibt alles wie bisher, deshalb hier bewusst
    # KEIN `hinweise`-Eintrag.
    # N-238: Kapazität UND Wirkungsgrad über den geteilten Helper — der
    # HA-Sensor `eedc_speicher_voll_um` liest dieselbe Regel, und zwei
    # gleichlautende Faltungen wären genau die Drift-Klasse dieses Projekts.
    speicher_kap, speicher_eta = aggregiere_speicher_basis(speicher_invs)
    speicher_kap = speicher_kap or 0.0

    # Start-SoC: Ø SoC um Mitternacht der letzten 7 Tage
    start_soc = 50.0  # Default
    if speicher_kap > 0:
        soc_result = await db.execute(
            select(TagesEnergieProfil.soc_prozent)
            .where(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum >= datum - timedelta(days=7),
                TagesEnergieProfil.datum < datum,
                TagesEnergieProfil.stunde == 0,
                TagesEnergieProfil.soc_prozent.isnot(None),
            )
            .order_by(TagesEnergieProfil.datum.desc())
        )
        soc_werte = [r for r in soc_result.scalars().all()]
        if soc_werte:
            start_soc = sum(soc_werte) / len(soc_werte)

    # ── 4. Stündliche Bilanz + Batterie-Simulation ──
    # SoC-State-Machine + Bilanz-Rest liegen im Berechnungs-Layer (ADR-001).
    # Diese deskriptive Ganztags-Vorschau simuliert ab Mitternacht (start_soc =
    # 7-Tage-Mittel, start_stunde=0) — bewusst anders parametrisiert als der
    # HA-Export (ab aktuellem SoC), daher kein Symmetrie-Paar.
    stunden: list[StundenPrognose] = []
    sum_pv = 0.0
    sum_verbrauch: Optional[float] = None
    sum_netzbezug: Optional[float] = None
    sum_einspeisung: Optional[float] = None
    eigenverbrauch: Optional[float] = None
    autarkie: Optional[float] = None
    speicher_voll_um: Optional[str] = None
    speicher_leer_um: Optional[str] = None

    if verbrauch_stunden is None:
        # A28: ohne Verbrauchsprofil ist jede Bilanzgröße unbestimmt — die
        # Simulation liefe zwar durch (sie liest fehlende Slots als 0), würde
        # dann aber „Netzbezug 0, Autarkie 100 %" behaupten. Also gar nicht
        # rechnen und die Felder leer lassen (P4); das PV-Profil bleibt.
        sum_pv = sum(pv_stunden[:24])
        stunden = [
            StundenPrognose(
                stunde=h,
                pv_kw=round(pv_stunden[h] if h < len(pv_stunden) else 0.0, 3),
            )
            for h in range(24)
        ]
    else:
        sim = simuliere_speicher_tag(
            pv_stunden=pv_stunden,
            verbrauch_stunden=verbrauch_stunden,
            speicher_kap_kwh=speicher_kap,
            start_soc_prozent=start_soc,
            start_stunde=0,
            wirkungsgrad_prozent=speicher_eta,
        )
        speicher_voll_um = sim.speicher_voll_um
        speicher_leer_um = sim.speicher_leer_um

        sum_verbrauch = 0.0
        sum_netzbezug = 0.0
        sum_einspeisung = 0.0

        for b in sim.stunden_bilanz:
            sum_pv += b.pv_kwh
            sum_verbrauch += b.verbrauch_kwh
            sum_netzbezug += b.netzbezug_kwh
            sum_einspeisung += b.einspeisung_kwh

            stunden.append(StundenPrognose(
                stunde=b.stunde,
                pv_kw=round(b.pv_kwh, 3),
                verbrauch_kw=round(b.verbrauch_kwh, 3),
                netto_kw=round(b.netto_kwh, 3),
                netzbezug_kw=round(b.netzbezug_kwh, 3),
                einspeisung_kw=round(b.einspeisung_kwh, 3),
                soc_prozent=b.soc_prozent,
            ))

        # `eigenverbrauch` ist der PV-Eigenverbrauch (was die Anlage selbst nutzt,
        # inklusive der Speicherladung) — dieselbe Größe wie in
        # `core/berechnungen/tagesbilanz.py`, deshalb gleich benannt.
        eigenverbrauch = sum_pv - sum_einspeisung
        # N129: die Autarkie hat einen ANDEREN Zähler — den netzunabhängig
        # gedeckten Verbrauch. Bis 2026-07-28 stand hier der PV-Eigenverbrauch,
        # und weil der bei ladendem Speicher den Tagesverbrauch übersteigen kann,
        # meldete die Vorschau Autarkiegrade bis 125 %. Der Layer-SoT
        # (`kennzahlen.autarkie_prozent`) verzichtet ausdrücklich auf einen Cap
        # mit der Begründung „strukturell ≤ 100 %, weil Eigenverbrauch Teilmenge
        # des Gesamtverbrauchs ist" — diese Zusicherung gilt nur für den
        # richtigen Zähler. Ein Cap wäre hier die falsche Antwort gewesen: er
        # hätte 125 % auf 100 % gedrückt und den Fehler unsichtbar gemacht,
        # statt ihn zu beheben (ADR-001: Formel im Layer, nicht inline).
        autarkie = (
            autarkie_prozent(sum_verbrauch - sum_netzbezug, sum_verbrauch)
            if sum_verbrauch > 0 else 0.0
        )

    return TagesPrognoseResponse(
        datum=datum.isoformat(),
        stunden=stunden,
        pv_summe_kwh=round(sum_pv, 2),
        verbrauch_summe_kwh=round(sum_verbrauch, 2) if sum_verbrauch is not None else None,
        netzbezug_summe_kwh=round(sum_netzbezug, 2) if sum_netzbezug is not None else None,
        einspeisung_summe_kwh=round(sum_einspeisung, 2) if sum_einspeisung is not None else None,
        eigenverbrauch_kwh=round(eigenverbrauch, 2) if eigenverbrauch is not None else None,
        autarkie_prozent=round(autarkie, 1) if autarkie is not None else None,
        speicher_kapazitaet_kwh=round(speicher_kap, 1) if speicher_kap > 0 else None,
        speicher_voll_um=speicher_voll_um,
        speicher_leer_um=speicher_leer_um,
        verbrauch_basis=vp["basis"] if vp else None,
        pv_quelle=pv_quelle,
        daten_tage=vp["daten_tage"] if vp else None,
        hinweise=hinweise,
    )
