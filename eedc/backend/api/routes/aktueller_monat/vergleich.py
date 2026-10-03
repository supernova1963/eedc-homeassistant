"""Vergleichsgroessen von *Cockpit → Monat*: Vorjahresmonat, PVGIS-SOLL, Nachtsockel — und die
Tarifaufloesung (`_zeittarif_preis`), die Vorjahr und Endpunkt teilen.

Die Route konsumiert nur das Ergebnis; alle Funktionen hier lesen keinen Namen, den Tests am
Fassaden-Modul patchen (`datetime`, die fuenf Sammler).
"""
# Reiner Umzug aus `api/routes/aktueller_monat.py` (18.09.2026, Vorlage 1 des Refactorings
# grosser Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# exportiert alle Namen weiter, die Tests und Aufrufer bisher aus dem Modul importierten.

import logging
from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_monatsprognosen
from backend.services.strompreis_aggregator import wirksamer_arbeitspreis_cent
from backend.core.berechnungen import (
    Monatsfenster,
    anteilig,
    berechne_netzbezug_kosten,
    einspeise_erloes_euro,
)
from backend.services.monats_fakten import lade_monats_fakten
from backend.api.routes.aktueller_monat.schemas import SollPv

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# N-267: Zeittarif (HT/NT) in Cockpit → Monat
# ─────────────────────────────────────────────────────────────────────────────
#
# ⛔ Diese Route ist die VIERTE Bildungsstelle des Monatspreises, und das
# Konzept zu N-267 hat sie zunaechst uebersehen — es nannte drei
# (`monats_fakten::_lade_tarif`, `finanz_zeilen::baue_finanz_zeile`,
# `strompreise::monats_strompreis_lookup`). Gefunden erst beim Bau von Z2, an
# `netzbezug_preis_effektiv_cent`: aus ihm entstehen hier die
# Netzbezugskosten (`berechne_netzbezug_kosten`), die EV-Ersparnis und das
# ausgelieferte Feld `netzbezug_preis_cent`. Ohne die Einhaengung haette
# Cockpit → Monat den Hochtarif genannt, waehrend Cockpit → Jahr daneben den
# gewichteten Preis zeigt — „zwei Zahlen auf einer Seite", die v4.0.1-Klasse.
#
# ⭐ Die Lehre steht schon in `test_zeittarif_ht_nt.py::test_wz1b_*`: JEDE
# Bildungsstelle braucht ihre eigene Gegenprobe. Die Zaehlung „drei" war eine
# Behauptung, kein Befund — sie kam aus einem Grep ueber Aufrufer des
# Resolvers, und diese Route bildet den Preis eine Ebene darueber.

async def _zeittarif_preis(
    db, anlage_id: int, jahr: int, monat: int, tarif, fallback: float, cache: dict
) -> float:
    """Der wirksame Arbeitspreis (ct/kWh) — mit Zeitfenstern gewichtet.

    ``fallback`` gilt, wenn es die Tarifzeile nicht gibt; ohne Fenster liefert
    der Helfer die Spalte unveraendert zurueck, ohne die Datenbank zu fragen.
    """
    if tarif is None or tarif.netzbezug_arbeitspreis_cent_kwh is None:
        return fallback
    return await wirksamer_arbeitspreis_cent(
        db, anlage_id, jahr, monat, tarif, cache=cache
    )


_UNGELADEN = object()


# Der Vorjahres-Block — Feldnamen und ANWESENHEITSREGELN genau wie im eigenen Pfad bis 03.10.2026 (gelesen gegen
# `b8c59b08:…/vergleich.py`), damit T-Konto, Kacheln und PDF unverändert lesen. Nur die Werte kommen jetzt aus der
# Monatsantwort des Vorjahresmonats (N-610).

