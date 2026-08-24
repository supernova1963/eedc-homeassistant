"""Der abgeleitete PV-Anteil der Heimladung erreicht **jede** Sicht (F-16).

Single Source of Truth für die **Anwendung** der Ableitung aus
``core/berechnungen/pv_anteil_ladung.py`` auf die Monatszeilen einer Anlage.

**Warum es diese Datei gibt — und warum sie nicht in den Monats-Fakten steht.**
``a7a50abc`` hat die Ableitung dort eingehängt, wo die kanonische Monatszeile
entsteht: **oberhalb** von ``get_emob_heimladung_canonical``. Wer die Felder
``EmobFakten.ladung_pv_kwh``/``ladung_netz_kwh`` liest, sah den Anteil; wer die
mitgereichten Rohdicts selbst poolt oder ``InvestitionMonatsdaten`` direkt liest,
sah ihn nicht. Beide Gruppen zeigen dieselbe Größe an — der Komponenten-Hub
weiterhin **0 %**, Cockpit/Auswertungen den abgeleiteten Anteil. Von achtzehn
Lesestellen sahen ihn vier. Vor ``a7a50abc`` waren alle gleich (überall 0 %);
die Drift ist also **im eigenen Commit entstanden**, dieselbe Klasse wie #331
(fünf Rechenstellen statt zwei) und F-15.

**Die Heilung ist eine Schicht-Frage, kein Anschluss je Sicht.** Alle Leser
gehen durch ``get_emob_pv_netz_kwh(dict)`` — entweder direkt oder über
``summiere_emob_quelle`` / ``get_emob_heimladung_canonical``. Deshalb setzt
diese Datei eine Ebene **tiefer** an als der Fund: sie reichert die
Monatszeilen an, bevor irgendjemand sie poolt. Danach ist es gleichgültig, ob
eine Sicht die Fakten-Felder liest, global poolt oder je Investition rechnet —
sie sehen alle dieselbe Aufteilung.

⚠ **Ein gepflegter Wert gewinnt immer, auch eine gepflegte 0** — geprüft wird
die Anwesenheit des Schlüssels ``ladung_pv_kwh``, nicht seine Größe (F-15-Klasse
eine Ebene weiter). Der Torwächter läuft über **beide** Quellen zusammen: hat
die Wallbox keinen PV-Wert, das Fahrzeug aber schon, dann hat der Anwender den
Anteil erfasst.

⚠ **Angereichert wird der ANTEIL, nicht die Kilowattstunde.** Die Quote der
Tagesebene wird auf die Ladung **der Zeile** angewandt; die Trias
``ladung_kwh == ladung_pv_kwh + ladung_netz_kwh`` bleibt damit in jeder Zeile
geschlossen, und jede Summe darüber ebenfalls. Die kWh der Tagesebene direkt zu
übernehmen zerbräche sie (#262, PV-Anteil über 100 %).

⚠ **Nicht angereichert wird der Community-Payload.** Er trägt gemessene Werte an
einen fremden Server, der die Rohdaten nie gesehen hat und nichts nachrechnet;
eine Schätzung dort wäre in einem Benchmark nicht mehr als solche erkennbar.
Die Monats-Fakten führen dafür ``eauto_summe_gemessen``/``wallbox_summe_gemessen``
neben den angereicherten Summen.
"""

from typing import Iterable, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import get_eauto_ladung_kwh, get_emob_pv_netz_kwh
from backend.services.eauto_wirtschaftlichkeit import wallbox_ist_heimlade_quelle
from backend.services.energie_profil.monats_aus_tagen import (
    MonatsSchluessel,
    lade_monats_summen_aus_tagen,
)

__all__ = [
    "hat_gepflegten_pv_anteil",
    "reichere_ladezeilen_an",
    "lade_abgeleitete_ladeanteile",
    "reichere_monatszeilen_an",
]

#: Eine Monatszeile, wie die Direkt-Leser sie halten: Monat, Quelle, Rohdict.
#: ``ist_wallbox`` unterscheidet die beiden Quellen — der Torwächter und die
#: Quellenwahl brauchen sie getrennt, der Aufrufer hält sie oft gemischt.
LadeZeile = tuple[MonatsSchluessel, bool, dict]


