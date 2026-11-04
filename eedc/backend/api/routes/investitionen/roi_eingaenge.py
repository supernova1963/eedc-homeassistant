"""ROI-Dashboard — die Eingaenge: Anlage, Tarife (Ø-Jahreswert nach vorn, ADR-002/P8), Investitionen, Benzinpreis-Lookup,
sonstige Ertraege/Ausgaben je Investition und anlagenweit (P10), die Kalender-Anker der Treppe (N-525) samt der Closures,
die die Phasen dafuer aufrufen.
"""
# Vorlage 5b des Refactorings grosser Dateien (18.09.2026): Phasen des Endpunkts
# `roi.py::get_roi_dashboard` byte-identisch als Funktionen, Schnittstelle als Schluesselwort-
# Parameter und Rueckgabe-Dict; der Endpunkt orchestriert. Kein Verhaltenswechsel — Gate ist
# `plans/skript-golden-master-investitionen.py` (alte gegen neue Antworten, bitgleich).
# ⚠ Dieses Modul importiert Helfer und Schemas aus `roi.py`; `roi.py` importiert die Phasen
# deshalb erst IM Endpunkt (sonst Importzyklus) — dieselbe Bauform wie die Lazy-Importe der
# Energieprofil-Routen.

from typing import Optional
from sqlalchemy import select
from backend.core.exceptions import not_found
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_im_jahr, sort_investitionen_nach_typ
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import PARAM_E_AUTO_DEFAULTS
from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT
from backend.services.eauto_wirtschaftlichkeit import letzter_kraftstoffpreis_aus_lookup
from backend.services.monats_fakten import ist_pv_ladeanteil_prozent, lade_monats_fakten
from backend.core.berechnungen.kapitalrechnung import ErsparnisZeile, KapitalEreignis
from backend.utils.sonstige_positionen import berechne_sonstige_summen


