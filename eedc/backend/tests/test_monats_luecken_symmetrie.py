"""
Symmetrie-Test R20-2: Backend-Lücken-Ableitung == Frontend `lib/monatsLuecken.ts`.

Der Backend-Endpoint `GET /monatsabschluss/naechster` und die Frontend-
Tabellen-Färbung MÜSSEN denselben „frühesten offenen Monat" liefern (§7-Invariante
„eine Quelle"). Vorher war der Endpoint blind für Binnen-Lücken (naiv „letzter+1")
→ Status-Fusszeile „alle abgeschlossen" widersprach dem Monatsdaten-Block
„nächster offener: Jan 2026" ([[feedback_aggregations_drift]]).

Diese Fixtures sind 1:1 aus `frontend/src/lib/monatsLuecken.test.ts` gespiegelt;
die erwarteten Ergebnisse müssen wortgleich sein — driftet eine Seite, bricht hier.
"""

from datetime import date

from backend.api.routes.monatsabschluss.views import get_naechster_monat
from backend.core.monats_luecken import (
    aus_monat_index,
    ermittle_fehlende_monate,
    ermittle_start_anker,
    monat_index,
    naechster_offener_monat,
    naechster_offener_monat_fuer,
)
from backend.models import Anlage, Investition, Monatsdaten


def _bereich(start: tuple[int, int], ende: tuple[int, int]) -> set[tuple[int, int]]:
    """Alle Monate von start bis ende (inkl.) als Menge."""
    return {aus_monat_index(i) for i in range(monat_index(*start), monat_index(*ende) + 1)}


# ── monat_index / aus_monat_index (== monatIndex / ausMonatIndex) ──────────────


def test_monat_index_ist_umkehrbar_und_chronologisch():
    assert monat_index(2026, 1) < monat_index(2026, 2)
    assert monat_index(2025, 12) + 1 == monat_index(2026, 1)  # Jahresgrenze
    assert aus_monat_index(monat_index(2024, 7)) == (2024, 7)


# ── ermittle_start_anker (== ermittleStartAnker) ───────────────────────────────


def test_start_anker_nimmt_fruehestes_investitions_anschaffungsdatum():
    assert ermittle_start_anker(
        anschaffungsdaten=[date(2023, 12, 1), date(2023, 6, 1), date(2025, 1, 1), None],
        anlage_installationsdatum=None,
        vorhandene={(2024, 1)},
    ) == (2023, 6)


def test_start_anker_faellt_auf_anlage_installationsdatum_zurueck():
    assert ermittle_start_anker(
        anschaffungsdaten=[None],
        anlage_installationsdatum=date(2022, 4, 1),
        vorhandene={(2023, 1)},
    ) == (2022, 4)


def test_start_anker_faellt_zuletzt_auf_frueheste_datenzeile_zurueck():
    assert ermittle_start_anker(
        anschaffungsdaten=[],
        anlage_installationsdatum=None,
        vorhandene={(2024, 5), (2024, 3), (2024, 9)},
    ) == (2024, 3)


def test_start_anker_ist_none_ohne_quelle():
    assert ermittle_start_anker([], None, set()) is None


# ── ermittle_fehlende_monate (== ermittleFehlendeMonate) ───────────────────────


def test_fehlende_monate_findet_innere_luecken_demo_fall():
    # Bereich 2023/06 … 2026/06 (heute=2026/07), alles vorhanden außer Jan–Mär 2026.
    vorhandene = {m for m in _bereich((2023, 6), (2026, 6)) if not (m[0] == 2026 and m[1] in (1, 2, 3))}
    assert ermittle_fehlende_monate(vorhandene, (2023, 6), (2026, 7)) == [
        (2026, 1),
        (2026, 2),
        (2026, 3),
    ]


def test_fehlende_monate_schliesst_laufenden_monat_aus():
    # Bereich 2026/05 … 2026/06 → nur Juni fehlt, Juli (heute) NICHT.
    assert ermittle_fehlende_monate({(2026, 5)}, (2026, 5), (2026, 7)) == [(2026, 6)]


def test_fehlende_monate_findet_nachlaufende_luecken():
    assert ermittle_fehlende_monate({(2026, 3)}, (2026, 3), (2026, 7)) == [
        (2026, 4),
        (2026, 5),
        (2026, 6),
    ]


def test_fehlende_monate_leer_bei_lueckenlos():
    assert ermittle_fehlende_monate({(2026, 4), (2026, 5)}, (2026, 4), (2026, 6)) == []


def test_fehlende_monate_leer_ohne_anker():
    assert ermittle_fehlende_monate({(2026, 1)}, None, (2026, 7)) == []


# ── naechster_offener_monat (== naechsterOffenerMonat, EINE Quelle) ────────────