def hat_gepflegten_pv_anteil(
    eauto_daten: Iterable[dict],
    wallbox_daten: Iterable[dict] = (),
) -> bool:
    """Traegt die **kanonische Quelle** einen erfassten ``ladung_pv_kwh``-Wert?

    Der Torwaechter vor der Ableitung (N-141 Weg c, Rahmenbedingung 1: *ein
    gepflegter echter Wert gewinnt immer*).

    ⚠ **Geprueft wird die Anwesenheit des Schluessels, nicht seine Groesse.** Eine
    gepflegte ``0`` heisst „diesen Monat kam nichts aus der Sonne" und ist eine
    Aussage — sie mit einer Schaetzung zu ueberschreiben waere schlimmer als die
    Luecke, die dieser Fund schliesst. Die Unterscheidung ist dieselbe wie bei
    F-15 (``wert or DEFAULT`` verschluckte eine gepflegte 0), nur eine Ebene
    weiter: dort ein Tarif, hier eine Energiemenge.

    ⛔ **Gefragt wird NUR die Quelle — bis 2026-08-24 waren es beide Seiten.**
    Der alte Wortlaut hier lautete *„die Quellenwahl des Pools ist eine Frage
    der Menge, nicht der Pflege"*. Das traf die Regel nicht: ``get_emob_
    heimladung_canonical`` waehlt **strukturell** (Wallbox mit Heimladung ⇒ sie
    ist die Wahrheit, der E-Auto-Wert wird ignoriert), nicht nach Menge. Ein
    ignorierter Wert bekam damit ein Vetorecht gegen die Ableitung fuer die
    Quelle, die ihn gerade verworfen hatte.

    **Was das kostete, Ende zu Ende gemessen** (Wallbox ``ladung_kwh`` 200 ohne
    PV-Split, E-Auto mit einem Altwert 130/50, Tagesebene 62 %):

    ===========================  =========================================
    mit dem E-Auto-Altwert       Quelle=wallbox, PV=0, Netz=200  ⇒   **0 %**
    ohne ihn, sonst gleich       Quelle=wallbox, PV=124, Netz=76 ⇒  **62 %**
    ===========================  =========================================

    Nicht eine falsche Zahl, sondern **gar keine** — und zwar genau in den
    Monaten, die ``migrate_emob_canonical_source`` (v3.36.0) bewusst als
    „unaufloesbar" stehen liess (``winner_pv == 0 and loser_pv > 0``).

    ⚠ **Kein Bestand wird angefasst.** Der E-Auto-Wert bleibt stehen, wo er
    steht; er zaehlt nur nicht mehr gegen eine Quelle, die er nicht ist.
    """
    quelle = (
        wallbox_daten
        if wallbox_ist_heimlade_quelle(wallbox_daten)
        else eauto_daten
    )
    return any(
        zeile.get("ladung_pv_kwh") is not None
        for zeile in quelle
        if zeile
    )


