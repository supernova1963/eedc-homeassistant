"""Die Abfrage beim Sensorwechsel (Sensorwechsel mit Grund, Bauplan B-2, Konzept S-1/S-8; Sitzung 3b).

**Wann gefragt wird** (``pruefe``, die eine Prüf-Funktion aller Wege): Maßstab ist die **wirksame** Quelle eines
Zählerschlüssels vor und nach der Änderung (``quelle.wirksame_quellen`` — der Resolver des Schreibers samt Gateway-Zeile, nicht
der ``quellen``-Eintrag). Gefragt wird, wenn

* der Schlüssel **eigene Werte** hat (Zählerstände der Reihe oder Kanalzeilen — ohne sie ist nichts zu schützen, Bauplan §8
  Nr. 17: weder gefragt noch verzeichnet),
* die neue Quelle **Werte liefern kann** (alles außer «Keine» — der Wechsel nach «Keine» wird ohne Frage verzeichnet) und
* sie sich von der **letzten Quelle mit Werten** unterscheidet: A → «Keine» → B fragt bei B, A → «Keine» → A nicht.

**Die zwei Gründe** (Konzept §2): ``fortsetzung`` — der neue Sensor misst dasselbe weiter, die Wechsel-Zeile trägt den Grund,
die Leser überbrücken die Naht (Sitzung 2); ``korrektur`` — bisher war der falsche Sensor zugeordnet, seit «falsch seit»; der
Dienst ``korrektur.py`` (Sitzung 3a) verwirft und füllt neu. Vorschau = Lauf: die Prüf-Routen bauen den Auftrag mit
``korrektur_auftrag`` und zählen mit ``korrektur.lage`` wie der Lauf.

**Ablauf in einer Schreib-Route** (Feld-Route, Preset): vor der Änderung ``verzeichnen.momentaufnahme``, danach die Änderung,
dann ``vollziehe`` — fehlt für eine fragepflichtige Änderung der Grund, wirft sie ``GrundFehlt`` (die Route antwortet 422, der
Aufrufer rollt zurück); sonst verzeichnet sie und führt die Korrektur aus (ein Commit des Aufrufers, danach
``nach_dem_commit``). Die Prüf-Routen machen dieselbe Änderung, fragen ``pruefe`` und rollen zurück — sie schreiben nichts.
Energie-Vorschläge und die Gateway-Route ``PUT`` überspringen eine fragepflichtige Änderung und nennen sie.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, distinct, func, select

from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, GRUND_KORREKTUR, HERKUNFT_WECHSEL
from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_KEINE, aenderungen, lade_wirksame_quellen
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, ist_luecken_zeile, lade_wechsel

logger = logging.getLogger(__name__)

GRUENDE = (GRUND_FORTSETZUNG, GRUND_KORREKTUR)
#: Schlüssel in ``gruende``/``labels`` für «jede fragepflichtige Änderung dieses Aufrufs» (die Feld-Route ändert ein Feld).
ALLE = "*"

#: Wortlaute der Ablehnung (422) — die Oberfläche fragt vorher, diese Sätze sieht nur ein Aufruf an ihr vorbei.
SATZ_GRUND_FEHLT = ("Die Zuordnung von {felder} hat eigene Werte. Sag eedc, ob die bisherigen Werte bleiben (der neue Sensor "
                    "setzt fort) oder verworfen werden (bisher war der falsche Sensor zugeordnet).")
SATZ_FALSCH_SEIT_FEHLT = "Für eine Korrektur fehlt «falsch seit» ({feld})."
SATZ_FALSCH_SEIT_ZUKUNFT = "«Falsch seit» muss vor der nächsten vollen Stunde liegen ({feld})."


class GrundFehlt(ValueError):
    """Eine fragepflichtige Änderung ohne (gültigen) Grund — die Route antwortet 422."""


@dataclass
class Frage:
    """Eine wirksame Änderung eines Schlüssels mit eigenen Werten (nur solche werden verzeichnet)."""

    sensor_key: str
    vorher: Optional[dict]
    nachher: Optional[dict]
    grund_erforderlich: bool
    erster_wert: Optional[datetime] = None
    tage: int = 0
    stand_alt: Optional[float] = None
    stand_neu: Optional[float] = None
    vorgabe_falsch_seit: Optional[datetime] = None
    #: U2 Lauf b (F9): was «bleiben» zwischen zwei HA-Sensoren tut (``bleiben.angaben``; ``None`` bei jeder anderen Quelle).
    bleiben: Optional[dict] = None


def kann_werte_liefern(q: Optional[dict]) -> bool:
    return isinstance(q, dict) and bool(q.get("art")) and q.get("art") != ART_KEINE


def _gleich(a: Optional[dict], b: Optional[dict]) -> bool:
    return (a or {}) == (b or {})


def _davor(w, vor: Optional[datetime], vor_id: Optional[int]) -> bool:
    """Lag der verzeichnete Wechsel ``w`` vor der gefragten Zeile? Reihenfolge ``ab_ts``, dann Zeilen-Nummer — zwei Wechsel
    in derselben Stunde (Fehlklick «Keine» und sofort zurück) tragen dasselbe ``ab_ts`` (Bauplan §13 Nr. 66)."""
    if vor is None:
        return True
    if w.ab_ts != vor:
        return w.ab_ts < vor
    return vor_id is not None and w.id is not None and w.id < vor_id


async def letzte_quelle_mit_werten(db, anlage_id: int, sensor_key: str, aktuell: Optional[dict],
                                   vor: Optional[datetime] = None, vor_id: Optional[int] = None) -> Optional[dict]:
    """Die Quelle, gegen die verglichen wird: die heutige, wenn sie Werte liefern kann, sonst die letzte verzeichnete mit
    Werten (A → «Keine» → B fragt bei B). ``None`` = unbekannt (dann wird gefragt). ``vor``/``vor_id``: nur verzeichnete
    Wechsel vor der Zeile mit diesem ``ab_ts`` und dieser Nummer (gleiches ``ab_ts``, kleinere Nummer zählt mit) — dieselbe
    Frage zum Zeitpunkt eines früheren Wechsels, wie ``pruefe`` sie im Augenblick des Wechsels stellte (``haette_gefragt``,
    Sitzung 4). Eine Lücken-Zeile ist kein Wechsel (``zeitpunkt.ist_luecken_zeile``, Bauplan «Zu §14» Nr. 105)."""
    if kann_werte_liefern(aktuell):
        return aktuell
    zeilen = sorted((w for w in (await lade_wechsel(db, anlage_id)).get(sensor_key, ())
                     if w.aufgehoben_durch is None and not ist_luecken_zeile(w) and _davor(w, vor, vor_id)),
                    key=lambda w: (w.ab_ts, w.id or 0), reverse=True)
    for w in zeilen:
        for q in (w.nachher, w.vorher):
            if kann_werte_liefern(q):
                return q
    return None


def frage_noetig(nachher: Optional[dict], letzte: Optional[dict]) -> bool:
    """Die Regel «wann wird gefragt» bei eigenen Werten: die neue Quelle kann Werte liefern und ist nicht die letzte Quelle
    mit Werten (unbekannt ⇒ gefragt)."""
    return kann_werte_liefern(nachher) and (letzte is None or not _gleich(letzte, nachher))


async def haette_gefragt(db, anlage_id: int, w) -> bool:
    """Hätte die Abfrage (B-2) bei diesem verzeichneten Wechsel nach dem Grund gefragt? (Sitzung 4, B-7: der Befund «Zuordnung
    geändert, Grund fehlt» und «Grund nachtragen» fragen hier, nicht nachgebaut.) Dieselbe Regel wie ``pruefe`` zum Zeitpunkt
    des Wechsels: eigene Werte vor ``ab_ts``, die neue Quelle kann Werte liefern und ist nicht die letzte Quelle mit Werten
    davor. Ein «Zähler getauscht» (``vorher = nachher``) ist kein Wechsel der Quelle."""
    from backend.services.zuordnung_wechsel.quelle import hat_eigene_werte

    if _gleich(w.vorher, w.nachher):
        return False
    if not await hat_eigene_werte(db, anlage_id, w.sensor_key, vor=w.ab_ts):
        return False
    letzte = await letzte_quelle_mit_werten(db, anlage_id, w.sensor_key, w.vorher, vor=w.ab_ts, vor_id=w.id)
    return frage_noetig(w.nachher, letzte)


async def pruefe(db, anlage, vorher: dict[str, dict], nachher: dict[str, dict], *, details: bool = True,
                 ha_svc=None, jetzt: Optional[datetime] = None,
                 zaehlt_ab: Optional[dict[str, datetime]] = None) -> list[Frage]:
    """Die Prüf-Funktion aller Wege: je Schlüssel mit eigenen Werten, dessen wirksame Quelle sich ändert, eine ``Frage``
    (``grund_erforderlich`` nach dem Modul-Docstring). Ein Schlüssel ohne eigene Werte fehlt (nicht gefragt, nicht verzeichnet).
    ``zaehlt_ab`` (je Schlüssel oder ``ALLE``): «Der neue Sensor zählt ab» für die Angaben zu «bleiben» — ein Wert, den eedc
    nicht annimmt, wirft ``bleiben.ZaehltAbAbgelehnt``."""
    aus: list[Frage] = []
    for a in await aenderungen(db, anlage, vorher, nachher):
        if not a.eigene_werte:
            continue
        letzte = await letzte_quelle_mit_werten(db, anlage.id, a.sensor_key, a.vorher)
        noetig = frage_noetig(a.nachher, letzte)
        f = Frage(a.sensor_key, a.vorher, a.nachher, noetig)
        if noetig and details:
            await _details(db, anlage.id, f, ha_svc, jetzt or datetime.now(), _je_key(zaehlt_ab or {}, f.sensor_key))
        aus.append(f)
    _zaehlt_ab_ohne_frage(aus, zaehlt_ab)
    return aus


def _zaehlt_ab_nur_bleiben(fragen: list[Frage], grund: dict, zaehlt_ab: Optional[dict[str, datetime]]) -> None:
    """«Der neue Sensor zählt ab» gehört zu «bleiben» — mit «verwerfen» ⇒ 422."""
    from backend.services.zuordnung_wechsel.bleiben import SATZ_NUR_BLEIBEN, ZaehltAbAbgelehnt

    for f in fragen:
        if (f.grund_erforderlich and _je_key(zaehlt_ab or {}, f.sensor_key) is not None
                and grund[f.sensor_key][0] != GRUND_FORTSETZUNG):
            raise ZaehltAbAbgelehnt(SATZ_NUR_BLEIBEN)


def _zaehlt_ab_ohne_frage(fragen: list[Frage], zaehlt_ab: Optional[dict[str, datetime]]) -> None:
    """«Der neue Sensor zählt ab» für einen Schlüssel ohne Wechsel «bleiben» zwischen zwei HA-Sensoren ⇒ 422."""
    from backend.services.zuordnung_wechsel.bleiben import SATZ_NUR_HA, ZaehltAbAbgelehnt, ist_ha_zu_ha

    for key, wert in (zaehlt_ab or {}).items():
        if wert is None:
            continue
        treffer = [f for f in fragen if f.grund_erforderlich and (key == ALLE or f.sensor_key == key)]
        if not treffer or not all(ist_ha_zu_ha(f.vorher, f.nachher) for f in treffer):
            raise ZaehltAbAbgelehnt(SATZ_NUR_HA)


# ── Angaben für den Dialog (lesend) ─────────────────────────────────────────────────────────────────────────


async def _reihe(db, anlage_id: int, key: str) -> tuple[Optional[datetime], int]:
    """Erster Zeitpunkt und Zahl der Tage der Zählerstand-Reihe (ohne Stände — kein Reihen-Leser)."""
    from backend.models.sensor_snapshot import SensorSnapshot

    bed = and_(SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key)
    erster, tage = (await db.execute(select(func.min(SensorSnapshot.zeitpunkt),
                                            func.count(distinct(func.date(SensorSnapshot.zeitpunkt)))).where(bed))).one()
    return erster, int(tage or 0)


async def _stand_neu(ha_svc, kanal, key: str, nachher: Optional[dict]) -> Optional[float]:
    """Der Zählerstand (``state``) einer HA-Entität jetzt (der neuen, Lab-K W6 auch der bisherigen), in der Einheit des
    Kanals (Bauplan §11 Nr. 47; MQTT: unbekannt, bis Werte kommen; ohne ``state`` keine Angabe)."""
    from backend.services.kanal.angaben import zaehlerstand_ha_jetzt
    from backend.services.kanal.katalog import zaehler_art

    if not (isinstance(nachher, dict) and nachher.get("art") == ART_HA and nachher.get("entity_id")):
        return None
    eid = nachher["entity_id"]
    try:
        if ha_svc is None or not ha_svc.is_available:
            return None
        art = kanal.art if kanal is not None else (zaehler_art(key, None) or "sum")
        return await zaehlerstand_ha_jetzt(ha_svc, kanal.id if kanal is not None else 0, art, eid)
    except Exception as e:  # noqa: BLE001 — eine Anzeige, kein Blocker
        logger.debug("Stand der neuen Quelle %s nicht lesbar: %s", eid, e)
        return None


async def _beginn_bisherige_quelle(db, anlage_id: int, f: Frage, kanal, erster: Optional[datetime]) -> Optional[datetime]:
    """Vorgabe für «falsch seit» (Konzept S-4, Bauplan §11 Nr. 54): Beginn der bisherigen Quelle — der jüngste verzeichnete
    Wechsel, **der sie brachte** (``nachher`` = die letzte Quelle mit Werten; kein Wechsel nach «Keine», kein «Zähler
    getauscht» mit ``vorher = nachher``), sonst der Beginn ihres Abschnitts im Kanal, sonst der erste eigene Wert."""
    from backend.services.kanal.angaben import beginn_juengste_quelle

    bisherige = await letzte_quelle_mit_werten(db, anlage_id, f.sensor_key, f.vorher)
    zeilen = [w for w in (await lade_wechsel(db, anlage_id)).get(f.sensor_key, ())
              if w.aufgehoben_durch is None and bisherige is not None and _gleich(w.nachher, bisherige)
              and not _gleich(w.vorher, w.nachher)]
    if zeilen:
        return max(w.ab_ts for w in zeilen)
    beginn = await beginn_juengste_quelle(db, kanal.id) if kanal is not None else None
    if beginn is not None:
        return beginn
    return None if erster is None else erster.replace(minute=0, second=0, microsecond=0)


def _dienst(ha_svc):
    if ha_svc is not None:
        return ha_svc
    from backend.services.zuordnung_wechsel.korrektur import ha_eingerichtet

    if not ha_eingerichtet():
        return None
    from backend.services.ha_statistics_service import get_ha_statistics_service

    return get_ha_statistics_service()


async def _details(db, anlage_id: int, f: Frage, ha_svc, jetzt: datetime, zaehlt_ab: Optional[datetime] = None) -> None:
    """Die Angaben des Dialogs: erster eigener Wert und Tage (Reihe, sonst Kanal), der letzte Zählerstand (``state``) des
    bisherigen Sensors aus dem Kanal (ein Schlüssel ohne Kanal hat hier keinen), der Zählerstand der neuen HA-Entität jetzt,
    die Vorgabe für «falsch seit»; zwischen zwei HA-Sensoren die Angaben zu «bleiben» (``bleiben.angaben``, U2 Lauf b)."""
    from backend.services.kanal.angaben import angaben, kanal_des_schluessels
    from backend.services.zuordnung_wechsel import bleiben

    kanal = await kanal_des_schluessels(db, anlage_id, f.sensor_key)
    erster, tage = await _reihe(db, anlage_id, f.sensor_key)
    k_erster, k_tage, stand = await angaben(db, kanal) if kanal is not None else (None, 0, None)
    if erster is None or (k_erster is not None and k_erster < erster):
        erster, tage = k_erster, k_tage        # Lab-K W2: der früheste eigene Wert (Kanal oder Reihe)
    f.erster_wert, f.tage, f.stand_alt = erster, tage, stand
    svc = _dienst(ha_svc)
    f.stand_neu = await _stand_neu(svc, kanal, f.sensor_key, f.nachher)
    # Lab-K W6: der letzte Stand der bisherigen HA-Quelle aus HA (Kurzzeitstatistik) — die letzte Kanalzeile endet bis zu
    # einer Stunde früher; ohne Angabe aus HA bleibt die der Kanalzeile.
    alt_jetzt = await _stand_neu(svc, kanal, f.sensor_key, f.vorher)
    if alt_jetzt is not None:
        f.stand_alt = alt_jetzt
    f.vorgabe_falsch_seit = await _beginn_bisherige_quelle(db, anlage_id, f, kanal, erster)
    f.bleiben = await bleiben.angaben(db, anlage_id, f.sensor_key, f.vorher, f.nachher, ab_ts=ab_ts_aus(jetzt),
                                      erklaert_ts=jetzt, jetzt=jetzt, zaehlt_ab=zaehlt_ab, ha_svc=ha_svc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.replace(microsecond=0).isoformat()


def antwort(f: Optional[Frage], label: Optional[str] = None) -> dict[str, Any]:
    """Die Antwort der Prüf-Route je Schlüssel (Bauplan B-2: ``grund_erforderlich, erster_wert, tage, stand_alt, stand_neu``)."""
    if f is None:
        return {"grund_erforderlich": False, "erster_wert": None, "tage": 0, "stand_alt": None, "stand_neu": None,
                "sensor_key": None, "label": label, "verzeichnet": False, "vorgabe_falsch_seit": None, "bleiben": None,
                "bleiben_satz": None}
    from backend.services.zuordnung_wechsel.rohstand import bleiben_satz

    return {"grund_erforderlich": f.grund_erforderlich, "erster_wert": _iso(f.erster_wert), "tage": f.tage,
            "stand_alt": f.stand_alt, "stand_neu": f.stand_neu, "sensor_key": f.sensor_key, "label": label,
            "verzeichnet": True, "vorgabe_falsch_seit": _iso(f.vorgabe_falsch_seit), "bleiben": f.bleiben,
            # U3 b (G5, E5): was «bleiben» bei MQTT bzw. zwischen Home Assistant und MQTT tut.
            "bleiben_satz": None if f.bleiben else bleiben_satz(f.vorher, f.nachher, f.sensor_key)}


# ── Korrektur über den Dienst aus Sitzung 3a ─────────────────────────────────────────────────────────────────


def volle_stunde(dt: datetime) -> datetime:
    """Örtliche volle Stunde ohne Zone (wie ``zuordnung_wechsel.ab_ts``); eine Angabe mit Zone wird erst örtlich."""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.replace(minute=0, second=0, microsecond=0)


def korrektur_auftrag(anlage_id: int, f: Frage, falsch_seit: datetime, jetzt: datetime):
    """Der Auftrag des Dienstes für eine Korrektur beim Wechsel: falsch in ``[falsch_seit, ab)``, richtig ist die neue Quelle."""
    from backend.services.zuordnung_wechsel.korrektur import Auftrag

    return Auftrag(anlage_id=anlage_id, sensor_key=f.sensor_key, falsch_seit=volle_stunde(falsch_seit),
                   ab=ab_ts_aus(jetzt), vorher=f.vorher, nachher=f.nachher, herkunft=HERKUNFT_WECHSEL, erklaert=jetzt)


def _pruefe_falsch_seit(f: Frage, falsch_seit: Optional[datetime], jetzt: datetime, label: str) -> None:
    if falsch_seit is None:
        raise GrundFehlt(SATZ_FALSCH_SEIT_FEHLT.format(feld=label))
    if volle_stunde(falsch_seit) >= ab_ts_aus(jetzt):
        raise GrundFehlt(SATZ_FALSCH_SEIT_ZUKUNFT.format(feld=label))


async def korrektur_vorschau(db, anlage_id: int, f: Frage, falsch_seit: datetime, jetzt: datetime) -> dict[str, Any]:
    """Die Vorschau des Dienstes für den Dialog (lesend; derselbe Auftrag wie der Lauf, ``korrektur.lage``)."""
    _pruefe_falsch_seit(f, falsch_seit, jetzt, f.sensor_key)
    return await vorschau_des_auftrags(db, korrektur_auftrag(anlage_id, f, falsch_seit, jetzt))


async def vorschau_des_auftrags(db, auftrag, *, nachtrag: bool = False) -> dict[str, Any]:
    """Vorschau = Lauf für einen Auftrag des Korrektur-Dienstes (Dialog beim Wechsel und «Grund nachtragen», Sitzung 4;
    ``nachtrag``: das Intervall endet am Wechsel, Bauplan §13 Nr. 69)."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    nicht = None
    try:
        svc = kr.ha_dienst(None)
    except kr.KorrekturNichtStartbar as e:
        svc, nicht = None, str(e)
    try:
        la = await kr.lage(db, auftrag, ha_svc=svc)
    except kr.KorrekturNichtStartbar as e:      # ein Abruf aus Home Assistant scheitert (Bauplan «Zu §14» Nr. 116 E-K6)
        svc, nicht = None, str(e)
        la = await kr.lage(db, auftrag, ha_svc=None)
    la.nicht_startbar = nicht
    saetze = kr.saetze(la)
    if nicht is None:            # der Kanal (§11 Nr. 48) vor dem Satz zum Rückweg
        saetze[-1:-1] = await kr.kanal_saetze(la, svc, bis_zum_wechsel=nachtrag)
    return {"saetze": saetze, **kr.vorschau_daten(la)}


