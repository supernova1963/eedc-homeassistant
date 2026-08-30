"""N-277: Der Prognose-Fallback liest den gepflegten PV-Anteil der Wärmepumpe.

**Wo der Fehler saß.** Hat eine Anlage *keine* historische Eigenverbrauchsquote
— eine Neuanlage —, schätzt die Finanzprognose den Eigenverbrauch aus einem
Komponentenmodell. Der WP-Anteil daran stand dort als feste Zahl:

    wp_pv_fb = wp_verbrauch_fb * 0.5 * (pv_faktor ** 0.5)

Das gepflegte Feld *„PV-Anteil (%) — Anteil des WP-Stroms aus PV"* wurde nicht
gelesen. Die Kette ist wirksam und sichtbar: ``wp_pv_fb`` → ``eigenverbrauch_kwh``
→ ``jahres_eigenverbrauch`` → ``jahres_ev_ersparnis`` → ``jahres_netto_ertrag``,
zusätzlich in die USt-Bemessung.

⭐ **Warum der naheliegende Fix falsch gewesen wäre** — das ist der Kern dieser
Proben. Die ``0.5`` ist **kein Jahresanteil**, sondern ein Basiswert *vor* der
saisonalen Dämpfung ``* (pv_faktor ** 0.5)``. Effektiv liefert die alte Formel
**38,5 %** im Jahresmittel (Januar 27 %, Juli 65 %, Dezember 23 % bei einer
Süd-Kurve) — die Winterdämpfung, die eine Wärmepumpe braucht, war also bereits
da. Hätte man ``0.5`` stumpf durch den gepflegten Wert ersetzt, käme bei
gepflegten 30 % effektiv **23,1 %** heraus: Der Anwender pflegt 30 und bekommt
23. Eine neue Drift, gebaut aus einem Fix.

**Deshalb wird normalisiert statt ersetzt:** Die saisonale *Form* bleibt, die
Jahressumme trifft genau den gepflegten Wert. Das Formularfeld bedeutet damit,
was draufsteht.

⚠ **Was die Formel weiterhin NICHT kann** und was deshalb keine Probe behauptet:
Sie bildet das PV-*Angebot* ab, nicht die *Gleichzeitigkeit* (die Wärmepumpe
läuft nachts und morgens, die PV mittags). Der reale Deckungsgrad liegt darunter.
Ein Gleichzeitigkeitsmodell bräuchte ein Lastprofil — das im Fallback-Fall
(Anlage ohne jede Historie) per Definition nicht existiert.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.aussichten import get_finanz_prognose
from backend.core.investition_parameter import PARAM_WAERMEPUMPE_DEFAULTS
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose

#: Monatsanteile einer Süd-Anlage in % des Jahresertrags. ⚠ OHNE eine aktive
#: PVGIS-Prognose ist `pv_faktor` konstant 1,0 — dann gibt es weder Dämpfung
#: noch Normierung, und die Proben würden die halbe Formel nicht erreichen.
#: Genau daran ist die erste Gegenprobe dieser Datei grün geblieben.
MONATSANTEILE = {1: 2.5, 2: 4.2, 3: 7.8, 4: 11.2, 5: 13.5, 6: 14.0,
                 7: 14.2, 8: 12.5, 9: 9.5, 10: 6.0, 11: 2.8, 12: 1.8}


async def _seed(db, *, pv_anteil_prozent: float | None) -> int:
    """Anlage MIT WP-Stromhistorie und OHNE historische EV-Quote.

    ⚠ **Die Lage ist enger, als „Neuanlage" klingt** — beide Bedingungen
    zusammen sind nötig, und das gehört zum Befund:

    * **Keine historische EV-Quote.** Sie entsteht nur, wenn ein Monat *sowohl*
      PV *als auch* Eigenverbrauch > 0 führt; sonst greift das Komponentenmodell.
    * **Aber WP-Stromhistorie.** ``wp_strom_monat_avg`` ist der Monats-Ø aus
      ``InvestitionMonatsdaten``; ohne ihn ist der WP-Beitrag schlicht 0 und der
      gepflegte Anteil wäre folgenlos.

    Real ist das die Anlage, die ihre Wärmepumpe schon erfasst, deren PV-Bilanz
    aber noch nicht steht — etwa weil die PV gerade dazugekommen ist.
    """
    anlage = Anlage(anlagenname="N-277", leistung_kwp=10.0,
                    standort_plz="10115", latitude=48.0, longitude=11.0)
    db.add(anlage)
    await db.flush()

    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2020, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=20000.0, leistung_kwp=10.0,
    ))
    db.add(PVGISPrognose(
        anlage_id=anlage.id,
        abgerufen_am=datetime(2025, 12, 1),
        latitude=48.0, longitude=11.0,
        neigung_grad=30.0, ausrichtung_grad=0.0,
        system_losses=14.0,
        jahresertrag_kwh=10000.0,
        spezifischer_ertrag_kwh_kwp=1000.0,
        monatswerte=[
            {"monat": m, "e_m": 10000.0 * a / 100.0, "h_m": 0.0, "sd_m": 0.0}
            for m, a in MONATSANTEILE.items()
        ],
        ist_aktiv=True,
    ))

    # Monatszeilen OHNE PV und OHNE Eigenverbrauch: sie erzeugen keine
    # EV-Quote (dafür müssten beide > 0 sein), setzen aber `anzahl_monate_hist`
    # auf 12. ⚠ Ohne sie fällt der Divisor auf 1 und der WP-Monats-Ø wird
    # zwölfmal zu groß — der erste Entwurf dieser Fixture rechnete so mit
    # 38.520 kWh WP-Strom im Jahr.
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=m,
                           netzbezug_kwh=400.0))

    params: dict = {
        "wp_art": "luft_wasser",
        "jaz": 3.5,
        "heizwaermebedarf_kwh": 12000,
        "warmwasserbedarf_kwh": 3000,
    }
    if pv_anteil_prozent is not None:
        params["pv_anteil_prozent"] = pv_anteil_prozent
    wp = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Luft-Wasser",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=15000.0,
        parameter=params,
    )
    db.add(wp)
    await db.flush()

    # WP-Stromhistorie — OHNE PV-/Bilanzdaten, s. Docstring.
    for m in range(1, 13):
        db.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=m,
            verbrauch_daten={"stromverbrauch_kwh": 300.0},
        ))
    await db.commit()
    return anlage.id


@pytest.mark.asyncio
async def test_n277_gepflegter_anteil_wirkt_auf_den_eigenverbrauch(db):
    """Zwei Anlagen, gleiche Daten, nur der gepflegte Anteil verschieden.

    Der Vergleich ist die Zusicherung: **20 % müssen weniger Eigenverbrauch
    ergeben als 60 %.** Vor dem Fix waren beide identisch, weil das Feld gar
    nicht gelesen wurde — genau daran ist diese Probe rot.
    """
    niedrig = await _seed(db, pv_anteil_prozent=20)
    hoch = await _seed(db, pv_anteil_prozent=60)

    p_niedrig = await get_finanz_prognose(anlage_id=niedrig, monate=12, db=db)
    p_hoch = await get_finanz_prognose(anlage_id=hoch, monate=12, db=db)

    assert p_niedrig.jahres_eigenverbrauch_kwh < p_hoch.jahres_eigenverbrauch_kwh
    # Und die Wirkung reicht bis zur sichtbaren Zahl durch.
    assert p_niedrig.jahres_ev_ersparnis_euro < p_hoch.jahres_ev_ersparnis_euro


@pytest.mark.asyncio
async def test_n277_ohne_pflege_gilt_der_katalog_default(db):
    """Ungepflegt = der Wert des Parameter-Katalogs, nicht eine dritte Zahl.

    Der Katalog führt 30 %; die alte Formel rechnete mit einem Basiswert von
    50 % (effektiv 38,5 %). Ein ungepflegtes Feld muss dasselbe liefern wie ein
    auf den Default gepflegtes — sonst gäbe es zwei Bedeutungen für „nicht
    ausgefüllt".
    """
    ohne = await _seed(db, pv_anteil_prozent=None)
    mit_default = await _seed(
        db, pv_anteil_prozent=PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"]
    )

    p_ohne = await get_finanz_prognose(anlage_id=ohne, monate=12, db=db)
    p_default = await get_finanz_prognose(anlage_id=mit_default, monate=12, db=db)

    assert p_ohne.jahres_eigenverbrauch_kwh == pytest.approx(
        p_default.jahres_eigenverbrauch_kwh
    )


@pytest.mark.asyncio
async def test_n277_der_gepflegte_wert_ist_das_jahresmittel(db):
    """Der Kern der Normalisierung — und der Grund, warum „ersetzen" falsch wäre.

    Gepflegte 30 % müssen **30 % des WP-Jahresstroms** als Eigenverbrauch
    ergeben — nicht 23 %, wie es eine unnormalisierte Dämpfung liefert.
    Gemessen über die Differenz zweier Anlagen (30 % gegen 0 %); der WP-Beitrag
    ist genau diese Differenz, alles andere ist identisch.

    ⚠ **Warum nicht 100 %** — das war der erste Entwurf, und er war rot aus
    einem richtigen Grund: Bei 100 % greift der Deckel ``min(eigenverbrauch,
    pv_kwh)``, weil eine Wärmepumpe im Januar mehr Strom zieht, als das Dach an
    PV liefert. Der Deckel ist korrekt; die Probe war unphysikalisch. Sie prüft
    jetzt einen Anteil, bei dem er nicht greift — der Deckel selbst hat seine
    eigene Probe darunter.
    """
    gepflegt = await _seed(db, pv_anteil_prozent=30)
    null = await _seed(db, pv_anteil_prozent=0)

    p_gepflegt = await get_finanz_prognose(anlage_id=gepflegt, monate=12, db=db)
    p_null = await get_finanz_prognose(anlage_id=null, monate=12, db=db)

    wp_beitrag = p_gepflegt.jahres_eigenverbrauch_kwh - p_null.jahres_eigenverbrauch_kwh
    assert p_gepflegt.wp_stromverbrauch_kwh > 0

    erwartet = 0.30 * p_gepflegt.wp_stromverbrauch_kwh
    assert wp_beitrag == pytest.approx(erwartet, rel=0.03)
    # Die Gegenrichtung, die den ganzen Fix trägt: die unnormalisierte Form
    # hätte rund 23 % geliefert (0,30 × 0,77). Ohne diese Zeile wäre die Probe
    # auch mit dem falschen Fix grün.
    assert wp_beitrag > 0.26 * p_gepflegt.wp_stromverbrauch_kwh


@pytest.mark.asyncio
async def test_n277_der_eigenverbrauch_bleibt_unter_der_erzeugung(db):
    """Der Deckel ist eine Eigenschaft, kein Hindernis — hier festgehalten.

    Bei einem gepflegten Anteil von 100 % will das Modell im Winter mehr
    WP-Strom aus PV decken, als das Dach überhaupt erzeugt. ``min(…, pv_kwh)``
    fängt das ab. **Diese Probe existiert, weil der erste Entwurf der Probe
    darüber genau daran gescheitert ist** — die Eigenschaft war vorher nirgends
    festgehalten und hätte bei einem künftigen Umbau still verschwinden können.
    """
    anlage_id = await _seed(db, pv_anteil_prozent=100)

    p = await get_finanz_prognose(anlage_id=anlage_id, monate=12, db=db)

    for m in p.monatswerte:
        assert m.eigenverbrauch_kwh <= m.pv_erzeugung_kwh + 1e-6, (
            f"Monat {m.monat}: Eigenverbrauch über der Erzeugung"
        )
    # Und die Deckelung muss wirklich eintreten, sonst prüft die Probe nichts.
    assert any(
        m.eigenverbrauch_kwh == pytest.approx(m.pv_erzeugung_kwh)
        for m in p.monatswerte
    ), "kein Monat gedeckelt — dann ist der Prüffall falsch gewählt"


@pytest.mark.asyncio
async def test_n277_die_saisonform_bleibt_erhalten(db):
    """Die Winterdämpfung ist der fachliche Kern — sie darf nicht wegfallen.

    Eine Wärmepumpe zieht im Januar rund **neunmal** so viel Strom wie im Juli
    (Saisonfaktoren 1,8 gegen 0,2). Käme jeder Monat mit demselben PV-Anteil
    durch, wäre der Januar-Beitrag auch neunmal so groß. Die Dämpfung
    ``* (pv_faktor ** 0.5)`` drückt ihn auf gut das Vierfache — denn im Januar
    liefert das Dach kaum PV.

    ⛔ **Die erste Fassung dieser Probe hat das NICHT gefangen.** Sie verglich
    Winter- und Sommer-Eigenverbrauchsquoten auf *Ungleichheit* — und die
    besteht auch ohne jede Dämpfung, weil der Grundverbrauch mit der Erzeugung
    mitwächst. Eine Gegenprobe mit entfernter Saisonform blieb grün. Jetzt wird
    das **Verhältnis** geprüft, und zwar gegen die Zahl, die ohne Dämpfung
    entstünde.
    """
    gepflegt = await _seed(db, pv_anteil_prozent=30)
    null = await _seed(db, pv_anteil_prozent=0)

    p_gepflegt = await get_finanz_prognose(anlage_id=gepflegt, monate=12, db=db)
    p_null = await get_finanz_prognose(anlage_id=null, monate=12, db=db)

    # Der WP-Beitrag je Monat ist die Differenz — alles andere ist identisch.
    ev_g = {m.monat: m.eigenverbrauch_kwh for m in p_gepflegt.monatswerte}
    ev_0 = {m.monat: m.eigenverbrauch_kwh for m in p_null.monatswerte}
    beitrag = {m: ev_g[m] - ev_0[m] for m in ev_g if m in ev_0}

    assert 1 in beitrag and 7 in beitrag, "Januar und Juli müssen im Horizont liegen"
    assert beitrag[7] > 0, "ohne Sommerbeitrag sagt das Verhältnis nichts"

    verhaeltnis = beitrag[1] / beitrag[7]
    # Ohne Dämpfung wäre es 1,8 / 0,2 = 9,0 — das Verhältnis der reinen
    # Saisonfaktoren. Mit Dämpfung liegt es bei gut 4.
    assert verhaeltnis < 6.0, (
        f"Januar/Juli = {verhaeltnis:.1f} — ohne Winterdämpfung wären es 9,0"
    )
    # Und die Gegenrichtung: der Winter bleibt der verbrauchsstärkere Monat.
    assert verhaeltnis > 1.0