def reichere_ladezeilen_an(
    *,
    eauto_daten: Sequence[dict],
    wallbox_daten: Sequence[dict],
    quote: Optional[float],
) -> tuple[list[dict], list[dict], bool]:
    """Schreibt den abgeleiteten PV-/Netz-Anteil in **Kopien** der Monatszeilen.

    Die Zeilen eines Monats kommen zusammen herein, weil der Torwächter über
    beide Quellen zusammen entscheidet (s. ``hat_gepflegten_pv_anteil``).

    Angewandt wird die Quote auf die Ladung **jeder Zeile**, gelesen über
    denselben SoT-Leser, den auch ``summiere_emob_quelle`` benutzt. Damit ist
    ``Σ angereicherte Zeilen == Σ Zeilen × quote`` — die Aufteilung ist auf
    Zeilen-, Quellen- und Poolebene dieselbe, egal wer wann summiert. Genau das
    war vorher nicht der Fall: die Fakten-Schicht rechnete die Quote auf die
    **gepoolte** Ladung, alle anderen sahen die ungeteilten Rohwerte (F-16).

    ⚠ **Es werden Kopien geschrieben.** Die Dicts stammen aus
    ``InvestitionMonatsdaten.verbrauch_daten`` und sind an eine Session
    gebundene JSON-Felder; sie in-place zu ändern hieße, eine Schätzung in die
    Datenbank zu schreiben, sobald irgendwo ein ``flag_modified`` fällt
    (CLAUDE.md §SQLAlchemy JSON-Felder). Programmatisch füllen bleibt verboten —
    dies ist eine **Lesezeit**-Anreicherung.

    Args:
        eauto_daten: ``verbrauch_daten`` der privaten E-Autos **eines Monats**,
            bereits nach Anschaffung/Stilllegung und Dienstwagen gefiltert.
        wallbox_daten: dasselbe für die Wallboxen.
        quote: Anteil der Heimladung aus eigener Sonne (0…1) aus der Tagesebene.
            ``None`` heißt „keine Aussage" und lässt alles unverändert.

    Returns:
        ``(eauto', wallbox', abgeleitet)`` — die Zeilen (Kopien nur dort, wo
        angereichert wurde) und die Angabe, ob überhaupt etwas abgeleitet wurde.
        ``abgeleitet`` ist genau dann ``True``, wenn eine Zeile eine Ladung > 0
        trug und der Torwächter offen war; es ist das Provenance-Signal für den
        Aufrufer und darf nicht aus ``quote is not None`` erraten werden.
    """
    ea = list(eauto_daten)
    wb = list(wallbox_daten)
    if quote is None or hat_gepflegten_pv_anteil(ea, wb):
        return ea, wb, False

    abgeleitet = False

    def _anreichern(zeilen: list[dict]) -> list[dict]:
        nonlocal abgeleitet
        ergebnis: list[dict] = []
        for zeile in zeilen:
            zeile = zeile or {}
            # ⛔ Ein gepflegter Wert wird NIE ueberschrieben — jetzt auch auf
            # Zeilenebene. Solange das Tor ueber beide Seiten lief, war das
            # zwangslaeufig erfuellt: war irgendwo ein Wert, blieb das Tor zu.
            # Seit das Tor nur die Quelle fragt, kann es offen sein, waehrend
            # die ANDERE Seite einen Altwert traegt — ohne diese Zeile wuerde
            # er hier durch eine Schaetzung ersetzt. Unter dem alten Verhalten
            # aendert die Pruefung nichts (sie war dort leer erfuellt).
            if zeile.get("ladung_pv_kwh") is not None:
                ergebnis.append(zeile)
                continue
            pv, netz = get_emob_pv_netz_kwh(
                zeile, total_kwh=get_eauto_ladung_kwh(zeile)
            )
            basis = pv + netz
            if basis <= 0:
                ergebnis.append(zeile)
                continue
            neu = dict(zeile)
            neu["ladung_pv_kwh"] = basis * quote
            neu["ladung_netz_kwh"] = basis - neu["ladung_pv_kwh"]
            ergebnis.append(neu)
            abgeleitet = True
        return ergebnis

    return _anreichern(ea), _anreichern(wb), abgeleitet


async def lade_abgeleitete_ladeanteile(
    db: AsyncSession,
    anlage_id: int,
    *,
    von: Optional[MonatsSchluessel] = None,
    bis: Optional[MonatsSchluessel] = None,
) -> dict[MonatsSchluessel, float]:
    """Die abgeleitete PV-Quote je Monat — für Sichten **außerhalb** der Fakten.

    Die Monats-Fakten holen sich die Tagesebene ohnehin und geben die Quote aus
    ``TagesMonatsSumme.abgeleiteter_pv_anteil``; diese Funktion ist der Weg für
    die Sichten, die ``InvestitionMonatsdaten`` selbst laden (Komponenten-Hub,
    Aussichten, HA-Export, der Komponenten-Detailblock von Cockpit → Monat).

    ⚠ **Zwei Queries je Aufruf.** Sie ist deshalb einmal je Route zu rufen und
    das Ergebnis über die Monatsschleife zu tragen — nicht je Monat erneut.
    Wer keine Heimladung ohne gepflegten Anteil hat, braucht sie gar nicht;
    die Aufrufer prüfen das vorher (Entscheid Gernot 2026-08-08: eine Anlage
    ohne E-Mobilität zahlt nichts).

    Returns:
        Je Monat mit einer Aussage eine Quote ``0…1``. Monate ohne Ladung in der
        Tagesspur **fehlen** — Abwesenheit ist „keine Aussage", nicht 0.
    """
    summen = await lade_monats_summen_aus_tagen(db, anlage_id, von=von, bis=bis)
    return {
        schluessel: quote
        for schluessel, summe in summen.items()
        if (quote := summe.abgeleiteter_pv_anteil) is not None
    }


