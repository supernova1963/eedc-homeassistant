"""Die Heim-Felder am E-Auto in der manuellen Erfassung — N-555 Stufe 2 (Konzept Regel 8).

⚑ **Umgestellt am 26.09.2026 (N-555 Stufe 2).** Bis dahin hieß diese Datei „Phase 2a Etappe
3 — Write-Side-Kanonisierung" und hielt fest: *existiert eine Wallbox, blendet die manuelle
Erfassung „Heim: PV/Netz" am E-Auto aus* (``bedingung_anlage: keine_wallbox``). Das war die
Formular-Hälfte von Entscheidung 1 des Wallbox-Konzepts („die Wallbox ist die kanonische
Quelle"). Das abgenommene Konzept Heimladung/Fahrverbrauch dreht sie (Gernots Modell vom
24.09.): **die Wallbox ist die Summe, ein Auto mit eigener Messung trägt seine eigene
Heimladung, die Wallbox den Rest** (Regel 0 + 2). Ohne die Messung je Auto zählte ein
Dienstwagen an der privaten Wallbox doppelt (F4). Die Felder stehen deshalb an **jedem**
E-Auto; nur an einem **Dienstwagen neben einer dienstlichen Wallbox in Betrieb** fehlen sie
(Regel 3: dort ist die dienstliche Wallbox die dienstliche Ladung).

**Substanz, die bleibt:** Fahrzeug- und Extern-Felder stehen in jedem Fall am E-Auto; die
Wallbox behält ihre Heimladungs-Felder; ohne Anlagen-Kontext (Import) wird nichts
ausgeblendet. Die Doppelzählungs-Sorge von Phase 2a (#262, Streudaten am Auto) trägt jetzt
der Daten-Checker (Regel 7, „Autos zusammen mehr als die Wallbox") — er meldet, er schützt
nicht (E2).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.core.field_definitions import get_felder_fuer_investition

HEIM = ("ladung_pv_kwh", "ladung_netz_kwh", "ladung_kwh")


def _inv(typ: str, *, dienstlich: bool = False, anschaffung: date | None = None):
    """Ein Platzhalter mit genau den Merkmalen, die der Auswerter fragt."""
    ns = SimpleNamespace(typ=typ, parameter={"ist_dienstlich": dienstlich})
    if anschaffung is not None:
        ns.ist_aktiv_im_monat = lambda j, m, a=anschaffung: (j, m) >= (a.year, a.month)
        ns.ist_aktiv_an = lambda tag, a=anschaffung: tag >= a
    return ns


def _felder(typ: str, anlage: list, *, dienstlich: bool = False, **monat) -> set[str]:
    return {
        f["feld"] for f in get_felder_fuer_investition(
            typ, {"ist_dienstlich": dienstlich}, anlage_investitionen=anlage, **monat,
        )
    }


def test_eauto_ohne_wallbox_zeigt_heim_ladefelder():
    """Steckerlader/Schuko (keine Wallbox) → E-Auto trägt die Heimladung selbst."""
    felder = _felder("e-auto", [_inv("e-auto")])
    assert set(HEIM) <= felder
    assert "km_gefahren" in felder
    assert "ladung_extern_kwh" in felder


def test_eauto_mit_wallbox_bietet_heim_ladefelder_an():
    """Regel 8: „Heim: PV/Netz/gesamt" an jedem E-Auto, auch neben einer privaten Wallbox."""
    felder = _felder("e-auto", [_inv("e-auto"), _inv("wallbox")])
    assert set(HEIM) <= felder
    assert "km_gefahren" in felder
    assert "verbrauch_kwh" in felder
    assert "ladung_extern_kwh" in felder
    assert "ladung_extern_euro" in felder


def test_dienstwagen_neben_dienstlicher_wallbox_ohne_heim_ladefelder():
    """Regel 3: die dienstliche Wallbox ist die dienstliche Ladung — keine Heim-Felder."""
    anlage = [_inv("e-auto", dienstlich=True), _inv("wallbox", dienstlich=True)]
    felder = _felder("e-auto", anlage, dienstlich=True)
    assert not (set(HEIM) & felder)
    # Fahrzeug- und Extern-Felder bleiben.
    assert {"km_gefahren", "verbrauch_kwh", "ladung_extern_kwh"} <= felder


def test_dienstwagen_neben_privater_wallbox_behaelt_heim_ladefelder():
    """Seine eigene Messung zieht die Wallbox-Summe um die dienstliche Ladung (Regel 2/3)."""
    anlage = [_inv("e-auto", dienstlich=True), _inv("wallbox")]
    assert set(HEIM) <= _felder("e-auto", anlage, dienstlich=True)


def test_privates_auto_neben_dienstlicher_wallbox_behaelt_heim_ladefelder():
    """Die Bedingung gilt nur am Dienstwagen (``bedingung_anlage_fuer``)."""
    anlage = [_inv("e-auto"), _inv("wallbox", dienstlich=True)]
    assert set(HEIM) <= _felder("e-auto", anlage)


def test_dienstliche_wallbox_nicht_in_betrieb_verdraengt_nicht():
    """Regel 0: „in Betrieb" im betrachteten Monat — vor ihrer Anschaffung gibt es sie nicht."""
    anlage = [
        _inv("e-auto", dienstlich=True),
        _inv("wallbox", dienstlich=True, anschaffung=date(2026, 6, 1)),
    ]
    assert set(HEIM) <= _felder("e-auto", anlage, dienstlich=True, jahr=2026, monat=5)
    assert not (set(HEIM) & _felder("e-auto", anlage, dienstlich=True, jahr=2026, monat=6))


def test_wallbox_felder_unveraendert():
    """Die Wallbox-Form behält ihre Heimladungs-Felder (sie ist die Summe, Regel 0)."""
    felder = _felder("wallbox", [_inv("e-auto"), _inv("wallbox")])
    assert "ladung_kwh" in felder
    assert "ladung_pv_kwh" in felder
    assert "ladevorgaenge" in felder


def test_ohne_anlage_kontext_alle_felder_sichtbar():
    """`anlage_investitionen=None` → bedingung_anlage wird nicht ausgewertet
    (z. B. Import-Kontext) → E-Auto-Heim-Felder bleiben sichtbar, auch am Dienstwagen."""
    felder = {f["feld"] for f in get_felder_fuer_investition("e-auto", {"ist_dienstlich": True})}
    assert set(HEIM) <= felder
