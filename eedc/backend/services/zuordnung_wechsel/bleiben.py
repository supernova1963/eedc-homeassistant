"""«Bisherige Werte bleiben» zwischen zwei Home-Assistant-Sensoren — die Angaben des Dialogs (Sensorwechsel U2 Lauf b,
Rechenweg ``opus-berichte/SENSORWECHSEL-U2-RECHENWEG-2026-11-19.md`` F9/F10, Bauplan Nr. 138–145).

Der Dialog «Warum wechselt die Quelle?» stellt **eine** Frage: die bisherigen Werte bleiben oder verwerfen. Bei «bleiben»
zwischen zwei HA-Sensoren rechnet eedc wie Home Assistant (``ansatz.py``: der alte Sensor bis zu seinem letzten Wert, der neue
ab seinem ersten). Was dafür geschieht, sagt die Prüf-Antwort — **Vorschau = Lauf**: dieselbe ``ansatz.lage`` an einer
gedachten Wechsel-Zeile (``pruef_zeile``), wie sie die Route anlegen würde.

* ``angaben``: seit wann HA den neuen Sensor führt (``seit`` = Beginn seiner ersten Stundenzeile), Überlappung, die Stunde, ab der
  der neue zählt (``zaehlt_ab``), bei Überlappung Vorgabe und zulässiger Bereich für «Der neue Sensor zählt ab» (frühestens
  die Stunde nach der ersten Zeile des neuen, spätestens die Stunde des Wechsels), Umfang des Neulesens (Stunden, Tage,
  abgeschlossene Monate mit gespeichertem Monatsabschluss), der Wartegrund (``ansatz.WARTET_*``) und die Sätze.
* ``setze_zaehlt_ab``: der Wert des Felds «Der neue Sensor zählt ab» an einer Zeile «bleiben» — nur bei Überlappung, nur im
  zulässigen Bereich (sonst ``ZaehltAbAbgelehnt``, die Routen antworten 422). Die Zeile trägt dann ``ansatz = offen_schnitt``
  und ``ab_ts`` = gewählte Stunde + 1 h (``ansatz._art_und_g``: G = ``ab_ts − 1 h``).
* ``wartet_satz``: der Wartegrund einer offenen Zeile in Anwender-Sprache (Fläche, Prüf-Antwort, Antwort der Routen).

Nur Home Assistant → Home Assistant (``ansatz.ist_ha_wechsel``); jede andere Kombination liest bei «bleiben» wie bisher (U3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

from backend.models.zuordnung_wechsel import ANSATZ_BEIDE, ANSATZ_OFFEN, ANSATZ_OFFEN_SCHNITT, GRUND_FORTSETZUNG
from backend.services.zuordnung_wechsel.abfrage import GrundFehlt

logger = logging.getLogger(__name__)

_STUNDE = timedelta(hours=1)

#: Die Bezeichnung des Felds im Dialog (Client ``ZAEHLT_AB_LABEL``) — die Ablehnungen nennen es wörtlich.
FELD = "Der neue Sensor zählt ab"

#: Wortlaute der Prüf-Antwort bei «bleiben» (Lauf b; Wortlaut-Vorlage an den Inhaber mit dem Abschlussbericht).
SATZ_SEIT = "Home Assistant führt {neu} seit {seit} Uhr."
SATZ_BEIDE = ("eedc rechnet wie Home Assistant mit beiden Sensoren: {alt} bis zu seinem letzten Wert, {neu} ab seinem ersten — "
              "die Stunde ab {g} Uhr zählt beide. Zwischen den Zählerständen der zwei Sensoren rechnet eedc keine Menge.")
#: Korrekturrunde Lab-K W3: führt Home Assistant für den alten Sensor in der Stunde G keine Zeile (er endete vorher), zählt
#: die Stunde nur den neuen — dann nicht «zählt beide».
#: U3-K (Nachmessung Lab-K LK-B7): «führt ab G keine Stunde mehr» war falsch, wenn dem alten nur die Zeile in G fehlt.
SATZ_BEIDE_NUR_NEU = ("eedc rechnet wie Home Assistant mit beiden Sensoren: {alt} bis zu seinem letzten Wert, {neu} ab seinem "
                      "ersten. Für die Stunde ab {g} Uhr führt Home Assistant von {alt} keinen Wert — sie zählt nur {neu}. "
                      "Zwischen den Zählerständen der zwei Sensoren rechnet eedc keine Menge.")
SATZ_SCHNITT = ("Beide Sensoren haben eine Zeit lang gleichzeitig gezählt. eedc zählt {alt} bis {g} Uhr und {neu} ab {g} Uhr; "
                "eine frühere Stunde wählst du unter «" + FELD + "».")
#: Lab-K W4: nach der Wahl einer Stunde unter «Der neue Sensor zählt ab» ohne den Hinweis auf das Feld.
SATZ_SCHNITT_GEWAEHLT = ("Beide Sensoren haben eine Zeit lang gleichzeitig gezählt. eedc zählt {alt} bis {g} Uhr und {neu} ab "
                         "{g} Uhr.")
#: Lab-K W1: «({stunden})» und «{tage}» tragen die Anzahl mit Ein- oder Mehrzahl (``zahlenformat.fmt_anzahl``).
SATZ_UMFANG = "Dafür liest eedc die Werte dieses Felds ab {g} Uhr neu aus Home Assistant ({stunden})"
SATZ_UMFANG_TAGE = " und bildet {tage} im Hintergrund neu; Wetter und Börsenpreis bleiben."
SATZ_UMFANG_KEIN_TAG = "; kein abgeschlossener Tag muss neu gebildet werden."
#: Lab-K W1: zählt der neue Sensor ab der laufenden Stunde, gibt es noch nichts neu zu lesen (statt «(0 Stunden)»).
SATZ_UMFANG_LAUFEND = ("Neu zu lesen ist noch nichts: die Stunde ab {g} Uhr läuft noch, und eedc liest sie mit dem nächsten "
                       "Stundenlauf.")
SATZ_MONATE = ("Gespeicherte Monatsabschlüsse ({liste}) bleiben, wie sie sind; was eedc im Monat aus den Tagen rechnet, folgt den "
               "neu gebildeten Tagen. Angleichen lässt sich ein solcher Monat unter «Monatsdaten» mit «Aus HA laden».")
SATZ_LOESCHEN = ("Den bisherigen Sensor kannst du in Home Assistant löschen: seine Statistik bleibt dort lesbar, und eedc rechnet "
                 "weiter mit ihr. Was er in den letzten Minuten vor dem Löschen noch gezählt hat (höchstens fünf), führt Home "
                 "Assistant nicht mehr — eedc dann auch nicht.")
SATZ_ALT_NICHT_IN_HA = ("Home Assistant führt die Statistik von {alt} nicht mehr — eedc rechnet ihn bis zu dem letzten "
                        "Zählerstand, den es von ihm aus Home Assistant gespeichert hat.")
#: Warum eine Zeile «bleiben» noch nicht wie Home Assistant gerechnet wird (``ansatz.WARTET_*``).
SATZ_WARTET = {
    "noch_keine_zeile": ("Home Assistant führt für {neu} noch keine Stundenwerte. eedc rechnet beide Sensoren wie Home "
                         "Assistant, sobald dort die erste volle Stunde von {neu} steht — es prüft das jede Stunde von "
                         "selbst. Bis dahin können die Werte dieses Felds ab dem Wechsel unvollständig sein."),
    "ha_nicht_erreichbar": ("Home Assistant ist gerade nicht erreichbar. eedc rechnet den Wechsel wie Home Assistant, sobald "
                            "es wieder erreichbar ist — es prüft das jede Stunde von selbst. Bis dahin "
                            "können die Werte dieses Felds ab dem Wechsel unvollständig sein."),
    "korrektur_lauf_offen": ("Für dieses Feld liest eedc aus einem früheren Lauf noch Werte aus Home Assistant neu. Danach "
                             "rechnet eedc den Wechsel wie Home Assistant — es prüft das jede Stunde von selbst."),
}
#: ``ansatz.WARTET_KANAL`` wartet nicht: eedc rechnet den Wechsel dann wie bisher (a-K) — in der Prüf-Antwort dieser Satz.
SATZ_KANAL_WIE_BISHER = ("Die Stundenwerte dieses Felds vor dem Wechsel stammen in eedc nicht aus der Statistik von {alt} in "
                         "Home Assistant. eedc rechnet den Wechsel deshalb wie bisher: die bisherigen Werte bleiben, und der "
                         "Unterschied zwischen altem und neuem Zählerstand zählt nicht als Menge; wo eedc aus den gespeicherten "
                         "Zählerständen rechnet, zählt die Stunde des Wechsels keinen Zuwachs.")
#: Ablehnungen des Felds «Der neue Sensor zählt ab» (422).
SATZ_NUR_HA = "«" + FELD + "» gibt es nur beim Wechsel zwischen zwei Sensoren aus Home Assistant."
SATZ_NUR_BLEIBEN = "«" + FELD + "» gehört zu «Bisherige Werte bleiben»."
SATZ_OHNE_UEBERLAPPUNG = ("«" + FELD + "» gibt es nur, wenn beide Sensoren eine Zeit lang gleichzeitig gezählt haben — hier "
                          "bestimmt Home Assistant die Stunde selbst.")
SATZ_NICHT_PRUEFBAR = ("«" + FELD + "» lässt sich gerade nicht prüfen (Home Assistant ist nicht erreichbar oder führt den neuen "
                       "Sensor noch nicht). Ohne diese Angabe zählt der neue Sensor ab der Stunde des Wechsels.")
SATZ_BEREICH = "«" + FELD + "» muss zwischen {von} und {bis} Uhr liegen."
#: Korrekturrunde U3-K (Nachmessung Lab-K LK-B3): besteht der Bereich aus einer einzigen Stunde (der vorige Wechsel liegt in
#: der Stunde davor), gibt es nichts zu wählen — der Dialog bietet kein Feld an, der Satz nennt die Stunde.
SATZ_BEREICH_EINE = "«" + FELD + "» kann hier nur {von} Uhr sein."


class ZaehltAbAbgelehnt(GrundFehlt):
    """Ein Wert für «Der neue Sensor zählt ab», den eedc so nicht annimmt (die Routen antworten 422 mit dem Satz; ein
    ``abfrage.GrundFehlt``, damit die Schreib-Routen ihn wie einen fehlenden Grund behandeln)."""


def _uhr(t: datetime) -> str:
    return t.strftime("%d.%m.%Y %H:%M")


def _iso(t: Optional[datetime]) -> Optional[str]:
    return None if t is None else t.replace(microsecond=0).isoformat()


def ist_ha_zu_ha(vorher: Optional[dict], nachher: Optional[dict]) -> bool:
    """Zwei verschiedene HA-Entitäten (dieselbe Bedingung wie ``ansatz.ist_ha_wechsel`` an einer Zeile)."""
    from backend.services.zuordnung_wechsel.ansatz import ist_ha_wechsel

    return ist_ha_wechsel(SimpleNamespace(vorher=vorher, nachher=nachher))


def volle_stunde(t: datetime) -> datetime:
    """Örtliche volle Stunde ohne Zone (eine Angabe mit Zone wird erst örtlich)."""
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t.replace(minute=0, second=0, microsecond=0)


def pruef_zeile(anlage_id: int, sensor_key: str, vorher: Optional[dict], nachher: Optional[dict], *, ab_ts: datetime,
                erklaert_ts: datetime, zaehlt_ab: Optional[datetime] = None):
    """Die gedachte Wechsel-Zeile «bleiben», an der ``ansatz.lage`` rechnet (Vorschau = Lauf): wie die Route sie anlegt
    (``ansatz = offen``), mit «Der neue Sensor zählt ab» wie ``setze_zaehlt_ab`` (``offen_schnitt``, ``ab_ts`` = Stunde + 1 h)."""
    return SimpleNamespace(
        id=None, anlage_id=anlage_id, sensor_key=sensor_key, vorher=vorher, nachher=nachher, grund=GRUND_FORTSETZUNG,
        aufgehoben_durch=None, erklaert_ts=erklaert_ts,
        ansatz=ANSATZ_OFFEN if zaehlt_ab is None else ANSATZ_OFFEN_SCHNITT,
        ab_ts=ab_ts if zaehlt_ab is None else volle_stunde(zaehlt_ab) + _STUNDE)


def bereich(la, row) -> Optional[tuple[datetime, datetime]]:
    """Zulässig für «Der neue Sensor zählt ab» (nur bei Überlappung): von der Stunde nach der ersten Zeile des neuen bis zur
    Stunde des Wechsels (Rechenweg F2 «T1 < G ≤ laufende Stunde», E-1 aus a2) — und nie vor dem vorigen Wechsel des Felds
    (Korrekturrunde Lab-K F5, ``ansatz.Lage.vorige_grenze``: sonst überschriebe das Ansetzen die Zeit der Quelle davor)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    if not la.ueberlappung or la.t1 is None:
        return None
    von = la.t1 + _STUNDE
    vorige = getattr(la, "vorige_grenze", None)
    if vorige is not None:
        von = max(von, volle_stunde(vorige))
    return von, max(von, ab_ts_aus(row.erklaert_ts) - _STUNDE)