@dataclass
class Vollzug:
    fragen: list[Frage]
    korrekturen: list[dict] = field(default_factory=list)
    ha_svc: Any = None
    #: Sensorwechsel U2 a2: die Wechsel-Zeilen «bleiben» zwischen zwei HA-Sensoren (``ansatz = offen``), die nach dem Commit
    #: angesetzt werden (``ansatz.setze_an``), mit der Uhr der Erklärung und Sitzungen an derselben Datenbank.
    ansaetze: list[int] = field(default_factory=list)
    jetzt: Optional[datetime] = None
    sitzungen: Any = None
    #: Je Wechsel «bleiben» das Ergebnis von ``ansatz.setze_an`` nach dem Commit (U2 Lauf b: Lauf bzw. Wartegrund).
    angesetzt: list[dict] = field(default_factory=list)

    def zusammenfassung(self, labels: Optional[dict[str, str]] = None) -> list[dict]:
        """Je Korrektur der Lauf für die Antwort der Route (Fortschritt an der Fläche); dazu je angesetztem Wechsel «bleiben»
        sein Lauf mit ``art = ansetzen`` (U2 Lauf b)."""
        laeufe = [{"lauf": e["summary"]["lauf"], "sensor_key": e["lage"].auftrag.sensor_key,
                   "label": _je_key(labels or {}, e["lage"].auftrag.sensor_key, e["lage"].auftrag.sensor_key),
                   "tage_neu": e["summary"]["tage_neu"], "zaehlerstaende_geloescht": e["summary"]["zaehlerstaende_geloescht"]}
                  for e in self.korrekturen]
        return laeufe + [z for e in self.angesetzt for z in self._ergebnis(e, labels)[0]]

    def wartet(self, labels: Optional[dict[str, str]] = None) -> list[dict]:
        """Je Wechsel «bleiben», der noch nicht wie Home Assistant gerechnet wird, der Grund in Anwender-Sprache."""
        return [z for e in self.angesetzt for z in self._ergebnis(e, labels)[1]]

    @staticmethod
    def _ergebnis(e: dict, labels: Optional[dict[str, str]]) -> tuple[list[dict], list[dict]]:
        from backend.services.zuordnung_wechsel.bleiben import ergebnis_der_route

        key = e["sensor_key"]
        return ergebnis_der_route(e, key, _je_key(labels or {}, key, key), e.get("vorher"), e.get("nachher"))


