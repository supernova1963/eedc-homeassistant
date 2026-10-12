"""Komponenten-Dashboards — die Basis: gewichtete Monatspreise (Netzbezug/Einspeisung je Verwendung, P8) und das
Monatsdaten-Antwortmodell, das alle Dashboards mitliefern.
"""
# Reiner Umzug aus `api/routes/investitionen/dashboards.py` (18.09.2026, Vorlage 6 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `dashboards.py` haengt den Router an der
# bisherigen Stelle ein und exportiert die Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from typing import Optional, Any, NamedTuple
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel


class GewichtetePreise(NamedTuple):
    """Mengengewichtete Ø-Tarife einer Periode, beide Preisseiten (ct/kWh).

    ``bezug_lookup`` trägt zusätzlich die **ungemittelten** Monatspreise, aus
    denen der Ø entstanden ist. Er geht an
    ``berechne_eauto_ersparnis_periode`` weiter, damit die Preisachse dort
    aufgelöst wird und nicht hier — sonst gäbe es die Mittelung an zwei Orten
    (F-18/N-181). Zwei getrennte Query-Schleifen über dieselben Monate wären
    der Preis dafür gewesen; so bleibt es bei einer.
    """
    bezug_cent: float
    einspeise_cent: float
    bezug_lookup: dict[tuple[int, int], float] = {}

def monatspreis_der_verwendung(tarif, verwendung: str) -> float:
    """Das Feld des Monatstarifs der Monats-Fakten (``TarifFakten``), das zu einer Verwendung gehört (N-712/N-713):
    ``wallbox`` → ``wallbox_preis_effektiv_cent`` (Flex-Ø des ganzen Zählers, Wallbox-Tarif Stufe 4), ``waermepumpe``
    → ``wp_preis_cent`` (ohne eigenen WP-Tarif der Hauszähler, N-663), sonst ``netzbezug_preis_cent``. Eine Auswahl,
    keine Auflösung — die steht in ``monats_fakten/tarif.py::_lade_tarif``."""
    if verwendung == "wallbox":
        return tarif.wallbox_preis_effektiv_cent
    if verwendung == "waermepumpe":
        return tarif.wp_preis_cent
    return tarif.netzbezug_preis_cent


