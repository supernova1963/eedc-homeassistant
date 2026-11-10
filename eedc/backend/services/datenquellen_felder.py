"""
Zuordnungen der Datenquellen-Fläche lesen — die vier lesenden Phasen von `GET /api/datenquellen/{anlage_id}/felder`.

Schnitt `zuordnungen_lesen` (Etappe E1 «Diagnose-Paket», 10.11.2026; Messung E0-Bericht §(7)): `_felder_laden`,
`_quellen_aufloesen`, `_praezedenzen` und `_antwort` schreiben nicht (statisch und auf vier Kopien: 0 Schreib-SQL, 0 dirty,
`sensor_mapping` bitgleich) — geschrieben wird nur in `_festschreiben`, und das bleibt in der Route. Damit rufen zwei Stellen
dieselbe Kette: die Route (danach `_festschreiben` und `_verfuegbarkeit`, Antwort bitgleich, GM `datenquellen-felder`) und das
Diagnose-Paket (`services/diagnose_paket/`), das nur liest.

Die Funktionen sind wörtlich aus `api/routes/datenquellen.py` verschoben (RF-82-Bauform, Kommentare eingeschlossen); die Route
importiert, was sie und ihre Nachbarn (`datenquellen_themen.py`, Tests) weiter unter dem alten Namen brauchen.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import zustands_kanon
from backend.core.berechnungen.preis_reihe import ist_dynamisch
from backend.core.betriebsmodus import (
    AUFGETEILTE_MODI,
    MODUS_FELD_KEY,
    betriebsmodus_klartext,
    betriebsmodus_werte_je_betriebsart,
)
from backend.core.feld_auswertungen import sichten_fuer
from backend.core.field_definitions import (
    anlage_typen_mit_kontext,
    basis_feld_key,
    ist_text_feld,
    wp_betriebsart,
    wp_menge,
)
from backend.core.investition_parameter import kuehlung_art
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.datenquellen_mapping_sync import feld_id
from backend.services.datenquellen_resolver import resolve_effektive_quelle
from backend.services.live_sensor_config import extract_live_config, legacy_invert_aktiv
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.utils.investition_filter import aktiv_am_tag, sort_investitionen_nach_typ


# Quell-Kennungen. B2.2 bietet die aktuell verfügbaren MQTT-Optionen; HA-Sensor
# und MQTT-Gateway folgen (P2 bzw. B3-Discovery). Präferenz-SoT HA > Gateway >
# Inbound > manuell (§2d).
#
# ⚠ Hier stand bis 2026-08-22 „Default (kein Eintrag) = Standard-Inbound" (N-315).
# Das ist seit B8-2 falsch: ohne Eintrag entscheidet `resolve_effektive_quelle`,
# und dessen Stufe 3 wählt Inbound NUR bei tatsächlichem Wert — sonst „keine",
# ohne zu persistieren (self-healing). Der Satz beschrieb den Zustand vor B8-2
# und widersprach dem Resolver-Docstring, an dem der Code hängt.
QUELLE_STANDARD = "mqtt_inbound_standard"
QUELLE_KEINE = "keine"
QUELLE_GATEWAY = "mqtt_gateway"
# HA-Sensor-Quellen (Schritt B): EINE Feld-Spalte „HA-Sensor", zwei Transporte —
# ha_app = Supervisor-Token (Add-on), ha_connector = Remote-HA per LL-Token
# (ha_remote/B4a). Der Resolver (B5) liest den Wert je nach aktiver Verbindung.
QUELLE_HA_APP = "ha_app"
QUELLE_HA_CONNECTOR = "ha_connector"
QUELLEN_HA = {QUELLE_HA_APP, QUELLE_HA_CONNECTOR}


#: Die zwei Nähte nach außen (HA-Transport, HA-Detail-Batch) — die Route reicht ihre Modul-Namen durch (s. `zuordnungen_lesen`).
HaAufloesen = Callable[[AsyncSession], Awaitable[tuple]]
HaDetails = Callable[[AsyncSession, set], Awaitable[dict]]


async def _resolve_ha(db: AsyncSession) -> tuple:
    """(api_url, token, quelle_kind) der aktiven HA-Verbindung — zentraler Helper.

    Delegiert an `services.ha_connection.resolve_ha_connection` (EINE Wahrheit,
    auch von der Live-Engine genutzt). kind = ha_app (Supervisor) | ha_connector
    (Remote-HA) | None.
    """
    from backend.services.ha_connection import resolve_ha_connection
    return await resolve_ha_connection(db)


async def _ha_states_detail(db: AsyncSession, entity_ids: set) -> dict:
    """Detail-Batch der HA-Entities: `{eid: {"wert","einheit","state_class"}}`.

    EIN `/states`-Call gegen die aktive HA-Verbindung (Supervisor ODER Remote-HA).
    `wert` (C1, Wert-Anzeige) + `einheit`/`state_class` (§2i-Validierung: Einheiten-
    Mismatch #200, fehlendes state_class). Nur die Fläche — Engine unberührt (C2).
    Nicht erreichbar → leeres Dict (Feld amber, keine Validierungs-Fehlalarme).
    """
    if not entity_ids:
        return {}
    api_url, token, _ = await _resolve_ha(db)
    if not api_url or not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{api_url}/states", headers={"Authorization": f"Bearer {token}"})
    except Exception:  # noqa: BLE001 — Netzwerk-/TLS-Fehler → keine Werte (Feld amber)
        return {}
    if resp.status_code != 200:
        return {}
    out: dict = {}
    for st in resp.json():
        eid = st.get("entity_id")
        if eid not in entity_ids:
            continue
        roh_state = st.get("state")
        try:
            wert = float(roh_state)
        except (ValueError, TypeError):
            wert = None
        attrs = st.get("attributes") or {}
        out[eid] = {
            "wert": wert,
            # F-53: der rohe State als Text. **Ein Zustandsfeld ist nie
            # numerisch** — `float()` warf ihn bisher weg, und die Fläche zeigte
            # „—" für eine Zuordnung, die einwandfrei funktionierte (kingcap1,
            # #263). Der Anwender konnte damit nicht unterscheiden, ob nichts
            # ankommt oder nur nichts angezeigt wird.
            #
            # ⚠ Für **numerische** Felder bleibt `wert` maßgeblich; dieser Text
            # ist dort dieselbe Zahl als String und wird von der Fläche nicht
            # gezeigt (s. `zustand`-Weiche beim Zusammenbau). Er hier
            # unbedingt mitzugeben statt bedingt hält diese Funktion frei von
            # Feld-Wissen — sie kennt Entities, keine Felder.
            "wert_text": str(roh_state) if roh_state is not None else None,
            "einheit": attrs.get("unit_of_measurement"),
            "state_class": attrs.get("state_class"),
            # Klarname für die Zeilen-Anzeige: die nackte entity_id sagt vielen
            # nichts, und die V3-Fläche zeigte hier den Friendly Name
            # (Rainer-PN 2026-07-25). Kommt aus demselben Batch — kein Zusatzabruf.
            "friendly_name": attrs.get("friendly_name"),
        }
    return out


# Additive Sub-Map in anlage.sensor_mapping: {field_id: {"quelle": ...}}. Stört
# die bestehende HA-Struktur (basis/investitionen) nicht; B8 führt beide zusammen.
QUELLEN_KEY = "quellen"


def _feld_id(match_key) -> str:
    """Stabile Feld-Kennung aus dem match_key (Zuordnungs-Schlüssel).

    N-559: die Form liegt in `datenquellen_mapping_sync.feld_id` — dieselbe, die
    das Aufräumen beim Löschen einer Investition sucht.
    """
    return feld_id(match_key)


def _feld_wert(
    q: str, eintrag: dict, zustand: bool, ha_werte: dict, ha_texte: dict, cache: tuple,
) -> tuple:
    """``(wert, wert_zeit, wert_text)`` der TATSÄCHLICH aufgelösten Quelle eines Feldes (§2d).

    HA → REST-Batch, Inbound/Gateway → Cache (Gateway republisht nach C2a-Fix über das Standard-Topic in denselben
    Inbound-Cache), keine → keiner. Amber = Ausfall sichtbar.

    F-53: Zustandsfelder tragen ihre Aussage im Text, nicht in `wert` — nur für sie wird ``wert_text`` gefüllt (bei
    einem Zahlenfeld stünde sonst dieselbe Zahl zweimal in der Antwort). HA-Bauform §9 (S1-3, Ü1): über MQTT trägt
    der Cache den rohen String; er gehört in ``wert_text`` wie im HA-Zweig, ``wert`` bleibt eine Zahl oder ``None``
    (die Fläche rundet ``wert`` — ein String ergäbe dort «NaN»).
    """
    if q in QUELLEN_HA:
        entity = eintrag.get("entity_id")
        return ha_werte.get(entity), None, (ha_texte.get(entity) if zustand else None)
    if q in (QUELLE_STANDARD, QUELLE_GATEWAY):
        wert, wert_zeit = cache
        if zustand:
            return None, wert_zeit, (str(wert) if wert is not None else None)
        return wert, wert_zeit, None
    return None, None, None  # keine


def _ist_mqtt_quelle(quelle: str) -> bool:
    """Liest das Feld aus dem MQTT-Inbound-Cache (Inbound oder Gateway)? — dort gelten die Modus-Codes (§9)."""
    return quelle in (QUELLE_STANDARD, QUELLE_GATEWAY)


def _zulaessige_werte(eintrag: dict, quelle: str = QUELLE_KEINE) -> list[dict] | None:
    """P-433-0 (Konzept #433 E12): die Werte-Tabelle des Kanons am Feld „Betriebsmodus“ (auch `betriebsmodus-3`).

    Nur dort — ein anderes Zustandsfeld hätte eine andere Tabelle; ``None`` für jedes übrige Feld. Die MQTT-Zahlencodes
    (HA-Bauform §9) nur, wenn das Feld über MQTT liest (Inbound/Gateway): am HA-Feld bleibt eine Ziffer ein unbekannter
    Wert (Entscheid H1 = A). Dieselbe Tabelle, ein Parameter — keine zweite Liste.
    """
    if eintrag.get("zustand") and basis_feld_key(eintrag.get("feld", "")) == MODUS_FELD_KEY:
        return betriebsmodus_werte_je_betriebsart(codes=_ist_mqtt_quelle(quelle))
    # P-433-2b K1: die Zustandsfelder der E-Mobilität tragen ihre Tabelle aus `core/zustands_kanon.py` (dieselbe Form).
    if eintrag.get("zustand") and eintrag.get("feld") in zustands_kanon.ZUSTANDS_FELDER:
        return zustands_kanon.werte_je_kanon(eintrag["feld"], codes=_ist_mqtt_quelle(quelle))
    # P-433-2b K2a: ein Textfeld (Fahrzeug am Ladepunkt) hat keinen Kanon und damit keine Werte-Tabelle.
    return None


def _wert_klartext(eintrag: dict, wert_text: str | None, quelle: str) -> str | None:
    """F-53: die Deutung des rohen Zustands im Kanon **seines** Felds — Betriebsmodus oder E-Mobilität (K1).

    Ein E-Mob-Wert, den eedc nicht kennt, hat keinen Klartext (``None`` — kein «Unbestimmt» wie beim Modus); die
    Fläche zeigt dann den Rohwert allein.

    P-433-2b K2a: ein **Textfeld** (`ist_text_feld`, Fahrzeug am Ladepunkt) hat keinen Kanon und damit keine Deutung
    — ``None``; die Fläche zeigt den Text selbst (leer als «(leer)»).
    """
    feld = eintrag.get("feld", "")
    if not wert_text or ist_text_feld(feld):
        return None
    if feld in zustands_kanon.ZUSTANDS_FELDER:
        return zustands_kanon.klartext_roh(feld, wert_text, codes=_ist_mqtt_quelle(quelle))
    return betriebsmodus_klartext(wert_text, codes=_ist_mqtt_quelle(quelle))


_TYP_WP = "waermepumpe"


def _wp_feld_zusatz(eintrag: dict) -> dict:
    """P-433-2 (Variante C, #431): Betriebsart und Mengenart je Feld — nur an Wärmepumpen-Feldern gefüllt.

    Beide kommen aus der Registry (`betriebsart`) bzw. ihrer Ableitung (`wp_menge`, thermisch ⇔ Wärme);
    die Fläche bündelt danach ihre Blöcke und bildet den Status im Blockkopf, ohne eigene Feldtabelle.
    """
    if eintrag.get("typ") != _TYP_WP:
        return {"betriebsart": None, "menge": None}
    feld = eintrag.get("feld", "")
    return {"betriebsart": wp_betriebsart(feld), "menge": wp_menge(feld)}


def _wp_gruppen_zusatz(typ: str, inv: Investition | None) -> dict:
    """P-433-2: je Wärmepumpe das Stammdatum `kuehlung_art` (P13 Gruppe 3: reist als Eigenschaft) und die
    Betriebsarten, die eedc aus einem Betriebsmodus-Sensor ableiten kann (Kanon `AUFGETEILTE_MODI`).

    Mit beidem entscheidet die Fläche, ob der Block «Kühlen» ohne Kühlzähler erscheint (gekühlt wird
    trotzdem) und wann ihr Kopf «aus Betriebsmodus abgeleitet» sagt — ohne zweite Tabelle im Client.
    Andere Typen bekommen nichts (Antwort für sie unverändert).
    """
    if typ != _TYP_WP:
        return {}
    return {"kuehlung_art": kuehlung_art(inv), "modus_ableitbar": sorted(AUFGETEILTE_MODI)}


async def _basis_preis_eintraege(db: AsyncSession, anlage_id: int) -> list[dict]:
    """Preis-Slots der Anlage im Eintrags-Shape der Fläche — HA-only.

    Bewusst NICHT in `build_expected_topics`: dort ist jeder Eintrag ein
    ERWARTETES MQTT-Topic (Wizard-Anzeige + Abdeckungs-Check #134). Ein
    Preis-Feld kommt aber nur über HA herein — als Topic gelistet wäre es eine
    Lücke, die niemand schließen kann. `topic` bleibt deshalb leer; damit
    findet auch `topic_suffix()` kein Gateway-Ziel und die 3-Stufen-Auflösung
    endet bei HA oder „keine".

    Sichtbar nur bei ausdrücklich dynamischem Tarif (`vertragsart`): bei einem
    Festpreis gehört der Preis in die Stammdaten. Ein angebotener Preis-Slot
    verleitet sonst dazu, sich einen Konstanten-Sensor zu bauen (Forum simon42
    #89667/54).
    """
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage
    from backend.core.field_definitions import BASIS_PREIS_FELDER, get_feld_bedarf

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein = tarife.get("allgemein")
    if not ist_dynamisch(allgemein):
        return []

    eintraege: list[dict] = []
    for feld in BASIS_PREIS_FELDER:
        bedarf, bedarf_gruppe = get_feld_bedarf("basis", feld["key"])
        # Dieselbe Bildung wie in `mqtt_topic_registry` (N-299): die Klammer
        # haengt an der Einheit. Heute traegt das eine Preis-Feld eine, die
        # Zeile haelt die Bildung ueber alle vier Erzeuger der Flaeche gleich.
        einheit_str = f" ({feld['einheit']})" if feld.get("einheit") else ""
        eintraege.append({
            "topic": "",
            "label": f"{feld['label']}{einheit_str}",
            "kategorie": "preis",
            "typ": "basis",
            "match_key": ("basis_preis", feld["key"]),
            "feld": feld["key"],
            "feld_label": feld["label"],
            "einheit": feld["einheit"],
            "hinweis": feld.get("hinweis", ""),
            "bedarf": bedarf,
            "bedarf_gruppe": bedarf_gruppe,
            "gruppe_id": "basis",
            "gruppe_titel": "Anlage (Basis)",
            "nur_ha": True,
        })
    return eintraege


async def _nach_eigenem_tarif(db: AsyncSession, anlage_id: int, eintraege: list[dict]) -> list[dict]:
    """N-770/N-771 (Bauplan F1): ein Feld mit ``tarif_verwendung`` (Netzbezug zum WP-/Wallbox-Tarif) ist ohne EIGENEN
    Tarif dieser Verwendung **erweitert** — es steht hinter „Weitere Größen erfassen" (R1: mit Quelle rückt es vor, die
    Fläche wertet ``erweitert and quelle == keine``). Mit eigenem Tarif steht es in der ersten Reihe (Block «Gerät
    gesamt» bzw. kWh-Abschnitt der Wallbox). Die Tarife werden nur geladen, wenn ein solches Feld vorkommt."""
    if not any(e.get("tarif_verwendung") for e in eintraege):
        return eintraege
    from backend.api.routes.strompreise import lade_tarife_fuer_anlage
    from backend.core.field_definitions.auswahl import tarif_label
    from backend.services.monats_fakten.tarif import tarif_verwendungen_der_flaeche

    eigene = tarif_verwendungen_der_flaeche(await lade_tarife_fuer_anlage(db, anlage_id))
    return [
        {**e, "erweitert": True} if e.get("tarif_verwendung") and e["tarif_verwendung"] not in eigene
        else _mit_tarif_label(e, tarif_label(e, eigene))
        for e in eintraege
    ]


def _mit_tarif_label(e: dict, label: "str | None") -> dict:
    """F12 (E6): unter dem gemeinsamen Tarif «Wärmepumpe und Wallbox» trägt das Feld an der WP das Label
    «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)» (``auswahl.tarif_label``); sonst unverändert."""
    if label is None:
        return e
    alt = e.get("feld_label") or ""
    return {**e, "feld_label": label, "label": str(e.get("label") or alt).replace(alt, label, 1) if alt else label}


def ohne_nicht_zuordenbare(eintraege: list[dict], quellen: dict) -> list[dict]:
    """Entfernt `nur_manuell`- und bauartfremde Felder aus der Zuordnungs-Fläche.

    Solche Felder sind **erfassbar** (Monatsabschluss, CSV-Import), aber nicht
    mehr **zuordenbar** — der automatische Erfassungsweg ist zurückgebaut, das
    Feld nicht gelöscht. Begründung je Feld in `core/field_definitions.py`
    (Attribut `nur_manuell`); erster Fall sind die BKW-eigenen Akku-Felder,
    seit der Akku als eigene Speicher-Investition erfasst wird.

    **Zweiter Fall seit dem 26.08.2026: `nicht_an_dieser_bauart`** (W-12). Die
    Größe existiert an diesem Gerätetyp nicht — eine Split-Klimaanlage hat
    keinen Warmwasserkreis (N-304/B5). Bis dahin bot die Fläche einer
    Klimaanlage `warmwasser_kwh` und `strom_warmwasser_kwh` trotzdem an: Der
    Filter in `get_alle_felder_fuer_investition` war ein exakter
    String-Vergleich auf `"luft_luft"` und kannte weder die Negation noch die
    Listenform. Genau die zwei Felder, deren Fehlen der Daten-Checker bei
    OB73-gif zu Unrecht angemahnt hatte (#263, im Checker repariert mit
    v4.0.28) — dritte Runde der #236-Folgewellen-Klasse.

    ⭐ **AUSNAHME — hat das Feld heute eine Quelle, bleibt es stehen. Für BEIDE
    Fälle, und das ist der Grund, warum hier gefiltert wird und nicht in der
    Registry.** Sonst verschwände eine bestehende Zuordnung unsichtbar und ließe
    sich nicht mehr entfernen. Der Fall ist real: azywietz-web führt zwei
    Klimaanlagen als `luft_wasser` (#383). Stellt er die Bauart um, muss ein
    zugeordneter Warmwasser-Sensor einen Weg heraus behalten. Dieselbe Falle hat
    `bedingung_anlage` schon einmal gestellt (s. `get_felder_fuer_investition`),
    und `test_klima_ohne_warmwasser_n304.py::test_zuordnungsflaeche_zeigt_das_feld_weiter`
    hält sie fest.
    """
    def _hat_quelle(fid: str) -> bool:
        eintrag = quellen.get(fid)
        if not isinstance(eintrag, dict):
            return False
        return eintrag.get("quelle", QUELLE_KEINE) != QUELLE_KEINE

    return [
        e for e in eintraege
        if not (e.get("nur_manuell") or e.get("nicht_an_dieser_bauart"))
        or _hat_quelle(_feld_id(e["match_key"]))
    ]


def _quellen_map(anlage: Anlage) -> dict:
    """Liest die Feld→Quelle-Map aus anlage.sensor_mapping (leer wenn keine)."""
    mapping = anlage.sensor_mapping or {}
    q = mapping.get(QUELLEN_KEY) if isinstance(mapping, dict) else None
    return q if isinstance(q, dict) else {}


def _pick(d, *keys):
    """Toleranter Dict-Zugriff (int/str-Schlüssel-Mischung im Cache)."""
    if isinstance(d, dict):
        for k in keys:
            if k in d:
                return d[k]
    return None


def _cache_wert(cache, aid: int, match_key) -> tuple:
    """Aktueller (wert, iso_zeit) aus dem MQTT-Inbound-Cache per match_key — sonst (None, None)."""
    if cache is None:
        return (None, None)
    live = _pick(cache._live, aid, str(aid)) or {}
    energy = _pick(cache._energy, aid, str(aid)) or {}
    kind = match_key[0]
    entry = None
    if kind == "basis_live":
        entry = (live.get("basis") or {}).get(match_key[1])
    elif kind == "basis_energy":
        entry = energy.get(match_key[1])
    elif kind == "inv_live":
        inv_map = _pick(live.get("inv") or {}, match_key[1], str(match_key[1]), int(match_key[1])) or {}
        entry = inv_map.get(match_key[2])
    elif kind == "inv_energy":
        entry = energy.get(f"inv/{match_key[1]}/{match_key[2]}")
    if not entry:
        return (None, None)
    val, ts = entry
    return (val, ts.isoformat() if hasattr(ts, "isoformat") else ts)


# ─── Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.2) ─────────────────────
def _ist_themen_topic(e: dict) -> bool:
    return e.get("abschnitt") == "themen"


def _ohne_themen(eintraege) -> list[dict]:
    """Die Registry-Einträge ohne Themen-Topics — die Feldliste der Fläche (Themen haben ihren eigenen Block)."""
    return [e for e in eintraege if not _ist_themen_topic(e)]


def _themen_ha_entities(anlage: Anlage) -> set:
    """Die HA-Entitäten aller Themen-Einträge (für den Detail-Abruf der Fläche, `_ha_states_detail`)."""
    from backend.services.themen_store import eintrag_von_feld_id

    return {
        v["entity_id"] for fid, v in _quellen_map(anlage).items()
        if eintrag_von_feld_id(fid) is not None and isinstance(v, dict)
        and v.get("quelle") in QUELLEN_HA and v.get("entity_id")
    }


def _thema_eintrag_wert(
    q: str, eintrag: dict, ha_detail: dict, cache_wert: tuple,
) -> tuple:
    """``(wert_text, einheit, wert_zeit)`` eines Themen-Eintrags aus seiner Quelle — wie geliefert, ohne Wert ``None``."""
    from backend.services.themen_store import wert_text

    if q in QUELLEN_HA:
        d = ha_detail.get(eintrag.get("entity_id")) or {}
        return wert_text(d.get("wert_text")), d.get("einheit") or "", None
    if q in (QUELLE_STANDARD, QUELLE_GATEWAY):
        return wert_text(cache_wert[0]), "", cache_wert[1]
    return None, "", None


def _themen_gruppe(
    anlage: Anlage, inv: Investition, quellen: dict, ha_detail: dict, cache, gateway_topics: dict, topics: dict,
) -> list[dict]:
    """Die Themen eines Geräts für die Fläche (G9): je Thema die Einträge mit Quelle, Zuordnung und Wert.

    Quelle eines Eintrags: sein ``quellen``-Eintrag; ohne Eintrag Inbound, wenn das Topic einen Wert trägt, sonst
    «keine» (die Regel der Felder, B8-2 Stufe 3 — hier ohne Festschreiben). ``topics``: Registry-Feld-ID → Topic.
    Typen ohne Überblick ⇒ ``[]``.
    """
    from backend.services.themen_store import eintrag_feld_id, eintrag_topic_key, lade_themen
    from backend.utils.investition_filter import UEBERBLICK_TYPEN

    if inv.typ not in UEBERBLICK_TYPEN:
        return []
    out: list[dict] = []
    for thema in lade_themen(anlage.sensor_mapping, inv.id)["liste"]:
        zeilen = []
        for e in thema["eintraege"]:
            fid = eintrag_feld_id(inv.id, e["id"])
            match_key = ("inv_live", str(inv.id), eintrag_topic_key(e["id"]))
            cw = _cache_wert(cache, anlage.id, match_key)
            eintrag = quellen.get(fid) if isinstance(quellen.get(fid), dict) else {}
            q = eintrag.get("quelle") or (QUELLE_STANDARD if cw[0] is not None else QUELLE_KEINE)
            text, einheit, zeit = _thema_eintrag_wert(q, eintrag, ha_detail, cw)
            zeilen.append({
                "id": e["id"], "label": e["label"], "feld_id": fid, "quelle": q,
                "ha_entity": eintrag.get("entity_id"),
                "ha_name": (ha_detail.get(eintrag.get("entity_id")) or {}).get("friendly_name"),
                "gateway_topic": gateway_topics.get(eintrag.get("mapping_id")),
                "standard_topic": topics.get(_feld_id(match_key), ""),
                "wert_text": text, "einheit": einheit, "wert_zeit": zeit,
            })
        out.append({"id": thema["id"], "name": thema["name"], "eintraege": zeilen})
    return out


def _themen_anhaengen(
    gruppen: list[dict], anlage: Anlage, inv_je_gruppe: dict, quellen: dict, ha_detail: dict, cache,
    gateway_topics: dict, alle_topics,
) -> None:
    """Setzt je Gerätegruppe ``themen`` (`_themen_gruppe`); die Basis-Gruppe bekommt keinen Schlüssel."""
    topics = {_feld_id(e["match_key"]): e["topic"] for e in alle_topics if _ist_themen_topic(e)}
    for gruppe in gruppen:
        inv = inv_je_gruppe.get(gruppe["id"])
        if inv is not None:
            gruppe["themen"] = _themen_gruppe(anlage, inv, quellen, ha_detail, cache, gateway_topics, topics)


@dataclass
class FelderKontext:
    """Geteilte Eingänge und Zwischenstände der `/felder`-Phasen (RF-82) — je Aufruf neu, nie zwischengespeichert."""

    anlage_id: int
    anlage: Anlage
    invs: list
    alle_topics: list
    eintraege: list
    quellen: dict
    invert_store: dict
    # `_quellen_aufloesen`
    gateway_topics: dict = field(default_factory=dict)
    cache: object = None
    ha_url: str | None = None
    ha_kind: str | None = None
    inv_live_map: dict = field(default_factory=dict)
    effektiv: dict = field(default_factory=dict)
    cache_wert: dict = field(default_factory=dict)
    neu_persistieren: dict = field(default_factory=dict)
    gw_deaktivieren: list = field(default_factory=list)
    ha_detail: dict = field(default_factory=dict)
    ha_werte: dict = field(default_factory=dict)
    ha_texte: dict = field(default_factory=dict)
    ha_namen: dict = field(default_factory=dict)
    # `_praezedenzen`
    probleme_je_feld: dict = field(default_factory=dict)
    bedarf_je_feld: dict = field(default_factory=dict)


async def _felder_laden(db: AsyncSession, anlage_id: int) -> FelderKontext:
    """Phase 1 von `/felder`: Anlage (404), aktive Investitionen in Typ-Reihenfolge, Registry-Einträge ohne Themen,
    Preis-Slots, `nur_manuell`-/Tarif-Filter und der Invert-Store."""
    anlage = (
        await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    ).scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Regel 0a: Gruppen in kanonischer Investitionstyp-Reihenfolge (nicht DB-Order).
    # aktiv_am_tag(heute) = aktiv-Flag + Anschaffung ≤ heute ≤ Stilllegung
    # (beide Grenzen, [[feedback_anschaffungsdatum_grenze]]) — NICHT aktiv_jetzt(),
    # das die Anschaffungs-Untergrenze nicht prüft.
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, aktiv_am_tag(date.today()))
    )).scalars().all()
    invs = sort_investitionen_nach_typ(invs)
    # Themen-Kacheln (4.2.0): die Topics der Themen-Einträge stehen in der Registry, aber nicht in der Feldliste —
    # sie bekommen ihren eigenen Block (`_themen_anhaengen`).
    alle_topics = await build_expected_topics(db, anlage, investitionen=invs)
    eintraege = _ohne_themen(alle_topics)
    # Preis-Slots hängen an derselben Basis-Gruppe, kommen aber nicht aus der
    # MQTT-Registry (s. Helper). Angehängt statt eingemischt: die Gruppierung
    # ist reihenfolge-erhaltend, „Anlage (Basis)" existiert an dieser Stelle
    # bereits — der Preis landet damit am Ende seines eigenen Abschnitts.
    eintraege += await _basis_preis_eintraege(db, anlage_id)

    quellen = _quellen_map(anlage)

    # `nur_manuell`-Felder gehören nicht auf diese Fläche: sie sind erfassbar
    # (Monatsabschluss, CSV-Import), aber nicht mehr zuordenbar — der Erfassungsweg
    # ist zurückgebaut, nicht das Feld (Begründung je Feld in
    # `core/field_definitions.py`). AUSNAHME: hat das Feld heute eine Quelle,
    # bleibt es stehen. Sonst verschwände eine bestehende Zuordnung unsichtbar und
    # ließe sich nicht mehr entfernen — dieselbe Falle, die `bedingung_anlage`
    # schon einmal gestellt hat (s. `get_felder_fuer_investition`).
    eintraege = ohne_nicht_zuordenbare(eintraege, quellen)
    # N-770/N-771 (F1): «Netzbezug zum WP-/Wallbox-Tarif» in der ersten Reihe nur mit eigenem Tarif (heute).
    eintraege = await _nach_eigenem_tarif(db, anlage_id, eintraege)

    # Vereinheitlichter Invert-Store (quellen-unabhängig, feld-/wert-level).
    invert_store = (anlage.sensor_mapping or {}).get("invertieren") or {}
    return FelderKontext(
        anlage_id=anlage_id, anlage=anlage, invs=invs, alle_topics=alle_topics, eintraege=eintraege,
        quellen=quellen, invert_store=invert_store,
    )


async def _quellen_aufloesen(
    db: AsyncSession, ctx: FelderKontext, ha_aufloesen: HaAufloesen = _resolve_ha,
    ha_details: HaDetails = _ha_states_detail,
) -> None:
    """Phase 2 von `/felder`: Gateway-Zeilen, Inbound-Cache, HA-Transport + Live-Maps, Pass 1 (effektive Quelle je Feld,
    B8-2) und der HA-Detail-Batch (Wert C1, Einheit/state_class §2i)."""
    anlage_id, anlage, eintraege, quellen = ctx.anlage_id, ctx.anlage, ctx.eintraege, ctx.quellen

    # Gateway-Quell-Topics dieser Anlage (mapping_id → quell_topic) für die
    # Anzeige der aktiven Gateway-Zuordnung je Feld (B3.3) + ziel_key→Row-Index
    # (nur AKTIVE Zeilen) für die B8-2-Auflösung / §2h-Deaktivierung.
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    gw_rows = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == anlage_id)
    )).scalars().all()
    gateway_topics = {m.id: m.quell_topic for m in gw_rows}
    gw_by_zielkey = {m.ziel_key: m for m in gw_rows if getattr(m, "aktiv", True)}

    # Aktuelle Live-/Energy-Werte aus dem MQTT-Inbound-Cache (B2.3). Ohne aktiven
    # Subscriber bleibt der Cache leer → wert=None → UI zeigt „—".
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
    svc = get_mqtt_inbound_service()
    cache = svc.cache if svc else None

    # HA-Verbindungstransport (Supervisor ODER Remote) + Live-Maps für die
    # B8-2-Auflösung noch NICHT zugeordneter Felder. Der zu PERSISTIERENDE
    # Transport nutzt denselben statischen Fallback wie die B8-1-Migration
    # (Add-on → ha_app, sonst ha_connector): ein per sensor_mapping HA-gemapptes
    # Feld ist HA-bequellt, auch wenn die Verbindung gerade nicht aktiv ist (kind
    # None) — die reale Verbindung löst der Read-Pfad ohnehin auf, das Feld zeigt
    # dann ehrlich amber statt fälschlich Inbound zu werden.
    from backend.core.config import HA_INTEGRATION_AVAILABLE
    ha_url, _ha_token, ha_kind = await ha_aufloesen(db)
    ha_kind_persist = ha_kind or (QUELLE_HA_APP if HA_INTEGRATION_AVAILABLE else QUELLE_HA_CONNECTOR)
    basis_live, inv_live_map, _bi, _ii = extract_live_config(anlage)

    # Pass 1 — effektive Quelle je Feld: expliziter `quellen`-Eintrag gilt; sonst
    # 3-Stufen-Auflösung (B8-2, Gernots Regel): HA-Sensor → HA · Gateway-Topic →
    # Gateway · Inbound-mit-Wert → Inbound · sonst „keine". POSITIVE Evidenz
    # (HA/Gateway/Inbound-mit-Wert) wird additiv festgeschrieben, damit Anzeige
    # UND Read-Through (C2a/C2b) übereinstimmen (HA-first echt statt MQTT-Merge).
    # Stummes Inbound bleibt UNENTSCHIEDEN (kein Eintrag) → bei jedem Aufruf neu
    # bewertet, self-healing, kein auto-„keine"-Ballast.
    effektiv: dict[str, dict] = {}
    cache_wert: dict[str, tuple] = {}
    neu_persistieren: dict[str, dict] = {}
    gw_deaktivieren: list = []
    for e in eintraege:
        fid = _feld_id(e["match_key"])
        cw = _cache_wert(cache, anlage_id, e["match_key"])
        cache_wert[fid] = cw
        eintrag = quellen.get(fid)
        if eintrag:
            effektiv[fid] = eintrag
            continue
        # N-780: ein Feld ohne Leser wird nicht auf Inbound gestempelt, auch wenn ein Wert im Cache liegt (HA und
        # eine vom Anwender angelegte Gateway-Zeile lösen weiter auf — sie bleiben sichtbar und löschbar).
        display_q, persist_entry, gw_row = resolve_effektive_quelle(
            fid, e["topic"], anlage.sensor_mapping or {},
            basis_live, inv_live_map, gw_by_zielkey, ha_kind_persist, cw[0] is not None and not e.get("ohne_leser"),
        )
        effektiv[fid] = persist_entry or {"quelle": display_q}
        if persist_entry is not None:
            neu_persistieren[fid] = persist_entry
            if gw_row is not None and getattr(gw_row, "aktiv", True):
                gw_deaktivieren.append(gw_row)

    # HA-zugeordnete Entities einmalig batch-lesen (explizit + neu aufgelöst):
    # Wert (C1) + Einheit/state_class (§2i-Validierung).
    ha_entities = {
        v.get("entity_id") for v in effektiv.values()
        if isinstance(v, dict) and v.get("quelle") in QUELLEN_HA and v.get("entity_id")
    }
    ha_detail = await ha_details(db, ha_entities | _themen_ha_entities(anlage))
    ha_werte = {eid: d.get("wert") for eid, d in ha_detail.items()}
    ha_texte = {eid: d.get("wert_text") for eid, d in ha_detail.items()}
    ha_namen = {eid: d.get("friendly_name") for eid, d in ha_detail.items()}
    ctx.gateway_topics, ctx.cache, ctx.ha_url, ctx.ha_kind = gateway_topics, cache, ha_url, ha_kind
    ctx.inv_live_map, ctx.effektiv, ctx.cache_wert = inv_live_map, effektiv, cache_wert
    ctx.neu_persistieren, ctx.gw_deaktivieren = neu_persistieren, gw_deaktivieren
    ctx.ha_detail, ctx.ha_werte, ctx.ha_texte, ctx.ha_namen = ha_detail, ha_werte, ha_texte, ha_namen


def _praezedenzen(ctx: FelderKontext) -> None:
    """Phase 3 von `/felder`: die §2i-Probleme je Feld (Einheit, state_class, Redundanz, Bauschnitt 7, N-537,
    Doppelmapping — in dieser Reihenfolge, sie ist die Reihenfolge der Liste `probleme`) und die Bedarfs-Einstufung
    je Gerät (§2i-6, N-456)."""
    invs, eintraege, effektiv, cache_wert = ctx.invs, ctx.eintraege, ctx.effektiv, ctx.cache_wert
    ha_detail, ha_werte, inv_live_map = ctx.ha_detail, ctx.ha_werte, ctx.inv_live_map

    # §2i — proaktive Zuordnungs-Validierung (rein diagnostisch): pro Feld eine
    # Liste `probleme`. Einheit-Mismatch (#200) + fehlendes state_class je HA-Feld;
    # Aggregat-Redundanz (PV gesamt/Netz kombi neben Komponenten); HA-Doppelmapping.
    from backend.services.datenquellen_validierung import (
        einheit_problem, state_class_problem,
        finde_redundante_aggregate, finde_doppelmappings, stufe_bedarf_ein,
        finde_gesamtleistung_verdraengt, finde_bkw_fuellt_kinder_luecken,
    )
    feld_einheit = {_feld_id(e["match_key"]): e.get("einheit", "") for e in eintraege}
    feld_feld = {_feld_id(e["match_key"]): e.get("feld", "") for e in eintraege}
    feld_typ = {_feld_id(e["match_key"]): e.get("typ", "basis") for e in eintraege}
    # N-537: die Investition je Feld — die Abtretung eines Balkonkraftwerks an
    # seine Kinder ist eine Aussage ueber GERAETE, nicht ueber Feldnamen.
    feld_inv = {
        _feld_id(e["match_key"]): (
            str(e["match_key"][1]) if e["match_key"][0] != "basis" else None
        )
        for e in eintraege
    }
    feld_bedarf = {_feld_id(e["match_key"]): e.get("bedarf", "optional") for e in eintraege}
    feld_bedarf_gruppe = {_feld_id(e["match_key"]): e.get("bedarf_gruppe") for e in eintraege}
    feld_bedingung_anlage = {
        _feld_id(e["match_key"]): e.get("bedingung_anlage") for e in eintraege
    }
    # N-555 Stufe 2: mit dem Pseudo-Typ „dienstliche Wallbox in Betrieb" (heute) —
    # derselbe SoT wie der Monatsabschluss (`anlage_typen_mit_kontext`).
    vorhandene_inv_typen = anlage_typen_mit_kontext(invs)
    probleme_je_feld: dict[str, list] = {}

    def _add_problem(fid: str, p: dict | None) -> None:
        if p:
            probleme_je_feld.setdefault(fid, []).append(p)

    ha_zuordnungen: dict[str, str] = {}
    for fid, v in effektiv.items():
        if isinstance(v, dict) and v.get("quelle") in QUELLEN_HA and v.get("entity_id"):
            eid = v["entity_id"]
            ha_zuordnungen[fid] = eid
            d = ha_detail.get(eid)
            if d:  # nur wenn HA erreichbar (sonst keine Einheit → kein Fehlalarm)
                _add_problem(fid, einheit_problem(feld_einheit.get(fid), d.get("einheit")))
                _add_problem(fid, state_class_problem(feld_einheit.get(fid), d.get("state_class")))
    def _hat_wert(fid: str) -> bool:
        """Kommt bei diesem Feld tatsächlich etwas an?

        ⭐ **Die Unterscheidung, die dieses Modul an anderer Stelle längst
        trifft** (`snapshot/keys.py`, 27.08.): *„Ein Stempel und eine Wahl sehen
        im Store bitgleich aus — deshalb entscheidet hier der Messwert, nicht
        der Eintrag."* Die B8-Materialisierung stempelt beim einmaligen
        Start-Lauf `mqtt_inbound_standard` auf **jedes** Feld ohne HA-Sensor und
        ohne Gateway-Zeile — gemessen an einer frisch angelegten Anlage: 31
        Felder, 31-mal. Ein solcher Stempel ist keine Zuordnung des Anwenders.

        Anlass (rapahl, PN 91806, 2026-08-30): Bei ihm trugen *Einspeisung (W)*
        und *Netzbezug (W)* solche Stempel ohne je empfangenen Wert (beide „–",
        beide amber) — und verdrängten damit rechnerisch seinen bidirektionalen
        Netzsensor, der als einziger lieferte (−1250 W). Die Meldung sagte
        „Wirkungslos … der Kombi-Sensor wird ignoriert"; die Live-Engine benutzt
        ihn aber, weil sie wertlose Felder verwirft
        (`live_power_service._apply_quellen_overrides`). Der Hinweis begründete
        sich also mit einer Wirkung, die nicht eintritt.

        ⚠ Dieselbe Kaskade wie die Wert-Anzeige weiter unten (§2d) — HA aus dem
        REST-Batch, Inbound/Gateway aus dem Cache, „keine" hat keinen Wert.
        """
        eintrag = effektiv.get(fid) or {}
        q = eintrag.get("quelle", QUELLE_KEINE)
        if q in QUELLEN_HA:
            return ha_werte.get(eintrag.get("entity_id")) is not None
        if q in (QUELLE_STANDARD, QUELLE_GATEWAY):
            return cache_wert.get(fid, (None, None))[0] is not None
        return False

    felder_belegt = [
        {"id": fid, "feld": feld_feld[fid], "typ": feld_typ[fid],
         "inv_id": feld_inv.get(fid),
         "belegt": (effektiv.get(fid, {}).get("quelle", QUELLE_KEINE) != QUELLE_KEINE),
         "hat_wert": _hat_wert(fid)}
        for fid in feld_feld
    ]
    for fid, p in finde_redundante_aggregate(felder_belegt).items():
        _add_problem(fid, p)
    # Bauschnitt 7 (12.09.2026): „Leistung gesamt" verdrängt an derselben
    # Wärmepumpe die Verlaufs-Aufteilung nach Heizen/Warmwasser.
    #
    # ⭐ **Maßgeblich ist die HA-`live`-Map**, nicht `belegt` und nicht
    # `hat_wert` — sie ist genau die Menge, die die Verdrängung bewirkt
    # (`live_sensor_config.extract_live_config` → `has_leistung`). Ein
    # `mqtt_inbound_standard`-Stempel der B8-Materialisierung steht zwar in
    # `quellen` (also „belegt"), erreicht diese Map aber nie und verdrängt
    # nichts; eine tote HA-Entity steht darin und verdrängt sehr wohl.
    # Beide Fälle sind gemessen, beide haben je einen Regel-Entwurf gekippt.
    inv_live_felder = [
        {
            "id": _feld_id(e["match_key"]),
            "feld": e.get("feld", ""),
            "typ": e.get("typ", "basis"),
            "inv_id": e["match_key"][1],
            # Roher Schlüssel: `leistung_w-<gid>` (Innengerät) ist NICHT das
            # Gerätefeld und verdrängt nicht — kein `basis_feld_key` hier.
            "in_ha_live": e["match_key"][2] in (
                inv_live_map.get(str(e["match_key"][1])) or {}
            ),
        }
        for e in eintraege if e["match_key"][0] == "inv_live"
    ]
    for fid, p in finde_gesamtleistung_verdraengt(inv_live_felder).items():
        _add_problem(fid, p)

    # N-537: Ein Balkonkraftwerk mit `pv-module`-Kindern hat seine Erzeugung an
    # sie abgetreten (N-266/N-536) — die Fläche sagt das jetzt an seiner Zeile,
    # so wie sie es für das Anlagen-Aggregat und die WP-Gesamtleistung längst
    # tut. `info`, kein Knopf: „auf keine setzen" wäre bei teilweise gemessenen
    # Kindern falscher Rat (dann trägt der Wert ihre Lücke).
    kind_zu_parent = {
        str(i.id): str(i.parent_investition_id)
        for i in invs
        if i.typ == "pv-module" and i.parent_investition_id is not None
    }
    for fid, p in finde_bkw_fuellt_kinder_luecken(felder_belegt, kind_zu_parent).items():
        _add_problem(fid, p)
    # ⛔ Hier stand bis #406 eine dritte Lage: das Aggregat sei „für Tag und
    # Stunde durch einzelne Erzeuger-Zähler verdrängt, die Tagessumme still zu
    # niedrig" (F-7 Stufe 1, Forum T89667 #109). Diese Warnung ist ERSATZLOS
    # entfallen, weil der Zustand, den sie meldete, nicht mehr eintritt: die
    # Präzedenz je Tag lässt das Aggregat die Bilanz tragen, sobald die
    # Einzelzähler sie nicht vollständig tragen. Eine Warnung ohne Defekt wäre
    # die Falschmeldung, gegen die [[feedback_user_fehlermeldungen]] steht.
    # Was ein eigener Zähler ZUSÄTZLICH bringt, sagt weiterhin der Hinweistext
    # an den Komponenten-Zeilen (`_PV_AGGREGAT_NUR_ANLAGENSUMME_TEXT`).
    for fid, p in finde_doppelmappings(ha_zuordnungen, feld_einheit, feld_typ).items():
        _add_problem(fid, p)

    # §2i-6 — Bedarfs-Einstufung: ist ein LEERES Feld überhaupt eine Lücke?
    # Ohne sie zählte der Rollup Aggregat-, Alternativ- und Optional-Felder als
    # „ohne Quelle" und meldete auf einer korrekt eingerichteten Anlage Fehlalarm.
    #
    # ⛔ **`inv_id` und `pflicht_am_geraet` sind seit N-456 Teil der Eingabe.**
    # Ohne sie war die Belegung anlagenweit: An einer Anlage mit ZWEI
    # Wärmepumpen schaltete ein zugeordnetes Feld an Gerät A die leeren Felder
    # an Gerät B auf „hier ist nichts einzutragen" — das zweite Gerät konnte gar
    # nicht als offen erscheinen. Und bei getrennter Strommessung erklärte diese
    # Fläche das zweite Stromfeld für inaktiv, während der Abdeckungs-Check
    # daneben (`_check_energieprofil_abdeckung`) dafür warnte: zwei Flächen,
    # eine Anlage, gegenteilige Aussage (N-86-Klasse).
    #
    # Die Investitions-ID steckt im `match_key` (`("inv_energy", <id>, <feld>)`)
    # — NICHT in der Feld-ID selbst: die entsteht als `"_".join(match_key)`, und
    # ein Feldname mit Unterstrichen ließe sich daraus nicht sicher zurücklesen.
    _feld_inv_id = {
        _feld_id(e["match_key"]): (
            str(e["match_key"][1])
            if str(e["match_key"][0]).startswith("inv_") else None
        )
        for e in eintraege
    }
    _feld_pflicht_am_geraet = {
        _feld_id(e["match_key"]): bool(e.get("pflicht_am_geraet")) for e in eintraege
    }
    _bedarf_eingabe = [
        {"id": fid,
         "feld": feld_feld[fid],
         "typ": feld_typ[fid],
         "belegt": (effektiv.get(fid, {}).get("quelle", QUELLE_KEINE) != QUELLE_KEINE),
         "bedarf": feld_bedarf.get(fid, "optional"),
         "bedarf_gruppe": feld_bedarf_gruppe.get(fid),
         "bedingung_anlage": feld_bedingung_anlage.get(fid),
         "inv_id": _feld_inv_id.get(fid),
         "pflicht_am_geraet": _feld_pflicht_am_geraet.get(fid, False)}
        for fid in feld_feld
    ]
    bedarf_je_feld = stufe_bedarf_ein(_bedarf_eingabe, vorhandene_inv_typen)
    ctx.probleme_je_feld, ctx.bedarf_je_feld = probleme_je_feld, bedarf_je_feld


def _antwort(ctx: FelderKontext) -> list[dict]:
    """Phase 4 von `/felder`: Pass 2 — Gruppen reihenfolge-erhaltend, je Feld der Antwort-Eintrag, dazu die Themen."""
    anlage, invs, eintraege, quellen, alle_topics = ctx.anlage, ctx.invs, ctx.eintraege, ctx.quellen, ctx.alle_topics
    invert_store, gateway_topics, cache, effektiv, cache_wert = (
        ctx.invert_store, ctx.gateway_topics, ctx.cache, ctx.effektiv, ctx.cache_wert,
    )
    ha_detail, ha_werte, ha_texte, ha_namen = ctx.ha_detail, ctx.ha_werte, ctx.ha_texte, ctx.ha_namen
    probleme_je_feld, bedarf_je_feld = ctx.probleme_je_feld, ctx.bedarf_je_feld

    # Pass 2 — Reihenfolge-erhaltend nach gruppe_id gruppieren + Response bauen.
    gruppen: list[dict] = []
    index: dict[str, dict] = {}
    inv_je_gruppe = {f"inv:{i.id}": i for i in invs}
    for e in eintraege:
        gid = e.get("gruppe_id", "basis")
        gruppe = index.get(gid)
        if gruppe is None:
            gruppe = {
                "id": gid,
                "titel": e.get("gruppe_titel", "—"),
                "typ": e.get("typ", "basis"),
                "felder": [],
                **_wp_gruppen_zusatz(e.get("typ", "basis"), inv_je_gruppe.get(gid)),
            }
            index[gid] = gruppe
            gruppen.append(gruppe)
        fid = _feld_id(e["match_key"])
        eintrag = effektiv.get(fid) or {}
        q = eintrag.get("quelle", QUELLE_KEINE)
        wert, wert_zeit, wert_text = _feld_wert(
            q, eintrag, bool(e.get("zustand")), ha_werte, ha_texte, cache_wert.get(fid, (None, None)),
        )
        gruppe["felder"].append({
            "id": fid,
            "feld": e.get("feld", ""),
            # Investitionstyp der Gruppe — für die Wissensbasis-Vorschläge im
            # HA-Picker (#343 A; 'basis' für Anlagen-Felder).
            "typ": gruppe.get("typ", ""),
            "label": e.get("feld_label", e.get("label", "")),
            "einheit": e.get("einheit", ""),
            "kategorie": e.get("kategorie", "energy"),
            "hinweis": e.get("hinweis", ""),
            "standard_topic": e["topic"],
            # HA-only-Feld: die Fläche blendet Gateway/Inbound aus, statt
            # Quellen anzubieten, die kein Leser abfragt — die Preis-Slots
            # (kommen nur über HA herein). Zustandsfelder sind es seit
            # HA-Bauform §9 (S1-3) nicht mehr: der Inbound hält ihren rohen
            # String; das Gateway blendet die Fläche nur am Betriebsmodus aus
            # (D3) — an den übrigen Zustandsfeldern reicht es seit P-433-2b K2b
            # den Text weiter (`mqtt_gateway_service._als_text`).
            # N-780: ein Energie-Feld ohne Leser (`ohne_leser`, Topic-Registry) ebenso — eedc nähme den MQTT-Wert an,
            # verarbeitete ihn aber nicht; HA-Sensor (Monatsabschluss-Vorschlag) und Hand bleiben. Eine bestehende
            # MQTT-/Gateway-Zuordnung bleibt sichtbar und über «Keine» entfernbar (die Fläche blendet nur die Knöpfe aus).
            "nur_ha": bool(e.get("nur_ha") or e.get("ohne_leser")),
            # Zustand statt Zahl (#263 K-2): steuert den Entity-Picker — für
            # diese Felder ist auch die `climate.`-Domain zulässig, und der
            # Energie-Filter greift nicht; am Betriebsmodus kein Gateway-Knopf (D3).
            "zustand": bool(e.get("zustand")),
            # P-433-2b K1: Datenquellen-Abschnitt aus der Registry («zustand» ⇒ «Zustand & Sitzung»), sonst nach Einheit.
            "abschnitt": e.get("abschnitt"),
            "quelle": q,
            # Gateway-Quell-Topic (falls zugeordnet) für die UI-Anzeige.
            "gateway_topic": gateway_topics.get(eintrag.get("mapping_id")),
            # Zugeordnete HA-Entity (nur bei quelle ha_app/ha_connector).
            "ha_entity": eintrag.get("entity_id"),
            # Klarname derselben Entity (None, wenn HA sie nicht kennt).
            "ha_name": ha_namen.get(eintrag.get("entity_id")),
            # Invert-Modell (Datenquellen-V4): Vorzeichen-Flip ist quellen-
            # UNABHÄNGIG, aus dem vereinheitlichten Store gelesen (nicht aus dem
            # quellen-Eintrag), am Read-Endwert angewendet.
            # N-562: ein Legacy-`live_invert` (vor v4) wirkt über die Union in
            # `extract_live_config` mit — der Schalter zeigt, was wirkt, nicht
            # nur, was im Store steht.
            "invertieren": bool(invert_store.get(fid))
            or legacy_invert_aktiv(anlage.sensor_mapping or {}, fid),
            # R1/W-2 (SOLL Wärme/Klima §3.2a): Die Größe ist an dieser Bauart
            # untypisch, aber möglich — etwa die Kühl-Achse an einer
            # Luft-Wasser-Wärmepumpe. Sie steht hinter dem Schritt „Weitere
            # Größen erfassen", **solange sie keine Quelle hat**; mit Quelle
            # rückt sie in ihren Einheiten-Abschnitt vor.
            #
            # ⭐ **Das ist R1 wörtlich** — *„was ein Gerät liefern kann, sagt
            # der zugeordnete Zähler, nicht seine Bauart"* — und zugleich die
            # Auflösung der P-6-Falle: nicht durch Wegnehmen nach Bauart,
            # sondern durch Sichtbarkeit nach Beleglage. Die Fläche bleibt kurz,
            # ohne einen Fall auszuschließen (MartyBr, T89667 #200: getrennter
            # Kühlzähler, nirgends hinterlegbar).
            "erweitert": bool(e.get("erweitert")) and q == QUELLE_KEINE,
            "wert": wert,
            # F-53: roher State (nur Zustandsfelder) + seine Deutung im Kanon.
            # **Beide**, weil die Fläche zwei Fragen beantworten muss: kommt
            # etwas an, und versteht eedc es? Eine unbekannte Schreibweise
            # erscheint als „Unbestimmt" neben ihrem Rohwert — sie landet
            # später in „nicht aufgeteilt", statt einer Seite zugeschlagen zu
            # werden. Der Kanon-SoT ist `core/betriebsmodus.py`, nicht der Client.
            "wert_text": wert_text,
            # HA-Bauform §9 (Entscheid H1 = A): die Zahlencodes gelten nur für einen Wert über MQTT.
            "wert_klartext": _wert_klartext(e, wert_text, q),
            # P-433-0 (Konzept #433 E12): die Werte, die eedc an diesem Feld
            # versteht — sichtbar am Feld, damit der Anwender seinen
            # Template-Sensor danach bauen kann. **Aus dem Kanon abgeleitet**
            # (`core/betriebsmodus.py`), nicht im Client getippt; nur am
            # Betriebsmodus-Feld (mit Innengeräte-Suffix), sonst ``None``.
            "zulaessige_werte": _zulaessige_werte(e, q),
            # P-433-2 (Variante C, #431): Betriebsart + Mengenart je WP-Feld (sonst ``None``).
            **_wp_feld_zusatz(e),
            "wert_zeit": wert_zeit,
            # §2i: diagnostische Zuordnungs-Probleme (Einheit/state_class/Redundanz/
            # Doppelmapping) — leere Liste, wenn alles sauber.
            "probleme": probleme_je_feld.get(fid, []),
            # §2i-6: „pflicht" | "optional" | "inaktiv" (+ Begründung). Steuert
            # rot/aufgeklappt vs. leise und die Rollup-Zählung.
            "bedarf": bedarf_je_feld.get(fid, {}).get("bedarf", "optional"),
            "bedarf_grund": bedarf_je_feld.get(fid, {}).get("grund"),
            "bedarf_text": bedarf_je_feld.get(fid, {}).get("text"),
            # **R-A (WK-16f, Prinzip F-7): wo dieser Wert erscheint.**
            # Eine Zuordnung ist ein Versprechen; die Fläche sagt jetzt, wo es
            # eingelöst wird — *„ausgewertet in: Cockpit → Monat · Komponenten
            # → Wärmepumpe"*. Die Liste kommt aus `core/feld_auswertungen.py`
            # und **nur** von dort: eine zweite Tabelle im Client wäre genau
            # die Drift-Bauform, an der `FeldProblem.art` schon einmal
            # auseinandergelaufen ist (N-35/N-40).
            #
            # ⚠ **Der Typ des EINTRAGS, nicht der der Gruppe.** Heute sind beide
            # deckungsgleich — die Gruppe erbt ihren Typ vom ersten Eintrag —,
            # und genau deshalb steht hier der Eintrag: Er ist die Quelle, die
            # Gruppe nur eine Zusammenfassung davon. Ein Sprengsatz auf die
            # Gruppenform blieb am 14.09.2026 **still**; das war der Beleg, dass
            # die Unterscheidung heute nichts trägt, und kein Grund, sie als
            # Begründung stehen zu lassen. Bei den Anlagen-Feldern steht dort
            # `basis` — so heißt der Schlüssel in der Tabelle (`TYP_ANLAGE`).
            "ausgewertet_in": sichten_fuer(e.get("typ", ""), e.get("feld", "")),
        })
    # Themen-Kacheln (4.2.0, TH-E1 §1.2): je Gerätegruppe `themen` (eigene Funktion, G9).
    _themen_anhaengen(gruppen, anlage, inv_je_gruppe, quellen, ha_detail, cache, gateway_topics, alle_topics)
    return gruppen


async def zuordnungen_lesen(
    db: AsyncSession, anlage_id: int, *, ha_aufloesen: HaAufloesen | None = None, ha_details: HaDetails | None = None,
) -> tuple[FelderKontext, list[dict]]:
    """Die Zuordnungen einer Anlage wie die Datenquellen-Fläche sie zeigt — Kontext und `gruppen`, **ohne zu schreiben**.

    Die vier Phasen in der Reihenfolge der Route (Anlage + Einträge → Quellen je Feld → §2i-Probleme und Bedarf → Gruppen).
    Eine in Pass 1 aufgelöste, noch nicht gespeicherte Quelle steht in `ctx.neu_persistieren`; festgeschrieben wird sie nur
    von der Route (`_festschreiben`). 404 als `HTTPException` wie bisher.

    `ha_aufloesen`/`ha_details` sind die zwei Nähte nach außen (Transport der HA-Verbindung, ein `/states`-Batch). Ohne
    Angabe gelten die Funktionen dieses Moduls; die Route reicht ihre eigenen Modul-Namen durch, damit Tests und der Golden
    Master `datenquellen-felder` die HA-Seite weiter an der Route ersetzen können.
    """
    ctx = await _felder_laden(db, anlage_id)
    await _quellen_aufloesen(db, ctx, ha_aufloesen or _resolve_ha, ha_details or _ha_states_detail)
    _praezedenzen(ctx)
    return ctx, _antwort(ctx)