def _je_key(d: dict, key: str, sonst=None):
    return d.get(key) or d.get(ALLE) or sonst


def offene_fragen(fragen: list[Frage], gruende: dict[str, tuple[str, Optional[datetime]]]) -> list[Frage]:
    return [f for f in fragen if f.grund_erforderlich and _je_key(gruende, f.sensor_key, (None,))[0] not in GRUENDE]


async def vollziehe(db, anlage, vorher: dict[str, dict], gruende: dict[str, tuple[str, Optional[datetime]]], *,
                    labels: Optional[dict[str, str]] = None, jetzt: Optional[datetime] = None,
                    zaehlt_ab: Optional[dict[str, datetime]] = None) -> Vollzug:
    """Nach der Änderung (in der Sitzung des Aufrufers, vor seinem Commit): prüfen, verzeichnen, Korrektur ausführen.

    ``gruende``: je Schlüssel ``(grund, falsch_seit)``. Fehlt für eine fragepflichtige Änderung der Grund ⇒ ``GrundFehlt``;
    HA eingerichtet und nicht erreichbar bei einer Korrektur ⇒ ``korrektur.KorrekturNichtStartbar``. ``zaehlt_ab`` (je
    Schlüssel oder ``ALLE``): «Der neue Sensor zählt ab» an einem Wechsel «bleiben» zwischen zwei HA-Sensoren mit Überlappung
    (``bleiben.setze_zaehlt_ab``); sonst ``bleiben.ZaehltAbAbgelehnt`` (ein ``GrundFehlt`` — die Route antwortet 422)."""
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel.verzeichnen import verzeichne

    labels = labels or {}
    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    fragen = await pruefe(db, anlage, vorher, await lade_wirksame_quellen(db, anlage), details=False, zaehlt_ab=zaehlt_ab)
    offen = offene_fragen(fragen, gruende)
    if offen:
        raise GrundFehlt(SATZ_GRUND_FEHLT.format(felder=" · ".join(_je_key(labels, f.sensor_key, f.sensor_key) for f in offen)))
    grund = {f.sensor_key: _je_key(gruende, f.sensor_key) for f in fragen if f.grund_erforderlich}
    korr = [f for f in fragen if f.grund_erforderlich and grund[f.sensor_key][0] == GRUND_KORREKTUR]
    _zaehlt_ab_nur_bleiben(fragen, grund, zaehlt_ab)
    for f in korr:
        _pruefe_falsch_seit(f, grund[f.sensor_key][1], jetzt, _je_key(labels, f.sensor_key, f.sensor_key))
    v = Vollzug(fragen, ha_svc=kr.ha_dienst(None) if korr else None)
    fort = {k: GRUND_FORTSETZUNG for k, (g, _f) in grund.items() if g == GRUND_FORTSETZUNG}
    zeilen = await verzeichne(db, anlage, vorher, jetzt=jetzt, gruende=fort, auslassen={f.sensor_key for f in korr})
    await _ansatz_offen(db, v, zeilen, jetzt, zaehlt_ab or {})
    for f in korr:
        v.korrekturen.append(await kr.fuehre_aus(db, korrektur_auftrag(anlage.id, f, grund[f.sensor_key][1], jetzt),
                                                  ha_svc=v.ha_svc, jetzt=jetzt))
    return v


