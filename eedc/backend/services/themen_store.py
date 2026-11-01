"""Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.1) — der Store der Themen je Gerät: reine Funktionen auf `sensor_mapping`.

Ein **Thema** ist eine Überschrift mit **Einträgen**; ein Eintrag ist eine frei gewählte HA-Entität bzw. ein
MQTT-Topic, deren Wert eedc **wie geliefert** zeigt (Kachel im Schaubild, Karte «Themen»). Es gibt nur Geräte mit
Block «Überblick» (`utils/investition_filter.py:UEBERBLICK_TYPEN`).

⛔ **Ein Store** (Bauplan §0): die Definition steht in ``sensor_mapping["investitionen"][<id>]["themen"]``, die Quelle
eines Eintrags **nur** in ``sensor_mapping["quellen"]["inv_thema_<inv>_<e>"]``. Kein Spiegel, kein Registry-Feld,
kein Kanal, keine Mitschrift.

```json
"investitionen": {"7": {"themen": {"naechste_id": 4, "liste": [
  {"id": "t1", "name": "Fahrzeugzustand", "eintraege": [{"id": "e2", "label": "Türen"}]}]}}}
```

* Kennungen ``t<n>``/``e<n>`` aus **einem** monotonen Zähler ``naechste_id`` je Gerät — nie ``max()+1``: eine
  gelöschte Kennung kommt nicht wieder, sonst erbte ein neuer Eintrag die alte Quelle (Ü10).
* Name ≤ 40, Label ≤ 60 Zeichen, getrimmt; leer nach dem Trim ist ein Fehler.
* Alle Schreibfunktionen arbeiten **in-place** auf dem übergebenen Mapping; ``flag_modified`` und Commit macht der
  Aufrufer. Entfernen liefert die Feld-IDs zurück — der Aufrufer löscht ``quellen[field_id]`` samt Gateway-Zeile.
"""

from __future__ import annotations

import re
from typing import Optional, TypedDict

from backend.core.field_definitions import THEMA_KEY_PRAEFIX

__all__ = [
    "THEMA_KEY_PRAEFIX", "FELD_ID_PRAEFIX", "NAME_MAX", "LABEL_MAX",
    "ThemenFehler", "ThemaNichtGefunden",
    "lade_themen", "thema_anlegen", "thema_umbenennen", "thema_verschieben", "thema_entfernen",
    "eintrag_anlegen", "eintrag_umbenennen", "eintrag_verschieben", "eintrag_entfernen",
    "finde_eintrag", "eintrag_feld_id", "eintrag_von_feld_id", "eintrag_topic_key", "ist_vorgabe_label",
    "eintrag_label_setzen_wenn_vorgabe", "KEIN_WERT", "wert_text",
]

#: Präfix der Feld-ID eines Eintrags in ``quellen`` (``inv_thema_<inv>_<e>``) — steht auch in
#: `datenquellen_mapping_sync.INV_FELD_PRAEFIXE` (Geräte-Löschen, JSON-Import-Remap).
FELD_ID_PRAEFIX = "inv_thema_"
NAME_MAX = 40
LABEL_MAX = 60

#: Ein State, der keinen Wert trägt — der Eintrag fehlt dann in Live-Antwort, Kachel und Karte und steht in der
#: Fläche amber (Bauplan §0 «Nur mit Wert»). Eine Regel für HA und MQTT (dort ist «leer» im Cache ein Wert, für die
#: Anzeige eines Themas aber keiner).
KEIN_WERT: frozenset[str] = frozenset({"", "unknown", "unavailable"})

_STORE_KEY = "themen"
_VORGABE_LABEL = re.compile(r"^Eintrag \d+$")


class ThemaEintrag(TypedDict):
    id: str
    label: str


class Thema(TypedDict):
    id: str
    name: str
    eintraege: list[ThemaEintrag]


class Themen(TypedDict):
    naechste_id: int
    liste: list[Thema]


class ThemenFehler(ValueError):
    """Eingabe ungültig (Name/Label leer oder zu lang) — die Route antwortet 400."""


class ThemaNichtGefunden(LookupError):
    """Thema oder Eintrag gibt es an diesem Gerät nicht — die Route antwortet 404."""


# ── Feld-ID und Topic-Key ─────────────────────────────────────────────────────

def eintrag_feld_id(inv_id, e_id: str) -> str:
    """``(7, "e3")`` → ``inv_thema_7_e3`` — der Schlüssel der Quelle in ``sensor_mapping["quellen"]``."""
    return f"{FELD_ID_PRAEFIX}{inv_id}_{e_id}"


def eintrag_von_feld_id(field_id) -> Optional[tuple[int, str]]:
    """``inv_thema_7_e3`` → ``(7, "e3")``; jede andere Form → ``None``."""
    if not isinstance(field_id, str) or not field_id.startswith(FELD_ID_PRAEFIX):
        return None
    inv_id, sep, e_id = field_id[len(FELD_ID_PRAEFIX):].partition("_")
    if not sep or not inv_id.isdigit() or not re.fullmatch(r"e\d+", e_id):
        return None
    return int(inv_id), e_id


