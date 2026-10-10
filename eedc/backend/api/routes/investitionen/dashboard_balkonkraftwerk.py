"""Komponenten-Dashboard Balkonkraftwerk.

GET /api/investitionen/dashboard/balkonkraftwerk/{anlage_id}
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.core.investition_kennwerte import ANZAHL_LESE_DEFAULT, get_bkw_kwp
from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
from backend.services.monats_fakten import lade_monats_fakten
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.core.berechnungen import (
    eigenverbrauch_ohne_verluste_kwh,
    bkw_eigenverbrauch_anteil,
    imd_typ_beitrag,
    eigenverbrauchsquote_prozent,
    speicher_wirkungsgrad,
    spezifischer_ertrag_kwh_kwp,
)
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse

router = APIRouter()


class BkwMonatsWert(BaseModel):
    """Ein Monat des Balkonkraftwerks, so wie die Kopfzahlen ihn rechnen (N-638).

    Der Hub-Verlauf las bis 4.1.3 die rohen ``verbrauch_daten`` — die Erzeugung unter
    einem Schlüssel, den das BKW nicht trägt (``erzeugung_kwh`` statt
    ``pv_erzeugung_kwh``, immer 0), Eigenverbrauch und Einspeisung nur aus Handpflege.
    Die Kopfzahlen rechneten daneben je Monat bewertet. Diese Reihe ist dieselbe
    Rechnung je Monat; Σ Monate = Kopfzahl (``gesamt_erzeugung_kwh``,
    ``gesamt_eigenverbrauch_kwh``).

    ``None`` heißt „nicht ableitbar" (ADR-002/P4), nicht 0: ohne Zählerzeile gibt es
    keine Hausbilanz, aus der ein Eigenverbrauch folgen könnte.
    """
    jahr: int
    monat: int
    #: aufgelöst (``ImdTypBeitrag.bkw_erzeugung``, beide Schreibweisen)
    erzeugung_kwh: float
    #: ``bkw_eigenverbrauch_anteil`` — ``None`` bei ``nicht_bewertbar``
    eigenverbrauch_kwh: Optional[float]
    #: ``gemessen`` · ``anteilig`` · ``nicht_bewertbar``
    eigenverbrauch_quelle: str
    #: gemessen, sonst Erzeugung − Eigenverbrauch (nie < 0); ``None`` ohne beides
    einspeisung_kwh: Optional[float]
    #: ``gemessen`` · ``abgeleitet`` · ``None``
    einspeisung_quelle: Optional[str]
    #: BKW-eigene Speicherfelder, unverändert (Altbestand, ``nur_manuell``)
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float


class BalkonkraftwerkDashboardResponse(BaseModel):
    """Balkonkraftwerk Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    #: N-638: die bewertete Monatsreihe — Hub-Verlauf und -Vergleich lesen sie statt
    #: ``monatsdaten[].verbrauch_daten``.
    monatsreihe: list[BkwMonatsWert] = []
    zusammenfassung: dict[str, Any]

