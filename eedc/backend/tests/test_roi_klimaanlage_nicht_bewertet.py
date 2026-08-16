"""ROI-Dashboard: bewertet wird, was gepflegt ist — nicht, was eedc sich denkt.

**Diese Datei hieß bis 2026-08-16 „Split-Klimaanlage bekommt keine erfundene
Heizungs-Ersparnis" und beruhte auf einer falschen Prämisse.** Sie lautete:
„Eine Split-Klimaanlage ersetzt keine Heizung." Das stimmt nicht (Gernot,
16.08.) — eine Luft-Luft-Wärmepumpe **kann** sehr wohl eine Gasheizung
ersetzen; ob sie dafür die effizienteste Bauart ist, ist eine andere Frage.

Der Defekt, den N-87/K-0b behoben hat, war nie die Bauart, sondern eine
**erfundene Eingabe**: Fehlte der Wärmebedarf, füllten ihn zwei Default-
Schichten auf (12.000 kWh Heizwärme + 3.000 kWh Warmwasser) ⇒ rund 1.100 €/Jahr
und 2.210 kg CO₂ gegen eine Heizung, die es nie gab, zusätzlich in den
Anlagen-Summen. Der damalige Fix band das an den **Typ**; seit N-88/F2b hängt
es an der **Pflege**:

- ``alter_energietraeger = "nichts"`` — es gab keine Vorgängerheizung. Neu, gilt
  für **jede** Wärmepumpenart (vorher unmöglich auszudrücken, Default war Gas —
  weshalb auch eine Luft-Wasser-WP im Neubau eine Gaskessel-Ersparnis bekam).
- **kein Wärmebedarf gepflegt** — die ROI-Zeile ist eine Prognose aus Bedarf ×
  JAZ/COP; ohne Bedarf gibt es nichts zu rechnen und keinen Default mehr.
- **unveränderte Vorbelegung an einer Luft-Luft-WP** — der Bestandsfall unten.

⚠ **Der Bestandsfall ist der wichtigste Test hier und der Grund, warum ein Fix
der Bauart „nur nichts erfinden, wenn nichts gepflegt ist" NICHT genügt:** Das
Investitionsformular hat die Vorbelegung bis v4.0.6 **mitgespeichert**, und seit
K-0b sind die beiden Felder für Klimaanlagen unsichtbar — der Anwender konnte
den Wert seither weder sehen noch korrigieren. Er zählt deshalb als offene
Frage, nicht als Antwort. Keine Migration, die rät: Befund plus Weg heraus.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten


# Die Vorbelegung, die das Formular bis v4.0.6 mitgespeichert hat.
GEPFLEGTE_PHANTOM_PARAMS = {
    "heizwaermebedarf_kwh": 12000,
    "warmwasserbedarf_kwh": 3000,
    "jaz": 3.5,
    "effizienz_modus": "gesamt_jaz",
    "alter_energietraeger": "gas",
    "alter_preis_cent_kwh": 12,
    "pv_anteil_prozent": 30,
}


async def _seed_wp(db, *, wp_art: str | None, parameter: dict | None = None) -> int:
    """Anlage mit genau einer Wärmepumpe des gegebenen Subtyps."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    params = dict(parameter if parameter is not None else GEPFLEGTE_PHANTOM_PARAMS)
    if wp_art is not None:
        params["wp_art"] = wp_art
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe",
        bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=8000.0,
        parameter=params,
    ))
    await db.flush()
    return anlage.id


def _wp_zeile(result):
    return next(b for b in result.berechnungen if b.investition_typ == "waermepumpe")


async def _roi(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )


# ============================================================================
# Der Fehler selbst
# ============================================================================


