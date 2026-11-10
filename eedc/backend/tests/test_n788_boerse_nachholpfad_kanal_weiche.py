"""N-788 (Päckchen DD, 10.11.2026): der Börsen-Nachholpfad kennt die Kanal-Weiche des Hauptpfads.

``ha_export_bezugspreis._boersenmittel_monat`` paart an einem Kanal-Tag (Mischzeilen, Beginn-Raster) den Börsenpreis der
Stunde ``h`` mit dem Bezug derselben Zeile ``h``; an einem Bestandstag den Preis der Zeile ``h`` (forward) mit dem Bezug
des Backward-Slots ``h + 1``. Der Nachholpfad ``_hole_boerse_nach`` (Abdeckung < 80 %) verschob bis Päckchen DD jeden
nachgeholten Preis auf ``h + 1`` — an einem Kanal-Tag paarte er so den Preis der Vorstunde.

Gezählt am 10.11.2026: Produktiv fester Tarif (der Pfad läuft nur bei dynamischem Tarif), Kopien ohne Kanal-Tage —
Zahlen unverändert.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services import ha_export_bezugspreis as hb

KANAL = date(2026, 6, 10)
BESTAND = date(2026, 6, 20)
PREISE = {h: 10.0 + h for h in range(24)}       # Preis der Wanduhr-Stunde [h, h+1)


@pytest.fixture
def markt(monkeypatch):
    from backend.services import preis_tag, strompreis_markt_service

    async def _fetch(tag, _markt):
        return dict(PREISE) if tag in (KANAL, BESTAND) else None

    monkeypatch.setattr(strompreis_markt_service, "fetch_marktpreise", _fetch)
    monkeypatch.setattr(preis_tag, "markt_der_anlage", lambda _a: "DE")
    monkeypatch.setattr(hb, "_markt_nachgeholt", set())


class _Anlage:
    id = 788


async def test_kanal_tag_paart_dieselbe_wanduhr_stunde_bestandstag_den_backward_slot(markt):
    boerse_je: dict = {}
    geholt = await hb._hole_boerse_nach(None, _Anlage(), 2026, 6, date(2026, 6, 1), date(2026, 6, 30), boerse_je,
                                        {KANAL})
    assert geholt is True
    # Kanal-Tag: Zeile h = [h, h+1) ⇒ Preis der Stunde h, ohne Verschiebung.
    assert [boerse_je[(KANAL, h)] for h in (0, 12, 23)] == [PREISE[0], PREISE[12], PREISE[23]]
    # Bestandstag: Slot h+1 = [h, h+1) ⇒ Preis der Stunde h; Stunde 23 ⇒ Slot 0 des Folgetags.
    assert [boerse_je[(BESTAND, h + 1)] for h in (0, 12, 22)] == [PREISE[0], PREISE[12], PREISE[22]]
    assert boerse_je[(date(2026, 6, 21), 0)] == PREISE[23]
    assert (BESTAND, 0) not in boerse_je        # Slot 0 gehört der Stunde 23 des Vortags — der wurde nicht geholt


def test_nachhol_ziel_wie_der_hauptpfad():
    assert hb._nachhol_ziel(KANAL, 12, {KANAL}) == (KANAL, 12)
    assert hb._nachhol_ziel(BESTAND, 12, {KANAL}) == (BESTAND, 13)
    assert hb._nachhol_ziel(BESTAND, 23, set()) == (date(2026, 6, 21), 0)
    # Ein Bestandspreis, dessen Slot auf einen Kanal-Tag fiele, bleibt draußen (dort trägt jede Stunde ihren eigenen).
    assert hb._nachhol_ziel(date(2026, 6, 9), 23, {KANAL}) is None