def _dienst(ha_svc):
    from backend.services.zuordnung_wechsel.abfrage import _dienst as d

    return d(ha_svc)


def _pruefe(la, row, zaehlt_ab: datetime) -> datetime:
    """Ist ``zaehlt_ab`` an dieser Lage zulässig? Returns die volle Stunde G, sonst ``ZaehltAbAbgelehnt``."""
    if la.t1 is None:
        raise ZaehltAbAbgelehnt(SATZ_NICHT_PRUEFBAR)
    b = bereich(la, row)
    if b is None:
        raise ZaehltAbAbgelehnt(SATZ_OHNE_UEBERLAPPUNG)
    g = volle_stunde(zaehlt_ab)
    if not b[0] <= g <= b[1]:
        raise ZaehltAbAbgelehnt(SATZ_BEREICH_EINE.format(von=_uhr(b[0])) if b[0] == b[1]
                                else SATZ_BEREICH.format(von=_uhr(b[0]), bis=_uhr(b[1])))
    return g


async def setze_zaehlt_ab(db, row, zaehlt_ab: datetime, *, jetzt: datetime, ha_svc=None) -> None:
    """«Der neue Sensor zählt ab» an einer Zeile «bleiben» (vor ihrem Ansetzen): prüft Überlappung und Bereich an derselben
    ``ansatz.lage`` wie die Prüf-Antwort und setzt ``ansatz = offen_schnitt``, ``ab_ts`` = Stunde + 1 h. Sonst
    ``ZaehltAbAbgelehnt``."""
    from backend.services.zuordnung_wechsel.ansatz import lage, wird_angesetzt

    if row.grund != GRUND_FORTSETZUNG:
        raise ZaehltAbAbgelehnt(SATZ_NUR_BLEIBEN)
    if not wird_angesetzt(row):
        raise ZaehltAbAbgelehnt(SATZ_NUR_HA)
    probe = pruef_zeile(row.anlage_id, row.sensor_key, row.vorher, row.nachher, ab_ts=row.ab_ts, erklaert_ts=row.erklaert_ts)
    g = _pruefe(await lage(db, probe, ha_svc=_dienst(ha_svc), jetzt=jetzt), probe, zaehlt_ab)
    row.ansatz, row.ab_ts = ANSATZ_OFFEN_SCHNITT, g + _STUNDE


