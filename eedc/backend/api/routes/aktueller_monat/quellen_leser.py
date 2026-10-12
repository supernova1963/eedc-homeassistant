"""Cockpit → Monat: Leser der Quellen-Kaskade ohne Uhr und ohne Test-Naht (RF-12).

Aus ``__init__.py`` wortgleich herausgelöst (Serie „Funktion vor Datei", RF-12 — die Datei lag über 900 netto): der
gespeicherte Zweig (``_collect_saved_data``, ADR-002/P10), die Kanal-Leser des Kalendermonats (HA-Bauform E4a-2/E4c/E4d),
die Regeln der gemessenen 0 (N-585, E4d) und die Wandlungsverluste (N-588). Hier steht nur, was kein Test am Paketmodul
tauscht und was weder die Uhr noch einen Sammler liest; Sammler, Endpunkt, Orchestrator und seine Phasen bleiben in
``__init__.py`` (Modul-Docstring dort), das diese Namen importiert und ruft.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat.schemas import DatenquelleInfo
from backend.models.anlage import Anlage
from backend.services.monats_fakten import MonatsFakt


#: N-585 — Felder, deren **gemessene 0** ein Monatswert ist (``KONZEPT-UNVOLLSTAENDIGE-WERTE.md`` §3): die
#: Basis-Zähler (Einspeisung, Netzbezug, Anlagen-PV-Zähler) …
_NULL_IST_MESSWERT_BASIS = frozenset({"einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"})
#: … und die Gerätefelder dieser Typen. ⛔ **Nicht** Wärmepumpe und PV-String (Bauplan N-585, „Nicht in diesem
#: Bau"): für eine WP-0 fehlt eine Darstellungsregel für „kein Betrieb" — die Grund-Texte sagten „kein
#: Stromverbrauch erfasst", die Ergebnis-Leiter „WP-Ersparnis fehlt" (Betriebsart-Kanäle der HA-Bauform). Vor N-609
#: (Teil B) hätte eine durchgelassene WP-0 über den damaligen Aggregat-Zweig zusätzlich eine Phantom-Ersparnis
#: erzeugt (gemessen 8,64 / 86,40 €). Eine String-0 neben dem Anlagenzähler nähme dem String dessen Rest — eine
#: sichtbare Änderung der PV-Achse ohne Matrix-Form. Für beide bleibt es bei „über 0".
_NULL_IST_MESSWERT_TYPEN = frozenset({"speicher", "balkonkraftwerk", "wallbox", "e-auto", "waermepumpe"})
#: ⭐ **Seit HA-Bauform E4d auch die Wärmepumpe** (Bauplan §8a, Rest N-585): die Darstellungsregel steht — eine gemessene
#: 0 beim Strom ist erfasst (F-5); Strom 0 und Wärme 0 sind Stufe 3 der Grund-Kette („kein Heizbetrieb in diesem
#: Zeitraum" bzw. „keine Warmwasserbereitung …", Klasse Zeitraum), Mengen 0, Ersparnis 0 €, die Ergebnis-Leiter führt
#: die Zeile nicht als „fehlt". Der Absatz oben beschreibt den Stand davor.


def _null_ist_messwert(feld_name: str, typ_je_inv: dict[str, str]) -> bool:
    """Gilt eine gemessene 0 dieses Felds als Wert? Basisfelder immer, Gerätefelder je Typ (N-585).

    ``typ_je_inv`` kommt aus den geladenen Investitionen der Anlage; sind sie nicht geladen, ist es leer und es
    gelten nur die Basisfelder.
    """
    if feld_name in _NULL_IST_MESSWERT_BASIS:
        return True
    if feld_name.startswith("inv_"):
        inv_id = feld_name[len("inv_"):].split("_", 1)[0]
        return typ_je_inv.get(inv_id) in _NULL_IST_MESSWERT_TYPEN
    return False


def _sensor_to_feld(anlage: Anlage) -> dict[str, str]:
    """``{sensor_id: feld}`` der HA-Zuordnung (Basis-Zähler und Gerätefelder) — der HA-Weg des Monats."""
    mapping = anlage.sensor_mapping or {}
    basis = mapping.get("basis", {})
    inv_mapping = mapping.get("investitionen", {})
    # Sensor-IDs sammeln und Rückmapping erstellen: sensor_id → feld_name
    sensor_to_feld: dict[str, str] = {}

    basis_feld_map = {
        "einspeisung": "einspeisung_kwh",
        "netzbezug": "netzbezug_kwh",
        "pv_gesamt": "pv_erzeugung_kwh",
    }
    for mapping_key, feld_name in basis_feld_map.items():
        feld_mapping = basis.get(mapping_key)
        if feld_mapping and feld_mapping.get("strategie") == "sensor" and feld_mapping.get("sensor_id"):
            sensor_to_feld[feld_mapping["sensor_id"]] = feld_name

    for inv_id_str, inv_data in inv_mapping.items():
        felder = inv_data.get("felder", {})
        for feld_key, feld_config in felder.items():
            if feld_config and feld_config.get("strategie") == "sensor" and feld_config.get("sensor_id"):
                sensor_to_feld[feld_config["sensor_id"]] = f"inv_{inv_id_str}_{feld_key}"

    return sensor_to_feld


async def _ha_statistik_aus_kanaelen(
    db: AsyncSession, anlage: Anlage, investitionen, jahr: int, monat: int,
    ha_stats: dict[str, tuple[float, DatenquelleInfo]],
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """HA-Bauform E4a-2 (Umschaltstelle 3, B-2): decken die Spiegel ALLER Bilanz-Sensoren den Kalendermonat voll,
    gilt ihr Kanal-Δ statt des HA-Lesers — ohne Deckel, ohne Rücksprung-Verwurf (R-5, HA-Teil). Nur wo der HA-Weg
    überhaupt geliefert hat (HA erreichbar); dieselbe Regel für die gemessene 0 (N-585) wie dort."""
    if not ha_stats:
        return ha_stats
    out, _ersetzt = await _ha_statistik_aus_kanaelen_mit_marke(db, anlage, investitionen, jahr, monat, ha_stats)
    return out


async def _ha_statistik_aus_kanaelen_mit_marke(
    db: AsyncSession, anlage: Anlage, investitionen, jahr: int, monat: int,
    ha_stats: dict[str, tuple[float, DatenquelleInfo]],
) -> tuple[dict[str, tuple[float, DatenquelleInfo]], bool]:
    """Wie ``_ha_statistik_aus_kanaelen``, dazu die Marke „die Bilanz-Gruppe kam aus den Kanälen" (HA-Bauform E4c:
    der Sonstiges-Erzeuger des Monats ohne Abschluss zählt nur dann, Lesart 1)."""
    if not ha_stats:
        return ha_stats, False
    from backend.services.kanal.bilanz_leser import kanal_kalendermonate

    ersatz = (await kanal_kalendermonate(db, anlage.id, [(jahr, monat)])).get((jahr, monat))
    if not ersatz:
        return ha_stats, False
    sensor_to_feld = _sensor_to_feld(anlage)
    typ_je_inv = {str(i.id): i.typ for i in investitionen}
    quelle = next(iter(ha_stats.values()))[1]
    out = dict(ha_stats)
    for sid, w in ersatz.items():
        feld = sensor_to_feld.get(sid)
        if not feld:
            continue
        if w.differenz > 0 or (w.differenz == 0 and w.intervalle >= 1 and _null_ist_messwert(feld, typ_je_inv)):
            out[feld] = (w.differenz, quelle)
        else:
            out.pop(feld, None)
    return out, True


async def _geraete_aus_kanaelen(
    db: AsyncSession, anlage: Anlage, investitionen, jahr: int, monat: int,
    ha_stats: dict[str, tuple[float, DatenquelleInfo]], *, monats_fakt, bilanz_ersetzt: bool,
):
    """HA-Bauform E4c (U5/U6): die E-Mob- und die Sonstiges-Gruppe des Kalendermonats aus den Kanälen.

    Nur auf dem HA-Weg (``ha_stats`` geliefert) und nur, wo der Monat für die Gruppe KEINE Zeile trägt (gespeichert
    schlägt gerechnet, P8). Je Gruppe die Quellenwahl des Lesers (``kanal/geraete_leser.geraete_kalendermonate``):

    * **E-Mob** gedeckt ⇒ die Gerätefelder (``inv_<id>_<feld>``) sind das Kanal-Δ des Kalendermonats (ohne Deckel, ohne
      Rücksprung-Verwurf, wie die Bilanz-Gruppe B-2), und der PV-Anteil der Heimladung ist der des abgeleiteten Kanals
      — dieselbe Aufteilung wie die Monats-Fakten (N-631: vorher stand die ganze Ladung als Netz, weil dieser Weg keine
      Quote kannte). Die Regeln (Wallbox-Regel, Pool, Dienstwagen) entscheidet weiter ``emob_heimladung_pool``.
    * **Sonstiges** — Verbraucher aus ihrer Gruppe (Entweder-oder W2-R4), Erzeuger aus den Kanal-Werten der
      Bilanz-Gruppe (nur wenn die Bilanz-Gruppe den Monat aus den Kanälen nahm, ``bilanz_ersetzt``) — als Zeilen durch
      dieselbe Faltung wie der Fakt (``monats_fakten.sonstiges_aus_zeilen``). Vorher führte Cockpit → Monat Sonstiges
      nur aus dem Monats-Fakt, ohne Abschluss also gar nicht (EV/Autarkie ohne BHKW).

    Returns: ``(ha_stats', emob, sonstiges)`` — ``emob`` = ``(gedeckt, quote)``, ``sonstiges`` = ``SonstigesFakten``
    oder ``None``.
    """
    if not ha_stats:
        return ha_stats, (False, None), None
    typen = {getattr(i, "typ", None) for i in investitionen}
    if not typen & {"e-auto", "wallbox", "sonstiges"}:
        return ha_stats, (False, None), None
    from backend.services.kanal.geraete_leser import geraete_kalendermonate
    from backend.services.monats_fakten import sonstiges_aus_zeilen
    from backend.services.snapshot.keys import KUMULATIVE_ZAEHLER_FELDER, _categorize_counter

    g = (await geraete_kalendermonate(db, anlage.id, [(jahr, monat)])).get((jahr, monat))
    zeilen_typen = set(monats_fakt.meta.typen_mit_zeile) if monats_fakt is not None else set()
    emob_zeile = monats_fakt is not None and bool(
        monats_fakt.emob.ladedaten_je_inv or monats_fakt.emob.dienstlich_ladedaten_je_inv)
    out = dict(ha_stats)
    quelle = next(iter(ha_stats.values()))[1]
    typ_je_inv = {str(i.id): i.typ for i in investitionen}

    emob = (False, None)
    if g is not None and g.emob.kanal and not emob_zeile:
        for inv_id, zeile in g.emob.zeilen.items():
            for feld, wert in zeile.items():
                key = f"inv_{inv_id}_{feld}"
                wert = round(wert, 2)
                if wert > 0 or (wert == 0 and _null_ist_messwert(key, typ_je_inv)):
                    out[key] = (wert, quelle)
                else:
                    out.pop(key, None)
        emob = (True, g.emob.quote)

    sonstiges = None
    if "sonstiges" not in zeilen_typen:
        zeilen: dict[int, dict] = {}
        if g is not None and g.sonstiges.kanal:
            zeilen.update({i: dict(z) for i, z in g.sonstiges.zeilen.items()})
        if bilanz_ersetzt:
            for inv in investitionen:
                if inv.typ != "sonstiges" or not inv.ist_aktiv_im_monat(jahr, monat):
                    continue
                params = inv.parameter if isinstance(inv.parameter, dict) else {}
                for feld in KUMULATIVE_ZAEHLER_FELDER.get("sonstiges", ()):
                    key = f"inv_{inv.id}_{feld}"
                    if key in out and _categorize_counter(feld, "sonstiges", params) == "erzeugung_sonstiges":
                        zeilen.setdefault(inv.id, {})[feld] = out[key][0]
        if zeilen:
            sonstiges = sonstiges_aus_zeilen(investitionen, (jahr, monat), zeilen)
            for feld, wert in (("sonstiges_erzeugung_kwh", sonstiges.erzeugung_kwh),
                               ("sonstiges_abgabe_kwh", sonstiges.abgabe_kwh)):
                if wert > 0:
                    out[feld] = (round(wert, 2), quelle)
    return out, emob, sonstiges


async def _wp_aus_kanaelen(
    db: AsyncSession, anlage: Anlage, investitionen, jahr: int, monat: int,
    ha_stats: dict[str, tuple[float, DatenquelleInfo]], *, monats_fakt,
):
    """HA-Bauform E4d (U4, N-630): die WP-Gruppe des Kalendermonats aus den Kanälen.

    Nur auf dem HA-Weg (``ha_stats`` geliefert) und nur, wo der Monat KEINE WP-Zeile trägt (gespeichert schlägt
    gerechnet, P8). Deckt die WP-Gruppe den Kalendermonat (``kanal/wp_leser.wp_kalendermonate``):

    * die Gerätefelder (``inv_<id>_<feld>``: Strom, Wärme je Feld, Betriebsart-Strom, Kälte) sind das Kanal-Δ des
      Kalendermonats — ohne Deckel, ohne Rücksprung-Verwurf, wie die Bilanz-Gruppe (B-2); K3/D1 fallen danach wie für
      jede Quelle in ``aggregiere_typen``;
    * die WP-Feldgruppe (``WpFakten``: Funktionsmengen, Betriebsart-Strom, Kälte, Strom je Betriebsart, Abdeckung,
      Mengen je Gerät) entsteht aus denselben Zeilen über die Faltung der Monats-Fakten (``monats_fakten.wp_aus_zeilen``)
      — vorher führte Cockpit → Monat sie nur aus dem Monats-Fakt, ohne Abschluss also gar nicht (N-630).

    Returns: ``(ha_stats', wp, zeilen)`` — ``wp`` = ``WpFakten`` oder ``None``, ``zeilen`` = die Kanal-Zeilen je Gerät.
    """
    if not ha_stats or not any(getattr(i, "typ", None) == "waermepumpe" for i in investitionen):
        return ha_stats, None, {}
    if monats_fakt is not None and "waermepumpe" in monats_fakt.meta.typen_mit_zeile:
        return ha_stats, None, {}
    from backend.core.betriebsmodus import MODUS_ABDECKUNG_FELD, MODUS_STROM_FELD
    from backend.services.kanal.wp_leser import wp_kalendermonate
    from backend.services.monats_fakten import wp_aus_zeilen

    z = (await wp_kalendermonate(db, anlage.id, [(jahr, monat)])).get((jahr, monat))
    if z is None or not z.kanal:
        return ha_stats, None, {}
    abgeleitet = set(MODUS_STROM_FELD.values()) | {MODUS_ABDECKUNG_FELD}
    out = dict(ha_stats)
    quelle = next(iter(ha_stats.values()))[1]
    typ_je_inv = {str(i.id): i.typ for i in investitionen}
    for inv_id, zeile in z.zeilen.items():
        for feld, wert in zeile.items():
            if feld in abgeleitet:
                continue                      # Teilmengen und Abdeckung sind keine Felder der Quellen-Kaskade
            key = f"inv_{inv_id}_{feld}"
            wert = round(wert, 2)
            if wert > 0 or (wert == 0 and _null_ist_messwert(key, typ_je_inv)):
                out[key] = (wert, quelle)
            else:
                out.pop(key, None)
    return out, wp_aus_zeilen(investitionen, (jahr, monat), z.zeilen), dict(z.zeilen)


def _wp_sicht(monats_fakt, wp):
    """Der Monats-Fakt, wie ihn die WP-Abschnitte lesen: mit der WP-Gruppe aus den Kanälen, wo es sie gibt (E4d).
    ⚠ Nur für die Wärme/Klima-Abschnitte — sie lesen ausschließlich ``.wp``; jede andere Gruppe bleibt der Fakt."""
    if wp is None:
        return monats_fakt
    if monats_fakt is not None:
        import dataclasses

        return dataclasses.replace(monats_fakt, wp=wp)
    from types import SimpleNamespace

    return SimpleNamespace(wp=wp)


def _collect_saved_data(
    fakt: Optional[MonatsFakt],
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Der **gespeicherte** Zweig der Quellen-Kaskade (Konfidenz 85 %).

    Faltet nichts mehr selbst: die Mengen kommen aus den Monats-Fakten
    (ADR-002/**P10**), wo Zeitfilter (``aktiv`` · Anschaffung · Stilllegung),
    Dienstwagen-Filter, P7-Auflösung der PV und der Monatstarif genau einmal
    gelten. Übrig bleibt hier die **Merge-Semantik** — und die ist bewusst
    unverändert:

    - Die ``> 0``-Gates sind keine Rechenregel, sondern die Präzedenz-Regel der
      Kaskade: ein Feld, das ``saved`` nicht setzt, darf von einer stärkeren
      Quelle (Connector · MQTT · HA-Statistics) kommen. ``is not None`` daraus
      zu machen wäre eine andere Route, nicht dieselbe mit anderer Herkunft.
    - Einspeisung/Netzbezug kommen weiter direkt von der ``Monatsdaten``-Zeile
      und **nur, wenn sie dort gesetzt sind**: ``ZaehlerFakten`` macht aus einer
      fehlenden Zahl eine 0,0, und eine 0,0 aus der schwächsten Quelle würde
      eine echte Lücke füllen, die eine stärkere Quelle noch schließen könnte.

    Zwei Zahlen ändern sich dadurch sichtbar (beide gewollt, ``C1c``):
    die PV ist **P7-aufgelöst** (das Anlagen-Aggregat füllt Modul-Lücken, statt
    dass der Monatsbericht bei reiner Aggregat-Pflege gar keine PV zeigt), und
    der BKW-Eigenverbrauch fällt ohne Messwert **nicht** mehr auf die volle
    Erzeugung zurück (der alte D5-Quirk, divergent zu Komponenten/Übersicht).
    """
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    if fakt is None:
        return resolved

    md = fakt.meta.monatsdaten
    quelle = DatenquelleInfo(
        quelle="gespeichert", konfidenz=85,
        zeitpunkt=(
            md.updated_at.isoformat()
            if md is not None and getattr(md, "updated_at", None) else None
        ),
    )

    if md is not None:
        for attr, feld in [
            ("einspeisung_kwh", "einspeisung_kwh"),
            ("netzbezug_kwh", "netzbezug_kwh"),
        ]:
            val = getattr(md, attr, None)
            if val is not None:
                resolved[feld] = (val, quelle)

    for feld, wert in (
        # Module (P7-aufgelöst) + BKW — die PV-Achse der Anlage.
        ("pv_erzeugung_kwh", fakt.erzeugung.pv_kwh),
        ("speicher_ladung_kwh", fakt.speicher.ladung_kwh),
        ("speicher_entladung_kwh", fakt.speicher.entladung_kwh),
        # #183: bei getrennter Strommessung ist der Gesamt-Strom bereits im
        # Resolver summiert; `waerme` = waerme_kwh oder Heiz+WW.
        ("wp_strom_kwh", fakt.wp.strom_kwh),
        ("wp_waerme_kwh", fakt.wp.waerme_kwh),
        # #263 K-2 (E-B): der Kühlanteil — Teilmenge von `wp_strom_kwh`, hier
        # nur mitgeführt, damit die Ersparnis-Rechnung ihn herausnehmen kann.
        ("wp_modus_kuehlen_kwh", fakt.wp.modus_strom_kuehlen_kwh),
        # Heimladungs-Trias aus EINER Quelle (#262) — Dienstwagen sind in der
        # Schicht bereits heraus ([[feedback_dienstwagen_alle_checks]]).
        ("emob_ladung_kwh", fakt.emob.ladung_kwh),
        ("emob_km", fakt.emob.km),
        ("emob_verbrauch_kwh", fakt.emob.fahrverbrauch_kwh),
        ("emob_pv_ladung_kwh", fakt.emob.ladung_pv_kwh),
        ("emob_ladung_extern_euro", fakt.emob.extern_euro),
        ("bkw_erzeugung_kwh", fakt.bkw.erzeugung_kwh),
        ("bkw_eigenverbrauch_kwh", fakt.bkw.eigenverbrauch_gemessen_kwh),
        # Sonstiger Erzeuger (BHKW) speist hinter den Hauszähler.
        ("sonstiges_erzeugung_kwh", fakt.sonstiges.erzeugung_kwh),
        # §9.2: Abgabe an Dritte — wird in der Bilanz unten vom Eigenverbrauch abgezogen.
        ("sonstiges_abgabe_kwh", fakt.sonstiges.abgabe_kwh),
    ):
        if wert > 0:
            resolved[feld] = (wert, quelle)
    return resolved


def _wp_gemessene_null_aus_fakt(resolved: dict, fakt: Optional[MonatsFakt]) -> None:
    """HA-Bauform E4d (Bauplan §8a, Rest N-585): die GEMESSENE 0 der Wärmepumpe aus der Monatszeile — als LETZTE Quelle.

    Die Zeile trägt Strom bzw. Wärme mit 0 (``WpFakten.strom_gemessen``/``waerme_gemessen``): „kein Betrieb im
    Zeitraum", kein fehlender Zähler. ⚠ **Nicht in ``_collect_saved_data``** — dort sind die ``> 0``-Gates die
    Präzedenz der Kaskade (eine gespeicherte 0 darf eine stärkere Quelle nicht sperren, Docstring dort). Deshalb erst
    NACH der Kaskade und NACH der Aggregation der Gerätefelder: nur ein Feld, das keine Quelle gefüllt hat, bekommt die
    gemessene 0 der Zeile. Ändert ``resolved`` an Ort und Stelle."""
    if fakt is None:
        return
    md = fakt.meta.monatsdaten
    quelle = DatenquelleInfo(
        quelle="gespeichert", konfidenz=85,
        zeitpunkt=md.updated_at.isoformat() if md is not None and getattr(md, "updated_at", None) else None,
    )
    for feld, wert, gemessen in (
        ("wp_strom_kwh", fakt.wp.strom_kwh, fakt.wp.strom_gemessen),
        ("wp_waerme_kwh", fakt.wp.waerme_kwh, fakt.wp.waerme_gemessen),
    ):
        if feld not in resolved and wert == 0 and gemessen:
            resolved[feld] = (0.0, quelle)


async def _wandlungsverluste_des_monats(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, fakt,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Wandlungsverluste, ihr Bezug (Σ String-Zähler) und der Messpunkt-Vertrag (``verluste_grund``) des Monats —
    HA-Bauform E4b, N-588. Bewertet werden sie in dieser Route über ``eigenverbrauch_ohne_verluste_kwh`` (Ersparnis,
    USt); die Bilanz (EV, Autarkie, Quote) bleibt.

    Quelle ist der Kanal-Monat (W2-R3), unabhängig davon, welche der Quellen dieser Route die Mengen trägt. Mit
    Monats-Fakt aus den Fakten (die den Kanal-Monat seit E4b auch für abgeschlossene Monate lesen); ohne Fakt — der
    laufende Monat ohne Zeile, ein Monat nur aus HA — direkt aus ``kanal_monate`` für diesen einen Monat, und nur, wenn
    die Anlage einen Anlagenzähler-Kanal hat. Ohne Anlagenzähler oder ohne Kanal-Deckung ``(None, None, None)``."""
    if fakt is not None:
        e = fakt.erzeugung
        return e.wandlungsverluste_kwh, e.wandlungsverluste_bezug_kwh, e.verluste_grund
    from backend.services.kanal.bilanz_leser import hat_anlagenzaehler_kanal, kanal_monate

    if not await hat_anlagenzaehler_kanal(db, anlage_id):
        return None, None, None
    summe = (await kanal_monate(db, anlage_id, von=(jahr, monat), bis=(jahr, monat))).get((jahr, monat))
    if summe is None:
        return None, None, None
    return summe.wandlungsverluste_kwh, summe.wandlungsverluste_bezug_kwh, summe.verluste_grund
