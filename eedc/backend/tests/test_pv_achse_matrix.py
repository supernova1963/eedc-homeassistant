"""Abnahme-Matrix der PV-Achse — eine Probe für alle Zuordnungsformen, Datenstände, Sichten.

Baustein (Formen, Seed, Schreibwege, Messfunktionen, Soll-Regel): ``pv_achse_matrix.py``.

**Was eine Zelle ist.** Form (F01–F15, 22 Ausprägungen) × Weg × Invariante (I1–I6). Weg ist
entweder ein **Datenstand** — ``HA`` (HA-Statistik + Tageszeilen) oder ``SA`` (Standalone,
Snapshot-Pfad) — für den Tag und den laufenden Monat, oder ein **Schreibweg** des
abgeschlossenen Monats — ``S1`` „Aus HA laden", ``S2`` HA-Statistik-Sammelimport, ``S3``
Handeingabe ohne HA. Jede Zelle prüft ALLE Sichten ihrer Invariante; was sie zählt, steht in
``bewerte``.

**Rote Zellen gegen HEAD** stehen in ``BEKANNT`` — mit der Menge der roten Sichten, dem Grund
und der Zuordnung (N-623 · N-624 · HA-Bauform-Rest mit Verweis · KANDIDAT). Die Zelle läuft dann
als ``xfail(strict=True, raises=BekannterMangel)``: Sie ist nur „erwartet rot", wenn GENAU diese
Sichten rot sind. Heilt ein Bau eine davon, wird die Zelle ROT (XPASS strict bzw. eine
``AssertionError``, die nicht ``BekannterMangel`` ist) und zwingt die Markierung weg; kippt eine
weitere Sicht, ebenso. **„Soll unklar"** (``SOLL_UNKLAR``) heißt: die Regel legt das Soll dieser
Sicht in dieser Form nicht eindeutig fest — die Sicht wird gemessen und gezeigt, aber nicht
bewertet; ``test_soll_unklar_ist_noch_eine_messung`` hält die Liste ehrlich.

**Schwesterdateien** — die Einzelproben, die diese Matrix nicht ersetzt, sondern umfasst:
``test_n587_pv_strings_vor_anlagenzaehler.py`` (laufender Monat, ohne Tageszeilen),
``test_n611_anlagenwert_alle_pv_quellen.py``, ``test_n613_pv_strings_abtretung_je_monat.py``,
``test_n621_bkw_anteil_am_anlagenwert.py``, ``test_n622_ha_monatswerte_pv_gesamtzaehler.py``,
``test_bkw_pv_achse_laufender_monat.py``, ``test_n536_bkw_traegt_nur_den_rest.py``.

**Laufzeit.** Eine Form kostet rund 5 s (HA-Teil ≈ 2 s mit S1+S2 auf einer kopierten
Datenbank, Standalone-Teil ≈ 3 s — der Snapshot-Pfad liest 25 Stände je Zähler und Tag). Die
Messung wird je Lauf und Form-Teil EINMAL gemacht und von allen Zellen geteilt, auch über die
xdist-Prozesse hinweg (``_messung``); die Zellen stehen form-weise hintereinander.

**Wie eine Zelle zu lesen ist.** I1 vergleicht jede Sicht mit einer Referenz (abgeschlossener
Monat: die Monats-Fakten; laufender Monat: Cockpit → Monat) — eine rote I1-Sicht heißt „weicht
von der Referenz ab", wer von beiden falsch liegt, sagt I3. I2 vergleicht Zeitebenen (Σ Tage,
vor/nach dem Abschluss), I3 das Soll der Regel (``pv_achse_matrix.soll_tag``/``soll_monat``),
I4 die Geräte, I5 Eigenverbrauch und Autarkie gegen die PV derselben Sicht, I6 „keine Sicht
nennt keine PV, wo eine andere eine nennt".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

try:
    import fcntl
except ImportError:  # pragma: no cover — Windows: dann misst jeder Prozess selbst
    fcntl = None  # type: ignore[assignment]

from backend.tests import pv_achse_matrix as mx

# ── Messung je Lauf einmal ──────────────────────────────────────────────────
#
# Eine Form kostet rund 5 s; ihre 30 Zellen teilen eine Messung. Unter `-n 3` verteilt xdist
# die Zellen einer Form auf mehrere Prozesse — ohne gemeinsamen Speicher maß jeder Prozess
# dieselbe Form noch einmal (gemessen 04.10.: 231 s CPU statt rund 118 s). Deshalb legt der
# erste Prozess die Messung als JSON neben die Temp-Ordner der Prozesse
# (`tmp_path_factory.getbasetemp().parent` ist unter xdist für alle Prozesse eines Laufs
# derselbe, pytest räumt ihn wie jeden Basistemp-Ordner selbst weg); die anderen warten per
# Dateisperre und lesen sie. Ohne xdist bleibt es beim Prozess-Speicher.

_MESSUNGEN: dict[tuple[str, str], mx.Messung] = {}


@pytest.fixture(scope="session")
def _matrix_ordner(tmp_path_factory) -> Optional[Path]:
    if not os.environ.get("PYTEST_XDIST_WORKER") or fcntl is None:
        return None
    ordner = tmp_path_factory.getbasetemp().parent / "pv-achse-matrix"
    ordner.mkdir(exist_ok=True)
    return ordner


async def _miss(fid: str, teil: str) -> mx.Messung:
    m = mx.Messung(mx.FORMEN[fid])
    if teil == "HA":
        await mx.messe_ha(m.form, m)
    else:
        await mx.messe_sa(m.form, m)
    return m


async def _messung(fid: str, teil: str, ordner: Optional[Path]) -> mx.Messung:
    schluessel = (fid, teil)
    if schluessel in _MESSUNGEN:
        return _MESSUNGEN[schluessel]
    if ordner is None:
        _MESSUNGEN[schluessel] = await _miss(fid, teil)
        return _MESSUNGEN[schluessel]
    datei = ordner / f"{fid}-{teil}.json"
    with open(ordner / f"{fid}-{teil}.lock", "w") as sperre:
        fcntl.flock(sperre, fcntl.LOCK_EX)
        try:
            if not datei.exists():
                neu = await _miss(fid, teil)
                datei.write_text(json.dumps({"tage": neu.tage, "laufend": neu.laufend, "vor": neu.vor,
                                             "nach": neu.nach, "nutzlast": neu.nutzlast}, default=str),
                                 encoding="utf-8")
            # Auch der messende Prozess liest die Datei: jede Zelle bewertet dieselben Bytes.
            d = json.loads(datei.read_text(encoding="utf-8"))
            m = mx.Messung(mx.FORMEN[fid], d["tage"], d["laufend"], d["vor"], d["nach"], d["nutzlast"])
        finally:
            fcntl.flock(sperre, fcntl.LOCK_UN)
    _MESSUNGEN[schluessel] = m
    return m


def _teil(weg: str) -> str:
    return "HA" if weg in ("HA", "S1", "S2") else "SA"


# ── Bewertung ───────────────────────────────────────────────────────────────


@dataclass
class Zelle:
    sicht: str
    ist: Any
    soll: Any
    status: str  # "ok" | "rot" — „Soll unklar" entscheidet das Register, nicht die Zelle
    notiz: str = ""


def _tol(soll: Optional[float]) -> float:
    """Rundungsrest einer Einzelzahl: Tages-Keys und Monatswerte runden auf 0,01. ⚠ Nicht
    lockern: die kleinste fachliche Abweichung der Matrix ist 0,06 kWh am Tag (F04, Balkon
    1,56 statt 1,50 — N-623); Summen über Tage haben ihre eigene Toleranz (``_TOL_TAGE``)."""
    return max(0.05, 0.001 * abs(soll or 0.0))


#: Σ über 30 Tage aus je Gerät auf 0,01 gerundeten Tages-Keys: bis 0,005 × Geräte × Tage.
_TOL_TAGE = 0.6


def _gleich(ist, soll, tol: Optional[float] = None) -> bool:
    if ist is None or soll is None:
        return ist is None and soll is None
    return abs(float(ist) - float(soll)) <= (tol if tol is not None else _tol(soll))


def _z(sicht, ist, soll, *, tol=None, notiz="") -> Zelle:
    return Zelle(sicht, ist, soll, "ok" if _gleich(ist, soll, tol) else "rot", notiz)


def _pv(d: Optional[dict]) -> Optional[float]:
    return None if d is None else d.get("pv")


def _tage_stand(m: mx.Messung, weg: str) -> dict:
    return m.tage["HA" if _teil(weg) == "HA" else "SA"]


def _juni_summe_stunden(m: mx.Messung, weg: str) -> float:
    return round(sum((_tage_stand(m, weg)[t.isoformat()]["stunden_pv"] or 0.0) for t in mx.TAGE_JUNI), 4)


def _tage_zellen(sicht: str, m: mx.Messung, stand: str, tage, wert_fn, soll_fn, tol=None) -> Zelle:
    """Eine Zelle über viele Tage: rot, sobald ein Tag abweicht; gezeigt wird der erste."""
    abw = []
    for t in tage:
        ist, soll = wert_fn(m.tage[stand][t.isoformat()], t), soll_fn(t)
        if not _gleich(ist, soll, tol):
            abw.append((t.isoformat(), ist, soll))
    if not abw:
        t0 = tage[0]
        return Zelle(sicht, wert_fn(m.tage[stand][t0.isoformat()], t0), soll_fn(t0), "ok", f"{len(tage)} Tage")
    t, ist, soll = abw[0]
    return Zelle(sicht, ist, soll, "rot", f"{len(abw)} von {len(tage)} Tagen, erster {t}")


def _je_geraet_soll(soll: mx.Soll) -> dict[str, float]:
    out = dict(soll.je_geraet)
    for g in soll.ohne_key:
        out.setdefault(g, 0.0)
    return out


def _je_geraet_zellen(prefix: str, ist: dict, soll: mx.Soll, form: mx.Form) -> list[Zelle]:
    """Je Gerät der Form eine Zelle; ein Gerät ohne Eintrag hat 0 (None = 0 für Geräte, die die
    Sicht nicht führen darf)."""
    out = []
    erwartet = _je_geraet_soll(soll)
    for g in form.geraete:
        s = erwartet.get(g.name)
        if s is None:
            continue
        i = ist.get(g.name)
        out.append(_z(f"{prefix}:{g.name}", 0.0 if i is None else i, s))
    return out


def _folge(sicht: str, d: Optional[dict], einsp: float, netz: float) -> list[Zelle]:
    """I5 für eine Sicht mit PV, EV, Autarkie: EV = max(0, PV − Einspeisung), Autarkie =
    EV / (EV + Netzbezug); bei PV > 0 weder None noch 0 (in allen Formen ist PV ≫ Einspeisung)."""
    if d is None or not d.get("pv"):
        return [Zelle(sicht, None if d is None else d.get("pv"), "PV > 0", "rot", "keine PV, keine Folgekennzahl")]
    pv = d["pv"]
    e = d.get("einsp") if d.get("einsp") is not None else einsp
    n = d.get("netz") if d.get("netz") is not None else netz
    ev_soll = max(0.0, pv - e)
    aut_soll = 100.0 * ev_soll / (ev_soll + n) if (ev_soll + n) else None
    out = [_z(f"{sicht}:ev", d.get("ev"), ev_soll)]
    if "autarkie" in d:
        out.append(_z(f"{sicht}:autarkie", d.get("autarkie"), aut_soll, tol=0.15))
    if d.get("ev") is not None and d["ev"] <= 0:
        out.append(Zelle(f"{sicht}:ev>0", d.get("ev"), "> 0", "rot", f"PV {pv}, EV 0"))
    return out


def bewerte(fid: str, weg: str, inv: str, m: mx.Messung) -> list[Zelle]:  # noqa: C901 — eine Tafel, kein Algorithmus
    form = mx.FORMEN[fid]
    juni = mx.soll_monat(form, mx.TAGE_JUNI)
    juli = mx.soll_monat(form, mx.TAGE_JULI)
    e_juni, n_juni = mx.soll_einspeisung(form, 30), mx.soll_netzbezug(30)
    e_juli, n_juli = mx.soll_einspeisung(form, 3), mx.soll_netzbezug(3)
    z: list[Zelle] = []

    # ── Datenstand: Tag und laufender Monat ──
    if weg in ("HA", "SA"):
        lf = m.laufend[weg]
        tage = mx.TAGE_JUNI + mx.TAGE_JULI
        juli_std = round(sum((m.tage[weg][t.isoformat()]["stunden_pv"] or 0.0) for t in mx.TAGE_JULI), 4)
        if inv == "I1":
            ref = _pv(lf["monat"])
            # Cockpit → Tag: „PV-Anlage" + „Balkonkraftwerk" ist die Erzeugung des Tages.
            z.append(_tage_zellen("tag:cockpit:pv_anlage+bkw", m, weg, tage,
                                  lambda d, t: round((d["tw_pv_anlage"] or 0.0) + (d["tw_bkw"] or 0.0), 4),
                                  lambda t, w=weg: m.tage[w][t.isoformat()]["tw_erzeugung"]))
            z += [_z("laufend:cockpit_jahr", _pv(lf["jahr"]), ref),
                  _z("laufend:jahr_verlauf", _pv(lf["verlauf"]), ref),
                  _z("laufend:jahr_verlauf_segmente", (lf["verlauf"] or {}).get("segmente"), ref)]
        elif inv == "I2":
            z += [_z("laufend:cockpit_monat=Σtage", _pv(lf["monat"]), juli_std),
                  _z("laufend:jahr_verlauf=Σtage", _pv(lf["verlauf"]), juli_std)]
        elif inv == "I3":
            z += [_tage_zellen("tag:stunden", m, weg, tage, lambda d, t: d["stunden_pv"],
                               lambda t: mx.soll_tag(form, t).summe),
                  _tage_zellen("tag:keys", m, weg, tage, lambda d, t: d["summe_keys"],
                               lambda t: mx.soll_tag(form, t).summe),
                  _tage_zellen("tag:cockpit", m, weg, tage, lambda d, t: d["tw_erzeugung"],
                               lambda t: mx.soll_tag(form, t).summe),
                  _z("laufend:cockpit_monat", _pv(lf["monat"]), juli.summe)]
        elif inv == "I4":
            for g in form.geraete:
                def _soll(t, g=g):
                    s = mx.soll_tag(form, t)
                    return s.je_geraet.get(g.name, 0.0 if (g.name in s.ohne_key or not mx._aktiv(g, t)) else None)
                z.append(_tage_zellen(f"tag:keys:{g.name}", m, weg, tage,
                                      lambda d, t, g=g: d["keys"].get(g.name, 0.0), _soll))
                z.append(_tage_zellen(f"tag:cockpit:{g.name}", m, weg, tage,
                                      lambda d, t, g=g: d["tw_erzeuger"].get(g.name, 0.0), _soll))
            z.append(_tage_zellen("tag:Σkeys=stunden", m, weg, tage, lambda d, t: d["summe_keys"],
                                  lambda t, w=weg: m.tage[w][t.isoformat()]["stunden_pv"]))
            bkw_namen = {g.name for g in form.geraete if g.typ == "balkonkraftwerk"}
            z.append(_tage_zellen("tag:cockpit:pv_anlage", m, weg, tage, lambda d, t: d["tw_pv_anlage"] or 0.0,
                                  lambda t: sum(v for n, v in mx.soll_tag(form, t).je_geraet.items()
                                                if n not in bkw_namen)))
            if bkw_namen:
                z.append(_tage_zellen("tag:cockpit:bkw", m, weg, tage, lambda d, t: d["tw_bkw"] or 0.0,
                                      lambda t: sum(v for n, v in mx.soll_tag(form, t).je_geraet.items()
                                                    if n in bkw_namen)))
            bkw = next((g for g in form.geraete if g.typ == "balkonkraftwerk"), None)
            if bkw is not None:
                eigen = mx.tagesmenge(bkw.rate) * 3 if bkw.zaehler else 0.0
                z.append(_z("laufend:cockpit_monat:bkw_eigen", (lf["monat"] or {}).get("bkw") or 0.0, eigen))
        elif inv == "I5":
            for t in tage:
                d = m.tage[weg][t.isoformat()]
                f = _folge(f"tag:{t.isoformat()}", {"pv": d["tw_erzeugung"], "ev": d["tw_eigenverbrauch"],
                                                    "einsp": d["tw_einspeisung"], "netz": d["tw_netzbezug"],
                                                    "autarkie": d["tw_autarkie"]},
                           mx.soll_einspeisung(form, 1), mx.soll_netzbezug(1))
                rot = [x for x in f if x.status == "rot"]
                if rot:
                    z.append(Zelle("tag:cockpit:folge", rot[0].ist, rot[0].soll, "rot", f"erster {t}: {rot[0].sicht}"))
                    break
            else:
                z.append(Zelle("tag:cockpit:folge", "EV/Autarkie je Tag", "folgen der PV", "ok"))
            z += _folge("laufend:cockpit_monat", lf["monat"], e_juli, n_juli)
            z += _folge("laufend:cockpit_jahr", lf["jahr"], e_juli, n_juli)
            z += _folge("laufend:jahr_verlauf", lf["verlauf"], e_juli, n_juli)
        elif inv == "I6":
            leer = [t.isoformat() for t in tage
                    if not m.tage[weg][t.isoformat()]["tz_vorhanden"]
                    or not m.tage[weg][t.isoformat()]["stunden_pv"]
                    or not m.tage[weg][t.isoformat()]["summe_keys"]
                    or not m.tage[weg][t.isoformat()]["tw_erzeugung"]]
            z.append(Zelle("tag:alle_tage_mit_pv", len(leer), 0, "ok" if not leer else "rot",
                           f"ohne PV: {leer[:3]}" if leer else ""))
            werte = {"laufend:cockpit_monat": _pv(lf["monat"]), "laufend:cockpit_jahr": _pv(lf["jahr"]),
                     "laufend:jahr_verlauf": _pv(lf["verlauf"])}
            if any(v for v in werte.values()):
                z += [Zelle(k, v, "> 0", "ok" if v else "rot") for k, v in werte.items()]
        return z

    # ── Schreibweg: abgeschlossener Monat ──
    vor, nach = m.vor[weg], m.nach[weg]
    fk = nach["fakten"] or {}
    if inv == "I1":
        ref = fk.get("pv")
        sichten = {
            "cockpit_monat": _pv(nach["monat"]), "cockpit_uebersicht": _pv(nach["uebersicht"]),
            "cockpit_jahr": _pv(nach["jahr"]), "tabelle": _pv(nach["tabelle"]),
            "jahr_verlauf": _pv(nach["verlauf"]), "jahr_verlauf_segmente": (nach["verlauf"] or {}).get("segmente"),
            "pv_strings_jahr": nach["pv_strings"]["jahr_summe"],
            "pv_strings_gesamtlaufzeit": nach["pv_strings"]["gesamt_summe"],
            "komponenten_verlauf_erzeugung": nach["komp_verlauf"]["erzeugung"],
            "komponenten_verlauf_verwendung": nach["komp_verlauf"]["verwendung"],
            "pdf_monatstabelle": nach["pdf"]["pv"], "pdf_string_vergleich": nach["pdf"]["string_summe"],
            "ha_export": nach["ha_export"]["pv"], "community": nach["community"]["pv"],
        }
        # Die PV-Map des Daten-Checkers führt nur vollständig auflösbare Monate (N42,
        # `daten_checker/_helpers.py::_get_pv_erzeugung_map`): ist der Monat nach der Regel eine
        # Teilsumme, ist ihr Soll „kein Eintrag".
        if juni.vollstaendig:
            sichten["daten_checker"] = nach["checker"]["pv"]
        else:
            z.append(_z("daten_checker:teilsumme_ohne_eintrag", nach["checker"]["pv"], None))
        if "vorschau" in nach and form.gesamt is not None:
            # Die Vorschau nennt den lokalen Gesamtwert nur, wenn ein Anlagenzähler zugeordnet ist.
            sichten["import_vorschau_lokal"] = nach["vorschau"]["pv"]
        z += [_z(k, v, ref, notiz="Referenz: Monats-Fakten") for k, v in sichten.items()]
    elif inv == "I2":
        z += [_z("cockpit_monat:vor=nach", _pv(vor["monat"]), _pv(nach["monat"])),
              _z("jahr_verlauf:vor=nach", _pv(vor["verlauf"]), _pv(nach["verlauf"]), tol=_TOL_TAGE),
              _z("fakten:tageswert=gespeichert", _pv(vor["fakten_tw"]), fk.get("pv"), tol=_TOL_TAGE),
              _z("Σtage_juni=cockpit_monat", _juni_summe_stunden(m, weg), _pv(nach["monat"]), tol=_TOL_TAGE)]
    elif inv == "I3":
        z += [_z("cockpit_monat:vor", _pv(vor["monat"]), juni.summe),
              _z("cockpit_monat:nach", _pv(nach["monat"]), juni.summe),
              _z("fakten", fk.get("pv"), juni.summe),
              # Cockpit → Jahr, Kopf: Juni (abgeschlossen) + Juli (läuft, drei Tage).
              _z("cockpit_jahr:kopf", nach.get("jahr_kopf"), juni.summe + juli.summe, tol=_TOL_TAGE),
              Zelle("fakten:vollstaendig", fk.get("vollstaendig"), juni.vollstaendig,
                    "ok" if fk.get("vollstaendig") == juni.vollstaendig else "rot")]
    elif inv == "I4":
        bkws = [g for g in form.geraete if g.typ == "balkonkraftwerk"]
        je = dict(fk.get("je_geraet") or {})
        for b in bkws:   # eine BKW ohne eigenen Wert führt ihren Anteil in `bkw_aus_anlagenwert_kwh`
            if not b.zaehler and fk.get("bkw_anteil"):
                je[b.name] = (je.get(b.name) or 0.0) + fk["bkw_anteil"]
        z += _je_geraet_zellen("fakten", je, juni, form)
        z += _je_geraet_zellen("pv_strings", nach["pv_strings"]["juni_je_geraet"], juni, form)
        z += _je_geraet_zellen("pdf_string_vergleich", nach["pdf"]["string_je_geraet"], juni, form)
        # Tageswert-Rückfall (vor dem Abschluss): die Fakten führen dort keine Werte je Modul, nur
        # die Gruppen Module (`pv_module_kwh`) und Balkonkraftwerk (`bkw_kwh`) — Soll ist die
        # Σ der Tages-Keys nach der Tagesregel (E4: ein BKW-Key trägt den Rest seiner Kinder).
        tw = vor["fakten_tw"] or {}
        bkw_namen = {g.name for g in form.geraete if g.typ == "balkonkraftwerk"}
        soll_bkw = sum(v for t in mx.TAGE_JUNI for n, v in mx.soll_tag(form, t).je_geraet.items() if n in bkw_namen)
        soll_mod = sum(v for t in mx.TAGE_JUNI for n, v in mx.soll_tag(form, t).je_geraet.items() if n not in bkw_namen)
        z.append(_z("fakten_tageswert:module", tw.get("pv_module") or 0.0, soll_mod, tol=_TOL_TAGE))
        if bkw_namen:
            z.append(_z("fakten_tageswert:bkw", tw.get("bkw") or 0.0, soll_bkw, tol=_TOL_TAGE))
        z.append(_z("fakten:Σgeraete=summe", round(sum(v or 0.0 for v in je.values()), 4), fk.get("pv")))
        z.append(_z("pv_strings:Σgeraete=summe",
                    round(sum(v or 0.0 for v in nach["pv_strings"]["juni_je_geraet"].values()), 4),
                    nach["pv_strings"]["jahr_summe"]))
        for b in bkws:
            eigen = mx.tagesmenge(b.rate) * 30 if (b.zaehler and not mx._kinder_von(form, b, mx.TAGE_JUNI[-1])) else 0.0
            z.append(_z("cockpit_monat:bkw_eigen", (nach["monat"] or {}).get("bkw") or 0.0, eigen))
            z.append(_z("community:bkw_eigen", nach["community"]["bkw"] or 0.0, eigen))
    elif inv == "I5":
        z += _folge("cockpit_monat:vor", vor["monat"], e_juni, n_juni)
        z += _folge("jahr_verlauf:vor", vor["verlauf"], e_juni, n_juni)
        for k in ("monat", "uebersicht", "jahr", "tabelle", "verlauf", "pdf", "ha_export", "community"):
            z += _folge(k, nach[k], e_juni, n_juni)
        z.append(_z("ha_export:spez=uebersicht", nach["ha_export"]["spez"], nach["uebersicht"]["spez"], tol=0.15))
    elif inv == "I6":
        werte = {"vor:cockpit_monat": _pv(vor["monat"]), "vor:jahr_verlauf": _pv(vor["verlauf"]),
                 "vor:fakten_tageswert": _pv(vor["fakten_tw"])}
        werte.update({f"nach:{k}": _pv(nach[k]) for k in
                      ("monat", "fakten", "uebersicht", "jahr", "tabelle", "verlauf", "pdf",
                       "ha_export", "community", "checker")})
        werte["nach:pv_strings"] = nach["pv_strings"]["jahr_summe"]
        if not juni.vollstaendig:
            werte.pop("nach:checker")   # N42: eine Teilsumme hat in der PV-Map keinen Eintrag (I1 prüft das)
        if any(v for v in werte.values()):
            z += [Zelle(k, v, "> 0", "ok" if v else "rot") for k, v in werte.items()]
    return z


# ── Register: rote Zellen gegen HEAD und „Soll unklar" ─────────────────────


class BekannterMangel(AssertionError):
    """Die Zelle ist rot, und zwar genau mit den Sichten, die ``BEKANNT`` für sie nennt."""


@dataclass(frozen=True)
class Mangel:
    sichten: frozenset[str]
    zuordnung: str   # "N-623" · "N-624" · "HA-Bauform" · "KANDIDAT"
    grund: str


@dataclass(frozen=True)
class Ursache:
    zuordnung: str
    grund: str


#: Die Ursachen der roten Zellen gegen HEAD ``737f476d`` (04.10.2026). Bericht mit Ist/Soll je
#: Zelle: ``~/.claude/plans/opus-berichte/PV-ACHSE-MATRIX.md``. Nur zeigen, nicht bauen.
URSACHE: dict[str, Ursache] = {
    "N624": Ursache(
        "N-624",
        "laufender Monat mit Tageszeilen: der Anlagen-PV-Zähler aus der HA-Monatsstatistik wird als "
        "Teilzeitraum markiert und durch die Einzelzähler ersetzt (core/berechnungen/datenquellen.py::"
        "mqtt_teilzeitraum_felder ⇒ aktueller_monat/aggregation.py)",
    ),
    "N623": Ursache(
        "N-623",
        "Tag im Aggregat-Fall: gemessene Erzeuger bekommen ihren kWp-Anteil statt ihres Zählerwerts "
        "(snapshot/tages_tabelle.py:321 ⇒ loese_pv_tageswerte_auf); BKW mit Modul-Kindern ohne bkw_-Key "
        "(Gegenprüfung W5). Folgt in den Tageswert-Rückfall der Monats-Fakten und in die Standalone-Tagesebene",
    ),
    "HABF_C": Ursache(
        "HA-Bauform-Rest (c)",
        "folge-prompt-ha-bauform.md, Nachtrag 03.10. abends (c): die BKW-Kinder-Stufe von P7 (N-266/E4) fehlt "
        "im Monat ohne Abschluss ⇒ BKW-Zähler und gemessene Kinder zählen beide",
    ),
    "HABF_S2": Ursache(
        "HA-Bauform-Rest S1/S2",
        "folge-prompt-ha-bauform.md, Nachtrag 03.10. nachts (S1-Pflichtpunkt BKW ohne eigenen Wert, S2 "
        "Import-Verteilung), Handbuch Einstellungen §7.6: der Sammelimport speichert den Anlagenzähler nicht "
        "und verteilt ihn nur auf Module ohne eigenen Wert (BKW ohne Wert 0, Kinder unter gemessenem BKW "
        "bekommen einen Anteil). Folgen: der Tageswert-Rückfall füllt die BKW-Gruppe aus den Tagen "
        "(Jahr-Verlauf über dem Monat), der Daten-Checker lässt den Monat aus",
    ),
    "K1": Ursache(
        "KANDIDAT K1",
        "Standalone: die Gesamtleistungs-Serie `pv_gesamt` der Kurve wird in `summiere_live_komponenten` "
        "(energie_profil/aggregator.py:394-410) als kWh in `komponenten_kwh` summiert und bleibt neben den "
        "`pv_<id>`-Keys der Zählertabelle stehen (:1642 überschreibt nur deren Keys); "
        "`lade_monats_summen_aus_tagen` zählt jeden `pv_`-Key ⇒ Tagesebene doppelt",
    ),
    "K2": Ursache(
        "KANDIDAT K2",
        "Teilsumme: monats_fakten/bau.py:107 `pv_kwh = (pv_modul_summe or 0.0) + …` verwirft die gemessenen "
        "Module, sobald ein Modul ohne Wert und ohne Anlagenwert ist (KONZEPT-UNVOLLSTAENDIGE-WERTE §2.1 nennt "
        "die Zeile, kein offener Fund) ⇒ Monat 90 statt 450, EV 0",
    ),
    "K3": Ursache(
        "KANDIDAT K3",
        "abgeschlossener Monat, BKW mit Modul-Kindern: Cockpit → Monat füllt `bkw_erzeugung_kwh` per "
        "setdefault aus dem HA-BKW-Zähler, obwohl das BKW im Monat abgetreten hat (Monats-Fakten 0, ADR-002/P11)",
    ),
    "K4": Ursache(
        "KANDIDAT K4",
        "Import-Vorschau einer reinen BKW-Anlage mit Anlagenzähler: der lokale Gesamtwert entsteht nur aus "
        "`pv-module` (api/routes/ha_statistics.py:706-723) ⇒ „Fehlt lokal: PV Erzeugung Gesamt“, Aktion "
        "„importieren“, obwohl der Monat abgeschlossen ist",
    ),
    "K5": Ursache(
        "KANDIDAT K5",
        "laufender Monat: ein BKW ohne eigenen Zähler bekommt aus der Tagesebene seinen kWp-Anteil als "
        "`bkw_erzeugung_kwh` (aktueller_monat/__init__.py:576); im abgeschlossenen Monat steht der Anteil in "
        "`bkw_aus_anlagenwert_kwh`, die eigene Zeile bleibt 0 (monats_fakten/fakten.py:90-99)",
    ),
}

#: ``Ursache → {(Form, Weg, Invariante): rote Sichten}`` — gemessen, nicht hergeleitet.
ROT: dict[str, dict[tuple[str, str, str], tuple[str, ...]]] = {
    'N624': {
        ('F03', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F03', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F03', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F03', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F03', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F03', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F04', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F04', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F04', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F04', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F04', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F05', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F05', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F05', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F05', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F05', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F08b', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F08b', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F08b', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F08b', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F08b', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F08b', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F09a-G', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09a-G', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09a-G', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09a-G', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F09a-G', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F09a-G', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F09b-G', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09b-G', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09b-G', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09b-G', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F09b-G', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F09b-G', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F09c-G', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09c-G', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09c-G', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09c-G', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F09c-G', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F09c-G', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F12', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F12', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F12', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F12', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F12', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F14', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F14', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F14', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F14', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F14', 'S2', 'I3'): ('cockpit_jahr:kopf',),
    },
    'N623': {
        ('F03', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F03', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F03', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F03', 'SA', 'I4'): (
            'laufend:cockpit_monat:bkw_eigen', 'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F03', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F04', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F04', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F04', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F04', 'SA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F04', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F05', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F05', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F05', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F05', 'SA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F05', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08a', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F08a', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08a', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08a', 'SA', 'I4'): (
            'laufend:cockpit_monat:bkw_eigen', 'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F08a', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08b', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F08b', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08b', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F08b', 'SA', 'I4'): (
            'laufend:cockpit_monat:bkw_eigen', 'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F08b', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09a-G', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Kind 1', 'tag:keys:Kind 2',
            'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09a-G', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09a-G', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09a-G', 'SA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Kind 1', 'tag:keys:Kind 2',
            'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09a-G', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09b-G', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Kind 1', 'tag:keys:Kind 2',
            'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09b-G', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09b-G', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09b-G', 'SA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:bkw', 'tag:cockpit:pv_anlage', 'tag:keys:Balkon', 'tag:keys:Kind 1', 'tag:keys:Kind 2',
            'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09b-G', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F09c-G', 'HA', 'I4'): (
            'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:keys:Kind 1',
            'tag:keys:Kind 2', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09c-G', 'SA', 'I4'): (
            'tag:cockpit:Kind 1', 'tag:cockpit:Kind 2', 'tag:cockpit:Süd', 'tag:cockpit:West',
            'tag:cockpit:pv_anlage', 'tag:keys:Kind 1', 'tag:keys:Kind 2', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F09c-G', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F12', 'HA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F12', 'S1', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F12', 'S2', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F12', 'SA', 'I4'): (
            'tag:cockpit:Balkon', 'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:bkw', 'tag:cockpit:pv_anlage',
            'tag:keys:Balkon', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F12', 'S3', 'I4'): ('fakten_tageswert:bkw', 'fakten_tageswert:module',),
        ('F14', 'HA', 'I4'): ('tag:cockpit:Süd', 'tag:cockpit:West', 'tag:keys:Süd', 'tag:keys:West',),
        ('F14', 'SA', 'I4'): (
            'tag:cockpit:Süd', 'tag:cockpit:West', 'tag:cockpit:pv_anlage', 'tag:keys:Süd', 'tag:keys:West',
        ),
        ('F14', 'S3', 'I4'): ('fakten_tageswert:module',),
    },
    'HABF_C': {
        ('F09b-G', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09b-G', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09b-G', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09b-G', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F09b-G', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F09b-G', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F09c-G', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09c-G', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09c-G', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09c-G', 'HA', 'I5'): ('laufend:cockpit_jahr:ev>0', 'laufend:cockpit_monat:ev>0',),
        ('F09c-G', 'S1', 'I3'): ('cockpit_jahr:kopf',),
        ('F09c-G', 'S2', 'I3'): ('cockpit_jahr:kopf',),
        ('F09b-oG', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09b-oG', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09b-oG', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09b-oG', 'S1', 'I2'): ('cockpit_monat:vor=nach',),
        ('F09b-oG', 'S1', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:vor',),
        ('F09b-oG', 'S2', 'I2'): ('cockpit_monat:vor=nach',),
        ('F09b-oG', 'S2', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:vor',),
        ('F09c-oG', 'HA', 'I1'): ('laufend:jahr_verlauf', 'laufend:jahr_verlauf_segmente',),
        ('F09c-oG', 'HA', 'I2'): ('laufend:cockpit_monat=Σtage',),
        ('F09c-oG', 'HA', 'I3'): ('laufend:cockpit_monat',),
        ('F09c-oG', 'S1', 'I2'): ('cockpit_monat:vor=nach',),
        ('F09c-oG', 'S1', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:vor',),
        ('F09c-oG', 'S2', 'I2'): ('cockpit_monat:vor=nach',),
        ('F09c-oG', 'S2', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:vor',),
    },
    'HABF_S2': {
        ('F01', 'S2', 'I1'): ('daten_checker', 'jahr_verlauf', 'jahr_verlauf_segmente',),
        ('F01', 'S2', 'I2'): ('jahr_verlauf:vor=nach',),
        ('F01', 'S2', 'I4'): (
            'fakten:Balkon', 'fakten:Süd', 'fakten:West', 'pdf_string_vergleich:Balkon', 'pdf_string_vergleich:Süd',
            'pdf_string_vergleich:West', 'pv_strings:Balkon', 'pv_strings:Süd', 'pv_strings:West',
        ),
        ('F01', 'S2', 'I6'): ('nach:checker',),
        ('F04', 'S2', 'I1'): ('daten_checker', 'jahr_verlauf', 'jahr_verlauf_segmente',),
        ('F04', 'S2', 'I2'): ('jahr_verlauf:vor=nach',),
        ('F04', 'S2', 'I4'): (
            'fakten:Balkon', 'fakten:West', 'pdf_string_vergleich:Balkon', 'pdf_string_vergleich:West',
            'pv_strings:Balkon', 'pv_strings:West',
        ),
        ('F04', 'S2', 'I6'): ('nach:checker',),
        ('F05', 'S2', 'I1'): ('daten_checker', 'jahr_verlauf', 'jahr_verlauf_segmente',),
        ('F05', 'S2', 'I2'): (
            'cockpit_monat:vor=nach', 'fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',
            'Σtage_juni=cockpit_monat',
        ),
        ('F05', 'S2', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:nach', 'fakten',),
        ('F05', 'S2', 'I4'): ('fakten:Balkon', 'pdf_string_vergleich:Balkon', 'pv_strings:Balkon',),
        ('F05', 'S2', 'I6'): ('nach:checker',),
        ('F09a-G', 'S2', 'I4'): (
            'fakten:Kind 1', 'fakten:Kind 2', 'fakten:Süd', 'fakten:West', 'pdf_string_vergleich:Kind 1',
            'pdf_string_vergleich:Kind 2', 'pdf_string_vergleich:Süd', 'pdf_string_vergleich:West',
            'pv_strings:Kind 1', 'pv_strings:Kind 2', 'pv_strings:Süd', 'pv_strings:West',
        ),
        ('F09b-G', 'S2', 'I4'): (
            'fakten:Kind 2', 'fakten:Süd', 'fakten:West', 'pdf_string_vergleich:Kind 2', 'pdf_string_vergleich:Süd',
            'pdf_string_vergleich:West', 'pv_strings:Kind 2', 'pv_strings:Süd', 'pv_strings:West',
        ),
        ('F12', 'S2', 'I1'): ('daten_checker', 'jahr_verlauf', 'jahr_verlauf_segmente',),
        ('F12', 'S2', 'I2'): ('jahr_verlauf:vor=nach',),
        ('F12', 'S2', 'I4'): (
            'fakten:Balkon', 'fakten:West', 'pdf_string_vergleich:Balkon', 'pdf_string_vergleich:West',
            'pv_strings:Balkon', 'pv_strings:West',
        ),
        ('F12', 'S2', 'I6'): ('nach:checker',),
    },
    'K1': {
        ('F01', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F01', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F01', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F01', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F01', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F01', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F01', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F02', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F02', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F02', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F02', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F02', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F02', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F02', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F03', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F03', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F03', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F03', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F03', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F03', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F03', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F04', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F04', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F04', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F04', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F04', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F04', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F04', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F05', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F05', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F05', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F05', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F05', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F05', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F05', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F08a', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F08a', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F08a', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F08a', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F08a', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F08a', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F08a', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F08b', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F08b', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F08b', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F08b', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F08b', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F08b', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F08b', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F09a-G', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F09a-G', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F09a-G', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F09a-G', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F09a-G', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F09a-G', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F09a-G', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F09b-G', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F09b-G', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F09b-G', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F09b-G', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F09b-G', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F09b-G', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F09b-G', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F09c-G', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F09c-G', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F09c-G', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F09c-G', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F09c-G', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F09c-G', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F09c-G', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F10', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F10', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F10', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F10', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F10', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F10', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F10', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F11', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F11', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F11', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F11', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F11', 'S3', 'I1'): ('jahr_verlauf', 'jahr_verlauf_segmente',),
        ('F11', 'S3', 'I2'): ('fakten:tageswert=gespeichert',),
        ('F11', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F11', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F12', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F12', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F12', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F12', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F12', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F12', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F12', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F13a', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F13a', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F13a', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F13a', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F13a', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F13a', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F13a', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F13b', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F13b', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F13b', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F13b', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F13b', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F13b', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F13b', 'S3', 'I4'): ('fakten_tageswert:module',),
        ('F14', 'SA', 'I1'): ('tag:cockpit:pv_anlage+bkw',),
        ('F14', 'SA', 'I2'): ('laufend:cockpit_monat=Σtage', 'laufend:jahr_verlauf=Σtage',),
        ('F14', 'SA', 'I3'): ('laufend:cockpit_monat',),
        ('F14', 'SA', 'I4'): ('tag:cockpit:pv_anlage',),
        ('F14', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'jahr_verlauf:vor=nach',),
        ('F14', 'S3', 'I3'): ('cockpit_jahr:kopf',),
        ('F14', 'S3', 'I4'): ('fakten_tageswert:module',),
    },
    'K2': {
        ('F07', 'S1', 'I1'): (
            'jahr_verlauf', 'jahr_verlauf_segmente', 'komponenten_verlauf_erzeugung',
            'komponenten_verlauf_verwendung', 'pdf_string_vergleich', 'pv_strings_gesamtlaufzeit', 'pv_strings_jahr',
        ),
        ('F07', 'S1', 'I2'): ('cockpit_monat:vor=nach', 'fakten:tageswert=gespeichert', 'Σtage_juni=cockpit_monat',),
        ('F07', 'S1', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:nach', 'fakten',),
        ('F07', 'S1', 'I4'): ('fakten:Σgeraete=summe',),
        ('F07', 'S1', 'I5'): (
            'community:ev>0', 'ha_export:ev>0', 'jahr:ev>0', 'monat:ev>0', 'pdf:ev>0', 'tabelle:ev>0',
            'uebersicht:ev>0',
        ),
        ('F07', 'S2', 'I1'): (
            'jahr_verlauf', 'jahr_verlauf_segmente', 'komponenten_verlauf_erzeugung',
            'komponenten_verlauf_verwendung', 'pdf_string_vergleich', 'pv_strings_gesamtlaufzeit', 'pv_strings_jahr',
        ),
        ('F07', 'S2', 'I2'): ('cockpit_monat:vor=nach', 'fakten:tageswert=gespeichert', 'Σtage_juni=cockpit_monat',),
        ('F07', 'S2', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:nach', 'fakten',),
        ('F07', 'S2', 'I4'): ('fakten:Σgeraete=summe',),
        ('F07', 'S2', 'I5'): (
            'community:ev>0', 'ha_export:ev>0', 'jahr:ev>0', 'monat:ev>0', 'pdf:ev>0', 'tabelle:ev>0',
            'uebersicht:ev>0',
        ),
        ('F07', 'S3', 'I1'): (
            'jahr_verlauf', 'jahr_verlauf_segmente', 'komponenten_verlauf_erzeugung',
            'komponenten_verlauf_verwendung', 'pdf_string_vergleich', 'pv_strings_gesamtlaufzeit', 'pv_strings_jahr',
        ),
        ('F07', 'S3', 'I2'): ('fakten:tageswert=gespeichert', 'Σtage_juni=cockpit_monat',),
        ('F07', 'S3', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:nach', 'fakten',),
        ('F07', 'S3', 'I4'): ('fakten:Σgeraete=summe',),
        ('F07', 'S3', 'I5'): (
            'community:ev>0', 'ha_export:ev>0', 'jahr:ev>0', 'monat:ev>0', 'pdf:ev>0', 'tabelle:ev>0',
            'uebersicht:ev>0',
        ),
    },
    'K3': {
        ('F09a-G', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09a-G', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09b-G', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09b-G', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09c-G', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09c-G', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09a-oG', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09a-oG', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09b-oG', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09b-oG', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09c-oG', 'S1', 'I4'): ('cockpit_monat:bkw_eigen',),
        ('F09c-oG', 'S2', 'I4'): ('cockpit_monat:bkw_eigen',),
    },
    'K4': {
        ('F11', 'S1', 'I1'): ('import_vorschau_lokal',),
        ('F11', 'S2', 'I1'): ('import_vorschau_lokal',),
    },
    'K5': {
        ('F01', 'HA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F01', 'SA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F04', 'HA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F04', 'SA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F05', 'HA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F05', 'SA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F12', 'HA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
        ('F12', 'SA', 'I4'): ('laufend:cockpit_monat:bkw_eigen',),
    },
}


def _baue_bekannt() -> dict[tuple[str, str, str], Mangel]:
    """Je Zelle die Vereinigung der roten Sichten aller Ursachen, die sie treffen."""
    sichten: dict[tuple[str, str, str], set[str]] = {}
    kennungen: dict[tuple[str, str, str], list[str]] = {}
    for kennung, zellen in ROT.items():
        for zelle, rote in zellen.items():
            sichten.setdefault(zelle, set()).update(rote)
            kennungen.setdefault(zelle, []).append(kennung)
    return {
        zelle: Mangel(
            frozenset(sichten[zelle]),
            " + ".join(URSACHE[k].zuordnung for k in kennungen[zelle]),
            " ‖ ".join(URSACHE[k].grund for k in kennungen[zelle]),
        )
        for zelle in sichten
    }


#: ``(Form, Weg, Invariante) → Mangel``.
BEKANNT: dict[tuple[str, str, str], Mangel] = _baue_bekannt()

#: ``(Form, Weg, Invariante, Sicht) → Grund``: die Regel legt das Soll dieser Sicht nicht fest.
SOLL_UNKLAR: dict[tuple[str, str, str, str], str] = {}

_U_SA_VOR = (
    "Cockpit → Monat sammelt die Tagesebene NUR im laufenden Monat (aktueller_monat/__init__.py:731-738, "
    "N-472: in einem abgeschlossenen Monat wäre sie „eine stille Untertreibung“, die Antwort ist der "
    "Monatsabschluss). Ohne HA hat ein vergangener Monat vor dem Abschluss also keine PV — während "
    "Cockpit → Jahr → Verlauf denselben Monat aus den Tageswerten zeigt (N-121). Ob „nichts verschwindet“ "
    "hier gilt oder die N-472-Begründung, ist nicht entschieden."
)
_U_KINDER_LAUFEND = (
    "BKW mit Modul-Kindern im laufenden Monat: der Monat tritt ab (ADR-002/P11 ⇒ eigene Zeile 0), der Tag "
    "zeigt das Gerät mit dem Rest seiner Kinder (E4) — die Tagesebene speist den laufenden Monat. Welche "
    "Regel dort gilt, ist offen (HA-Bauform Nachtrag 03.10. (c), Einwertung K-C)."
)
for _f in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08a", "F08b", "F09a-G", "F09b-G", "F09c-G",
           "F09a-oG", "F09b-oG", "F09c-oG", "F10", "F11", "F12", "F13a", "F13b", "F14", "F15"):
    SOLL_UNKLAR[(_f, "S3", "I2", "cockpit_monat:vor=nach")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I3", "cockpit_monat:vor")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I5", "cockpit_monat:vor")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I6", "vor:cockpit_monat")] = _U_SA_VOR
for _f in ("F09a-G", "F09b-G", "F09c-G", "F09a-oG", "F09b-oG", "F09c-oG", "F10"):
    for _w in ("HA", "SA"):
        SOLL_UNKLAR[(_f, _w, "I4", "laufend:cockpit_monat:bkw_eigen")] = _U_KINDER_LAUFEND


WEGE = ("HA", "S1", "S2", "SA", "S3")
INVARIANTEN = ("I1", "I2", "I3", "I4", "I5", "I6")


def _zellen_params():
    for fid in mx.FORMEN:
        for weg in WEGE:
            for inv in INVARIANTEN:
                mangel = BEKANNT.get((fid, weg, inv))
                marks = ()
                if mangel is not None:
                    marks = (pytest.mark.xfail(strict=True, raises=BekannterMangel,
                                               reason=f"{mangel.zuordnung}: {mangel.grund}"),)
                yield pytest.param(fid, weg, inv, marks=marks, id=f"{fid}-{weg}-{inv}")


def _rot(fid, weg, inv, zellen: list[Zelle]) -> dict[str, Zelle]:
    out = {}
    for x in zellen:
        if (fid, weg, inv, x.sicht) in SOLL_UNKLAR:
            continue
        if x.status == "rot":
            out[x.sicht] = x
    return out


def _bericht(zellen) -> str:
    return "\n".join(f"  {x.sicht}: ist {x.ist} · soll {x.soll} {('· ' + x.notiz) if x.notiz else ''}"
                     for x in zellen.values())


@pytest.mark.parametrize("fid,weg,inv", list(_zellen_params()))
async def test_zelle(fid, weg, inv, _matrix_ordner):
    m = await _messung(fid, _teil(weg), _matrix_ordner)
    zellen = bewerte(fid, weg, inv, m)
    assert zellen, "Eine Zelle ohne Prüfung misst nichts."
    rot = _rot(fid, weg, inv, zellen)
    mangel = BEKANNT.get((fid, weg, inv))
    erwartet = mangel.sichten if mangel else frozenset()
    if set(rot) != set(erwartet):
        geheilt = sorted(erwartet - set(rot))
        neu = sorted(set(rot) - erwartet)
        raise AssertionError(
            f"{fid} {weg} {inv}: rote Sichten weichen vom Register ab.\n"
            f" neu rot: {neu}\n geheilt (Markierung entfernen): {geheilt}\n" + _bericht(rot)
        )
    if rot:
        raise BekannterMangel(f"{mangel.zuordnung} — {mangel.grund}\n" + _bericht(rot))


@pytest.mark.parametrize("schluessel", sorted(SOLL_UNKLAR), ids=lambda s: "-".join(s))
async def test_soll_unklar_ist_noch_eine_messung(schluessel, _matrix_ordner):
    """Eine „Soll unklar"-Sicht muss es in ihrer Zelle noch geben — sonst ist der Eintrag tot."""
    fid, weg, inv, sicht = schluessel
    m = await _messung(fid, _teil(weg), _matrix_ordner)
    assert sicht in {x.sicht for x in bewerte(fid, weg, inv, m)}, f"{schluessel} misst nichts mehr"


def test_register_zeigt_nur_auf_bestehende_zellen():
    zellen = {(f, w, i) for f in mx.FORMEN for w in WEGE for i in INVARIANTEN}
    assert set(BEKANNT) <= zellen
    assert {k[:3] for k in SOLL_UNKLAR} <= zellen
