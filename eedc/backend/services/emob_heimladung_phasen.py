"""Die Phasen von ``eauto_wirtschaftlichkeit.entscheide_emob_heimladung`` (N-555, Konzept Regel 0–3, 6).

RF-24 (Serie „Funktion vor Datei", 14.10.2026): die eine Funktion ist ein Orchestrator geworden; ihre Phasen
stehen hier, weil ``services/eauto_wirtschaftlichkeit.py`` mit ihnen über netto 900 gestiegen wäre
(Nebenkriterium Datei). Reiner Umzug — die Regel steht weiter an EINER Stelle: ``entscheide_emob_heimladung``
ist der einzige Einstieg, die Phasen sind privat und werden von nirgends sonst gerufen. Bausteine
(Dataclasses, Konstanten, ``eigene_messung_des_autos``, ``summiere_emob_quelle``, ``waehle_extern_paar``)
bleiben in ``eauto_wirtschaftlichkeit`` und werden von dort gelesen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Optional

from backend.core.field_definitions import traegt_heimlade_wert
from backend.services.eauto_wirtschaftlichkeit import (
    ART_GEMESSEN,
    ART_NULL,
    ART_REST,
    ART_SCHAETZUNG,
    QUELLE_EAUTO,
    QUELLE_LEER,
    QUELLE_NULL,
    QUELLE_SCHAETZUNG,
    QUELLE_WALLBOX,
    AutoHeimladung,
    DienstlicheLadung,
    EmobLadungPool,
    _hat_heim_pv_netz,
    dienstliche_ladung_der_zeile,
    eauto_zeile_ohne_altwert,
    eigene_messung_des_autos,
    summiere_emob_quelle,
    waehle_extern_paar,
)


# ── RF-24 (Serie „Funktion vor Datei"): die Phasen von `entscheide_emob_heimladung` ──
# Reiner Umzug: jede Phase trägt ihre Verzweigungen mit, Reihenfolge und Rechenausdrücke
# wie bis 14.10.2026 im Rumpf der einen Funktion. Die Regel steht weiter an EINER Stelle
# (Konzept Regel 6) — `entscheide_emob_heimladung` ist ihr einziger Einstieg, die Phasen
# sind privat und werden von nirgends sonst gerufen.


@dataclass
class _HeimladeEingang:
    """Die Eingänge EINES Monats nach dem Auspacken — gelesen von jeder Phase."""
    eauto_je_inv: dict
    wallbox_zeilen: list
    wallbox_in_betrieb: Any
    dienstwagen_je_inv: dict
    dwb_je_inv: dict
    dienstliche_wallbox_in_betrieb: Any
    dienstwagen_in_betrieb: list
    heim_gesamt: frozenset
    quellen: frozenset
    bloecke: dict
    pv_quote: Optional[float]
    wallbox_ids: Optional[Iterable[int]]
    speicher_quote: Optional[float]

    def hat_quelle(self, inv_id: int) -> bool:
        return any(_inv_der_quelle(q) == inv_id for q in self.quellen)


def _eingaenge_des_monats(
    *,
    eauto_je_inv, wallbox_zeilen, wallbox_in_betrieb, dienstwagen_je_inv,
    dienstliche_wallbox_je_inv, dienstliche_wallbox_in_betrieb, heimlade_quellen,
    pv_quote, heim_gesamt, wallbox_ids, eauto_in_betrieb, dienstwagen_in_betrieb,
    bloecke, speicher_quote,
) -> _HeimladeEingang:
    """Die Argumente von ``entscheide_emob_heimladung`` ausgepackt (Voreinstellungen ``None``)."""
    eauto_je_inv = dict(eauto_je_inv or {})
    for _inv_id in (eauto_in_betrieb or ()):
        eauto_je_inv.setdefault(_inv_id, {})
    dienstwagen_in_betrieb = list(dienstwagen_in_betrieb or ())
    wallbox_zeilen = [z or {} for z in (wallbox_zeilen or ())]
    dienstwagen_je_inv = dict(dienstwagen_je_inv or {})
    dwb_je_inv = dict(dienstliche_wallbox_je_inv or {})
    if wallbox_in_betrieb is None:
        wallbox_in_betrieb = bool(wallbox_zeilen)
    if dienstliche_wallbox_in_betrieb is None:
        dienstliche_wallbox_in_betrieb = bool(dwb_je_inv)
    heim_gesamt = frozenset(heim_gesamt or ())
    quellen = frozenset(heimlade_quellen or ())
    bloecke = dict(bloecke or {})
    # Stufe 3: ein Dienstwagen mit Blöcken, aber ohne Monatszeile, hat trotzdem eine Messung.
    for _inv_id in dienstwagen_in_betrieb:
        if _inv_id in bloecke:
            dienstwagen_je_inv.setdefault(_inv_id, {})
    return _HeimladeEingang(
        eauto_je_inv=eauto_je_inv,
        wallbox_zeilen=wallbox_zeilen,
        wallbox_in_betrieb=wallbox_in_betrieb,
        dienstwagen_je_inv=dienstwagen_je_inv,
        dwb_je_inv=dwb_je_inv,
        dienstliche_wallbox_in_betrieb=dienstliche_wallbox_in_betrieb,
        dienstwagen_in_betrieb=dienstwagen_in_betrieb,
        heim_gesamt=heim_gesamt,
        quellen=quellen,
        bloecke=bloecke,
        pv_quote=pv_quote,
        wallbox_ids=wallbox_ids,
        speicher_quote=speicher_quote,
    )


def _inv_der_quelle(q):
    return q[0] if isinstance(q, (tuple, list)) and q else None


def _quellen_der_privaten_heimladung(e: _HeimladeEingang) -> tuple[bool, list]:
    """``(wallbox_quelle, quellen_privat)`` — wessen Quelle ist eine Wallbox-Quelle?"""
    quellen = e.quellen
    # Quellen, die über die PRIVATE Heimladung etwas sagen (Regel 1: „0" statt „leer").
    if e.wallbox_ids is not None:
        _wb_ids = set(e.wallbox_ids)
        wallbox_quelle = any(_inv_der_quelle(q) in _wb_ids for q in quellen)
        quellen_privat = [
            q for q in quellen
            if _inv_der_quelle(q) in _wb_ids or _inv_der_quelle(q) in e.eauto_je_inv
        ]
    else:
        auto_ids = set(e.eauto_je_inv) | set(e.dienstwagen_je_inv)
        wallbox_quelle = any(_inv_der_quelle(q) not in auto_ids for q in quellen)
        quellen_privat = [
            q for q in quellen if _inv_der_quelle(q) not in e.dienstwagen_je_inv
        ]
    return wallbox_quelle, quellen_privat


def _wallbox_des_monats(
    e: _HeimladeEingang, wallbox_quelle: bool,
) -> tuple[EmobLadungPool, bool, Optional[float]]:
    """``(wb, wallbox_hat_wert, wb_pv_anteil)`` — die Summe der privaten Wallboxen (Regel 0)."""
    wb = summiere_emob_quelle(e.wallbox_zeilen)
    wallbox_hat_wert = bool(
        e.wallbox_in_betrieb and (
            any(traegt_heimlade_wert("wallbox", z) for z in e.wallbox_zeilen)
            or wallbox_quelle
        )
    )
    wb_pv_anteil = (wb.pv_kwh / wb.ladung_kwh) if wb.ladung_kwh > 0 else None
    return wb, wallbox_hat_wert, wb_pv_anteil


def _eigene_messungen_privat(
    e: _HeimladeEingang, wb_pv_anteil: Optional[float],
) -> tuple[dict[int, tuple[float, float]], bool]:
    """``(gemessen, anteil_abgeleitet)`` der privaten Autos (Regel 2 Schritt 1)."""
    abgeleitet = False

    # ── Schritt 1: eigene Messungen der privaten Autos ────────────────────────
    gemessen: dict[int, tuple[float, float]] = {}
    for inv_id, zeile in e.eauto_je_inv.items():
        m = eigene_messung_des_autos(
            zeile, wallbox_in_betrieb=e.wallbox_in_betrieb,
            heim_gesamt=inv_id in e.heim_gesamt, hat_quelle=e.hat_quelle(inv_id),
            wallbox_pv_anteil=wb_pv_anteil if e.wallbox_in_betrieb else None,
            pv_quote=e.pv_quote,
            block=e.bloecke.get(inv_id),
        )
        if m is not None:
            gemessen[inv_id] = (m[0], m[1])
            abgeleitet = abgeleitet or m[2]
    return gemessen, abgeleitet


def _dienstliche_ladung_des_monats(
    e: _HeimladeEingang, wb_pv_anteil: Optional[float],
) -> tuple[dict[int, DienstlicheLadung], dict[int, tuple[float, float]], set[int]]:
    """``(dienstlich_je_inv, dw_gemessen, dw_ungemessen)`` — Regel 3."""
    # ── Regel 3: Dienstwagen und dienstliche Wallbox ───────────────────────────
    dienstlich_je_inv: dict[int, DienstlicheLadung] = {}
    dw_gemessen: dict[int, tuple[float, float]] = {}
    dw_ungemessen: set[int] = set()
    if e.dienstliche_wallbox_in_betrieb:
        # Die dienstliche Wallbox ist die dienstliche Ladung; Felder und Schätzung der
        # Dienstwagen zählen daneben nicht — auch keine alten oder importierten Werte.
        for inv_id, zeile in e.dwb_je_inv.items():
            dienstlich_je_inv[inv_id] = dienstliche_ladung_der_zeile(zeile)
    else:
        for inv_id, zeile in e.dwb_je_inv.items():  # außer Betrieb übergeben: wie bisher
            dienstlich_je_inv[inv_id] = dienstliche_ladung_der_zeile(zeile)
        _dienstwagen_ohne_dienstliche_wallbox(
            e, wb_pv_anteil, dienstlich_je_inv, dw_gemessen, dw_ungemessen,
        )
    return dienstlich_je_inv, dw_gemessen, dw_ungemessen


def _dienstwagen_ohne_dienstliche_wallbox(
    e: _HeimladeEingang,
    wb_pv_anteil: Optional[float],
    dienstlich_je_inv: dict[int, DienstlicheLadung],
    dw_gemessen: dict[int, tuple[float, float]],
    dw_ungemessen: set[int],
) -> None:
    """Regel 3 ohne dienstliche Wallbox in Betrieb: die Dienstwagen selbst (schreibt in die drei Sammler)."""
    for inv_id, zeile in e.dienstwagen_je_inv.items():
        m = eigene_messung_des_autos(
            zeile, wallbox_in_betrieb=e.wallbox_in_betrieb,
            heim_gesamt=inv_id in e.heim_gesamt, hat_quelle=e.hat_quelle(inv_id),
            wallbox_pv_anteil=wb_pv_anteil if e.wallbox_in_betrieb else None,
            pv_quote=None,  # wie bisher: eine Dienstwagen-Zeile wird nie abgeleitet
            block=e.bloecke.get(inv_id),
        )
        if m is not None:
            dienstlich_je_inv[inv_id] = DienstlicheLadung(m[0], m[1], True)
            dw_gemessen[inv_id] = (m[0], m[1])
            continue
        # Ohne eigene Messung: Fahrverbrauch als Schätzung, als Netzstrom (wie bisher);
        # sie wird NIE vom Rest abgezogen — sie enthält auch das Laden beim Arbeitgeber.
        # Steht statt des Fahrverbrauchs nur ein ALTER Gesamtwert da (Herkunft
        # unbekannt, neben der Wallbox keine eigene Messung), ist er die Basis der
        # Schätzung: im Bestand ist das meist der umgebuchte Fahrverbrauch vom
        # 01.–09.05.2026 (Regel 5), und die dienstliche Menge bleibt wie in Stufe 1.
        zeile = zeile or {}
        basis = float(zeile.get("verbrauch_kwh") or 0) or float(zeile.get("ladung_kwh") or 0)
        dienstlich_je_inv[inv_id] = DienstlicheLadung(0.0, max(0.0, basis), False)
        dw_ungemessen.add(inv_id)
    # Ein Dienstwagen in Betrieb OHNE Monatszeile hat keine eigene Messung (Regel 3,
    # Community E3, Master 26.09.): er zählt zu `dienstwagen_ungemessen` — wo er lädt,
    # ist nicht feststellbar. Keine dienstliche Menge (sein Fahrverbrauch ist unbekannt,
    # also 0), kein Abzug vom Rest.
    for inv_id in e.dienstwagen_in_betrieb:
        if inv_id not in e.dienstwagen_je_inv:
            dw_ungemessen.add(inv_id)


def _rest_der_wallbox(
    wb: EmobLadungPool,
    wallbox_hat_wert: bool,
    gemessen: dict[int, tuple[float, float]],
    dw_gemessen: dict[int, tuple[float, float]],
) -> tuple[float, float]:
    """``(rest_pv, rest_netz)`` — Regel 2 Schritt 2."""
    # ── Schritt 2: der Rest der Wallbox ───────────────────────────────────────
    rest_pv = rest_netz = 0.0
    if wallbox_hat_wert:
        messung_pv = sum(p for p, _ in gemessen.values()) + sum(p for p, _ in dw_gemessen.values())
        messung = messung_pv + sum(n for _, n in gemessen.values()) + sum(
            n for _, n in dw_gemessen.values()
        )
        rest = max(0.0, wb.ladung_kwh - messung)
        rest_pv = min(max(0.0, wb.pv_kwh - messung_pv), rest)
        rest_netz = rest - rest_pv
    return rest_pv, rest_netz


@dataclass
class _AutosDesMonats:
    """Schritt 3 (bzw. Regel 1): die Heimladung je privatem Auto und was dabei entschieden wurde."""
    je_auto: dict[int, AutoHeimladung]
    schaetzung: dict[int, tuple[float, float]]
    rest_zugeordnet: bool
    nur_wallbox: bool
    abgeleitet: bool


def _autos_ohne_messung(
    e: _HeimladeEingang,
    gemessen: dict[int, tuple[float, float]],
    wallbox_hat_wert: bool,
    rest_pv: float,
    rest_netz: float,
) -> _AutosDesMonats:
    """Regel 2 Schritt 3 (Wallbox trägt einen Wert) bzw. Regel 1 (sonst)."""
    # ── Schritt 3 (bzw. Regel 1): die privaten Autos ohne eigene Messung ──────
    je_auto: dict[int, AutoHeimladung] = {
        inv_id: AutoHeimladung(p, n, ART_GEMESSEN) for inv_id, (p, n) in gemessen.items()
    }
    empfaenger = [i for i in e.eauto_je_inv if i not in gemessen]
    schaetzung: dict[int, tuple[float, float]] = {}
    rest_zugeordnet = False
    abgeleitet = False
    nur_wallbox = not e.eauto_je_inv and not e.dienstwagen_je_inv and not any(
        True for _ in e.dienstwagen_in_betrieb
    )
    if wallbox_hat_wert:
        rest_zugeordnet = _rest_an_die_autos(e, empfaenger, nur_wallbox, rest_pv, rest_netz, je_auto)
    else:
        abgeleitet = _schaetzung_ohne_wallbox_wert(e, empfaenger, je_auto, schaetzung)
    return _AutosDesMonats(je_auto, schaetzung, rest_zugeordnet, nur_wallbox, abgeleitet)


def _rest_an_die_autos(
    e: _HeimladeEingang,
    empfaenger: list[int],
    nur_wallbox: bool,
    rest_pv: float,
    rest_netz: float,
    je_auto: dict[int, AutoHeimladung],
) -> bool:
    """Schritt 3: der Rest nach km an die privaten Autos ohne Messung (E6) — ``rest_zugeordnet``."""
    rest_zugeordnet = False
    if nur_wallbox:
        # W-1: keine Fahrzeuge angelegt ⇒ die Wallbox ist das private Auto.
        rest_zugeordnet = True
    elif empfaenger:
        rest_zugeordnet = True
        km = {
            i: max(0.0, float((e.eauto_je_inv[i] or {}).get("km_gefahren") or 0))
            for i in empfaenger
        }
        km_summe = sum(km.values())
        for i in empfaenger:
            f = km[i] / km_summe if km_summe > 0 else 1.0 / len(empfaenger)
            je_auto[i] = AutoHeimladung(rest_pv * f, rest_netz * f, ART_REST)
    return rest_zugeordnet


def _schaetzung_ohne_wallbox_wert(
    e: _HeimladeEingang,
    empfaenger: list[int],
    je_auto: dict[int, AutoHeimladung],
    schaetzung: dict[int, tuple[float, float]],
) -> bool:
    """Regel 1: ohne Wert der Wallbox ⇒ 0 oder der Fahrverbrauch als Schätzung — ``anteil_abgeleitet``."""
    pv_quote = e.pv_quote
    abgeleitet = False
    for i in empfaenger:
        zeile = e.eauto_je_inv[i] or {}
        if traegt_heimlade_wert("e-auto", zeile):
            # z. B. ein alter Gesamtwert neben einer (leeren) Wallbox: über die
            # Heimladung ist etwas bekannt (Regel 1) — keine Schätzung.
            je_auto[i] = AutoHeimladung(0.0, 0.0, ART_NULL)
            continue
        fahrverbrauch = float(zeile.get("verbrauch_kwh") or 0)
        if fahrverbrauch > 0:
            pv = fahrverbrauch * pv_quote if pv_quote is not None else 0.0
            schaetzung[i] = (pv, fahrverbrauch - pv)
            je_auto[i] = AutoHeimladung(pv, fahrverbrauch - pv, ART_SCHAETZUNG)
            abgeleitet = abgeleitet or pv_quote is not None
        else:
            je_auto[i] = AutoHeimladung(0.0, 0.0, ART_NULL)
    return abgeleitet


def _speicher_je_auto(e: _HeimladeEingang, je_auto: dict[int, AutoHeimladung]) -> None:
    """N-569-Ergänzung: ``speicher_kwh`` je privatem Auto (nur Ausweis) — ersetzt die Einträge an Ort und Stelle."""
    speicher_quote = e.speicher_quote
    # ── N-569-Ergänzung: davon aus dem Speicher je privatem Auto (nur Ausweis) ───
    # Mit Blöcken: ihr Speicherteil, der Teil ohne ableitbare Stunde mit dem Tagesanteil;
    # sonst Ladung × Tagesanteil — je Auto nie mehr als sein PV-Teil (Teilmenge, Anhang E).
    for _i, _a in list(je_auto.items()):
        _b = e.bloecke.get(_i) if _i not in e.dienstwagen_je_inv else None
        _genutzt = _b is not None and not _hat_heim_pv_netz(e.eauto_je_inv.get(_i))
        if _genutzt and (_b.speicher_kwh is not None or speicher_quote is not None):
            _sp = (_b.speicher_kwh or 0.0) + _b.kwh_ohne_pv * (speicher_quote or 0.0)
        elif not _genutzt and speicher_quote is not None:
            _sp = _a.ladung_kwh * speicher_quote
        else:
            continue
        je_auto[_i] = replace(_a, speicher_kwh=max(0.0, min(_a.pv_kwh, _sp)))


def _quelle_des_monats(
    e: _HeimladeEingang,
    wb: EmobLadungPool,
    wallbox_hat_wert: bool,
    gemessen: dict[int, tuple[float, float]],
    schaetzung: dict[int, tuple[float, float]],
    quellen_privat: list,
) -> str:
    """``pool.quelle`` — was den Monat **bestimmt** (nicht, woraus der Topf besteht)."""
    hat_messung = any(p + n > 0 for p, n in gemessen.values())
    if wallbox_hat_wert and wb.ladung_kwh > 0:
        name = QUELLE_WALLBOX
    elif hat_messung:
        name = QUELLE_EAUTO
    elif schaetzung:
        name = QUELLE_SCHAETZUNG
    elif (
        wallbox_hat_wert or gemessen
        or any(traegt_heimlade_wert("e-auto", z) for z in e.eauto_je_inv.values())
        or quellen_privat
    ):
        name = QUELLE_NULL
    else:
        name = QUELLE_LEER
    return name


def _topf_des_monats(
    e: _HeimladeEingang,
    wb: EmobLadungPool,
    autos: _AutosDesMonats,
    rest_pv: float,
    rest_netz: float,
    name: str,
) -> EmobLadungPool:
    """Der Topf: die private Heimladung (Regel 3, G1) mit dem Extern-Paar und der Quelle."""
    # ── der Topf: die private Heimladung = Σ der privaten Autos (Regel 3, G1) ───
    # In JEDEM Fall, auch wenn die Wallbox über 0 geladen hat: eigene Messungen,
    # zugeordneter Rest und Schätzungen. Gast (nicht zugeordneter Rest) und gemessene
    # Dienstwagen stehen nicht darin — acht Leser (CO₂, Cockpit, PV-Anteil, HA-Anlagen-
    # sensoren, Jahresbericht, laufender Monat, Vorjahr, Community-E-Auto-Seite) fragen
    # „was hat dem Haushalt genützt?" und lesen genau diese Größe. ⛔ Nicht auf die
    # Wallbox drehen: so stand es im angehaltenen Bau vom 26.09. (Topf = Wallbox) und
    # zählte Gast und Dienstwagen in allen acht still als Ersparnis (Fable-Runde 7b).
    # Die Messung der Wallbox (Regel 0) trägt ihren eigenen Namen: ``wallbox_summe``.
    # Sind die Autos zusammen mehr als die Wallbox (E2), rechnen sie mit ihren Werten
    # weiter (Rest 0), der Daten-Checker meldet den Widerspruch (Regel 7).
    pool_pv = sum(a.pv_kwh for a in autos.je_auto.values())
    pool_netz = sum(a.netz_kwh for a in autos.je_auto.values())
    if autos.nur_wallbox and autos.rest_zugeordnet:
        # W-1: der Rest (= die ganze Wallbox) ist die private Heimladung.
        pool_pv += rest_pv
        pool_netz += rest_netz

    # Extern bleibt orthogonal (unverändert): das Paar kommt aus der Quelle mit den
    # höheren externen Kosten — die eine Regel, `waehle_extern_paar`.
    ea = summiere_emob_quelle(
        eauto_zeile_ohne_altwert(
            z, wallbox_in_betrieb=e.wallbox_in_betrieb, heim_gesamt=i in e.heim_gesamt,
        )
        for i, z in e.eauto_je_inv.items()
    )
    extern_kwh, extern_euro = waehle_extern_paar(
        wb.extern_kwh, wb.extern_euro, ea.extern_kwh, ea.extern_euro,
    )

    return EmobLadungPool(
        ladung_kwh=pool_pv + pool_netz,
        pv_kwh=pool_pv,
        netz_kwh=pool_netz,
        extern_kwh=extern_kwh,
        extern_euro=extern_euro,
        ladevorgaenge=max(wb.ladevorgaenge, ea.ladevorgaenge),
        quelle=name,
    )


def _bloecke_der_messungen(
    e: _HeimladeEingang,
    gemessen: dict[int, tuple[float, float]],
    dw_gemessen: dict[int, tuple[float, float]],
) -> dict:
    """``bloecke_je_auto``: die Ladeblöcke, die in diesem Monat die Messung eines Autos sind."""
    return {
        i: b for i, b in e.bloecke.items()
        if (i in gemessen or i in dw_gemessen) and not _hat_heim_pv_netz(
            e.eauto_je_inv.get(i) if i in e.eauto_je_inv else e.dienstwagen_je_inv.get(i)
        )
    }