def eintrag_topic_key(e_id: str) -> str:
    """``"e3"`` → ``"thema_e3"`` — der Live-Key des Eintrags im MQTT-Inbound (`…/live/inv/<id>_<slug>/thema_e3`)."""
    return f"{THEMA_KEY_PRAEFIX}{e_id}"


def wert_text(roh) -> Optional[str]:
    """Der Anzeige-Text eines rohen States/Payloads — getrimmt; ``None`` ohne Wert (`KEIN_WERT`)."""
    if roh is None:
        return None
    text = str(roh).strip()
    return None if text in KEIN_WERT else text


def ist_vorgabe_label(label: str) -> bool:
    """Trägt der Eintrag noch die Vorgabe «Eintrag n»? — dann übernimmt der erste HA-Pick den ``friendly_name``."""
    return bool(_VORGABE_LABEL.match(label or ""))


# ── Lesen ─────────────────────────────────────────────────────────────────────

def _knoten(mapping, inv_id, *, anlegen: bool) -> Optional[dict]:
    """Der Teilbaum ``investitionen[<id>]["themen"]`` — angelegt nur, wenn geschrieben wird."""
    if not isinstance(mapping, dict):
        return None
    invs = mapping.get("investitionen")
    if not isinstance(invs, dict):
        if not anlegen:
            return None
        invs = mapping["investitionen"] = {}
    eintrag = invs.get(str(inv_id))
    if not isinstance(eintrag, dict):
        if not anlegen:
            return None
        eintrag = invs[str(inv_id)] = {}
    knoten = eintrag.get(_STORE_KEY)
    if not isinstance(knoten, dict) or not isinstance(knoten.get("liste"), list):
        if not anlegen:
            return None
        knoten = eintrag[_STORE_KEY] = {"naechste_id": 1, "liste": []}
    if not isinstance(knoten.get("naechste_id"), int) or knoten["naechste_id"] < 1:
        knoten["naechste_id"] = _zaehler_aus_bestand(knoten["liste"])
    return knoten


def _zaehler_aus_bestand(liste: list) -> int:
    """Ein fehlender Zähler (von Hand gepflegte Datei) — einmalig über alle vergebenen Kennungen, danach monoton."""
    nummern = [0]
    for thema in liste:
        if isinstance(thema, dict):
            nummern.append(_nummer(thema.get("id")))
            nummern += [_nummer(e.get("id")) for e in thema.get("eintraege") or [] if isinstance(e, dict)]
    return max(nummern) + 1


def _nummer(kennung) -> int:
    m = re.fullmatch(r"[te](\d+)", str(kennung or ""))
    return int(m.group(1)) if m else 0


def lade_themen(mapping, inv_id) -> Themen:
    """Die Themen eines Geräts in Store-Reihenfolge — eine Kopie; ohne Themen ``{"naechste_id": 1, "liste": []}``.

    Einträge ohne gültige Kennung fallen still heraus (eine von Hand beschädigte Datei bricht die Fläche nicht).
    """
    knoten = _knoten(mapping, inv_id, anlegen=False)
    if knoten is None:
        return {"naechste_id": 1, "liste": []}
    liste: list[Thema] = []
    for thema in knoten["liste"]:
        if not isinstance(thema, dict) or not isinstance(thema.get("id"), str):
            continue
        eintraege: list[ThemaEintrag] = [
            {"id": e["id"], "label": str(e.get("label") or "")}
            for e in thema.get("eintraege") or []
            if isinstance(e, dict) and isinstance(e.get("id"), str)
        ]
        liste.append({"id": thema["id"], "name": str(thema.get("name") or ""), "eintraege": eintraege})
    return {"naechste_id": knoten["naechste_id"], "liste": liste}


def finde_eintrag(mapping, inv_id, e_id: str) -> Optional[tuple[Thema, ThemaEintrag]]:
    """``(Thema, Eintrag)`` zu einer Eintrags-Kennung dieses Geräts — sonst ``None``."""
    for thema in lade_themen(mapping, inv_id)["liste"]:
        for eintrag in thema["eintraege"]:
            if eintrag["id"] == e_id:
                return thema, eintrag
    return None


# ── Schreiben ─────────────────────────────────────────────────────────────────

def _text(wert, *, maximal: int, vorgabe: str, was: str) -> str:
    if wert is None:
        return vorgabe
    text = str(wert).strip()
    if not text:
        raise ThemenFehler(f"{was} darf nicht leer sein.")
    if len(text) > maximal:
        raise ThemenFehler(f"{was} ist zu lang (höchstens {maximal} Zeichen).")
    return text


def _neue_kennung(knoten: dict, art: str) -> str:
    nummer = knoten["naechste_id"]
    knoten["naechste_id"] = nummer + 1
    return f"{art}{nummer}"


def _thema(knoten: dict, t_id: str) -> dict:
    for thema in knoten["liste"]:
        if isinstance(thema, dict) and thema.get("id") == t_id:
            if not isinstance(thema.get("eintraege"), list):
                thema["eintraege"] = []
            return thema
    raise ThemaNichtGefunden("Thema nicht gefunden")


