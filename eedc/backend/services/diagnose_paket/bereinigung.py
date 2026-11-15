"""Bereinigung des Diagnose-Pakets v4 — Log-Zeilen, E-Mail, Struktur, Blatt-Regel und Marken (Bauplan §3.5, W-7 b/c).

* ``bereinige_log(text)`` — v3-Regexe plus Anführungszeichen zwischen Schlüssel und Trennzeichen, Werte in Anführungszeichen
  ganz, ``pw=``/``pw:``, ``credential``, E-Mail ⇒ ``<e-mail>``. Bekannt: überschwärzt auch («Der Hashwert stimmt» → «Der
  <geschwärzt>»).
* ``schwaerze_email(text)`` — nur das E-Mail-Muster (``data_provenance_log.writer``, ``writer`` in ``source_provenance``).
* ``bereinige_struktur(obj)`` — rekursiv: Schlüssel auf ``SCHLUESSELWOERTER`` ⇒ ``"<geschwärzt>"``; Text ⇒ ``bereinige_log``.
* ``filtere_json(spalte, zelle, sammler, ort)`` — für **jede** JSON-Zelle (K2, K3): SQL-NULL und Zahl bleiben; unlesbar oder
  falscher Obertyp ⇒ ``⟨ersetzt:unlesbar:<länge>⟩`` (nie Rohtext); Oberschlüssel-Allowlist; Blatt-Regel; Schlüsselwörter;
  Text, der nur über ``text_unter``/``"*"`` stehen bleibt, immer durch ``bereinige_log`` (Maßgabe Master 14.11.); unverändert ⇒
  gespeicherter Text bitgleich, verändert ⇒ ``json.dumps(obj)``. Eine Marke bleibt stehen ⇒ der Filter ist idempotent.

Importe nur stdlib + Register (werkzeugtauglich wie ``register.py``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.services.diagnose_paket.register import Spalte, ist_schluesselwort

GESCHWAERZT = "<geschwärzt>"
MARKE_RE = re.compile(r"⟨ersetzt:(?:str|list|dict|zahl|unlesbar):\d+⟩")

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")
_GEHEIM = re.compile(
    r"(?i)\b\w*(?:bearer|token|passw|secret|api_?key|apikey|authorization|kundennummer|hash|credential)\w*"
    r"\\?[\"']?(?:\s*[:=]\s*|\s+)(?:\"[^\"]*\"|'[^']*'|\S+)")
_PW = re.compile(r"(?i)\bpw\\?[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|\S+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def schwaerze_email(text: str) -> str:
    return _EMAIL.sub("<e-mail>", text)


def bereinige_log(text: str) -> str:
    """Log-/Aktivitäts-Text ohne URLs, Token-/Passwort-Muster und E-Mail-Adressen (W-7) — eine Remote-HA-URL kann
    Zugangsdaten tragen, eine SQLAlchemy-Fehlermeldung die Parameter einer Zeile."""
    text = _URL.sub("<url>", text)
    text = _BEARER.sub(GESCHWAERZT, text)
    text = _GEHEIM.sub(GESCHWAERZT, text)
    text = _PW.sub(GESCHWAERZT, text)
    return schwaerze_email(text)


def bereinige_struktur(obj: Any) -> Any:
    """Rekursiv: Schlüssel auf ``SCHLUESSELWOERTER`` ⇒ ``"<geschwärzt>"``; jeder Text ⇒ ``bereinige_log`` (Marken bleiben)."""
    if isinstance(obj, dict):
        return {k: (GESCHWAERZT if ist_schluesselwort(str(k)) else bereinige_struktur(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [bereinige_struktur(v) for v in obj]
    if isinstance(obj, str) and not MARKE_RE.fullmatch(obj):
        return bereinige_log(obj)
    return obj


@dataclass
class Sammler:
    """Was der Filter je Spalte (``"<tabelle>.<spalte>"``) gesehen hat — Namen, nie Werte (``lage.schema``)."""
    json_unbekannt: dict = field(default_factory=dict)
    json_unlesbar: dict = field(default_factory=dict)
    #: Zellen, deren Text unter ``text_unter``/``"*"`` die Bereinigung geändert hat (S1-Gate: an Kopien und Skala 0).
    text_bereinigt: dict = field(default_factory=dict)

    def unbekannt(self, ort: str, name: str) -> None:
        self.json_unbekannt.setdefault(ort, set()).add(name)

    def zaehle(self, wo: dict, ort: str) -> None:
        wo[ort] = wo.get(ort, 0) + 1


class _Paare(list):
    """Ein JSON-Objekt als Liste seiner Paare (``object_pairs_hook``) — doppelte Schlüssel bleiben sichtbar."""


def _marke(art: str, laenge: int) -> str:
    return f"⟨ersetzt:{art}:{laenge}⟩"


def _ist_marke(v: Any) -> bool:
    return isinstance(v, str) and MARKE_RE.fullmatch(v) is not None


class _Lauf:
    """Ein Durchlauf der Blatt-Regel über eine Zelle; ``geaendert`` ⇒ neu serialisieren."""

    def __init__(self, spalte: Spalte, sammler: Optional[Sammler], ort: str):
        self.s, self.sammler, self.ort = spalte, sammler, ort
        self.geaendert = False
        self.bereinigt = False
        self.alle_text = "*" in spalte.text_schluessel

    def _unbekannt(self, name: Optional[str]) -> None:
        if self.sammler is not None:
            self.sammler.unbekannt(self.ort, name if name is not None else "(wurzel)")

    def text(self, wert: str, schluessel: Optional[str], unter: bool) -> str:
        if _ist_marke(wert):
            return wert
        dynamisch = unter or self.alle_text
        if not (dynamisch or (schluessel is not None and schluessel in self.s.text_schluessel)):
            self._unbekannt(schluessel)
            self.geaendert = True
            return _marke("str", len(wert))
        neu = wert
        if dynamisch:
            neu = bereinige_log(wert)   # Maßgabe Master: dynamische Schlüssel sind nicht je Name geprüft
            self.bereinigt = self.bereinigt or neu != wert
        if self.s.klasse == "bereinigt:struktur":
            neu = bereinige_log(neu)
        elif self.s.klasse == "bereinigt:email" and schluessel == "writer":
            neu = schwaerze_email(neu)
        self.geaendert = self.geaendert or neu != wert
        return neu

    def wert(self, v: Any, schluessel: Optional[str], unter: bool) -> Any:
        if isinstance(v, _Paare):
            return self.objekt(v, unter)
        if isinstance(v, list):
            return [self.wert(x, schluessel, unter) for x in v]
        if isinstance(v, str):
            return self.text(v, schluessel, unter)
        return v

    def objekt(self, paare: _Paare, unter: bool, oberste: bool = False) -> dict:
        if len({k for k, _ in paare}) != len(paare):
            self.geaendert = True          # doppelte Schlüssel: jedes Paar geprüft, die Zelle neu serialisiert
        out: dict = {}
        for k, v in paare:
            if ist_schluesselwort(k):
                self.geaendert = self.geaendert or v != GESCHWAERZT
                out[k] = GESCHWAERZT
            elif oberste and self.s.oberschluessel is not None and k not in self.s.oberschluessel:
                out[k] = self.fremd(k, v)
            else:
                out[k] = self.wert(v, k, unter or k in self.s.text_unter)
        return out

    def fremd(self, k: str, v: Any) -> Any:
        """Oberschlüssel außerhalb der Allowlist: Wahrheitswert, ``null`` und Marken bleiben; eine Zahl nur mit
        ``fremde_zahlen_bleiben`` (``investitionen.parameter``); sonst Marke mit Typ und Länge (Zahl: Zeichen ihrer Form)."""
        if v is None or isinstance(v, bool) or _ist_marke(v):
            return v
        if isinstance(v, (int, float)) and self.s.fremde_zahlen_bleiben:
            return v
        self._unbekannt(k)
        self.geaendert = True
        if isinstance(v, (int, float)):
            return _marke("zahl", len(repr(v)))
        art = "str" if isinstance(v, str) else ("dict" if isinstance(v, _Paare) else "list")
        return _marke(art, len(v))


def _lesen(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_Paare)


def filtere_json(spalte: Spalte, zelle: Any, sammler: Optional[Sammler] = None, ort: str = "") -> Any:
    """Eine JSON-Zelle nach Register (Bauplan §3.5 Nr 1–5). ``zelle`` so, wie ``sqlite3`` sie liefert."""
    if zelle is None or isinstance(zelle, (bool, int, float)):
        return zelle
    try:
        roh = zelle.decode("utf-8") if isinstance(zelle, bytes) else str(zelle)
        obj = _lesen(roh)
    except (ValueError, UnicodeDecodeError):
        obj, roh = _Unlesbar, str(zelle)
    braucht_objekt = spalte.oberschluessel is not None
    if obj is _Unlesbar or (braucht_objekt and obj is not None and not isinstance(obj, _Paare)):
        if sammler is not None:
            sammler.zaehle(sammler.json_unlesbar, ort)
        return _marke("unlesbar", len(roh))
    lauf = _Lauf(spalte, sammler, ort)
    if isinstance(obj, _Paare):
        neu = lauf.objekt(obj, False, oberste=True)
    else:
        neu = lauf.wert(obj, None, False)
    if lauf.bereinigt and sammler is not None:
        sammler.zaehle(sammler.text_bereinigt, ort)
    if not lauf.geaendert:
        return zelle
    return json.dumps(neu)


class _UnlesbarTyp:
    pass


_Unlesbar = _UnlesbarTyp()