def wartet_satz(code: Optional[str], vorher: Optional[dict], nachher: Optional[dict]) -> Optional[str]:
    from backend.services.zuordnung_wechsel.nachtrag import quelle_text

    if code is None or code not in SATZ_WARTET:
        return None
    return SATZ_WARTET[code].format(alt=quelle_text(vorher), neu=quelle_text(nachher))


def ergebnis_der_route(e: dict, sensor_key: str, label: str, vorher: Optional[dict],
                       nachher: Optional[dict]) -> tuple[list[dict], list[dict]]:
    """Ein Ergebnis von ``ansatz.setze_an`` für die Antwort einer Route: ``(Läufe, Wartende)`` — angesetzt mit Lauf ⇒ der Lauf
    mit ``art = ansetzen`` (die Fläche zeigt seinen Fortschritt), offen ⇒ der Wartegrund als Satz."""
    la = e.get("lage") or {}
    if e.get("angesetzt"):
        if not e.get("lauf"):
            return [], []
        return [{"lauf": e["lauf"], "sensor_key": sensor_key, "label": label, "tage_neu": len(la.get("tage_neu") or []),
                 "zaehlerstaende_geloescht": e.get("staende_geloescht", 0), "art": "ansetzen"}], []
    satz = wartet_satz(la.get("wartet"), vorher, nachher)
    return [], ([{"sensor_key": sensor_key, "label": label, "wartet": la["wartet"], "satz": satz}] if satz else [])