#: Immer gesetzt (auch als ``None``).
VORJAHR_IMMER: tuple[str, ...] = (
    "einspeisung_kwh", "netzbezug_kwh", "netzbezug_durchschnittspreis_cent", "einspeise_durchschnittspreis_cent",
    "eigenverbrauch_kwh", "direktverbrauch_kwh", "gesamtverbrauch_kwh", "autarkie_prozent",
)
#: Mengen — nur gesetzt, wenn > 0 („eine 0 setzt kein Feld").
VORJAHR_MENGE_POSITIV: tuple[str, ...] = (
    "pv_erzeugung_kwh", "speicher_ladung_kwh", "speicher_entladung_kwh", "wp_strom_kwh", "wp_waerme_kwh",
    "wp_modus_kuehlen_kwh", "emob_ladung_kwh", "emob_km",
)
#: Vorjahres-Feldname → Feld der Monatsantwort, wo die Namen verschieden sind (Regel 0a: im Monat EIN Name je Größe).
VORJAHR_QUELLFELD: dict[str, str] = {"wp_modus_kuehlen_kwh": "wp_modus_strom_kuehlen_kwh"}
#: Der Finanzblock — nur mit Tarif (bis dahin: `if tarif_vj:`).
VORJAHR_FINANZ_IMMER: tuple[str, ...] = (
    "netto_ertrag_euro", "ust_eigenverbrauch_euro", "bkw_ersparnis_euro", "erzeuger_erloes_euro", "sonstige_netto_euro",
    "betriebskosten_anteilig_euro", "ergebnis_vor_betriebskosten_euro", "ergebnis_euro", "ergebnis_herleitung",
    "fehlende_posten",
)
#: Finanzfelder mit eigener Bedingung: Erlös/Ersparnis, sobald die MENGE > 0 ist (auch 0,00 €); WP/E-Mob, sobald ≠ 0
#: (auch negativ); Stromrechnung, sobald sie einen Wert hat (Netzbezug bekannt, E5).
VORJAHR_FINANZ_BEI_MENGE: dict[str, str] = {"einspeise_erloes_euro": "einspeisung_kwh", "ev_ersparnis_euro": "eigenverbrauch_kwh"}
VORJAHR_FINANZ_UNGLEICH_NULL: tuple[str, ...] = ("wp_ersparnis_euro", "emob_ersparnis_euro")
VORJAHR_FINANZ_MIT_WERT: tuple[str, ...] = ("netzbezug_kosten_euro", "netzbezug_arbeitspreis_kosten_euro")
VORJAHR_FELDER: tuple[str, ...] = (
    VORJAHR_IMMER + VORJAHR_MENGE_POSITIV + VORJAHR_FINANZ_IMMER + tuple(VORJAHR_FINANZ_BEI_MENGE)
    + VORJAHR_FINANZ_UNGLEICH_NULL + VORJAHR_FINANZ_MIT_WERT
)


def vorjahr_aus_monat(antwort: dict) -> dict:
    """Der Vorjahres-Block aus der Monatsantwort des Vorjahresmonats — Namen, Typen und Anwesenheit wie bisher."""
    def wert(feld: str):
        return antwort.get(VORJAHR_QUELLFELD.get(feld, feld))

    result: dict = {k: wert(k) for k in VORJAHR_IMMER}
    gv = result.get("gesamtverbrauch_kwh")
    if gv is None or gv <= 0:  # bis dahin: `round(gv, 1) if gv > 0 else None`, ebenso die Autarkie
        result["gesamtverbrauch_kwh"] = None
        result["autarkie_prozent"] = None
    for k in VORJAHR_MENGE_POSITIV:
        v = wert(k)
        if v is not None and v > 0:
            result[k] = v
    # Ohne Tarif gab es keinen Finanzblock (die Monatsroute setzt ihren Preis nur mit Tarif).
    if antwort.get("netzbezug_preis_effektiv_cent") is None:
        return result
    for k in VORJAHR_FINANZ_IMMER:
        result[k] = wert(k)
    for k, menge in VORJAHR_FINANZ_BEI_MENGE.items():
        m = antwort.get(menge)
        if m is not None and m > 0 and wert(k) is not None:
            result[k] = wert(k)
    for k in VORJAHR_FINANZ_UNGLEICH_NULL:
        v = wert(k)
        if v:  # ≠ 0, auch negativ
            result[k] = v
    for k in VORJAHR_FINANZ_MIT_WERT:
        if wert(k) is not None:
            result[k] = wert(k)
    return result


async def _load_vorjahr(
    anlage_id: int, investitionen: list[Investition], jahr: int, monat: int, db: AsyncSession,
    *, fakt=_UNGELADEN, ust_satz=None, tarif_cache: Optional[dict] = None, kontext=None,
    hinweise: Optional[list] = None,
) -> Optional[dict]:
    """Der Vorjahresmonat — DERSELBE Monat, über dieselbe Funktion gerechnet (N-610, 03.10.2026).

    Bis 03.10.2026 stand hier ein eigener Pfad (Mengen aus den Monats-Fakten, eigene Preisauflösung, eigene WP-/E-Mob-
    Zeilen, eigene Leiter-Füllung). Er glich seinem Monat nicht: N-608 (Bezugspreis ohne Stufe „gemessen": 70 € statt
    90 €), und umgekehrt trug ER den Eigenverbrauch richtig, während die Monatsroute die V2H-Entladung vergaß
    (r28 7 von 37, r27 10 von 26 Paaren). Statt eines Einzelfixes je Abweichung ruft das Vorjahr jetzt
    ``_berechne_monat(jahr − 1, monat, ohne_vorjahr=True)`` (kein Vorjahr des Vorjahres, keine Rekursion) und liest die
    Felder des Vorjahres-Blocks aus dieser Antwort (`vorjahr_aus_monat`). Die Symmetrie hält
    `tests/test_n610_v2h_im_monat_und_vorjahr.py` über alle Felder.

    Ohne Zählerzeile im Vorjahresmonat gibt es — wie bisher — keinen Vergleich (`None`). ``investitionen``, ``ust_satz``
    und ``tarif_cache`` bleiben in der Signatur (Aufrufer, Proben); gerechnet wird mit dem Kontext des Vorjahres.
    """
    from backend.api.routes.aktueller_monat import _berechne_monat
    from backend.api.routes.aktueller_monat.kontext import MonatsKontext

    vj = jahr - 1
    if fakt is _UNGELADEN:
        fakten_vj = await lade_monats_fakten(db, anlage_id, von=(vj, monat), bis=(vj, monat))
        fakt = fakten_vj[0] if fakten_vj else None
    if fakt is None or fakt.meta.monatsdaten is None:
        return None
    # Der Kontext des laufenden Jahres trägt die Fakten J−1…J und den Satz von J−1 — daraus der Kontext des Vorjahres,
    # ohne zweite Ladung (ein eigener Kontext lüde J−2…J−1; der USt-Rückfall auf J−2 bliebe dann der einzige Unterschied).
    kontext_vj = None
    if kontext is not None:
        kontext_vj = MonatsKontext(
            jahr=vj, fakten=kontext.fakten, ust_satz=kontext.ust_satz_vj, ust_satz_vj=None,
            tarif_cache=kontext.tarif_cache,
        )
    try:
        antwort = await _berechne_monat(anlage_id, vj, monat, db, kontext=kontext_vj, ohne_vorjahr=True)
    except Exception:  # noqa: BLE001 — der Vergleich darf den Monat nicht kippen (wie der alte Finanz-Zweig)
        logger.warning("Vorjahresvergleich %02d/%s nicht berechenbar", monat, vj, exc_info=True)
        if hinweise is not None:
            hinweise.append(f"Vorjahresvergleich für {monat:02d}/{vj} nicht berechenbar.")
        return None
    return vorjahr_aus_monat(antwort.model_dump())


