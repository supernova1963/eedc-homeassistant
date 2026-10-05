"""Abnahme-Matrix der PV-Achse — eine Probe für alle Zuordnungsformen, Datenstände, Sichten.

Baustein (Formen, Seed, Schreibwege, Messfunktionen, Soll-Regel): ``pv_achse_matrix.py``.

**Was eine Zelle ist.** Form (F01–F16, 23 Ausprägungen) × Weg × Invariante (I1–I6). Weg ist
entweder ein **Datenstand** — ``HA`` (HA-Statistik + Tageszeilen) oder ``SA`` (Standalone,
Snapshot-Pfad) — für den Tag und den laufenden Monat, oder ein **Schreibweg** des
abgeschlossenen Monats — ``S1`` „Aus HA laden", ``S2`` HA-Statistik-Sammelimport, ``S3``
Handeingabe ohne HA. Jede Zelle prüft ALLE Sichten ihrer Invariante; was sie zählt, steht in
``bewerte``.

**Rote Zellen** stehen in ``BEKANNT`` — mit der Menge der roten Sichten, dem Grund und der
Zuordnung (seit dem Bau der PV-Achse, 04.10.2026, nur noch der Sammelimport, HA-Bauform S1, als
benannte Erwartung mit Verweis). Die Zelle läuft dann
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
from backend.tests.matrix_haltewerte import PV_HALTEWERTE

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


#: Formen, deren Geld-Sichten gemessen und gezeigt werden (Auftrag Achsen-Matrix 2, „Zusatz an der PV-Matrix").
GELD_SICHTEN_FORMEN = ("F13a",)


def _geld_sichten(nach: dict) -> list[Zelle]:
    """Ersparnis aus Eigenverbrauch und CO₂ je Sicht, neben dem Eigenverbrauch derselben Sicht. Ihr Soll legt der
    Bauplan der HA-Bauform fest (N-588: Σ Einzelzähler > Anlagenzähler ⇒ Wandlungsverluste) — hier nur gemessen.
    Gezeigt wird als „soll" die Rechnung EV × 30 ct derselben Sicht (Tarif der Form), nicht ein Urteil."""
    out = []
    for k in ("monat", "uebersicht", "tabelle", "pdf", "ha_export"):
        d = nach[k] or {}
        ev = d.get("ev")
        out.append(Zelle(f"geld:{k}:ev_ersparnis", d.get("ev_ersparnis"),
                         None if ev is None else round(ev * 0.30, 2), "ok", "EV × 30 ct derselben Sicht"))
    for k in ("uebersicht", "ha_export", "community"):
        out.append(Zelle(f"geld:{k}:co2", (nach[k] or {}).get("co2"), None, "ok", "N-588"))
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
                # Die eigene Zeile nennt nur Gemessenes (N-628), und ein im Monat an seine Modul-Kinder
                # abgetretenes BKW keine (N-627, ADR-002/P11 — der Monat tritt ab, auch der laufende).
                abgetreten = bool(mx._kinder_von(form, bkw, mx.TAGE_JULI[-1]))
                eigen = mx.tagesmenge(bkw.rate) * 3 if (bkw.zaehler and not abgetreten) else 0.0
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
        # Ein im Monat abgetretenes BKW (Kinder aktiv) gibt sein Segment an die Module — die
        # Monatsregel gilt auch hier (Bauplan PV-Achse T4, Zusatz Master: vor = nach dem Abschluss).
        tw = vor["fakten_tw"] or {}
        bkw_namen = {g.name for g in form.geraete if g.typ == "balkonkraftwerk"
                     and not mx._kinder_von(form, g, mx.TAGE_JUNI[-1])}
        soll_bkw = sum(v for t in mx.TAGE_JUNI for n, v in mx.soll_tag(form, t).je_geraet.items() if n in bkw_namen)
        soll_mod = sum(v for t in mx.TAGE_JUNI for n, v in mx.soll_tag(form, t).je_geraet.items() if n not in bkw_namen)
        z.append(_z("fakten_tageswert:module", tw.get("pv_module") or 0.0, soll_mod, tol=_TOL_TAGE))
        if any(g.typ == "balkonkraftwerk" for g in form.geraete):
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
        if fid in GELD_SICHTEN_FORMEN:
            z += _geld_sichten(nach)
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
    zuordnung: str   # seit dem Bau der PV-Achse nur noch "HA-Bauform S1 (Sammelimport)"
    grund: str


