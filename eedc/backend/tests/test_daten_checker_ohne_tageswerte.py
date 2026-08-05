"""Daten-Checker: „noch keine Tageswerte" ist kein „falsche Quelle".

Der Quellen-Status-Check hatte drei Zweige — HA-LTS aktiv, HA-LTS bereit aber
Aggregate aus älterer Quelle, Standalone. Der **vierte** Zustand fehlte: HA ist
erreichbar, es gibt aber **überhaupt keine** ``TagesZusammenfassung`` mit
Stundenwerten. Der fiel in den zweiten Zweig, und dessen Text ist dafür
formatiert, dass eine Zeile existiert::

    „die TagesZusammenfassung vom **?** wurde aber noch aus
     '**unbekannt**' geschrieben"

Das ist eine Behauptung über eine Zeile, die es nicht gibt — und der Satz
schickt den Anwender auf die Suche nach einer falschen *Quelle*, während in
Wahrheit noch **gar nichts** aggregiert ist. Erreichbar ist der Zustand für
jeden frisch eingerichteten Add-on-Anwender in der ersten Stunde, und dauerhaft
für jeden, dessen kWh-Zähler nicht zugeordnet sind.

Gefunden beim Messen der Fehlermeldung von kaba-kakao (Forum T89667/98), aber
**unabhängig von seinem Fall**: sein Container erreicht die Recorder-DB gar
nicht und landet im Standalone-Zweig. Dieser Befund trifft den HA-Add-on-Betrieb.

Der Check liest ausschließlich ``self.db`` und den HA-Statistics-Dienst — beide
werden gestellt, damit der Test ohne DB und ohne HA läuft
([[feedback_tests_ci_hermetisch]]).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from backend.models.anlage import Anlage
from backend.services.daten_checker import CheckKategorie, CheckSeverity, DatenChecker


class _FakeHaStats:
    """Nur `is_available` wird von diesem Check gelesen."""

    def __init__(self, verfuegbar: bool):
        self._v = verfuegbar

    @property
    def is_available(self) -> bool:
        return self._v


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDb:
    """Liefert die eine Zeile, die der Check per `scalar_one_or_none` erwartet."""

    def __init__(self, row=None):
        self._row = row

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._row)


def _patch(monkeypatch, verfuegbar: bool) -> None:
    import backend.services.ha_statistics_service as ha_mod
    monkeypatch.setattr(
        ha_mod, "get_ha_statistics_service", lambda: _FakeHaStats(verfuegbar)
    )


def _tz_zeile(source: str):
    """TagesZusammenfassung-Attrappe mit Herkunftsvermerk."""
    return SimpleNamespace(
        datum=date(2026, 8, 4),
        source_provenance={"pv_erzeugung_kwh": {"source": source}},
    )


async def _befund(db, monkeypatch, *, ha_verfuegbar: bool):
    _patch(monkeypatch, ha_verfuegbar)
    checker = DatenChecker(db=db)
    ergebnisse = await checker._check_datenquelle_status(Anlage(anlagenname="T"))
    assert len(ergebnisse) == 1
    return ergebnisse[0]


async def test_ohne_jede_tageszeile_meldet_der_check_genau_das(monkeypatch):
    """Der reparierte Fall: keine Zeile ⇒ „noch keine Tageswerte", kein „?"."""
    b = await _befund(_FakeDb(None), monkeypatch, ha_verfuegbar=True)

    assert b.kategorie == CheckKategorie.DATENQUELLE_STATUS.value
    assert b.schwere == CheckSeverity.INFO.value
    assert b.meldung == "Noch keine Tageswerte aggregiert"
    # Der eigentliche Beleg: die alten Platzhalter dürfen nicht mehr auftauchen.
    assert "vom ?" not in b.details
    assert "unbekannt" not in b.details
    # Und der Hinweis muss auflösbar sein (Daten-Checker-Doktrin: kein
    # Hinweis ohne Weg) — Zuordnung der kWh-Zähler bzw. Nachfüllen.
    assert "Datenquellen" in b.details
    assert "kWh" in b.details
    assert b.link


async def test_zeile_aus_aelterer_quelle_meldet_weiterhin_die_quelle(monkeypatch):
    """Gegenprobe: der Zweig, für den der alte Text gedacht war, bleibt intakt —
    mit echtem Datum und echter Quelle statt Platzhaltern."""
    b = await _befund(
        _FakeDb(_tz_zeile("auto:monatsabschluss")), monkeypatch, ha_verfuegbar=True
    )

    assert b.meldung == "HA-Statistics-Pfad bereit, Aggregate aus älterer Quelle"
    assert "2026-08-04" in b.details
    assert "auto:monatsabschluss" in b.details
    assert "vom ?" not in b.details


async def test_zeile_aus_ha_statistics_bleibt_ok(monkeypatch):
    """Gegenprobe: der OK-Zweig ist von der Reparatur unberührt."""
    b = await _befund(
        _FakeDb(_tz_zeile("external:ha_statistics:hourly")),
        monkeypatch,
        ha_verfuegbar=True,
    )

    assert b.schwere == CheckSeverity.OK.value
    assert b.meldung == "HA-Statistics als Source-of-Truth aktiv"


async def test_ohne_ha_bleibt_es_der_standalone_hinweis(monkeypatch):
    """Gegenprobe: ohne erreichbare Recorder-DB gilt weiterhin der
    Standalone-Zweig — auch dann, wenn es keine Tageszeile gibt. Der neue
    Zweig darf ihn NICHT überschreiben, sonst verlöre der Container-Nutzer
    die einzige Meldung, die seine Lage beschreibt."""
    b = await _befund(_FakeDb(None), monkeypatch, ha_verfuegbar=False)

    assert b.meldung == "Standalone-Modus aktiv (kein HA-LTS)"