async def wartende(db, anlage_id: int, *, ha_svc=None, jetzt: Optional[datetime] = None) -> list[dict]:
    """Die offenen Wechsel «bleiben» der Anlage (``ansatz.ist_offen``) mit dem Grund, aus dem sie warten — dieselbe
    ``ansatz.lage`` wie der Stundenlauf (lesend). Eine Zeile, die jetzt ansetzbar wäre, steht ohne Satz nicht in der Liste
    (der nächste Stundenlauf setzt sie an)."""
    from sqlalchemy import select

    from backend.models.zuordnung_wechsel import ZuordnungWechsel
    from backend.services.zuordnung_wechsel.ansatz import ist_ha_wechsel, ist_offen, lage

    zeilen = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == anlage_id)
                               .order_by(ZuordnungWechsel.id))).scalars().all()
    svc = _dienst(ha_svc)
    out = []
    for row in zeilen:
        if not (ist_offen(row) and ist_ha_wechsel(row)):
            continue
        try:
            code = (await lage(db, row, ha_svc=svc, jetzt=jetzt or datetime.now())).wartet
        except Exception as e:  # noqa: BLE001 — eine Anzeige
            logger.warning("Wartender Wechsel %s nicht lesbar: %s: %s", row.id, type(e).__name__, e)
            continue
        satz = wartet_satz(code, row.vorher, row.nachher)
        if satz:
            out.append({"wechsel_id": row.id, "sensor_key": row.sensor_key, "wartet": code, "satz": satz})
    return out