@dataclass(frozen=True)
class Ursache:
    zuordnung: str
    grund: str


#: Die Ursachen der roten Zellen — Stand nach dem Bau der PV-Achse (Bauplan
#: ``~/.claude/plans/bauplan-pv-achse-regelfehler.md``, T1–T7, 04.10.2026; Bericht
#: ``~/.claude/plans/opus-berichte/PV-ACHSE-BAU.md``). Gegen ``737f476d`` waren es 242 Zellen mit
#: neun Ursachen; geheilt sind N-623 (Tag im Aggregat-Fall), N-624 (Teilzeitraum-Marke), K1/N-625
#: (Leistungs-Summe neben der Zählertabelle), K2/N-626 (Teilsumme), „HA-Bauform (c)" + K3/N-627
#: (der Monat tritt ab), K4/N-629 (Vorschau ohne Modul) und K5/N-628 (BKW-Zeile nur gemessen).
#: Erhebung je Zelle: ``opus-berichte/PV-ACHSE-MATRIX.md`` (vorher) und ``PV-ACHSE-BAU.md`` (nachher).
URSACHE: dict[str, Ursache] = {
    "SAMMELIMPORT": Ursache(
        "HA-Bauform S1 (Sammelimport)",
        "folge-prompt-ha-bauform.md (S1-Pflichtpunkt), Handbuch Einstellungen §7.6: der HA-Statistik-"
        "Sammelimport speichert den Anlagenzähler nicht (P7 verbietet das programmatische Füllen) und "
        "verteilt ihn nur auf Module ohne eigenen Wert — ein Balkonkraftwerk ohne Wert bekommt 0, Kinder "
        "unter einem gemessenen BKW einen Anteil. Folgen (gemessen nach dem Bau): Werte je Gerät weichen "
        "ab (z. B. F04 West 270 statt 225, Balkon 0 statt 45), der Jahr-Verlauf füllt die BKW-Gruppe aus "
        "den Tagen (675/676,8 statt 630), F05 nennt nach dem Import 540 statt 630, der Daten-Checker lässt "
        "den Monat aus. Kein Regelfehler der Lesewege, sondern ein fehlender Speicherort",
    ),
}