async def test_klimaanlage_bekommt_keine_ersparnis_obwohl_parameter_gepflegt_sind(db):
    """Der Bestandsfall: die Phantomwerte stehen in `parameter` — trotzdem 0.

    Genau hier hätte ein Fix der Bauart „nur nichts erfinden, wenn nichts
    gepflegt ist" versagt.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    zeile = _wp_zeile(result)
    assert zeile.jahres_einsparung == 0
    assert zeile.co2_einsparung_kg is None
    assert zeile.roi_prozent is None
    assert zeile.amortisation_jahre is None


async def test_klimaanlage_sagt_warum_statt_still_null_zu_liefern(db):
    """`nicht_bewertet` unterscheidet den FEHLENDEN Wert von einer Null-Ersparnis."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung["nicht_bewertet"] is True
    hinweis = zeile.detail_berechnung["hinweis"]
    assert hinweis.startswith("Nicht bewertet:")
    # Der Text nennt den GRUND (die alte Vorbelegung) und den Weg heraus — beides,
    # sonst ist es ein Befund ohne Handlung (P-6). Kein Anker auf ein einzelnes
    # Wort wie „Klimaanlage": das hat beim Umbau 2026-08-16 den Test rot gemacht,
    # obwohl die Aussage unverändert richtig war.
    assert "12.000" in hinweis and "3.000" in hinweis
    assert "nichts ersetzt" in hinweis


async def test_klimaanlage_bleibt_als_zeile_sichtbar(db):
    """Nicht bewertet heißt nicht unsichtbar: Kosten zählen weiter (wie beim WR)."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    zeile = _wp_zeile(result)
    assert zeile.anschaffungskosten == pytest.approx(8000.0)
    assert result.gesamt_investition == pytest.approx(8000.0)


async def test_anlagen_summen_tragen_den_phantomwert_nicht_mehr(db):
    """Die Kopfzahlen der ROI-Sicht waren mitbetroffen, nicht nur die Zeile."""
    anlage_id = await _seed_wp(db, wp_art="luft_luft")
    result = await _roi(db, anlage_id)

    assert result.gesamt_jahres_einsparung == 0
    assert result.gesamt_co2_einsparung_kg == 0
    # Ohne Ersparnis gibt es keinen Break-Even — und keine erfundene Kurve.
    assert result.gesamt_roi_prozent is None
    assert result.gesamt_amortisation_jahre is None
    assert result.gesamt_amortisation_jahr is None


# ============================================================================
# Regressionsschutz: klassische Wärmepumpen dürfen sich NICHT bewegen
# ============================================================================


async def test_klassische_waermepumpe_rechnet_unveraendert(db):
    """Luft-Wasser-WP: die bisherigen Zahlen bleiben exakt stehen.

    Die Werte sind die des Default-Satzes (15.000 kWh / JAZ 3,5 / 30 % PV /
    Gas 12 ct) — sie belegen, dass der Klima-Zweig die klassische WP nicht
    streift.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_wasser")
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung > 0
    assert zeile.co2_einsparung_kg == pytest.approx(2210.0)
    assert zeile.detail_berechnung.get("nicht_bewertet") is not True


async def test_waermepumpe_ohne_wp_art_gilt_als_klassisch(db):
    """Legacy-Bestand ohne `wp_art` darf die Wärme-Erwartung nicht verlieren.

    Gleiche Festlegung wie im SoT-Helper `ist_luft_luft_waermepumpe`: eine
    fehlende Angabe schaltet die Bewertung NICHT stillschweigend ab.
    """
    anlage_id = await _seed_wp(db, wp_art=None)
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung > 0
    assert zeile.detail_berechnung.get("nicht_bewertet") is not True