async def _gewichtete_monatspreise(
    db: AsyncSession,
    anlage_id: int,
    verwendung: str,
    gewichte: dict[tuple[int, int], float],
    fallback_bezug: float,
    fallback_einspeise: float,
) -> GewichtetePreise:
    """Mengengewichtete Ø der Tarife, die in den Monaten der Periode galten.

    ADR-002/P8 für die Komponenten-Dashboards. Sie summieren Energien über die
    ganze Lebensdauer und bewerten sie EINMAL — mit dem heutigen Tarif hätte
    jede Preiserhöhung die komplette Historie rückwirkend neu bewertet.

    Warum ein gewichteter Ø statt einer strengen Monatsmultiplikation: Bei
    aktivem Wallbox-Pool (#262) ersetzt `attribute_emob_pool_by_km` die
    Monatswerte durch EINEN nach km verteilten Gesamtwert — eine
    Monatsaufteilung der Netzladung existiert dort nicht. Der Ø wird deshalb
    mit derselben Größe gewichtet, nach der auch attribuiert wird. Für Anlagen
    ohne Tarifwechsel ist das Ergebnis identisch zum bisherigen Wert.

    **Warum BEIDE Preisseiten aus einer Schleife kommen:** die Funktion hieß
    bis v4.0.7 `_gewichteter_monatspreis` und lieferte nur den Bezugspreis —
    die Einspeisevergütung daneben blieb der HEUTE gültige Wert. In jedem
    Spread (`bezug − einspeise` bei V2H und Speicher) standen damit zwei
    Summanden aus verschiedenen Zeitpunkten. Zwei getrennte Aufrufe wären
    zudem eine zweite Query-Schleife über dieselben Monate.

    Die Vergütung trägt bewusst dieselben Gewichte wie der Bezugspreis, auch
    wo die bewertete Menge eine andere ist (V2H-Entladung statt Netzladung):
    eine eigene Gewichtung wäre nur mit einer Monatsaufteilung der
    V2H-Energie ehrlich, und die existiert im Pool-Fall gerade nicht. Die
    Näherung ist damit dieselbe, die der Bezugspreis hier seit v4.0.5 macht.

    Args:
        gewichte: ``{(jahr, monat): menge}`` — Netzladung bzw. km je Monat.
        fallback_bezug: Bezugspreis ohne Gewichte (ct/kWh).
        fallback_einspeise: Einspeisevergütung ohne Gewichte (ct/kWh).
    """
    summe_gewicht = sum(g for g in gewichte.values() if g and g > 0)
    if summe_gewicht <= 0:
        return GewichtetePreise(fallback_bezug, fallback_einspeise, {})

    # ⭐ **#412 (11.09.2026): auch hier gilt die volle Preis-Kaskade.** Bis dahin
    # las diese Schleife allein den Tarif — der **abgerechnete** Monats-Ø aus
    # dem Monatsabschluss kam nie an, obwohl Cockpit → Übersicht und die
    # Aussichten ihn für dieselbe E-Mob-Ersparnis längst nahmen. Dieselbe
    # Größe, zwei Zahlen, je nachdem welche Sicht der Anwender öffnet — die
    # F-18-Klasse, eine Ebene tiefer: Der bestehende Wächter prüft, **dass**
    # ein Lookup übergeben wird, nicht **welcher**.
    #
    # ⭐ **N-712 (12.10.2026): der Monatspreis kommt aus den Monats-Fakten**
    # (`tarife_der_monate`, Entscheid Gernot: Kanon ist der Monatspreis der
    # Schicht). Bis dahin setzte diese Schleife ihn selbst zusammen — mit
    # `fallback=fallback_bezug`, also dem HEUTIGEN Tarif, für Monate vor dem
    # ersten Tarif (Fall C: E-Auto-Hub 666,00 statt 675,00 €). Die Schicht
    # rechnet dort mit der Vorbelegung `NETZBEZUG_DEFAULT_CENT`, und so jetzt
    # jeder Hub. `fallback_bezug` gilt nur noch ohne Gewichte (oben).
    #
    # ⭐ N-715/N-716 (12.10.2026): die VERGÜTUNG kommt aus derselben Quelle
    # (`TarifFakten.einspeiseverguetung_cent`: #392-Monatssatz → Tarif des
    # Monats → Vorbelegung 8,2 ct). Bis dahin stand hier
    # `resolve_einspeiseverguetung_cent(m_tarife, fallback=fallback_einspeise)` —
    # vor dem ersten Tarif die HEUTIGE Vergütung (V2H 96,00 statt 93,80 €) und
    # ohne den gepflegten Monatssatz (V2H 88,00 statt 108,00 €, Erlös eines
    # Sonstiges-Erzeugers 25,60 statt 9,60 €). `fallback_einspeise` gilt wie
    # `fallback_bezug` nur noch ohne Gewichte.
    from backend.services.monats_fakten import tarife_der_monate

    _monate = [(j, m) for (j, m), g in gewichte.items() if g and g > 0]
    _monatspreis = await tarife_der_monate(db, anlage_id, _monate)

    gewichteter_bezug = 0.0
    gewichtete_einspeisung = 0.0
    bezug_lookup: dict[tuple[int, int], float] = {}
    for (jahr, monat), gewicht in gewichte.items():
        if not gewicht or gewicht <= 0:
            continue
        m_tarif = _monatspreis[(jahr, monat)]
        m_bezug = monatspreis_der_verwendung(m_tarif, verwendung)
        bezug_lookup[(jahr, monat)] = m_bezug
        gewichteter_bezug += m_bezug * gewicht
        gewichtete_einspeisung += m_tarif.einspeiseverguetung_cent * gewicht
    return GewichtetePreise(
        gewichteter_bezug / summe_gewicht,
        gewichtete_einspeisung / summe_gewicht,
        bezug_lookup,
    )

class InvestitionMonatsdatenResponse(BaseModel):
    """Monatsdaten für eine Investition."""
    #: ``None`` nur für eine Zeile, die nicht gespeichert ist: der E-Auto-Hub zeigt einen
    #: Monat, in dem das Auto Rest der Wallbox bekommt, aber keine eigene Monatszeile hat
    #: (N-564, ``verbrauch_daten.ladung_aus_rest``). Jede gespeicherte Zeile trägt ihre ID.
    id: Optional[int] = None
    investition_id: int
    jahr: int
    monat: int
    verbrauch_daten: dict[str, Any]
    einsparung_monat_euro: Optional[float]
    co2_einsparung_kg: Optional[float]

    class Config:
        from_attributes = True


class InvestitionMonatsdatenFormResponse(InvestitionMonatsdatenResponse):
    """Eine Gerätezeile, wie das Monatsformular sie lädt — mit ihren Herkunftsmarken.

    N-578 B2a (H1): ``abgeleitet_felder`` = ``{sub_key: ABGELEITET_*}`` aus der
    Provenance der Zeile (`provenance.abgeleitete_subkeys`). Das Formular lädt
    einen ``summe_achsen``-markierten WP-Gesamtstrom **nicht** als Handpflege,
    damit seine Auto-Summe bei jedem Speichern neu rechnet.

    ⚠ **Eigenes Modell statt eines Feldes am geteilten:** Die Dashboards liefern
    `InvestitionMonatsdatenResponse` in ihren Antworten aus — ein Feld dort
    änderte jede Hub-Antwort. Additiv und nur an der Laderoute des Formulars.
    """
    abgeleitet_felder: dict[str, str] = {}