@router.get("/dashboard/balkonkraftwerk/{anlage_id}", response_model=list[BalkonkraftwerkDashboardResponse])
async def get_balkonkraftwerk_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(
        None, description="Override: Strompreis (auto aus dem Monatstarif wenn leer)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Balkonkraftwerk Dashboard für eine Anlage.

    ⛔ **N-114 (05.09.2026): kein Vergütungs-Query-Parameter mehr.** Er stand seit
    F-4 in der Signatur und wurde nie gelesen — die Route rechnet ausdrücklich
    mit `erloes_einspeisung = 0` (BKW-Einspeisung ist unvergütet). Eine API, die
    einen Satz anbietet, den sie nicht verwendet, behauptet das Gegenteil dessen,
    was sie tut. Ersatzlos entfernt, nicht verdrahtet.

    Zeigt Balkonkraftwerke mit Erzeugung, Eigenverbrauch, Ersparnis.

    **Befund F-4 der Drift-Inventur 2026-07-31**, hier behoben — die Sicht
    bewertete zweimal an der Wirklichkeit vorbei:

    (a) ``strompreis_cent`` war ein **Pflicht-Query mit Default 30,0**, und
    keiner der beiden Frontend-Aufrufer (``v4/komponentenAdapter.tsx``,
    ``v4/BkwHubBloecke.tsx``) übergab je einen Preis — der Default griff also
    immer, unabhängig vom gepflegten Tarif. Jetzt kommt der Preis je Monat aus
    den Monats-Fakten (ADR-002/**P8**) und wird mit dem Eigenverbrauch des
    jeweiligen Monats gewichtet; der Query-Parameter bleibt als Override.

    (b) Bewertet wurde der **gemessene** ``eigenverbrauch_kwh``. Der ist im
    Normalfall 0 — beim Balkonkraftwerk ist ``pv_erzeugung_kwh`` das
    Pflichtfeld und das einzige, das Sensor-/MQTT-Pfad schreiben können. Der
    Hub zeigte deshalb **0 € Ersparnis**, während das Cockpit dieselbe Energie
    seit ``0faad16b`` (ADR-002/**P9**) korrekt bewertet. Jetzt entscheidet
    ``bkw_eigenverbrauch_anteil`` (ADR-001, ``core/berechnungen/bkw_finanz.py``)
    je Monat: gemessener EV bei fehlender Erzeugung, sonst der Anteil an der
    Hausbilanz — und **nicht bewertbar**, wo mangels Zählerzeile keine Bilanz
    existiert (P4), statt still 0 €.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.BALKONKRAFTWERK.value)
    )
    balkonkraftwerke = inv_result.scalars().all()

    if not balkonkraftwerke:
        return []

    # Batch-Query: Alle Monatsdaten für alle BKW auf einmal laden
    bkw_ids = [b.id for b in balkonkraftwerke]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(bkw_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Anlagen-Kontext je Monat aus der EINEN Aufbereitung (ADR-002/P10):
    # Hausbilanz-Eigenverbrauch, Erzeugung hinter dem Zähler und der Tarif, der
    # in DIESEM Monat galt. Die BKW-eigenen Mengen bleiben per-Investition —
    # dafür hat die Schicht bewusst keine Sicht (Register N-2).
    fakten_je_monat = {
        f.schluessel: f for f in await lade_monats_fakten(db, anlage_id)
    }

    dashboards = []
    for bkw in balkonkraftwerke:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(bkw.id, [])
            if bkw.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_speicher_ladung = 0
        gesamt_speicher_entladung = 0
        # F-4: die bewertete Menge und ihr Preis, beide je Monat aufgelöst.
        ev_bewertet_kwh = 0.0
        # N-588: dieselbe Menge ohne die bewertbaren Wandlungsverluste — Eingang von Ersparnis und CO₂.
        eigenverbrauch_ohne_verluste_bkw_kwh = 0.0
        ersparnis_eigenverbrauch = 0.0
        ev_monate_nicht_bewertbar = 0
        monatsreihe: list[BkwMonatsWert] = []

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # Kanonische Auflösung statt Literal-Schlüsseln (ADR-002/P6):
            # `imd_typ_beitrag` kennt beide Schreibweisen der Erzeugung.
            beitrag = imd_typ_beitrag(bkw, d)
            gesamt_erzeugung += beitrag.bkw_erzeugung
            gesamt_eigenverbrauch += beitrag.bkw_eigenverbrauch
            gesamt_speicher_ladung += beitrag.bkw_speicher_ladung
            gesamt_speicher_entladung += beitrag.bkw_speicher_entladung
            gesamt_einspeisung += d.get('einspeisung_kwh', 0) or 0

            fakt = fakten_je_monat.get((md.jahr, md.monat))
            ev_anlage = fakt.kennzahlen.eigenverbrauch_kwh if fakt else 0.0
            anteil = bkw_eigenverbrauch_anteil(
                bkw_erzeugung_kwh=beitrag.bkw_erzeugung,
                bkw_eigenverbrauch_gemessen_kwh=beitrag.bkw_eigenverbrauch,
                erzeugung_hinter_zaehler_kwh=(
                    fakt.erzeugung.hinter_zaehler_kwh if fakt else 0.0
                ),
                eigenverbrauch_gesamt_kwh=ev_anlage,
                hat_zaehlerzeile=bool(fakt and fakt.meta.hat_zaehlerzeile),
            )
            # N-588 (Entscheid Master 10.10.2026, F-1 (A)): zwei Anteile. Der Bilanz-Anteil oben trägt Eigenverbrauch,
            # Einspeisung und Monatsreihe des Hubs (F2: die Bilanz trägt die Wandlungsverluste); Ersparnis und CO₂
            # bewerten den Anteil am Eigenverbrauch OHNE die Verluste, wenn der Messpunkt-Vertrag hält — sonst
            # sind beide gleich.
            anteil_bewertet = bkw_eigenverbrauch_anteil(
                bkw_erzeugung_kwh=beitrag.bkw_erzeugung,
                bkw_eigenverbrauch_gemessen_kwh=beitrag.bkw_eigenverbrauch,
                erzeugung_hinter_zaehler_kwh=(
                    fakt.erzeugung.hinter_zaehler_kwh if fakt else 0.0
                ),
                eigenverbrauch_gesamt_kwh=(
                    eigenverbrauch_ohne_verluste_kwh(
                        ev_anlage, fakt.erzeugung.wandlungsverluste_kwh, fakt.erzeugung.verluste_grund,
                    ) if fakt else 0.0
                ),
                hat_zaehlerzeile=bool(fakt and fakt.meta.hat_zaehlerzeile),
            )
            if not anteil.bewertbar and beitrag.bkw_erzeugung > 0:
                ev_monate_nicht_bewertbar += 1
            ev_bewertet_kwh += anteil.kwh
            eigenverbrauch_ohne_verluste_bkw_kwh += anteil_bewertet.kwh
            # P8: der Preis DIESES Monats, nicht der heutige — ein Tarifwechsel
            # hätte sonst die ganze Historie rückwirkend neu bewertet.
            preis_cent = (
                strompreis_cent
                if strompreis_cent is not None
                else (fakt.tarif.netzbezug_preis_cent if fakt else NETZBEZUG_DEFAULT_CENT)
            )
            ersparnis_eigenverbrauch += anteil_bewertet.kwh * preis_cent / 100
            monatsreihe.append(_monatswert(md, d, beitrag, anteil))

        # Parameter
        params = bkw.parameter or {}
        leistung_wp = params.get('leistung_wp', 0)
        # Lese-Default 1 (`ANZAHL_LESE_DEFAULT`), nicht die Formular-Vorbelegung 2:
        # ein BKW ohne gepflegte `anzahl` wurde hier mit DOPPELTER Leistung und
        # damit halbem spez. Ertrag ausgewiesen (N-D).
        anzahl = params.get('anzahl') or ANZAHL_LESE_DEFAULT
        hat_speicher = params.get('hat_speicher', False)
        speicher_kapazitaet = params.get('speicher_kapazitaet_wh', 0)

        # Berechnungen — kWp über den SoT-Helper (ADR-002/P3-a). Die frühere
        # Formel hatte die Priorität UMGEKEHRT (`parameter` vor Spalte) und
        # ignorierte damit den vom Formular gepflegten Spaltenwert.
        gesamt_leistung_wp = get_bkw_kwp(bkw) * 1000

        # Einspeisung berechnen falls nicht explizit erfasst
        # Einspeisung = Erzeugung - Eigenverbrauch (unvergütet ins Netz).
        # Auf der BEWERTETEN Menge, wie Quote und CO₂ — sonst stünde hier 0 kWh
        # Einspeisung neben einer Eigenverbrauchsquote von 70 %.
        if gesamt_einspeisung == 0 and gesamt_erzeugung > 0 and ev_bewertet_kwh > 0:
            gesamt_einspeisung = max(0, gesamt_erzeugung - ev_bewertet_kwh)

        # Eigenverbrauchsquote — auf der BEWERTETEN Menge, nicht auf dem
        # gemessenen Feld: sonst nennt die Kachel 0 % neben einer Ersparnis > 0.
        eigenverbrauch_quote = eigenverbrauchsquote_prozent(ev_bewertet_kwh, gesamt_erzeugung)

        # Speicher-Effizienz über den Layer-SoT (N-252) — der integrierte
        # Speicher eines BKW rechnet nach derselben Regel wie jeder andere.
        _eta_bkw = speicher_wirkungsgrad(
            gesamt_speicher_ladung, gesamt_speicher_entladung, None,
            langes_fenster_quelle="fenster_lang",
        )
        speicher_effizienz = _eta_bkw.prozent

        # `ersparnis_eigenverbrauch` steht bereits — je Monat aus
        # `bkw_eigenverbrauch_anteil` × Monatstarif (s. Docstring, F-4).
        # Einspeisung bei BKW ist i.d.R. unvergütet (keine Einspeisevergütung ohne Anmeldung)
        # Wird nur als Info angezeigt, nicht als Erlös
        erloes_einspeisung = 0  # BKW-Einspeisung ist unvergütet
        gesamt_ersparnis = ersparnis_eigenverbrauch

        # CO2-Einsparung für Eigenverbrauch — dieselbe Menge wie die Ersparnis.
        # Der Kanon rechnet CO₂-PV auf dem EIGENVERBRAUCH (`berechne_co2_bilanz`,
        # DI-2); eingespeister Strom ist nicht die eigene Ersparnis.
        co2_ersparnis = eigenverbrauch_ohne_verluste_bkw_kwh * CO2_FAKTOR_STROM_KG_KWH

        # Spezifischer Ertrag (kWh pro kWp)
        spezifischer_ertrag = spezifischer_ertrag_kwh_kwp(
            gesamt_erzeugung, gesamt_leistung_wp / 1000 if gesamt_leistung_wp > 0 else 0
        ) or 0

        zusammenfassung = {
            'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
            # Die BEWERTETE Menge (F-4): gemessen, wo gemessen wurde, sonst der
            # Anteil an der Hausbilanz. Der rohe Messwert steht daneben, damit
            # eine Pflege-Lücke sichtbar bleibt statt als 0 zu verschwinden.
            'gesamt_eigenverbrauch_kwh': round(ev_bewertet_kwh, 1),
            'eigenverbrauch_gemessen_kwh': round(gesamt_eigenverbrauch, 1),
            # P4: Monate mit Erzeugung, für die mangels Zählerzeile keine
            # Hausbilanz existiert — dort ist die Ersparnis nicht 0, sondern
            # unbekannt, und das Frontend darf das sagen.
            'monate_nicht_bewertbar': ev_monate_nicht_bewertbar,
            'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),  # Berechnet: unvergütet ins Netz
            'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
            'spezifischer_ertrag_kwh_kwp': round(spezifischer_ertrag, 0),
            # Leistung
            'leistung_wp': gesamt_leistung_wp,
            'anzahl_module': anzahl,
            # Speicher (falls vorhanden)
            'hat_speicher': hat_speicher,
            'speicher_kapazitaet_wh': speicher_kapazitaet,
            'speicher_ladung_kwh': round(gesamt_speicher_ladung, 1) if hat_speicher else 0,
            'speicher_entladung_kwh': round(gesamt_speicher_entladung, 1) if hat_speicher else 0,
            'speicher_effizienz_prozent': (
                round(speicher_effizienz, 1)
                if hat_speicher and speicher_effizienz is not None else None
            ),
            'speicher_effizienz_quelle': _eta_bkw.quelle if hat_speicher else None,
            # Finanzen
            'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
            'erloes_einspeisung_euro': round(erloes_einspeisung, 2),  # 0 bei BKW (unvergütet)
            'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
            # CO2
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(BalkonkraftwerkDashboardResponse(
            investition=bkw,
            monatsdaten=monatsdaten,
            monatsreihe=monatsreihe,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


def _monatswert(md, d: dict, beitrag, anteil) -> BkwMonatsWert:
    """Ein Monat der Reihe aus denselben Werten, die die Kopfzahlen summieren (N-638).

    Eigenverbrauch und seine Quelle kommen unverändert aus ``bkw_eigenverbrauch_anteil``
    (ADR-001-SoT, ``core/berechnungen/bkw_finanz.py``). Die Einspeisung ist die
    gemessene der Zeile, wo eine steht (Altbestand/Import — das BKW hat kein solches
    Erfassungsfeld); sonst der Rest der Erzeugung nach dem Eigenverbrauch, wie die
    Kopfzahl ihn bildet. Ist der Eigenverbrauch nicht bewertbar, ist es dieser Rest
    auch — ``None`` statt einer Erzeugung, die als Einspeisung ausgegeben würde (P4).
    """
    ev_kwh = anteil.kwh if anteil.quelle != "nicht_bewertbar" else None
    einsp_gemessen = d.get("einspeisung_kwh")
    if einsp_gemessen is not None:
        einsp_kwh: Optional[float] = float(einsp_gemessen)
        einsp_quelle: Optional[str] = "gemessen"
    elif ev_kwh is not None:
        einsp_kwh = max(0.0, beitrag.bkw_erzeugung - ev_kwh)
        einsp_quelle = "abgeleitet"
    else:
        einsp_kwh, einsp_quelle = None, None
    return BkwMonatsWert(
        jahr=md.jahr,
        monat=md.monat,
        erzeugung_kwh=beitrag.bkw_erzeugung,
        eigenverbrauch_kwh=ev_kwh,
        eigenverbrauch_quelle=anteil.quelle,
        einspeisung_kwh=einsp_kwh,
        einspeisung_quelle=einsp_quelle,
        speicher_ladung_kwh=beitrag.bkw_speicher_ladung,
        speicher_entladung_kwh=beitrag.bkw_speicher_entladung,
    )