async def test_klimaanlage_ohne_gepflegte_parameter_erfindet_auch_nichts(db):
    """Der zweite Weg in denselben Fehler: leeres `parameter`-Dict.

    Ohne den Fix griffen hier die Defaults in `crud.py` UND die zweite
    Default-Schicht in `berechne_waermepumpe_einsparung`.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_luft", parameter={})
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.jahres_einsparung == 0
    assert zeile.co2_einsparung_kg is None
    assert zeile.detail_berechnung["nicht_bewertet"] is True


# ============================================================================
# Dieselbe Anzeige-Regel, zweiter Anlass: Speicher ohne Kapazität (N-89)
# ============================================================================


async def _seed_speicher_ohne_kapazitaet(db) -> int:
    """Anlage mit einem AC-Speicher, dessen Kapazität niemand gepflegt hat."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku ohne kWh",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0,
        parameter={},
    ))
    await db.flush()
    return anlage.id


async def test_speicher_ohne_kapazitaet_ist_nicht_bewertet_statt_null(db):
    """N-89: „0 €" behauptet „spart nichts" — gemeint war „unbekannt".

    Die Route wusste es längst (`detail['kapazitaet_fehlt']`), aber die
    ROI-Tabelle liest ausschließlich `nicht_bewertet` — das Flag aus N-87 —
    und zeigte deshalb eine harte 0. Beide Schlüssel stehen jetzt
    nebeneinander: `kapazitaet_fehlt` ist die Ursache (der Komponenten-Hub
    liest sie), `nicht_bewertet` die Anzeige-Folge.
    """
    anlage_id = await _seed_speicher_ohne_kapazitaet(db)
    result = await _roi(db, anlage_id)

    zeile = next(b for b in result.berechnungen if b.investition_typ == "speicher")
    assert zeile.jahres_einsparung == 0          # zählt nicht in die Summe
    assert zeile.detail_berechnung["kapazitaet_fehlt"] is True
    assert zeile.detail_berechnung["nicht_bewertet"] is True
    assert "Kapazität" in zeile.detail_berechnung["hinweis"]


# ============================================================================
# N-88/F2b — die Pflege entscheidet, nicht die Bauart
# ============================================================================


async def test_klimaanlage_die_heizt_wird_bewertet(db):
    """Der Fall, den die alte Typ-Regel zu Unrecht unterdrückt hat.

    Wer mit seiner Luft-Luft-WP heizt, eine Gasheizung ersetzt hat und seinen
    echten Bedarf pflegt, bekommt seine Zeile — wie jede andere Wärmepumpe.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_luft", parameter={
        **GEPFLEGTE_PHANTOM_PARAMS,
        # Ein Wert, den ein Mensch eingetragen hat — nicht die Vorbelegung.
        "heizwaermebedarf_kwh": 7400,
        "warmwasserbedarf_kwh": 1800,
    })
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile.jahres_einsparung > 0


async def test_nichts_ersetzt_wird_nicht_bewertet_egal_welche_bauart(db):
    """„nichts ersetzt" schlägt alles — und gilt für JEDE Wärmepumpenart.

    Der Neubau-Fall, den F2(a) am 02.08. offen gelassen hat: eine klassische
    Luft-Wasser-WP bekam eine Gaskessel-Ersparnis, weil `alter_energietraeger`
    kein „nichts" kannte und auf Gas fiel.
    """
    for art in ("luft_wasser", "luft_luft"):
        anlage_id = await _seed_wp(db, wp_art=art, parameter={
            **GEPFLEGTE_PHANTOM_PARAMS,
            "heizwaermebedarf_kwh": 7400,
            "warmwasserbedarf_kwh": 1800,
            "alter_energietraeger": "nichts",
        })
        result = await _roi(db, anlage_id)
        zeile = _wp_zeile(result)

        assert zeile.detail_berechnung["nicht_bewertet"] is True, art
        assert "nichts ersetzt (Neubau)" in zeile.detail_berechnung["hinweis"], art
        assert zeile.jahres_einsparung == 0, art
        # Und die Anlagen-Summen tragen ihn auch nicht.
        assert result.gesamt_jahres_einsparung == 0, art


async def test_ohne_gepflegten_bedarf_wird_nichts_erfunden(db):
    """Kein Default mehr: ohne Bedarf keine Prognose.

    Trifft Geräte, die nie über das Formular gespeichert wurden (Import,
    Setup-Wizard) — sie trugen bisher stillschweigend 12.000 + 3.000 kWh.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_wasser", parameter={
        "jaz": 3.5, "effizienz_modus": "gesamt_jaz",
        "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12,
    })
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung["nicht_bewertet"] is True
    assert "kein Wärmebedarf gepflegt" in zeile.detail_berechnung["hinweis"]
    assert zeile.jahres_einsparung == 0


