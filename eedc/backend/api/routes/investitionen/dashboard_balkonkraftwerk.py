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
from backend.services.monats_fakten import (
    BKW_ERZEUGUNG_ABGETRETEN,
    BKW_ERZEUGUNG_GEMESSEN,
    BKW_ERZEUGUNG_KWP_ANTEIL,
    bkw_beitrag_im_monat,
    lade_monats_fakten,
)
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.services.finanz_zeilen import ev_preis_je_monat
from backend.core.berechnungen import (
    abgetretene_bkw_ids,
    imd_typ_beitrag,
    eigenverbrauchsquote_prozent,
    speicher_wirkungsgrad,
    spezifischer_ertrag_kwh_kwp,
)
from backend.api.routes.investitionen.crud import InvestitionResponse
from backend.api.routes.investitionen.dashboard_basis import InvestitionMonatsdatenResponse

router = APIRouter()


#: N-664/N-671 (K4): woher die Erzeugung eines Monats kommt — aus den Monats-Fakten, wie im Cockpit. Seit N-724 stehen
#: die Werte mit der Rechnung in ``services/monats_fakten/ableitungen.py::bkw_beitrag_im_monat`` (Hub und T-Konto).
ERZEUGUNG_GEMESSEN = BKW_ERZEUGUNG_GEMESSEN
ERZEUGUNG_KWP_ANTEIL = BKW_ERZEUGUNG_KWP_ANTEIL
ERZEUGUNG_ABGETRETEN = BKW_ERZEUGUNG_ABGETRETEN


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
    #: N-664/N-671: aus den Monats-Fakten — der eigene Wert, sonst der kWp-Anteil am Anlagenzähler, 0 wenn an die
    #: Modul-Kinder abgetreten (bis K4: die eigene Zeile des Geräts, ``ImdTypBeitrag.bkw_erzeugung``)
    erzeugung_kwh: float
    #: ``gemessen`` · ``kwp_anteil`` (geschätzt, nicht gemessen) · ``abgetreten``
    erzeugung_quelle: str = ERZEUGUNG_GEMESSEN
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

    **N-664 / N-671 (K4, Entscheid Gernot 10.10.2026: „BKW-Hub sollte mit den anderen Hubs verfahren"):** Kopf und
    Monatsreihe lesen die Erzeugung aus den Monats-Fakten, wie das Cockpit — nicht mehr aus der Zeile des Geräts. Ein
    BKW ohne eigenen Zähler bekam dort keinen Monat (Kopf 0, „Keine Verlaufsdaten"), während die Fakten ihm seinen
    kWp-Anteil am Anlagenzähler geben; ein an Modul-Kinder abgetretenes BKW zeigte seinen Zähler (90 kWh), die Fakten
    führen es mit 0. Je Monat: eigener Wert (``bkw.erzeugung_je_investition``), sonst der Anteil
    (``erzeugung.bkw_aus_anlagenwert_je_investition``, Kennzeichen ``kwp_anteil``), abgetreten 0. Der gemessene
    Eigenverbrauch des Geräts gilt wie in der Faltung der Fakten nur ohne beides (P9-Zusatzregel, ``roh.py``).
    """
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    alle_investitionen = list(inv_result.scalars().all())
    balkonkraftwerke = [
        i for i in alle_investitionen if i.typ == InvestitionTyp.BALKONKRAFTWERK.value
    ]

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
    # ADR-002/P11 je Monat (Zeitfilter → Selektor), dieselbe Regel wie `monats_fakten/laden.py`.
    abgetreten_cache: dict[tuple[int, int], frozenset] = {}

    def abgetreten_im_monat(jahr: int, monat: int) -> frozenset:
        if (jahr, monat) not in abgetreten_cache:
            abgetreten_cache[(jahr, monat)] = abgetretene_bkw_ids(
                [i for i in alle_investitionen if i.ist_aktiv_im_monat(jahr, monat)]
            )
        return abgetreten_cache[(jahr, monat)]

    # ⭐ N-724 (12.10.2026, Entscheid Master): der Preis der Ersparnis ist der EV-Preis des Monats — derselbe, mit dem die
    # Eigenverbrauchs-Ersparnis der Anlage und die Zeile „Balkon" im T-Konto rechnen (ADR-002/P9: der BKW-Eigenverbrauch
    # zählt wie Eigenverbrauch; A-2/N-607: mit gemessenem EV-Ø der Preis der vermiedenen Stunden). Bis dahin stand hier
    # der Bezugspreis der Monats-Fakten (gemessen: Hub 8,57 € gegen T-Konto 2,14 € bei EV-Ø 10 ct, Bezug 40 ct).
    _bkw_monate = {
        (md.jahr, md.monat) for lst in md_by_inv.values() for md in lst
    } | {k for k, f in fakten_je_monat.items() if f.erzeugung.bkw_aus_anlagenwert_je_investition}
    ev_preis_je_schluessel = (
        await ev_preis_je_monat(
            db, anlage_id,
            [(j, m, fakten_je_monat[(j, m)].meta.monatsdaten) for (j, m) in sorted(_bkw_monate)
             if (j, m) in fakten_je_monat],
            tarif_cache={},
        )
        if strompreis_cent is None else {}
    )

    dashboards = []
    for bkw in balkonkraftwerke:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(bkw.id, [])
            if bkw.ist_aktiv_im_monat(md.jahr, md.monat)
        ]
        md_je_monat = {(md.jahr, md.monat): md for md in monatsdaten}

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
        # N-664: davon der kWp-Anteil am Anlagenzähler (geschätzt) · N-671: Monate, in denen die Modul-Kinder tragen.
        erzeugung_aus_anlagenwert = 0.0
        monate_abgetreten = 0
        # N-724: die Erzeugung der Monate mit bewertbarem Eigenverbrauch — Nenner der Quote.
        erzeugung_bewertbar = 0.0

        # Die Monate der Reihe: jede eigene Zeile des Geräts und jeder Monat, in dem die Fakten ihm einen Anteil am
        # Anlagenwert geben (ein BKW ohne eigenen Zähler hat keine Zeile, N-664). Chronologisch wie die Fakten.
        monate = sorted(
            set(md_je_monat)
            | {
                k for k, f in fakten_je_monat.items()
                if bkw.id in f.erzeugung.bkw_aus_anlagenwert_je_investition and bkw.ist_aktiv_im_monat(*k)
            }
        )
        for schluessel in monate:
            md = md_je_monat.get(schluessel)
            d = (md.verbrauch_daten or {}) if md is not None else {}
            # Kanonische Auflösung statt Literal-Schlüsseln (ADR-002/P6) — für die BKW-eigenen Felder, die die
            # Schicht nicht je Gerät führt (gemessener Eigenverbrauch, Speicher, gespeicherte Einspeisung).
            beitrag = imd_typ_beitrag(bkw, d)
            fakt = fakten_je_monat.get(schluessel)
            # N-724: Erzeugung, Herkunft und beide Eigenverbrauchs-Anteile aus der EINEN Stelle, die auch die Zeile
            # „Balkon" im T-Konto von Cockpit → Monat rechnet. P9-Zusatzregel wie in der Faltung der Fakten
            # (`roh.py::falte`): ein abgetretenes BKW und ein Empfänger des Anlagenwerts tragen keinen eigenen
            # Ersatz-Eigenverbrauch und keine eigene Einspeisung.
            bm = bkw_beitrag_im_monat(
                bkw.id, fakt,
                zeile_erzeugung_kwh=beitrag.bkw_erzeugung,
                zeile_eigenverbrauch_kwh=beitrag.bkw_eigenverbrauch,
                abgetreten=bkw.id in abgetreten_im_monat(*schluessel),
            )
            erzeugung, quelle = bm.erzeugung_kwh, bm.erzeugung_quelle
            eigene_zeile_traegt = bm.eigene_zeile_traegt
            ev_gemessen = bm.eigenverbrauch_gemessen_kwh
            if quelle == ERZEUGUNG_KWP_ANTEIL:
                erzeugung_aus_anlagenwert += erzeugung
            elif quelle == ERZEUGUNG_ABGETRETEN:
                monate_abgetreten += 1
            gesamt_erzeugung += erzeugung
            gesamt_eigenverbrauch += ev_gemessen
            gesamt_speicher_ladung += beitrag.bkw_speicher_ladung
            gesamt_speicher_entladung += beitrag.bkw_speicher_entladung

            # N-588 (Entscheid Master 10.10.2026, F-1 (A)): zwei Anteile. Der Bilanz-Anteil trägt Eigenverbrauch,
            # Einspeisung und Monatsreihe des Hubs (F2: die Bilanz trägt die Wandlungsverluste); Ersparnis und CO₂
            # bewerten den Anteil am Eigenverbrauch OHNE die Verluste, wenn der Messpunkt-Vertrag hält — sonst
            # sind beide gleich.
            anteil, anteil_bewertet = bm.anteil, bm.anteil_bewertet
            if not anteil.bewertbar and erzeugung > 0:
                ev_monate_nicht_bewertbar += 1
            ev_bewertet_kwh += anteil.kwh
            eigenverbrauch_ohne_verluste_bkw_kwh += anteil_bewertet.kwh
            # P8: der Preis DIESES Monats, nicht der heutige — ein Tarifwechsel
            # hätte sonst die ganze Historie rückwirkend neu bewertet.
            preis_cent = (
                strompreis_cent
                if strompreis_cent is not None
                else ev_preis_je_schluessel.get(
                    schluessel, fakt.tarif.netzbezug_preis_cent if fakt else NETZBEZUG_DEFAULT_CENT)
            )
            ersparnis_eigenverbrauch += anteil_bewertet.kwh * preis_cent / 100
            monatswert = _monatswert(
                schluessel, d if eigene_zeile_traegt else {}, beitrag, anteil, erzeugung, quelle,
            )
            monatsreihe.append(monatswert)
            # N-724: Kopf = Σ Reihe. Die Einspeisung und der Nenner der Quote zählen nur die Monate, deren Reihe einen
            # Wert trägt — ein Monat ohne Zählerzeile ist „nicht bewertbar" (P4), seine Erzeugung keine Einspeisung.
            if monatswert.einspeisung_kwh is not None:
                gesamt_einspeisung += monatswert.einspeisung_kwh
            if monatswert.eigenverbrauch_kwh is not None:
                erzeugung_bewertbar += erzeugung

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

        # N-724 (12.10.2026): die Einspeisung ist Σ der Monatsreihe (oben je Monat aufsummiert) — gemessen, wo eine
        # gespeichert ist, sonst Erzeugung − bewerteter Eigenverbrauch des Monats; Monate ohne Zählerzeile tragen
        # nichts. Bis dahin stand hier `Σ Erzeugung − Σ EV` über ALLE Monate, sobald keine Einspeisung gespeichert
        # war (Kopf 75,1 gegen Σ Reihe 15,1), und eine gespeicherte in EINEM Monat verdrängte die abgeleitete der
        # übrigen (Kopf 10,0 gegen 25,1).
        #
        # Eigenverbrauchsquote — auf der BEWERTETEN Menge und über die Monate, in denen sie bewertbar ist: sonst
        # teilt der Eigenverbrauch eines Monats durch die Erzeugung eines anderen (28,5 % gegen 66,5 %).
        eigenverbrauch_quote = eigenverbrauchsquote_prozent(ev_bewertet_kwh, erzeugung_bewertbar)

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
            # N-664: davon nicht gemessen, sondern der kWp-Anteil am Anlagenzähler — das Kennzeichen „geschätzt".
            'erzeugung_aus_anlagenwert_kwh': round(erzeugung_aus_anlagenwert, 1),
            # N-671: Monate, deren Erzeugung bei den Modul-Kindern steht (der Hub zeigt dort 0, wie die Fakten).
            'monate_abgetreten': monate_abgetreten,
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


def _monatswert(schluessel, d: dict, beitrag, anteil, erzeugung: float, quelle: str) -> BkwMonatsWert:
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
        einsp_kwh = max(0.0, erzeugung - ev_kwh)
        einsp_quelle = "abgeleitet"
    else:
        einsp_kwh, einsp_quelle = None, None
    return BkwMonatsWert(
        jahr=schluessel[0],
        monat=schluessel[1],
        erzeugung_kwh=erzeugung,
        erzeugung_quelle=quelle,
        eigenverbrauch_kwh=ev_kwh,
        eigenverbrauch_quelle=anteil.quelle,
        einspeisung_kwh=einsp_kwh,
        einspeisung_quelle=einsp_quelle,
        speicher_ladung_kwh=beitrag.bkw_speicher_ladung,
        speicher_entladung_kwh=beitrag.bkw_speicher_entladung,
    )