async def _ansatz_offen(db, v: Vollzug, zeilen, jetzt: datetime, zaehlt_ab: dict[str, datetime]) -> None:
    """Sensorwechsel U2 a2 (Rechenweg F3): eine Fortsetzung zwischen zwei HA-Sensoren bekommt ``ansatz = offen`` — nach dem
    Commit setzt der Dienst sie an, wenn HA den neuen schon führt, sonst der nächste Stundenlauf. Mit «Der neue Sensor zählt
    ab» (U2 Lauf b, F9) ``offen_schnitt`` an der gewählten Stunde (``bleiben.setze_zaehlt_ab``)."""
    from backend.models.zuordnung_wechsel import ANSATZ_OFFEN
    from backend.services.zuordnung_wechsel.ansatz import wird_angesetzt
    from backend.services.zuordnung_wechsel.bleiben import setze_zaehlt_ab
    from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    for row in zeilen:
        if wird_angesetzt(row):
            row.ansatz = ANSATZ_OFFEN
            wert = _je_key(zaehlt_ab, row.sensor_key)
            if wert is not None:
                await setze_zaehlt_ab(db, row, wert, jetzt=jetzt)
                vergiss(db, row.anlage_id)
            v.ansaetze.append(row.id)
    if v.ansaetze:
        from backend.core.database import get_session

        await db.flush()
        v.jetzt, v.sitzungen = jetzt, sitzungen_wie(db, get_session)