async def test_klassische_wp_mit_vorbelegung_rechnet_unveraendert(db):
    """Negativprobe zum Bestandsschutz: die Vorbelegungs-Regel gilt NUR luft_luft.

    Bei einer Luft-Wasser-WP war der Bedarf immer sichtbar und änderbar; 12.000/
    3.000 sind dort eine brauchbare Schätzung. Ohne diesen Test wäre der
    Bestandsschutz oben nicht von einem „gilt für alle" zu unterscheiden — und
    das hätte jeder klassischen Wärmepumpe die Bewertung genommen.
    """
    anlage_id = await _seed_wp(db, wp_art="luft_wasser")
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile.jahres_einsparung > 0


async def test_halb_gepflegter_bedarf_erfindet_die_andere_haelfte_nicht(db):
    """Der Restfall, den erst ein stummer Sprengsatz sichtbar gemacht hat.

    `_wp_nicht_bewertbar` lässt den Rechenzweig schon bei EINEM gepflegten
    Bedarfsfeld laufen (ODER über Gesamt-/Heiz-/Warmwasserbedarf). Wer nur den
    Warmwasserbedarf einträgt, hätte über den alten Default trotzdem 12.000 kWh
    Heizwärme zugerechnet bekommen — also erneut den Phantomwert, nur durch die
    Hintertür. Gemessen wird deshalb die HÖHE, nicht bloß „wird bewertet".
    """
    nur_ww = await _seed_wp(db, wp_art="luft_wasser", parameter={
        "jaz": 3.5, "effizienz_modus": "gesamt_jaz",
        "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12,
        "pv_anteil_prozent": 30,
        "warmwasserbedarf_kwh": 3000,
    })
    beides = await _seed_wp(db, wp_art="luft_wasser", parameter={
        "jaz": 3.5, "effizienz_modus": "gesamt_jaz",
        "alter_energietraeger": "gas", "alter_preis_cent_kwh": 12,
        "pv_anteil_prozent": 30,
        "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000,
    })

    zeile_ww = _wp_zeile(await _roi(db, nur_ww))
    zeile_beides = _wp_zeile(await _roi(db, beides))

    # Bewertet wird beides — aber die halbe Pflege ergibt auch nur den halben Bedarf.
    assert zeile_ww.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile_ww.jahres_einsparung > 0
    assert zeile_ww.jahres_einsparung < zeile_beides.jahres_einsparung
    # 3.000 statt 15.000 kWh Bedarf ⇒ rund ein Fünftel der Altanlagen-Kosten.
    assert zeile_ww.detail_berechnung["alte_heizung_kosten_euro"] == pytest.approx(
        zeile_beides.detail_berechnung["alte_heizung_kosten_euro"] / 5, rel=0.02
    )


# ============================================================================
# N-258 — eine „nicht bewertete" Zeile zeigt trotzdem eine Zahl
#
# Zwei getrennte Ursachen, beide vor dem Bau am Code gemessen:
#
# A) `netto_einsparung = jahres_einsparung - betriebskosten` lief unbedingt ⇒
#    eine unbewertete Zeile mit 200 € Betriebskosten trug **−200 €** in die
#    Anlagen-Summe (die Zeile selbst zeigte „—" — Zeile und Summe widersprachen
#    sich also).
# B) Das Flag wurde zurückgenommen, sobald sonstige Erträge/Ausgaben gepflegt
#    waren (N-87). Dann zeigte die Zeile die −200 € **sichtbar** — und ohne den
#    Zusatz „· nicht bewertet", der am selben Flag hängt.
#
# ⚠ Gemessen wird die **HÖHE**, nicht bloß „wird bewertet" — dieselbe Lehre wie
# beim stummen Sprengsatz zu `test_halb_gepflegter_bedarf_…` darüber: Ursache A
# ließ `nicht_bewertet` unangetastet und wäre einem Flag-Prüfer entgangen.
# ============================================================================