async def reichere_monatszeilen_an(
    db: AsyncSession,
    anlage_id: int,
    zeilen: Sequence[LadeZeile],
) -> list[dict]:
    """Der bequeme Weg für Sichten, die ``InvestitionMonatsdaten`` selbst laden.

    Nimmt die Zeilen **einer Sicht** in beliebiger Reihenfolge, gruppiert sie
    intern nach Monat und Quelle, wendet die Ableitung an und gibt die Dicts in
    **derselben Reihenfolge** zurück. Damit behält der Aufrufer seine eigene
    Struktur (Listen je Investition, Maps je Monat, verschachtelte Schleifen) und
    tauscht nur die Dicts aus.

    ⚠ **Die Query fällt nur an, wenn sie etwas ändern kann.** Trägt keine Zeile
    Heimladung oder ist der Anteil überall gepflegt, kehrt die Funktion ohne
    Datenbankzugriff zurück — eine Anlage ohne E-Mobilität zahlt nichts
    (Entscheid Gernot 2026-08-08, dieselbe Vorprüfung wie in der Fakten-Schicht).

    ⚠ **Der Torwächter gilt je Monat, nicht global.** Wer im Januar seinen
    PV-Anteil gepflegt hat und im Februar nicht, bekommt den Januar unverändert
    und den Februar abgeleitet. Ein globaler Torwächter würde bei einer einzigen
    gepflegten Zeile die ganze Historie ungeteilt lassen.

    Args:
        db: Session.
        anlage_id: Anlage.
        zeilen: ``(monat, ist_wallbox, verbrauch_daten)`` je Monatszeile,
            bereits nach Anschaffung/Stilllegung und Dienstwagen gefiltert.

    Returns:
        Die ``verbrauch_daten``-Dicts in Eingangsreihenfolge; angereichert, wo
        die Ableitung greift, sonst das unveränderte Original.
    """
    zeilen = list(zeilen)
    if not zeilen:
        return []

    je_monat: dict[MonatsSchluessel, tuple[list[int], list[int]]] = {}
    for index, (schluessel, ist_wallbox, _daten) in enumerate(zeilen):
        eauto_idx, wallbox_idx = je_monat.setdefault(schluessel, ([], []))
        (wallbox_idx if ist_wallbox else eauto_idx).append(index)

    # Vorprüfung vor der Query — dieselbe Bedingung wie in `_RohMonat.
    # emob_ladung_ohne_pv_anteil`: eine Sicht ohne ungepflegte Heimladung
    # bezahlt die Tagesebene nicht.
    offen = [
        schluessel
        for schluessel, (eauto_idx, wallbox_idx) in je_monat.items()
        if not hat_gepflegten_pv_anteil(
            [zeilen[i][2] for i in eauto_idx], [zeilen[i][2] for i in wallbox_idx]
        )
        and any(
            get_eauto_ladung_kwh(zeilen[i][2] or {}) > 0
            for i in (*eauto_idx, *wallbox_idx)
        )
    ]
    if not offen:
        return [daten for _s, _w, daten in zeilen]

    quoten = await lade_abgeleitete_ladeanteile(
        db, anlage_id, von=min(offen), bis=max(offen)
    )

    ergebnis: list[dict] = [daten for _s, _w, daten in zeilen]
    for schluessel in offen:
        quote = quoten.get(schluessel)
        if quote is None:
            continue
        eauto_idx, wallbox_idx = je_monat[schluessel]
        ea, wb, _abgeleitet = reichere_ladezeilen_an(
            eauto_daten=[zeilen[i][2] for i in eauto_idx],
            wallbox_daten=[zeilen[i][2] for i in wallbox_idx],
            quote=quote,
        )
        for i, daten in zip(eauto_idx, ea):
            ergebnis[i] = daten
        for i, daten in zip(wallbox_idx, wb):
            ergebnis[i] = daten
    return ergebnis
