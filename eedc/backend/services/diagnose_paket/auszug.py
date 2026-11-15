"""Auszug des Diagnose-Pakets v4 — eine Lese-Transaktion, ein ZIP-Mitglied je Tabelle (Bauplan §3.4, §3.9; G1, W-7 d).

* Verbindung ``Path(db_pfad).resolve().as_uri() + "?mode=ro"`` (K1: nie einen Pfad in eine URI kleben —
  ``settings.database_path`` hat die Form ``//data/eedc.db``, ``file://data/…`` scheitert mit ``invalid uri authority``).
* ``BEGIN`` … alle Tabellen … ``COMMIT`` (ein Stand; WAL hält Schreiber frei). Läuft im Thread (``asyncio.to_thread``).
* Spalten = Register ∩ ``PRAGMA table_info`` ohne ``raus`` — nie ein Bezeichner, den ``PRAGMA`` nicht kennt (SQLite liest einen
  unbekannten Bezeichner in Anführungszeichen als Text). Filterspalte fehlt ⇒ Teilfehler ``filterspalte_fehlt``, keine Abfrage.
* Werte so, wie ``sqlite3`` sie liefert (keine ``detect_types``); Klassen nach Register; ``bytes`` ⇒ Teilfehler der Tabelle.
* Mitglied ``tabellen/<t>.json``: ``{"spalten":[…],"zeilen":[`` ⏎ je Zeile eine Liste ⏎ ``]}``, ``fetchmany(5000)``.

Rohes SQL auf ``tages_energie_profil`` steht hier mit Grund in ``tests/test_tep_mengen_leser_waechter.py`` (der Auszug liest
Speicherwerte, er bildet keine Menge).
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend.services.diagnose_paket.bereinigung import Sammler, bereinige_log, filtere_json, schwaerze_email
from backend.services.diagnose_paket.register import NIE, PROFIL_DIAGNOSE, REGISTER, Spalte, Tabelle

BLOCK = 5000
#: ``IN (…)`` in Stücken (SQLite-Parametergrenze).
_IN_STUECK = 500


class Teilfehler(Exception):
    """Eine Tabelle kann nicht (vollständig) ausgezogen werden — das Paket kommt trotzdem, ``inhalt.json`` nennt den Grund."""


@dataclass
class TabellenStand:
    zeilen: int = 0
    status: str = "ok"
    grund: Optional[str] = None


@dataclass
class AuszugErgebnis:
    tabellen: dict = field(default_factory=dict)
    schema: dict = field(default_factory=dict)
    ohne_anlagenbezug: dict = field(default_factory=lambda: {"data_provenance_log": 0})
    #: nicht leere Freitext-Zellen + ``parameter.beschreibung`` (Inhaltsliste «Notizen»).
    notizen: int = 0
    #: ``activity_log``-Zeilen ohne Anlage (installationsweit, Q5).
    aktivitaet_ohne_anlage: int = 0
    sammler: Sammler = field(default_factory=Sammler)


def verbinde(db_pfad: str) -> sqlite3.Connection:
    """Nur lesend; ``db_pfad`` darf jede Form haben, die ``settings.database_path`` liefert (K1)."""
    uri = Path(db_pfad).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, isolation_level=None, timeout=30, check_same_thread=False)


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# ─── Schema ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _pragma(con: sqlite3.Connection) -> dict[str, list[str]]:
    namen = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {t: [r[1] for r in con.execute(f"PRAGMA table_info({_q(t)})")] for t in namen}


def _schema(db: dict[str, list[str]]) -> dict:
    """Namen, nie Werte: was die Datenbank hat und das Register nicht kennt, und umgekehrt."""
    bekannt = set(REGISTER) | NIE
    db_ohne = {"tabellen": sorted(t for t in db if t not in bekannt), "spalten": {}}
    reg_ohne = {"tabellen": sorted(t for t in REGISTER if t not in db), "spalten": {}}
    for t, tab in sorted(REGISTER.items()):
        if t not in db:
            continue
        mehr = [s for s in db[t] if s not in tab.spalten]
        weniger = [s for s in tab.spalten if s not in db[t]]
        if mehr:
            db_ohne["spalten"][t] = mehr
        if weniger:
            reg_ohne["spalten"][t] = weniger
    return {"db_ohne_register": db_ohne, "register_ohne_db": reg_ohne}


# ─── Filter ──────────────────────────────────────────────────────────────────────────────────────────────────────

class _Filter:
    """Filter je Filterart; Eltern-ID-Mengen werden einmal je Tabelle gelesen (Werte nur als Parameter)."""

    def __init__(self, con: sqlite3.Connection, db: dict[str, list[str]], anlage_id: int):
        self.con, self.db, self.anlage_id = con, db, anlage_id
        self._ids: dict[str, list] = {}

    def pruefe_spalte(self, tab: Tabelle, t: str) -> None:
        spalte = tab.filterspalte
        if spalte is not None and spalte not in self.db.get(t, []):
            raise Teilfehler("filterspalte_fehlt")

    def ids(self, t: str) -> list:
        """``id`` der Zeilen einer Elterntabelle, nach deren eigenem Filter."""
        if t not in self._ids:
            tab = REGISTER[t]
            if t not in self.db or "id" not in self.db[t]:
                raise Teilfehler(f"eltern {t}: fehlt")
            self.pruefe_spalte(tab, t)
            self._ids[t] = [r[0] for blk in self.abfragen(t, tab, [_q("id")]) for r in blk]
        return self._ids[t]

    def abfragen(self, t: str, tab: Tabelle, spalten_sql: list[str]) -> Iterable[list]:
        """Blöcke von Zeilen der Tabelle ``t`` nach ihrer Filterart."""
        kopf = f"SELECT {', '.join(spalten_sql)} FROM {_q(t)}"
        art = tab.filterart
        if art == "ganz" or art == "natural_key":
            yield from self._bloecke(kopf, ())
        elif art == "anlage":
            yield from self._bloecke(f"{kopf} WHERE {_q(tab.filterspalte)} = ?", (self.anlage_id,))
        elif art == "anlage_oder_null":
            yield from self._bloecke(f"{kopf} WHERE {_q('anlage_id')} = ? OR {_q('anlage_id')} IS NULL", (self.anlage_id,))
        elif art.startswith("ueber:"):
            ids = self.ids(tab.eltern)
            for i in range(0, len(ids), _IN_STUECK):
                stueck = ids[i:i + _IN_STUECK]
                yield from self._bloecke(
                    f"{kopf} WHERE {_q(tab.filterspalte)} IN ({', '.join('?' * len(stueck))})", tuple(stueck))
        else:
            raise Teilfehler(f"filterart {art} unbekannt")

    def _bloecke(self, sql: str, params: tuple) -> Iterable[list]:
        cur = self.con.execute(sql, params)
        while True:
            blk = cur.fetchmany(BLOCK)
            if not blk:
                return
            yield blk


def _gehoert_zur_anlage(row_pk_json: Any, anlage_id: int, geraete: set) -> Optional[bool]:
    """``data_provenance_log`` über den Natural Key: ``True``/``False``; ``None`` ⇒ ohne Anlagenbezug (gezählt)."""
    try:
        pk = json.loads(row_pk_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(pk, dict) or ("anlage_id" not in pk and "investition_id" not in pk):
        return None
    return pk.get("anlage_id") == anlage_id or pk.get("investition_id") in geraete


# ─── Zellen ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _runde(v: Any) -> Any:
    return round(v, 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _zellen_wandler(t: str, spalten: list[str], koordinaten: dict, erg: AuszugErgebnis) -> list[tuple[int, Callable]]:
    """(Index, Wandler) je Spalte, die nicht unverändert hinausgeht."""
    from backend.services.pvgis_aktualitaet import koordinate_gleich

    out: list[tuple[int, Callable]] = []
    for i, name in enumerate(spalten):
        s: Spalte = REGISTER[t].spalten[name]
        ort = f"{t}.{name}"
        if s.json:
            out.append((i, lambda v, s=s, ort=ort: filtere_json(s, v, erg.sammler, ort)))
        elif s.klasse == "gerundet" and t == "pvgis_prognosen" and koordinaten.get(name) is not None:
            anl = koordinaten[name]
            out.append((i, lambda v, anl=anl: round(anl, 2) if isinstance(v, (int, float)) and koordinate_gleich(anl, v)
                        else _runde(v)))
        elif s.klasse == "gerundet":
            out.append((i, _runde))
        elif s.klasse == "bereinigt:log":
            out.append((i, lambda v: bereinige_log(v) if isinstance(v, str) else v))
        elif s.klasse == "bereinigt:email":
            out.append((i, lambda v: schwaerze_email(v) if isinstance(v, str) else v))
    return out


def _zaehle_notizen(t: str, spalten: list[str], zeile: tuple, erg: AuszugErgebnis) -> None:
    for i, name in enumerate(spalten):
        s = REGISTER[t].spalten[name]
        if s.freitext and isinstance(zeile[i], str) and zeile[i].strip():
            erg.notizen += 1
    if t == "investitionen" and "parameter" in spalten:
        try:
            p = json.loads(zeile[spalten.index("parameter")] or "null")
        except (TypeError, ValueError):
            return
        if isinstance(p, dict) and isinstance(p.get("beschreibung"), str) and p["beschreibung"].strip():
            erg.notizen += 1


# ─── Tabelle → Mitglied ──────────────────────────────────────────────────────────────────────────────────────────

def _zeilen(f: _Filter, t: str, spalten: list[str], koordinaten: dict, erg: AuszugErgebnis) -> Iterable[list]:
    tab = REGISTER[t]
    wandler = _zellen_wandler(t, spalten, koordinaten, erg)
    sql_spalten = [_q(s) for s in spalten]
    pk_i = spalten.index("row_pk_json") if tab.filterart == "natural_key" else None
    geraete = set(f.ids("investitionen")) if pk_i is not None else set()
    for blk in f.abfragen(t, tab, sql_spalten):
        for roh in blk:
            if pk_i is not None:
                bezug = _gehoert_zur_anlage(roh[pk_i], f.anlage_id, geraete)
                if bezug is None:
                    erg.ohne_anlagenbezug[t] = erg.ohne_anlagenbezug.get(t, 0) + 1
                if not bezug:
                    continue
            for i, v in enumerate(roh):
                if isinstance(v, bytes):
                    raise Teilfehler(f"BLOB in {spalten[i]}")
            if t == "activity_log" and roh[spalten.index("anlage_id")] is None:
                erg.aktivitaet_ohne_anlage += 1
            _zaehle_notizen(t, spalten, roh, erg)
            zeile = list(roh)
            for i, fn in wandler:
                zeile[i] = fn(zeile[i])
            yield zeile


def _schreibe_tabelle(zf: zipfile.ZipFile, f: _Filter, t: str, spalten: list[str], koordinaten: dict,
                      erg: AuszugErgebnis) -> TabellenStand:
    stand = TabellenStand()
    f.pruefe_spalte(REGISTER[t], t)
    with zf.open(f"tabellen/{t}.json", "w", force_zip64=True) as m:
        m.write(('{"spalten":' + json.dumps(spalten, ensure_ascii=False, separators=(",", ":")) + ',"zeilen":[').encode())
        try:
            for zeile in _zeilen(f, t, spalten, koordinaten, erg):
                m.write((",\n" if stand.zeilen else "\n").encode())
                m.write(json.dumps(zeile, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                stand.zeilen += 1
        finally:
            m.write(b"\n]}")
    return stand


def _koordinaten(con: sqlite3.Connection, db: dict, anlage_id: int) -> dict:
    """Die ungerundeten Koordinaten der Anlage (Prognose-Koordinate am selben Ort ⇒ deren gerundeter Wert, Q1)."""
    spalten = [s for s in ("latitude", "longitude") if s in db.get("anlagen", [])]
    if not spalten or "id" not in db.get("anlagen", []):
        return {}
    r = con.execute(f"SELECT {', '.join(map(_q, spalten))} FROM anlagen WHERE id = ?", (anlage_id,)).fetchone()
    return dict(zip(spalten, r)) if r else {}


def auszug(db_pfad: str, anlage_id: int, zf: zipfile.ZipFile, *, profil: str = PROFIL_DIAGNOSE) -> AuszugErgebnis:
    """Alle Register-Tabellen der Anlage in ``zf`` (alphabetisch) — eine Lese-Transaktion. Ein Teilfehler hält die übrigen
    Tabellen nicht auf."""
    if profil != PROFIL_DIAGNOSE:
        raise ValueError(f"Profil {profil!r} gibt es nicht")
    erg = AuszugErgebnis()
    con = verbinde(db_pfad)
    try:
        con.execute("BEGIN")
        db = _pragma(con)
        erg.schema = _schema(db)
        koordinaten = _koordinaten(con, db, anlage_id)
        f = _Filter(con, db, anlage_id)
        for t in sorted(REGISTER):
            if t not in db:
                erg.tabellen[t] = TabellenStand(status="fehler", grund="tabelle_fehlt")
                continue
            spalten = [s for s, sp in REGISTER[t].spalten.items() if sp.klasse != "raus" and s in db[t]]
            try:
                erg.tabellen[t] = _schreibe_tabelle(zf, f, t, spalten, koordinaten, erg)
            except Teilfehler as e:
                erg.tabellen[t] = TabellenStand(status="fehler", grund=str(e))
            except Exception as e:  # noqa: BLE001 — Teilfehler-Fang (G5): das Paket kommt, inhalt.json nennt den Grund
                erg.tabellen[t] = TabellenStand(status="fehler", grund=f"{type(e).__name__}: {bereinige_log(str(e))}")
        con.execute("COMMIT")
    finally:
        con.close()
    return erg