NEUBAU_PARAMS = {
    "jaz": 3.5, "effizienz_modus": "gesamt_jaz",
    "alter_energietraeger": "nichts", "alter_preis_cent_kwh": 12,
    "pv_anteil_prozent": 30,
    "heizwaermebedarf_kwh": 7400, "warmwasserbedarf_kwh": 1800,
}


async def _seed_wp_mit(
    db, *, params: dict, betriebskosten: float = 0.0,
    positionen: list[dict] | None = None,
) -> int:
    """Eine WP mit Betriebskosten und/oder gepflegten sonstigen Positionen."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Test-WP",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=8000.0,
        betriebskosten_jahr=betriebskosten, parameter=dict(params),
    )
    db.add(inv)
    await db.flush()
    if positionen:
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2025, monat=10,
            verbrauch_daten={"sonstige_positionen": positionen},
        ))
        await db.flush()
    return anlage.id


async def test_a_betriebskosten_sind_keine_negative_einsparung(db):
    """Ursache A: 0 − 200 stand als „Jahres-Einsparung" in der Anlagen-Summe."""
    anlage_id = await _seed_wp_mit(db, params=NEUBAU_PARAMS, betriebskosten=200.0)
    result = await _roi(db, anlage_id)
    zeile = _wp_zeile(result)

    assert zeile.detail_berechnung["nicht_bewertet"] is True
    assert zeile.jahres_einsparung == 0          # vor dem Fix: −200,0
    assert result.gesamt_jahres_einsparung == 0  # vor dem Fix: −200,0


async def test_a_betriebskosten_bleiben_trotzdem_in_der_rechnung(db):
    """Die Gegenprobe zum Fix: unterdrückt wird die ANZEIGE, nicht der Betrag.

    Ein Fix, der die Betriebskosten schlicht fallen lässt, wäre die andere
    Unwahrheit — sie fallen ja real an. Sichtbar wird das im Annahme-Satz, den
    beide Amortisations-Dauern mitführen (Konzept §5/Bauschritt 6).
    """
    anlage_id = await _seed_wp_mit(db, params=NEUBAU_PARAMS, betriebskosten=200.0)
    result = await _roi(db, anlage_id)

    assert "200,00 €/Jahr Betriebskosten" in _wp_zeile(result).amortisation_annahme
    assert "200,00 €/Jahr Betriebskosten" in result.amortisation_annahme


async def test_a_bewertete_zeile_zieht_ihre_betriebskosten_weiter_ab(db):
    """Negativprobe: der Regelfall darf sich um keinen Cent bewegen."""
    ohne = await _seed_wp_mit(db, params=GEPFLEGTE_PHANTOM_PARAMS)
    mit = await _seed_wp_mit(db, params=GEPFLEGTE_PHANTOM_PARAMS, betriebskosten=200.0)

    zeile_ohne = _wp_zeile(await _roi(db, ohne))
    zeile_mit = _wp_zeile(await _roi(db, mit))

    assert zeile_ohne.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile_mit.jahres_einsparung == pytest.approx(
        zeile_ohne.jahres_einsparung - 200.0
    )