def _stunden(g: datetime, jetzt: datetime) -> int:
    """Die Stundenzeilen ab G bis zur laufenden Stunde, die der Kanal neu liest (ein Zähler, keine Rechnung)."""
    return len(range(int(g.timestamp()), int(volle_stunde(jetzt).timestamp()), 3600))


async def _monate(db, anlage_id: int, la) -> list[tuple[int, int]]:
    from backend.services import verwerfen_vor_quellbeginn as vq

    abschluss = await vq.abschluss_monate(db, anlage_id)
    return sorted({(d.year, d.month) for d in la.tage if (d.year, d.month) in abschluss})


def _satz_art(la, gewaehlt: bool) -> str:
    """Der Satz zur Art des Ansatzes: «zählt beide» nur, wenn HA für den alten Sensor in der Stunde G eine Zeile führt (W3);
    nach der Wahl einer Stunde «Der neue Sensor zählt ab» ohne den Hinweis auf das Feld (W4)."""
    if la.art == ANSATZ_BEIDE:
        return SATZ_BEIDE if getattr(la, "alt_in_g", True) is not False else SATZ_BEIDE_NUR_NEU
    return SATZ_SCHNITT_GEWAEHLT if gewaehlt else SATZ_SCHNITT


def _saetze(la, alt: str, neu: str, umfang: dict[str, Any], monate: list[tuple[int, int]], *,
            gewaehlt: bool = False) -> list[str]:
    from backend.core.zahlenformat import fmt_anzahl
    from backend.services.verwerfen_vor_quellbeginn import _monate_text as _monate

    s = [SATZ_SEIT.format(neu=neu, seit=_uhr(la.t1))]
    s.append(_satz_art(la, gewaehlt).format(alt=alt, neu=neu, g=_uhr(la.g)))
    tage = umfang["tage"]
    if umfang["stunden"] or tage:
        s.append(SATZ_UMFANG.format(g=_uhr(la.g), stunden=fmt_anzahl(umfang["stunden"], "Stunde", "Stunden"))
                 + (SATZ_UMFANG_TAGE.format(tage=fmt_anzahl(tage, "Tag", "Tage")) if tage else SATZ_UMFANG_KEIN_TAG))
    else:
        s.append(SATZ_UMFANG_LAUFEND.format(g=_uhr(la.g)))
    if monate:
        s.append(SATZ_MONATE.format(liste=_monate(monate)))
    s.append(SATZ_LOESCHEN if la.alt_von_ha else SATZ_ALT_NICHT_IN_HA.format(alt=alt))
    return s