#: ``Ursache → {(Form, Weg, Invariante): rote Sichten}`` — gemessen, nicht hergeleitet.
ROT: dict[str, dict[tuple[str, str, str], tuple[str, ...]]] = {
    'SAMMELIMPORT': {
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
        ('F05', 'S2', 'I2'): ('cockpit_monat:vor=nach', 'fakten:tageswert=gespeichert', 'Σtage_juni=cockpit_monat',),
        ('F05', 'S2', 'I3'): ('cockpit_jahr:kopf', 'cockpit_monat:nach', 'fakten',),
        ('F05', 'S2', 'I4'): ('fakten:Balkon', 'pdf_string_vergleich:Balkon', 'pv_strings:Balkon',),
        ('F05', 'S2', 'I6'): ('nach:checker',),
        ('F09a-G', 'S2', 'I4'): (
            'fakten:Kind 1', 'fakten:Kind 2', 'fakten:Süd', 'fakten:West', 'pdf_string_vergleich:Kind 1',
            'pdf_string_vergleich:Kind 2', 'pdf_string_vergleich:Süd', 'pdf_string_vergleich:West', 'pv_strings:Kind 1',
            'pv_strings:Kind 2', 'pv_strings:Süd', 'pv_strings:West',
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
for _f in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08a", "F08b", "F09a-G", "F09b-G", "F09c-G",
           "F09a-oG", "F09b-oG", "F09c-oG", "F10", "F11", "F12", "F13a", "F13b", "F14", "F15", "F16"):
    SOLL_UNKLAR[(_f, "S3", "I2", "cockpit_monat:vor=nach")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I3", "cockpit_monat:vor")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I5", "cockpit_monat:vor")] = _U_SA_VOR
    SOLL_UNKLAR[(_f, "S3", "I6", "vor:cockpit_monat")] = _U_SA_VOR
_U_N588 = (
    "N-588 (Auftrag Achsen-Matrix 2, Zusatz F13a): Σ Einzelzähler 21 > Anlagenzähler 19,8 je Sonnentag — der "
    "Unterschied sind Wandlungsverluste. Ob Ersparnis und CO₂ auf dem Eigenverbrauch aus Σ Einzel oder aus dem "
    "Anlagenzähler (abzüglich Verluste) rechnen, legt der Bauplan der HA-Bauform fest. Gemessen, nicht bewertet."
)
for _f in GELD_SICHTEN_FORMEN:
    for _w in ("S1", "S2", "S3"):
        for _k in ("monat", "uebersicht", "tabelle", "pdf", "ha_export"):
            SOLL_UNKLAR[(_f, _w, "I5", f"geld:{_k}:ev_ersparnis")] = _U_N588
        for _k in ("uebersicht", "ha_export", "community"):
            SOLL_UNKLAR[(_f, _w, "I5", f"geld:{_k}:co2")] = _U_N588
# „Soll unklar 2" (BKW-Zeile im laufenden Monat bei Modul-Kindern) ist seit dem Bau der PV-Achse
# (Bauplan T4, 04.10.2026) festes Soll 0: der Monat tritt ab, auch der laufende (N-627) — in `bewerte`.


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


def _haltewert_gleich(ist, gehalten) -> bool:
    if ist is None or gehalten is None:
        return ist is None and gehalten is None
    return abs(float(ist) - float(gehalten)) <= 1e-6


@pytest.mark.parametrize("schluessel", sorted(SOLL_UNKLAR), ids=lambda s: "-".join(s))
async def test_soll_unklar_haltewert(schluessel, _matrix_ordner):
    """Haltewert (HA-Bauform E0): eine „Soll unklar"-Sicht misst, was am 05.10.2026 gemessen wurde
    (``matrix_haltewerte.PV_HALTEWERTE``) — der Umbau ändert sie nicht still. Kein Soll, ein Festwert."""
    assert schluessel in PV_HALTEWERTE, f"{schluessel}: „Soll unklar“ ohne Haltewert"
    fid, weg, inv, sicht = schluessel
    m = await _messung(fid, _teil(weg), _matrix_ordner)
    ist = {x.sicht: x.ist for x in bewerte(fid, weg, inv, m)}.get(sicht)
    assert _haltewert_gleich(ist, PV_HALTEWERTE[schluessel]), (
        f"{schluessel}: gemessen {ist}, festgehalten {PV_HALTEWERTE[schluessel]}")


def test_haltewerte_nur_fuer_soll_unklar():
    """Jeder Haltewert gehört zu einer „Soll unklar"-Sicht — fällt sie heraus, fällt ihr Haltewert mit."""
    assert set(PV_HALTEWERTE) == set(SOLL_UNKLAR), sorted(set(PV_HALTEWERTE) ^ set(SOLL_UNKLAR))


def test_register_zeigt_nur_auf_bestehende_zellen():
    zellen = {(f, w, i) for f in mx.FORMEN for w in WEGE for i in INVARIANTEN}
    assert set(BEKANNT) <= zellen
    assert {k[:3] for k in SOLL_UNKLAR} <= zellen