def _schreibknoten(mapping, inv_id) -> dict:
    knoten = _knoten(mapping, inv_id, anlegen=True)
    if knoten is None:  # pragma: no cover — nur bei einem Mapping, das kein dict ist
        raise ThemenFehler("Zuordnung der Anlage ist beschädigt.")
    return knoten


def _verschiebe(liste: list, element: dict, position: int) -> None:
    """``element`` an ``position`` (0-basiert, auf die Liste geklemmt)."""
    liste.remove(element)
    ziel = max(0, min(int(position), len(liste)))
    liste.insert(ziel, element)


def thema_anlegen(mapping, inv_id, name: Optional[str] = None) -> Thema:
    """Neues Thema am Ende; ohne Namen «Thema n» (n = Anzahl danach)."""
    knoten = _schreibknoten(mapping, inv_id)
    text = _text(name, maximal=NAME_MAX, vorgabe=f"Thema {len(knoten['liste']) + 1}", was="Der Name")
    thema = {"id": _neue_kennung(knoten, "t"), "name": text, "eintraege": []}
    knoten["liste"].append(thema)
    return thema


def thema_umbenennen(mapping, inv_id, t_id: str, name: str) -> Thema:
    thema = _thema(_schreibknoten(mapping, inv_id), t_id)
    thema["name"] = _text(name, maximal=NAME_MAX, vorgabe="", was="Der Name")
    return thema


def thema_verschieben(mapping, inv_id, t_id: str, position: int) -> Thema:
    knoten = _schreibknoten(mapping, inv_id)
    thema = _thema(knoten, t_id)
    _verschiebe(knoten["liste"], thema, position)
    return thema


def thema_entfernen(mapping, inv_id, t_id: str) -> tuple[Thema, list[str]]:
    """Entfernt das Thema samt Einträgen — ``(Thema, Feld-IDs seiner Einträge)``."""
    knoten = _schreibknoten(mapping, inv_id)
    thema = _thema(knoten, t_id)
    knoten["liste"].remove(thema)
    return thema, [eintrag_feld_id(inv_id, e["id"]) for e in thema["eintraege"] if isinstance(e, dict)]


def _eintrag(thema: dict, e_id: str) -> dict:
    for eintrag in thema["eintraege"]:
        if isinstance(eintrag, dict) and eintrag.get("id") == e_id:
            return eintrag
    raise ThemaNichtGefunden("Eintrag nicht gefunden")


def eintrag_anlegen(mapping, inv_id, t_id: str, label: Optional[str] = None) -> ThemaEintrag:
    """Neuer Eintrag ohne Quelle am Ende des Themas; ohne Label «Eintrag n» (n = Anzahl im Thema danach)."""
    knoten = _schreibknoten(mapping, inv_id)
    thema = _thema(knoten, t_id)
    text = _text(label, maximal=LABEL_MAX, vorgabe=f"Eintrag {len(thema['eintraege']) + 1}", was="Das Label")
    eintrag = {"id": _neue_kennung(knoten, "e"), "label": text}
    thema["eintraege"].append(eintrag)
    return eintrag


def eintrag_umbenennen(mapping, inv_id, t_id: str, e_id: str, label: str) -> ThemaEintrag:
    eintrag = _eintrag(_thema(_schreibknoten(mapping, inv_id), t_id), e_id)
    eintrag["label"] = _text(label, maximal=LABEL_MAX, vorgabe="", was="Das Label")
    return eintrag


def eintrag_verschieben(mapping, inv_id, t_id: str, e_id: str, position: int) -> ThemaEintrag:
    thema = _thema(_schreibknoten(mapping, inv_id), t_id)
    eintrag = _eintrag(thema, e_id)
    _verschiebe(thema["eintraege"], eintrag, position)
    return eintrag


def eintrag_entfernen(mapping, inv_id, t_id: str, e_id: str) -> tuple[ThemaEintrag, str]:
    """Entfernt den Eintrag — ``(Eintrag, Feld-ID)``; die Quelle räumt der Aufrufer."""
    thema = _thema(_schreibknoten(mapping, inv_id), t_id)
    eintrag = _eintrag(thema, e_id)
    thema["eintraege"].remove(eintrag)
    return eintrag, eintrag_feld_id(inv_id, e_id)


def eintrag_label_setzen_wenn_vorgabe(mapping, inv_id, e_id: str, label: Optional[str]) -> bool:
    """Beim ersten HA-Pick: steht noch die Vorgabe «Eintrag n», übernimmt der Eintrag ``label`` (``friendly_name``).

    Gekürzt auf ``LABEL_MAX``; ohne Label oder mit eigenem Label des Anwenders ändert sich nichts. ``True`` bei
    Änderung.
    """
    text = (label or "").strip()[:LABEL_MAX].strip()
    knoten = _knoten(mapping, inv_id, anlegen=False)
    if not text or knoten is None:
        return False
    for thema in knoten["liste"]:
        for eintrag in (thema.get("eintraege") or []) if isinstance(thema, dict) else []:
            if isinstance(eintrag, dict) and eintrag.get("id") == e_id and ist_vorgabe_label(eintrag.get("label")):
                eintrag["label"] = text
                return True
    return False