async def lade_roi_eingaenge(*, anlage_id, db, einspeiseverguetung_cent, jahr, strompreis_cent):
    """Der Kopf des ROI-Dashboards: laedt Anlage, Tarife, Investitionen, Benzinpreise, sonstige Positionen und die
    Monats-Fakten; liefert die Closures fuer den IST-PV-Ladeanteil, die kumulierten sonstigen Positionen und die
    Kalender-Treppe.

    Aus `get_roi_dashboard` Zeilen 714-944 (Stand vor dem Umzug) byte-identisch herausgeloest — Vorlage 5b.

    RF-46 (4.11.2026, Bauform RF-1): Orchestrator über Phasen — `_ist_pv_ladeanteil_einmal` (Closure, N-188),
    `_tarifpreise` (Strom aus Tarif, Einspeisung `is not None`, #392, WP-/Wallbox-Tarif), `_kraftstoffpreise`,
    `_buche_sonstige` (je Zeile der sonstigen Positionen), `_anlagenweite_positionen` (Monats-Fakten, P10) und
    `_kalender_treppe` (Basisjahr, Treppen-Closure, anlagenweite Kapital-Ereignisse; N-525). Der Tarif-Lader und
    der `InvestitionMonatsdaten`-Lader bleiben HIER — unter diesem Namen stehen sie in `P8_BASELINE_AUSNAHMEN`
    und `P10_PER_INVESTITION` (test_wurzelmuster_konformitaet.py). Reihenfolge der Abfragen und die 18
    Rückgabe-Schlüssel unverändert.
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # N-188: der IST-PV-Anteil der Heimladung als Prognose-Vorbelegung.
    # **Höchstens einmal je Request** — die Fakten-Schicht ist nicht billig, und
    # die E-Auto-Schleife weiter unten läuft je Fahrzeug. `False` ist der „noch
    # nicht geholt"-Marker, weil `None` selbst eine Antwort ist („keine
    # Heimladung im Zeitraum") und ein zweiter Anlauf sie nur wiederholen würde.
    _ist_pv_ladeanteil = _ist_pv_ladeanteil_einmal(db, anlage_id, jahr)

    # Tarife laden (allgemein + Spezialtarife)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    strompreis_cent, einspeiseverguetung_cent, wp_strompreis, wallbox_strompreis = _tarifpreise(
        tarife, strompreis_cent=strompreis_cent, einspeiseverguetung_cent=einspeiseverguetung_cent,
    )

    # Investitionen laden — Issue #123: ROI historisch, spätere Stilllegung
    # darf Vergangenheit nicht löschen. Siehe Roadmap R1 für zeitanteilige Gewichtung.
    inv_stmt = (
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .order_by(Investition.id)
    )
    if jahr is not None:
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    inv_result = await db.execute(inv_stmt)
    investitionen = sort_investitionen_nach_typ(inv_result.scalars().all())

    # Benzinpreis-Lookup für E-Auto-ROI: Monatsdaten.kraftstoffpreis_euro
    # (EU Weekly Oil Bulletin, seit v3.17.0) ist die Realität. Vorher las
    # `get_roi_dashboard` nur den Query-Default 1,85 € und ignorierte sowohl
    # diese Daten als auch das per-Investition gespeicherte `benzinpreis_euro`
    # — gleiche Bug-Klasse wie der v3.25.0-Fix für jahresfahrleistung_km etc.,
    # damals für benzinpreis_euro vergessen.
    letzter_marktpreis, benzinpreis_hinweis_euro = await _kraftstoffpreise(db, anlage_id)

    # Sonstige Erträge & Ausgaben (manuell pro Investition/Monat gepflegt) —
    # #310 rilmor-mhrs: get_roi_dashboard hat diese realisierten Beträge nie
    # eingerechnet, während Cockpit-Monatsbericht und Aussichten-Finanzprognose
    # sie längst über `berechne_sonstige_netto` berücksichtigen. Reiner Read-
    # Pfad, SoT-Helper `utils/sonstige_positionen`.
    from backend.utils.sonstige_positionen import berechne_sonstige_summen
    inv_ids_alle = [inv.id for inv in investitionen]
    # F-19 + Bauschritt 7: Erträge und Ausgaben getrennt — beide **kumuliert
    # in den Nenner**, mit umgekehrtem Vorzeichen. Im Zähler steht seit §8/3
    # keine von beiden (SoT `core/berechnungen/kapitalrechnung.py`).
    sonstige_ertraege_by_inv: dict[int, float] = {}
    sonstige_ausgaben_by_inv: dict[int, float] = {}
    # N-525: dieselben Beträge zusätzlich je (Investition, Jahr) — netto als
    # Kapital (Ausgabe +, Ertrag −), damit die Kalender-Treppe sie im Jahr ihrer
    # Buchung stuft statt am Anschaffungsjahr.
    sonstige_netto_by_inv_jahr: dict[tuple[int, int], float] = {}
    if inv_ids_alle:
        smd_query = select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_(inv_ids_alle)
        )
        if jahr is not None:
            smd_query = smd_query.where(InvestitionMonatsdaten.jahr == jahr)
        smd_result = await db.execute(smd_query)
        for imd in smd_result.scalars().all():
            _s = berechne_sonstige_summen(imd.verbrauch_daten)
            _buche_sonstige(
                _s, investition_id=imd.investition_id, jahr=imd.jahr,
                sonstige_ertraege_by_inv=sonstige_ertraege_by_inv,
                sonstige_ausgaben_by_inv=sonstige_ausgaben_by_inv,
                sonstige_netto_by_inv_jahr=sonstige_netto_by_inv_jahr,
            )

    def _sonstige_ertraege_kumuliert_fuer(inv_ids: list[int]) -> float:
        """Sonstige **Erträge** **kumuliert** — sie MINDERN den Nenner.

        ⚠ **Seit §8/3 (2026-08-10) gehen sie nicht mehr in den Zähler**, und
        seit **Bauschritt 7** (ebenfalls 2026-08-10) stehen sie im
        **Kapitaleinsatz**: eine Förderung ist Geld, das nie eingesetzt wurde.
        Eine Position im Monatsabschluss ist per Form einmal geflossen (§2/2);
        sie auf ein Jahr zu mitteln und fortzuschreiben unterstellt eine
        Wiederholung, die niemand behauptet hat — spiegelbildlich zu F-19 auf
        der Ausgabenseite. Wer einen *wiederkehrenden* Ertrag meint, pflegt ihn
        seit §8/1 als „Ertrag/Jahr" an der Investition; nur der wirkt in der
        Prognose.

        Damit entfällt auch der Jahres-Divisor: `sonstige_netto_euro` in der
        Detailspalte war bis dahin **gemischt** (annualisierter Ertrag gegen
        kumulierte Ausgabe). Jetzt sind beide Seiten kumuliert und die
        Differenz ist wieder eine Aussage.
        """
        return sum(sonstige_ertraege_by_inv.get(i, 0.0) for i in inv_ids)

    def _sonstige_ausgaben_kumuliert_fuer(inv_ids: list[int]) -> float:
        """Sonstige **Ausgaben** **kumuliert** — sie gehen in den NENNER.

        ⚠ **Kumuliert, nicht annualisiert — das ist F-19.** Bis 2026-08-09 lief
        die Summe durch einen Jahres-Divisor und wurde dem **Zähler**
        zugeschlagen. Eine einmalige Reparatur belastete damit jedes Jahr aufs
        Neue (Wärmepumpe: 8,1 → 42,6 Jahre Amortisation).
        """
        return sum(sonstige_ausgaben_by_inv.get(i, 0.0) for i in inv_ids)

    # Die **anlagenweiten** Positionen (Monatsabschluss ohne Komponente,
    # G19-1) — Bauschritt 4 des Wirtschaftlichkeits-Konzepts §8.
    #
    # ⚑ Sie haben **keine** Investition und können deshalb auf keiner ROI-Zeile
    # stehen; sie wirken ausschließlich auf die Gesamt-Zahlen. Bis 2026-08-10
    # wirkten sie hier **gar nicht**: die Query oben liest nur
    # `InvestitionMonatsdaten`. Gemessen am 10.08. — eine anlagenweite Ausgabe
    # von 3.000 € bewegte den Kapitaleinsatz dieser Route um 0 €, während der
    # HA-Sensor sie voll trug (18.000 gegen 15.000); eine anlagenweite Förderung
    # von 500 € war in der ganzen Sicht unsichtbar.
    #
    # Gelesen über die Monats-Fakten (P10) statt über eine eigene
    # `Monatsdaten`-Faltung — `anlage_*_euro` ist genau der Anteil der
    # Basis-Positionen, also **ohne** die IMD-Beträge, die oben schon gezählt
    # sind. Ein `f.sonstiges.ausgaben_euro` an dieser Stelle wäre die
    # Doppelzählung.
    _anlage_fakten, anlage_sonstige_ausgaben, anlage_sonstige_ertraege = await _anlagenweite_positionen(
        db, anlage_id, jahr,
    )

    # N-525 — die Kalender-Treppe: Kalender-Anker VOR den Zeilen, damit jede
    # Zeile ihr Jahr kennt. `basis_jahr` = frühestes Anschaffungsjahr; ohne ein
    # einziges Datum läuft die Reihe als Index ab 0 (die Achse bleibt Index-
    # basiert, kein erfundenes Jahr — dieselbe Regel wie bisher).
    basis_jahr, kapital_ereignisse, ersparnis_zeilen, _treppe_zeile = _kalender_treppe(
        investitionen, sonstige_netto_by_inv_jahr, _anlage_fakten,
    )
    return {
        "_anlage_fakten": _anlage_fakten,
        "_ist_pv_ladeanteil": _ist_pv_ladeanteil,
        "_sonstige_ausgaben_kumuliert_fuer": _sonstige_ausgaben_kumuliert_fuer,
        "_sonstige_ertraege_kumuliert_fuer": _sonstige_ertraege_kumuliert_fuer,
        "_treppe_zeile": _treppe_zeile,
        "anlage": anlage,
        "anlage_sonstige_ausgaben": anlage_sonstige_ausgaben,
        "anlage_sonstige_ertraege": anlage_sonstige_ertraege,
        "basis_jahr": basis_jahr,
        "benzinpreis_hinweis_euro": benzinpreis_hinweis_euro,
        "einspeiseverguetung_cent": einspeiseverguetung_cent,
        "ersparnis_zeilen": ersparnis_zeilen,
        "investitionen": investitionen,
        "kapital_ereignisse": kapital_ereignisse,
        "letzter_marktpreis": letzter_marktpreis,
        "strompreis_cent": strompreis_cent,
        "wallbox_strompreis": wallbox_strompreis,
        "wp_strompreis": wp_strompreis,
    }


def _ist_pv_ladeanteil_einmal(db, anlage_id, jahr):
    """N-188 (RF-46): die Closure, die den IST-PV-Anteil der Heimladung hoechstens einmal je Request holt."""
    _ist_anteil_cache: list = [False]

    async def _ist_pv_ladeanteil() -> Optional[float]:
        if _ist_anteil_cache[0] is False:
            _ist_anteil_cache[0] = await ist_pv_ladeanteil_prozent(
                db,
                anlage_id,
                von=(jahr, 1) if jahr is not None else None,
                bis=(jahr, 12) if jahr is not None else None,
            )
        return _ist_anteil_cache[0]

    return _ist_pv_ladeanteil


def _tarifpreise(tarife, *, strompreis_cent, einspeiseverguetung_cent):
    """Die Preise aus den heutigen Tarifen (RF-46; Ø-Jahreswert nach vorn, ADR-002/P8). Rückgabe
    `(strompreis_cent, einspeiseverguetung_cent, wp_strompreis, wallbox_strompreis)`."""
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "allgemein")
    # `is not None` statt truthy: **0** ist seit 08.08.2026 die Vorbelegung
    # eines neuen Tarifs (eedc rät keinen EEG-Satz mehr) und ein gepflegter
    # Wert — mit `or` rechnete die Wirtschaftlichkeit je Investition still mit
    # 8,2 ct, während Cockpit und Jahresbericht 0 nehmen.
    #
    # #392: bewusst der heutige STAMMWERT, kein Monatswert der variablen
    # Vergütung — dieselbe Entscheidung wie beim Netzbezugspreis zwei Zeilen
    # darüber (N-113): die ROI-Rechnung bildet einen Durchschnitts-Jahreswert
    # für die Amortisation über die LEBENSDAUER nach vorn, und dafür ist der
    # heutige Tarif die richtige Basis. Rückblickende Sichten (Cockpit,
    # Jahresbericht, Speicher-Dashboard) lösen je Monat auf.
    if einspeiseverguetung_cent is None:
        einspeiseverguetung_cent = (
            allgemein_tarif.einspeiseverguetung_cent_kwh
            if allgemein_tarif and allgemein_tarif.einspeiseverguetung_cent_kwh is not None
            else EINSPEISEVERGUETUNG_DEFAULT_CENT
        )
    wp_tarif = tarife.get("waermepumpe")
    wp_strompreis = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else strompreis_cent
    wallbox_tarif = tarife.get("wallbox")
    wallbox_strompreis = wallbox_tarif.netzbezug_arbeitspreis_cent_kwh if wallbox_tarif else strompreis_cent
    return strompreis_cent, einspeiseverguetung_cent, wp_strompreis, wallbox_strompreis


async def _kraftstoffpreise(db, anlage_id):
    """Benzinpreis-Lookup (RF-46): letzter gepflegter Monatspreis und der Hinweiswert der Antwort (Default ohne
    Monatspreis). Rückgabe `(letzter_marktpreis, benzinpreis_hinweis_euro)`."""
    benzinpreis_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    benzinpreis_lookup: dict[tuple[int, int], Optional[float]] = {
        (md.jahr, md.monat): md.kraftstoffpreis_euro
        for md in benzinpreis_md_result.scalars().all()
    }
    letzter_marktpreis = letzter_kraftstoffpreis_aus_lookup(benzinpreis_lookup)
    benzinpreis_hinweis_euro = (
        letzter_marktpreis
        if letzter_marktpreis is not None
        else float(PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"])
    )
    return letzter_marktpreis, benzinpreis_hinweis_euro


def _buche_sonstige(
    _s: dict, *, investition_id: int, jahr: int,
    sonstige_ertraege_by_inv: dict, sonstige_ausgaben_by_inv: dict, sonstige_netto_by_inv_jahr: dict,
) -> None:
    """Bucht die Betraege EINER Zeile der sonstigen Positionen (RF-46): Ertraege und Ausgaben je Investition,
    netto als Kapital je (Investition, Jahr). Bekommt die Summen aus `berechne_sonstige_summen` — die Zeile
    selbst (`verbrauch_daten`) liest der Orchestrator."""
    if _s["ertraege_euro"]:
        sonstige_ertraege_by_inv[investition_id] = (
            sonstige_ertraege_by_inv.get(investition_id, 0.0)
            + _s["ertraege_euro"]
        )
    if _s["ausgaben_euro"]:
        sonstige_ausgaben_by_inv[investition_id] = (
            sonstige_ausgaben_by_inv.get(investition_id, 0.0)
            + _s["ausgaben_euro"]
        )
    _netto = (_s["ausgaben_euro"] or 0.0) - (_s["ertraege_euro"] or 0.0)
    if _netto:
        _key = (investition_id, jahr)
        sonstige_netto_by_inv_jahr[_key] = sonstige_netto_by_inv_jahr.get(_key, 0.0) + _netto


async def _anlagenweite_positionen(db, anlage_id, jahr):
    """Die anlagenweiten sonstigen Positionen aus den Monats-Fakten (RF-46, P10; Bauschritt 4). Rückgabe
    `(_anlage_fakten, anlage_sonstige_ausgaben, anlage_sonstige_ertraege)`."""
    from backend.services.monats_fakten import lade_monats_fakten
    _anlage_fakten = await lade_monats_fakten(
        db,
        anlage_id,
        von=(jahr, 1) if jahr is not None else None,
        bis=(jahr, 12) if jahr is not None else None,
    )
    anlage_sonstige_ausgaben = sum(
        f.sonstiges.anlage_ausgaben_euro for f in _anlage_fakten
    )
    # ⚑ Die anlagenweiten **Erträge** wirken seit Bauschritt 7 wieder — nicht
    # mehr annualisiert im Zähler (das war §8/3), sondern **mindernd im
    # Nenner**, genau wie ihre Ausgaben-Geschwister. Auf einer ROI-Zeile können
    # sie nicht stehen: sie haben keine Investition. Deshalb wirken sie
    # ausschließlich auf die Gesamt-Zahlen (Bauschritt 4).
    anlage_sonstige_ertraege = sum(
        f.sonstiges.anlage_ertraege_euro for f in _anlage_fakten
    )
    return _anlage_fakten, anlage_sonstige_ausgaben, anlage_sonstige_ertraege


def _kalender_treppe(investitionen, sonstige_netto_by_inv_jahr, _anlage_fakten):
    """N-525 (RF-46): Basisjahr, die beiden Listen der Treppe, die Closure `_treppe_zeile` für die Zeilen-Phasen —
    und die anlagenweiten Positionen als Kapital-Ereignisse im Jahr ihres Monats (vor jeder Zeile). Rückgabe
    `(basis_jahr, kapital_ereignisse, ersparnis_zeilen, _treppe_zeile)`."""
    _inst_jahre = [
        inv.anschaffungsdatum.year for inv in investitionen
        if inv.anschaffungsdatum is not None
    ]
    basis_jahr: Optional[int] = min(_inst_jahre) if _inst_jahre else None
    kapital_ereignisse: list[KapitalEreignis] = []
    ersparnis_zeilen: list[ErsparnisZeile] = []

    def _treppen_jahr(*invs) -> int:
        """Das Jahr einer Zeile: früheste Anschaffung ihrer Komponenten; ohne
        Datum die Basis (bzw. 0 im Index-Modus)."""
        if basis_jahr is None:
            return 0
        jahre = [i.anschaffungsdatum.year for i in invs if i.anschaffungsdatum is not None]
        return min(jahre) if jahre else basis_jahr

    def _treppe_zeile(*, invs, kosten_je_inv: dict[int, float], netto_einsparung: float) -> int:
        """Trägt eine ROI-Zeile in die Treppe ein: relevante Kosten je Komponente
        ab deren Jahr, sonstige Positionen im Jahr ihrer Buchung, die Netto-
        Jahres-Einsparung der Zeile ab dem Zeilenjahr. Gibt das Zeilenjahr zurück."""
        zeilen_jahr = _treppen_jahr(*invs)
        for i in invs:
            betrag = kosten_je_inv.get(i.id, 0.0)
            if betrag:
                kapital_ereignisse.append(KapitalEreignis(_treppen_jahr(i), betrag))
        for (inv_id, pos_jahr), betrag in sonstige_netto_by_inv_jahr.items():
            if betrag and any(inv_id == i.id for i in invs):
                kapital_ereignisse.append(
                    KapitalEreignis(pos_jahr if basis_jahr is not None else 0, betrag)
                )
        ersparnis_zeilen.append(ErsparnisZeile(zeilen_jahr, netto_einsparung))
        return zeilen_jahr

    # Anlagenweite Positionen (ohne Investition) im Jahr ihres Monats.
    for f in _anlage_fakten:
        _netto = (f.sonstiges.anlage_ausgaben_euro or 0.0) - (f.sonstiges.anlage_ertraege_euro or 0.0)
        if _netto:
            kapital_ereignisse.append(
                KapitalEreignis(f.jahr if basis_jahr is not None else 0, _netto)
            )
    return basis_jahr, kapital_ereignisse, ersparnis_zeilen, _treppe_zeile