async def test_b_gepflegte_wartung_macht_die_zeile_nicht_bewertet(db):
    """Ursache B: ein Wartungsposten nahm das Flag zurück — und zeigte −200 €.

    Der Fall ist nicht exotisch: Die Demo-Wärmepumpe trägt zwei Wartungsposten
    à 180 €, und eine gepflegte Wartungsrechnung hat jeder reale Anwender.
    """
    anlage_id = await _seed_wp_mit(
        db, params=NEUBAU_PARAMS, betriebskosten=200.0,
        positionen=[{"typ": "ausgabe", "betrag": 180.0, "bezeichnung": "Wartung"}],
    )
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung["nicht_bewertet"] is True  # vor dem Fix: False
    assert zeile.jahres_einsparung == 0                       # vor dem Fix: −200,0


async def test_b_gepflegter_betrag_geht_nicht_verloren(db):
    """Die Gegenprobe zu B — und der Grund, warum die Rücknahme entfallen konnte.

    Die N-87-Begründung lautete „dann seine Zahl zeigen statt —". Gemessen am
    16.08.: Die Einsparungs-Spalte trägt seinen Betrag NIE. Eine gepflegte
    Förderung von 180 € ließ die Zeile „0,00 €" zeigen — also genau die Fake-0,
    gegen die N-87 angetreten war. Sein Betrag wirkt im **Kapitaleinsatz**, und
    das tut er hier unverändert weiter.
    """
    ohne = await _seed_wp_mit(db, params=NEUBAU_PARAMS)
    mit = await _seed_wp_mit(
        db, params=NEUBAU_PARAMS,
        positionen=[{"typ": "ertrag", "betrag": 180.0, "bezeichnung": "Förderung"}],
    )

    zeile_ohne = _wp_zeile(await _roi(db, ohne))
    zeile_mit = _wp_zeile(await _roi(db, mit))

    assert zeile_ohne.kapitaleinsatz == pytest.approx(8000.0)
    assert zeile_mit.kapitaleinsatz == pytest.approx(7820.0)
    assert zeile_mit.detail_berechnung["sonstige_ertraege_euro"] == pytest.approx(180.0)
    # Und die Zeile bleibt unbewertet statt „0,00 €" zu behaupten.
    assert zeile_mit.detail_berechnung["nicht_bewertet"] is True
    assert zeile_mit.jahres_einsparung == 0


async def test_b_bewertete_zeile_mit_positionen_bleibt_bewertet(db):
    """Negativprobe: der Wegfall der Rücknahme schaltet nichts NEU ab.

    Eine Zeile, die ohnehin bewertet ist, war von `nicht_bewertet` nie
    betroffen — mit oder ohne gepflegte Position.
    """
    anlage_id = await _seed_wp_mit(
        db, params=GEPFLEGTE_PHANTOM_PARAMS,
        positionen=[{"typ": "ausgabe", "betrag": 180.0, "bezeichnung": "Wartung"}],
    )
    zeile = _wp_zeile(await _roi(db, anlage_id))

    assert zeile.detail_berechnung.get("nicht_bewertet") is not True
    assert zeile.jahres_einsparung > 0
    assert zeile.kapitaleinsatz == pytest.approx(8180.0)


async def test_speicher_ohne_kapazitaet_faellt_unter_dieselbe_regel(db):
    """N-258 ist keine Wärmepumpen-Regel — sie hängt am Flag, nicht am Typ.

    Der zweite Träger von `nicht_bewertet` ist der Speicher ohne gepflegte
    Kapazität (N-89). Ohne diese Probe wäre der Fix von der einen Fläche, an
    der er gefunden wurde, nicht zu unterscheiden.
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku ohne kWh",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0,
        betriebskosten_jahr=50.0, parameter={},
    ))
    await db.flush()
    result = await _roi(db, anlage.id)

    zeile = next(b for b in result.berechnungen if b.investition_typ == "speicher")
    assert zeile.detail_berechnung["nicht_bewertet"] is True
    assert zeile.jahres_einsparung == 0          # vor dem Fix: −50,0
    assert result.gesamt_jahres_einsparung == 0  # vor dem Fix: −50,0