def test_naechster_offener_liefert_frueheste_innere_luecke_nicht_letzter_plus_1():
    # Naive Backend-Logik hätte auf 2026/07 (letzter+1) gezielt; korrekt = Jan 2026.
    vorhandene = {m for m in _bereich((2023, 6), (2026, 6)) if not (m[0] == 2026 and m[1] in (1, 2, 3))}
    assert naechster_offener_monat(vorhandene, (2023, 6), (2026, 7)) == (2026, 1)


def test_naechster_offener_ist_none_bei_lueckenlos():
    assert naechster_offener_monat({(2026, 4), (2026, 5)}, (2026, 4), (2026, 6)) is None


# ── naechster_offener_monat_fuer (Voll-Aufruf wie im Endpoint) ─────────────────


def test_voll_aufruf_binnen_luecke():
    """Endpoint-Pfad: Anker aus Investitions-Datum + Binnen-Lücke → früheste Lücke."""
    vorhandene = {m for m in _bereich((2023, 6), (2026, 6)) if not (m[0] == 2026 and m[1] in (1, 2, 3))}
    assert naechster_offener_monat_fuer(
        vorhandene=vorhandene,
        anschaffungsdaten=[date(2023, 6, 1)],
        anlage_installationsdatum=None,
        heute=date(2026, 7, 19),
    ) == (2026, 1)


def test_voll_aufruf_keine_daten_startet_am_anker():
    """Brandneue Anlage: keine Datenzeilen, Anker = Installationsdatum → dessen Monat."""
    assert naechster_offener_monat_fuer(
        vorhandene=set(),
        anschaffungsdaten=[],
        anlage_installationsdatum=date(2026, 4, 1),
        heute=date(2026, 7, 19),
    ) == (2026, 4)


def test_voll_aufruf_lueckenlos_ist_none():
    """Lückenloser Bereich bis Vormonat → None („alle abgeschlossen")."""
    assert naechster_offener_monat_fuer(
        vorhandene=_bereich((2026, 1), (2026, 6)),
        anschaffungsdaten=[date(2026, 1, 1)],
        anlage_installationsdatum=None,
        heute=date(2026, 7, 19),
    ) is None


def test_voll_aufruf_nur_aktueller_monat_offen_ist_none():
    """Nur der laufende Monat wäre 'offen' → None (heute nie fällig)."""
    assert naechster_offener_monat_fuer(
        vorhandene=_bereich((2026, 1), (2026, 6)),
        anschaffungsdaten=[date(2026, 1, 1)],
        anlage_installationsdatum=None,
        heute=date(2026, 7, 19),
    ) is None


# ── Route-Bestandsschutz: Endpoint findet Binnen-Lücke (nicht letzter+1) ───────


async def test_endpoint_findet_binnen_luecke_nicht_letzter_plus_1(db):
    """Route-Ebene: Monatsdaten mit einer frühen Binnen-Lücke (2020-03).

    Alle Monate liegen weit in der Vergangenheit → das Ergebnis ist unabhängig
    von `date.today()`. Der frühere naive Endpoint hätte auf 'letzter+1' (2020-06)
    gezielt und die echte Lücke 2020-03 verschluckt (R20-2)."""
    anlage = Anlage(anlagenname="Lücke", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2020, 1, 1), leistung_kwp=10.0,
    ))
    for monat in (1, 2, 4, 5):  # 2020-03 fehlt (Binnen-Lücke)
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2020, monat=monat,
            einspeisung_kwh=400.0, netzbezug_kwh=300.0,
        ))
    await db.flush()

    resp = await get_naechster_monat(anlage.id, db)
    assert resp is not None
    assert (resp.jahr, resp.monat) == (2020, 3)


async def test_endpoint_none_bei_lueckenlos_bis_vormonat(db):
    """Lückenlos vom Anker bis vor 'heute' → None ('alle abgeschlossen')."""
    heute = date.today()
    anlage = Anlage(anlagenname="Voll", leistung_kwp=10.0, latitude=48.0)
    db.add(anlage)
    await db.flush()
    # Anker = Vor-Vormonat; fülle bis Vormonat(heute) lückenlos.
    start_idx = monat_index(heute.year, heute.month) - 3
    ende_idx = monat_index(heute.year, heute.month) - 1
    erster = aus_monat_index(start_idx)
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(erster[0], erster[1], 1), leistung_kwp=10.0,
    ))
    for idx in range(start_idx, ende_idx + 1):
        jahr, monat = aus_monat_index(idx)
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=jahr, monat=monat,
            einspeisung_kwh=400.0, netzbezug_kwh=300.0,
        ))
    await db.flush()

    assert await get_naechster_monat(anlage.id, db) is None
