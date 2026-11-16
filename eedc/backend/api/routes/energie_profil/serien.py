"""Energie-Profil — Stunden- und Serienreihen.

GET /api/energie-profil/{anlage_id}/komponenten-serien — `komponenten_kwh`-Keys eines Zeitraums als SerieInfo
GET /api/energie-profil/{anlage_id}/stunden            — 24 Stundenwerte eines Tages
"""
# Reiner Umzug aus `api/routes/energie_profil/views.py` (18.09.2026, Vorlage 4 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `views.py` haengt den Router ein und
# exportiert die Endpunkt-Namen weiter, die Aufrufer und Tests bisher von dort importierten.

from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.berechnungen import (
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    geraete_spalte_kw,
)
from backend.core.berechnungen.slot_konvention import (
    RASTER_BEGINN, RASTER_ENDE, forward_werte_je_backward_zeile, ist_beginn_raster,
)
from backend.core.exceptions import bad_request, not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from ._shared import (
    SerieInfo,
    StundenAntwort,
    StundenWertResponse,
    _key_to_serie_info,
)

router = APIRouter()


@router.get("/{anlage_id}/komponenten-serien", response_model=list[SerieInfo])
async def get_komponenten_serien(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Löst alle im Zeitraum vorkommenden `komponenten_kwh`-Keys zu SerieInfo
    (Label/Kategorie/Seite) auf.

    Dient der Tagestabelle, die pro Komponente eine eigene Diagnose-Spalte
    mit echtem Investitions-Label statt Roh-Key anbietet.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    if (bis - von).days > 366:
        raise bad_request("Zeitraum darf maximal 366 Tage umfassen")

    # HA-Bauform S5 (§3 (A) 26): an einem Kanal-Tag die Schlüssel wie `tage-werte` (Bilanz aus `kanal_tage`, Sonstiges
    # aus der Sonstiges-Gruppe) — `komponenten_der_tage`; die Tageszeilen lädt die Lesestelle selbst (E-S5-2, S5-R6).
    from backend.services.energie_profil.kanal_stunden import komponenten_der_tage

    alle_keys: set[str] = set()
    for komponenten_kwh in (await komponenten_der_tage(db, anlage_id, von, bis)).values():
        if komponenten_kwh:
            alle_keys.update(komponenten_kwh.keys())

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    serien: list[SerieInfo] = []
    for key in sorted(alle_keys):
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
    return serien

async def zeilen_der_stunden_sicht(db: AsyncSession, anlage_id: int, datum: date) -> tuple[list, list]:
    """Die Stundenzeilen, die ``/stunden`` zeigt: ``(vortag, rows)`` — aus ``get_stundenwerte`` herausgelöst (Päckchen
    BB2, N-783), damit der Leistungspfad-Rückfall der Tagesladung im Tag-Detail (``tag.py::_emob_ladung_tag``) dieselbe
    Zeilenmenge liest wie die Stundentabelle und bis dahin der Client.

    N-553: der Ladestand jeder Zeile kommt aus ihrer **Vorzeile** — dieselbe Regel wie in den Rechnungen (N-387,
    `slot_konvention`). Dafür wird der Vortag mitgeladen: ohne seine Stunde 23 bekäme Slot 0 dieses Tages keinen Wert,
    und das wäre eine Lücke, die es in den Daten nicht gibt. HA-Bauform S4 (S4-R-3b): und der Folgetag — an einem
    Kanal-Tag trägt seine Zeile 0 die Backward-Bahnen der Stunde 23 (`slot_konvention.bestandszeile_fuer_stundenbeginn`).
    Eine Abfrage, ein Tag mehr. HA-Bauform E-S3-2: an einem Tag mit Kanal-Gruppe tragen die Mengen der Kanal-Gruppen
    HAs `change` je Stunde (Mischzeilen, `energie_profil/kanal_stunden.py`, Stunde = Beginn seit S4); Wetter, Zählwerke
    und `komponenten` bleiben aus der Stundenzeile (S3-R6), nach Bahnen gepaart (S4-R-3b). Ohne Kanal-Gruppe: die
    Stundenzeilen des Tages unverändert."""
    from backend.services.energie_profil.kanal_stunden import stunden_des_tages

    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= datum - timedelta(days=1),
            TagesEnergieProfil.datum <= datum + timedelta(days=1),
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    alle = result.scalars().all()
    vortag = [z for z in alle if z.datum < datum]
    rows = await stunden_des_tages(db, anlage_id, datum, [z for z in alle if z.datum >= datum])
    return vortag, rows


@router.get("/{anlage_id}/stunden", response_model=StundenAntwort)
async def get_stundenwerte(
    anlage_id: int,
    datum: date = Query(..., description="Tag (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt die 24 Stundenwerte eines Tages aus TagesEnergieProfil zurück — an einem Tag mit Kanal-Gruppe die Mengen
    dieser Gruppen aus dem Kanal-Stundentag (HA-Bauform E-S3-2).

    Enthält zusätzlich `serien` mit aufgelösten Labels für alle in `komponenten`
    vorkommenden Einträge — damit Sonstiges-Investments (Poolpumpe, Sauna …)
    namentlich im Frontend angezeigt werden können.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise not_found("Anlage", anlage_id)

    from backend.services.energie_profil.kanal_stunden import aus_kanal_gruppe

    vortag, rows = await zeilen_der_stunden_sicht(db, anlage_id, datum)
    # SoC je Zeile über die EINE Paarung (N-553/N-387): Bestandszeilen aus der Vorzeile (der Vortag liefert Slot 0),
    # Mischzeilen (Beginn-Raster) zeilengleich — `forward_werte_je_backward_zeile` fragt das Attribut `raster`.
    soc_je_zeile = forward_werte_je_backward_zeile([*vortag, *rows], "soc_prozent")[len(vortag):]
    soc_je_stunde = {z.stunde: soc for z, soc in zip(rows, soc_je_zeile)}

    # ⭐ **Zwei Fragen, zwei Groessen** (N-553): Die Zeile oben beantwortet
    # „welcher Ladestand gehoert zu DIESER Stunde" — dafuer die Paarung. Die
    # Kachel „Ladestand · Stand am Tagesende" fragt etwas anderes: „was ist der
    # JUENGSTE gemessene Stand". Der steht ungepaart in der letzten Zeile des
    # Tages; durch die Paarung wandert er aus dem Tagesraster (er gehoert zu
    # Slot 0 des Folgetags). Deshalb reist er als eigenes Feld mit, statt dass
    # eine Groesse beide Fragen halb beantwortet.
    soc_zuletzt = next(
        (z.soc_prozent for z in reversed(rows) if z.soc_prozent is not None), None,
    )

    # Investments für Label-Auflösung laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    inv_map: dict[int, Investition] = {
        inv.id: inv for inv in inv_result.scalars().all()
    }

    # Alle vorkommenden Komponenten-Keys sammeln (über alle Stunden)
    alle_keys: set[str] = set()
    for r in rows:
        if r.komponenten:
            alle_keys.update(r.komponenten.keys())

    # Keys zu SerieInfo auflösen (nur einmal pro Key, geordnet)
    serien: list[SerieInfo] = []
    seen: set[str] = set()
    for key in sorted(alle_keys):
        if key in seen:
            continue
        info = _key_to_serie_info(key, inv_map)
        if info:
            serien.append(SerieInfo(**info))
            seen.add(key)

    # #263/T1 — die Geräte-Sammelspalten kennen BEIDE Pfade.
    #
    # `waermepumpe_kw`/`wallbox_kw` kommen aus dem Zähler-Snapshot und bleiben
    # leer, wenn nur ein Leistungssensor zugeordnet ist — während derselbe Wert
    # in `komponenten` steht, die gerätebenannte Spalte daneben ihn zeigt und
    # der Monats-Modus-Split aus ihm rechnet. Die Auflösung („Zähler schlägt
    # Leistung, kein Key heißt None") liegt im Layer, nicht hier.
    #
    # ⚠ **Bewusst nur die Geräte-Spalten.** `pv_kw` und `verbrauch_kw` sind
    # Bilanzgrößen — an ihnen hängen Performance-Ratio sowie Überschuss/Defizit
    # (`aggregator.py`). Ein Fallback dort änderte die Bilanz, nicht eine
    # Anzeige; das wäre ein eigener Vorgang mit eigener Messung.
    stunden = [
        StundenWertResponse(
            stunde=r.stunde,
            pv_kw=r.pv_kw,
            verbrauch_kw=r.verbrauch_kw,
            einspeisung_kw=r.einspeisung_kw,
            netzbezug_kw=r.netzbezug_kw,
            batterie_kw=r.batterie_kw,
            # HA-Bauform S4 E-S4-3 (H-2b): der Rückfall auf den Leistungspfad nur, wenn die Gruppe am Tag die Wahl
            # `bestand` hat — eine leere Stunde eines Kanal-Tags bleibt leer (ihre Menge steht in der Folgestunde).
            waermepumpe_kw=geraete_spalte_kw(
                r.waermepumpe_kw, None if aus_kanal_gruppe(r, "waermepumpe_kw") else r.komponenten,
                WAERMEPUMPE_KOMPONENTEN_PREFIXE,
            ),
            wallbox_kw=geraete_spalte_kw(
                r.wallbox_kw, None if aus_kanal_gruppe(r, "wallbox_kw") else r.komponenten, WALLBOX_KOMPONENTEN_PREFIXE,
            ),
            ueberschuss_kw=r.ueberschuss_kw,
            defizit_kw=r.defizit_kw,
            temperatur_c=r.temperatur_c,
            globalstrahlung_wm2=r.globalstrahlung_wm2,
            soc_prozent=soc_je_stunde.get(r.stunde),
            komponenten=r.komponenten,
            wp_starts_anzahl=r.wp_starts_anzahl,
            wp_betriebsstunden=r.wp_betriebsstunden,
            spannen=r.spannen or None,
            raster=RASTER_BEGINN if ist_beginn_raster(r) else RASTER_ENDE,
        )
        for r in rows
    ]

    return StundenAntwort(
        stunden=stunden, serien=serien, soc_zuletzt_prozent=soc_zuletzt,
    )