async def _load_soll_pv(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession, fenster: Monatsfenster,
) -> SollPv:
    """Lädt PVGIS SOLL-Wert für den Monat — aus der AKTIVEN Prognose (P5).

    Vorher stand hier ein `JOIN` auf `ist_aktiv` **ohne `limit`** und ein `sum()`
    darüber: bei zwei aktiven Prognosen kam der Monatswert doppelt zurück (N83).
    Der Fehler war nicht sichtbar, weil die Summe plausibel aussah — sie war nur
    doppelt so groß, und die SOLL/IST-Abweichung sowie die Grundlast-SOLL-Kachel
    rechneten mit. Der Auswahl-SoT trägt das `LIMIT 1` in der Subquery.

    **Im laufenden Monat trägt der Rückgabewert nur die abgelaufenen Tage**
    (N-69, Entscheid Gernot 2026-08-04): PVGIS liefert eine Monatssumme, der IST
    daneben ist angefangen. Ungekürzt maß die Erfüllungsquote das Datum statt
    die Anlage — am 4. August 19 % für eine Anlage, die über die abgeschlossenen
    Monate auf 119 % kam. Begründung der Kürzung im Layer-Docstring
    (`core/berechnungen/monatsfenster.py`); die Jahres-Sicht summiert diese
    Monatswerte und erbt die Korrektur damit ohne eigene Rechnung.
    """
    prognosen = await lade_aktive_monatsprognosen(db, anlage_id, monat=monat)
    if not prognosen:
        return SollPv(None, None)
    voll = sum(p.ertrag_kwh for p in prognosen)
    gekuerzt = anteilig(voll, fenster)
    return SollPv(
        anteilig=round(gekuerzt, 1) if gekuerzt is not None else None,
        monat=round(voll, 1),
    )

async def _load_grundlast_nacht_kw(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession,
) -> list[float]:
    """Nacht-Stunden-Leistungen (0–5 Uhr, verbrauch_kw > 0) des Monats aus dem
    stündlichen Energieprofil — Sourcing für `berechne_grundlast` (ADR-001:
    Formel liegt im Berechnungs-Layer, hier nur die Query). Leer, wenn die Anlage
    keine Stundenprofile hat (dann fällt die Sicht auf PVGIS-SOLL/IST zurück)."""
    from calendar import monthrange
    from backend.models.tages_energie_profil import TagesEnergieProfil

    from backend.core.berechnungen.spannen import verbrauch_gebuendelt

    monat_ende = date(jahr, monat, monthrange(jahr, monat)[1])
    result = await db.execute(
        select(TagesEnergieProfil.verbrauch_kw, TagesEnergieProfil.spannen).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= date(jahr, monat, 1),
            TagesEnergieProfil.datum <= monat_ende,
            TagesEnergieProfil.stunde < 5,
            TagesEnergieProfil.verbrauch_kw.is_not(None),
            TagesEnergieProfil.verbrauch_kw > 0,
        )
    )
    # Zählerlücken wie HA (§2, Ü3): eine Nachtzeile, deren Verbrauchs-Achsen
    # mehr als eine reale Stunde tragen, ist keine Stunden-Leistung — sie
    # fällt aus dem Median (dieselbe Regel wie `tage_werte`).
    return [float(r.verbrauch_kw) for r in result.all() if not verbrauch_gebuendelt(r)]