def _leer(wartet: Optional[str], satz: Optional[str]) -> dict[str, Any]:
    return {"wartet": wartet, "seit": None, "ueberlappung": None, "zaehlt_ab": None, "zaehlt_ab_vorgabe": None,
            "zaehlt_ab_frueheste": None, "zaehlt_ab_spaeteste": None, "stunden": None, "tage": None, "monate": [],
            "saetze": [satz] if satz else []}


async def angaben(db, anlage_id: int, sensor_key: str, vorher: Optional[dict], nachher: Optional[dict], *, ab_ts: datetime,
                  erklaert_ts: datetime, jetzt: datetime, zaehlt_ab: Optional[datetime] = None,
                  ha_svc=None) -> Optional[dict[str, Any]]:
    """Die Angaben der Prüf-Antwort zu «bleiben» (``None`` außer bei Home Assistant → Home Assistant). Mit ``zaehlt_ab`` die
    Vorschau an dieser Stunde (``ZaehltAbAbgelehnt``, wenn sie nicht zulässig ist)."""
    from backend.services.zuordnung_wechsel.ansatz import lage
    from backend.services.zuordnung_wechsel.nachtrag import quelle_text

    if not ist_ha_zu_ha(vorher, nachher):
        return None
    svc = _dienst(ha_svc)
    zeile = pruef_zeile(anlage_id, sensor_key, vorher, nachher, ab_ts=ab_ts, erklaert_ts=erklaert_ts)
    try:
        la = la_g = await lage(db, zeile, ha_svc=svc, jetzt=jetzt)
        if zaehlt_ab is not None:
            g = _pruefe(la, zeile, zaehlt_ab)
            la_g = await lage(db, pruef_zeile(anlage_id, sensor_key, vorher, nachher, ab_ts=ab_ts, erklaert_ts=erklaert_ts,
                                              zaehlt_ab=g), ha_svc=svc, jetzt=jetzt)
    except ZaehltAbAbgelehnt:
        raise
    except Exception as e:  # noqa: BLE001 — eine Anzeige: ohne sie fragt der Dialog wie bei jeder anderen Quelle
        logger.warning("Angaben «bleiben» %s nicht lesbar: %s: %s", sensor_key, type(e).__name__, e)
        return None
    if la_g.wartet == "kanal_nicht_ansetzbar":
        return _leer(la_g.wartet, SATZ_KANAL_WIE_BISHER.format(alt=quelle_text(vorher)))
    if la_g.wartet is not None:
        return _leer(la_g.wartet, wartet_satz(la_g.wartet, vorher, nachher))
    b = bereich(la, zeile)
    if b is not None and b[0] == b[1]:
        b = None                             # U3-K (LK-B3): eine einzige Stunde — kein Wahlfeld, der Satz nennt sie
    umfang = {"stunden": _stunden(la_g.g, jetzt), "tage": len(la_g.tage)}
    monate = await _monate(db, anlage_id, la_g)
    return {
        "wartet": None, "seit": _iso(la_g.t1), "ueberlappung": la_g.ueberlappung, "zaehlt_ab": _iso(la_g.g),
        "zaehlt_ab_vorgabe": _iso(la.g) if b else None, "zaehlt_ab_frueheste": _iso(b[0]) if b else None,
        "zaehlt_ab_spaeteste": _iso(b[1]) if b else None, **umfang, "monate": [f"{j}-{m:02d}" for j, m in monate],
        "saetze": _saetze(la_g, quelle_text(vorher), quelle_text(nachher), umfang, monate,
                          gewaehlt=zaehlt_ab is not None or (la_g.ueberlappung and b is None)),
    }


__all__ = ["FELD", "ZaehltAbAbgelehnt", "angaben", "bereich", "ergebnis_der_route", "ist_ha_zu_ha", "pruef_zeile",
           "setze_zaehlt_ab", "wartende", "wartet_satz"]