async def nach_dem_commit(v: Vollzug) -> None:
    """Nach dem Commit des Aufrufers: je Korrektur Kanal füllen und den Hintergrund-Lauf der Tage starten; je Wechsel
    «bleiben» ansetzen (U2 a2)."""
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel.ansatz import setze_an

    for erg in v.korrekturen:
        await kr.nach_dem_commit(erg, ha_svc=v.ha_svc)
    quellen = {f.sensor_key: (f.vorher, f.nachher) for f in v.fragen}
    for wechsel_id in v.ansaetze:
        e = await setze_an(v.sitzungen, wechsel_id, jetzt=v.jetzt)
        key = (e.get("lage") or {}).get("sensor_key") or e.get("sensor_key")
        if key is None:
            continue
        vorher, nachher = quellen.get(key, (None, None))
        v.angesetzt.append({**e, "sensor_key": key, "vorher": vorher, "nachher": nachher})


def aktivitaet_text(v: Vollzug, labels: dict[str, str]) -> str:
    """Der Zusatz der Protokoll-Zeile: Grund je Schlüssel."""
    from backend.core.zahlenformat import fmt_zahl

    teile = []
    korr = {e["lage"].auftrag.sensor_key: e["summary"] for e in v.korrekturen}
    for f in v.fragen:
        if not f.grund_erforderlich:
            continue
        name = _je_key(labels, f.sensor_key, f.sensor_key)
        if f.sensor_key in korr:
            s = korr[f.sensor_key]
            teile.append(f"{name}: Korrektur ({fmt_zahl(s['zaehlerstaende_geloescht'])} Zählerstände verworfen, "
                         f"{fmt_zahl(s['tage_neu'])} Tage werden neu gebildet)")
        else:
            teile.append(f"{name}: bisherige Werte bleiben")
    return " · ".join(teile)

