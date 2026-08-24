"""Der Wechselrichter ist kein PV-Erzeuger (F-57, #388 Mathek).

Schwesterdatei: ``test_live_pv_zaehler_f49.py`` — dort der Lesepfad der
Live-Kachel (Praezedenz Erzeuger-Zaehler → Anlagen-Zaehler → Trapez), hier die
Frage davor: **welche Felder darf es ueberhaupt geben, und wer besetzt die
Alternativ-Gruppe.**

Der gemessene Schaden (24.08.2026): ``wechselrichter/pv_erzeugung_kwh`` war
``("pflicht", "pv_energie")`` und hat damit die Gruppe besetzt — ein dort
zugeordneter Zaehler setzte ``basis:pv_gesamt`` **und** das Modul-Feld auf
„bereits an anderer Stelle zugeordnet", waehrend ihn selbst niemand las. Alle
drei PV-Quellen inaktiv, keine wirksam; die Live-Kachel fiel auf die
Trapez-Hochrechnung zurueck (+31 %).
"""

import pytest
from datetime import date

from backend.core.field_definitions import (
    get_alle_felder_fuer_investition,
    get_feld_bedarf,
    get_felder_fuer_investition,
)
from backend.services.datenquellen_validierung import stufe_bedarf_ein
from backend.services.monats_fakten import lade_monats_fakten
from backend.tests.factories import mach_anlage, mach_imd, mach_investition


class _Inv:
    def __init__(self, typ):
        self.typ = typ


class TestFeldRegistry:
    def test_der_monatsabschluss_bietet_es_nicht_mehr_an(self):
        """Weder mit noch ohne PV-Module — die alte Bedingung war spiegelverkehrt."""
        assert get_felder_fuer_investition("wechselrichter", {}) == []
        assert get_felder_fuer_investition(
            "wechselrichter", {}, [_Inv("wechselrichter")]
        ) == []
        assert get_felder_fuer_investition(
            "wechselrichter", {}, [_Inv("wechselrichter"), _Inv("pv-module")]
        ) == []

    def test_die_zuordnungsflaeche_kennt_es_weiter(self):
        """Bestandsschutz: eine alte Zuordnung muss entfernbar bleiben.

        ``nur_manuell`` nimmt es dort ab, **ausser** es traegt heute eine
        Quelle (``routes/datenquellen.py::ohne_nicht_zuordenbare``) — dafuer
        muss es hier ueberhaupt noch existieren.
        """
        felder = get_alle_felder_fuer_investition("wechselrichter")
        assert [f["feld"] for f in felder] == ["pv_erzeugung_kwh"]
        assert felder[0]["nur_bestand"] is True
        assert felder[0]["nur_manuell"] is True

    def test_es_besetzt_die_pv_gruppe_nicht_mehr(self):
        assert get_feld_bedarf("wechselrichter", "pv_erzeugung_kwh") == ("optional", None)

    def test_die_echten_pv_quellen_behalten_ihre_gruppe(self):
        """Gegenprobe: der Schnitt trifft nur den Wechselrichter."""
        assert get_feld_bedarf("pv-module", "pv_erzeugung_kwh") == ("pflicht", "pv_energie")
        assert get_feld_bedarf("balkonkraftwerk", "pv_erzeugung_kwh") == ("pflicht", "pv_energie")
        assert get_feld_bedarf("basis", "pv_gesamt_kwh") == ("pflicht", "pv_energie")


class TestKeineSackgasseMehr:
    """Die Bedarfs-Einstufung, an der der Anwender haengenblieb."""

    def _felder(self, wr_belegt: bool):
        def e(fid, typ, feld, belegt):
            bedarf, gruppe = get_feld_bedarf(typ, feld)
            return {"id": fid, "typ": typ, "feld": feld, "belegt": belegt,
                    "bedarf": bedarf, "bedarf_gruppe": gruppe}
        return [
            e("basis:pv_gesamt", "basis", "pv_gesamt_kwh", False),
            e("inv:5:pv_erzeugung_kwh", "pv-module", "pv_erzeugung_kwh", False),
            e("inv:7:pv_erzeugung_kwh", "wechselrichter", "pv_erzeugung_kwh", wr_belegt),
        ]

    def test_ein_zaehler_am_wechselrichter_verdeckt_nichts_mehr(self):
        r = stufe_bedarf_ein(self._felder(wr_belegt=True),
                             {"wechselrichter", "pv-module"})
        assert r["basis:pv_gesamt"]["bedarf"] == "pflicht", (
            "der Anlagen-Zaehler muss eingefordert werden — sonst bleibt nur "
            "die Trapez-Hochrechnung (#388)"
        )
        assert r["inv:5:pv_erzeugung_kwh"]["bedarf"] == "pflicht"
        assert r["inv:7:pv_erzeugung_kwh"]["bedarf"] == "optional"

    def test_ein_belegtes_modul_verdeckt_den_anlagenzaehler_weiterhin(self):
        """Gegenprobe: die Gruppen-Regel selbst bleibt unangetastet.

        Wer je String misst, braucht den Anlagen-Zaehler wirklich nicht — genau
        dafuer gibt es die Alternativ-Gruppe. Nur der Wechselrichter war nie ein
        gueltiges Mitglied.
        """
        felder = self._felder(wr_belegt=False)
        felder[1]["belegt"] = True
        r = stufe_bedarf_ein(felder, {"wechselrichter", "pv-module"})
        assert r["basis:pv_gesamt"]["bedarf"] == "inaktiv"
        assert r["basis:pv_gesamt"]["grund"] == "gruppe:pv_energie"


class TestRechnung:
    @pytest.mark.asyncio
    async def test_ein_wert_am_wechselrichter_traegt_nichts_bei(self, db):
        """Der Grund fuer den Schnitt — unveraendertes Verhalten, hier belegt."""
        a = mach_anlage(anlagenname="P", installationsdatum=date(2025, 1, 1))
        db.add(a)
        await db.flush()
        wr = mach_investition("wechselrichter", anlage_id=a.id, bezeichnung="WR",
                              anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0)
        db.add(wr)
        await db.flush()
        db.add(mach_imd(wr.id, 2025, 5, {"pv_erzeugung_kwh": 900.0}))
        await db.commit()

        fakten = await lade_monats_fakten(db, a.id, von=(2025, 5), bis=(2025, 5))
        assert fakten[0].erzeugung.pv_kwh == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_derselbe_wert_an_einem_pv_modul_zaehlt(self, db):
        """Gegenprobe — die Probe kann etwas sehen."""
        a = mach_anlage(anlagenname="P", installationsdatum=date(2025, 1, 1))
        db.add(a)
        await db.flush()
        modul = mach_investition("pv-module", anlage_id=a.id, bezeichnung="Dach",
                                 anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0)
        db.add(modul)
        await db.flush()
        db.add(mach_imd(modul.id, 2025, 5, {"pv_erzeugung_kwh": 900.0}))
        await db.commit()

        fakten = await lade_monats_fakten(db, a.id, von=(2025, 5), bis=(2025, 5))
        assert fakten[0].erzeugung.pv_kwh == pytest.approx(900.0)


class TestDatenCheckerNenntDieAltzuordnung:
    """Ohne diesen Hinweis merkt niemand, dass sein Sensor umziehen muss.

    ⚠ **Das Schweigen war der eigentliche Schaden.** Die Zuordnungs-Flaeche
    meldete Vollstaendigkeit, der Daten-Checker sagte nichts, und die Zahl war
    still zu hoch — der Melder von #388 hat zweimal geschrieben, ehe die Ursache
    gefunden war.
    """

    def _checker(self):
        from backend.services.daten_checker.stammdaten import StammdatenChecks
        return StammdatenChecks.__new__(StammdatenChecks)

    def _wr(self, *, monatswerte=()):
        wr = mach_investition("wechselrichter", id=7, anlage_id=1, bezeichnung="WR",
                              anschaffungsdatum=date(2025, 1, 1))
        wr.monatsdaten = [
            mach_imd(7, j, m, {"pv_erzeugung_kwh": 900.0}) for j, m in monatswerte
        ]
        return wr

    def test_eine_sensor_zuordnung_wird_gemeldet(self):
        mapping = {"investitionen": {"7": {"felder": {
            "pv_erzeugung_kwh": {"quelle": "ha", "entity_id": "sensor.pv"}}}}}
        r = self._checker()._check_wechselrichter_pv_altbestand(
            self._wr(), "WR", mapping)
        assert len(r) == 1
        assert r[0].schwere == "warning"
        assert "datenquellen" in r[0].link

    def test_auch_ein_reiner_monatswert_wird_gemeldet(self):
        r = self._checker()._check_wechselrichter_pv_altbestand(
            self._wr(monatswerte=[(2025, 5), (2025, 6)]), "WR", {})
        assert len(r) == 1
        assert "05/2025 bis 06/2025" in r[0].details

    def test_ohne_altbestand_schweigt_er(self):
        """Gegenprobe: kein Dauer-Hinweis fuer alle mit Wechselrichter."""
        assert self._checker()._check_wechselrichter_pv_altbestand(
            self._wr(), "WR", {}) == []

    def test_eine_leere_zuordnung_ist_keine_zuordnung(self):
        mapping = {"investitionen": {"7": {"felder": {
            "pv_erzeugung_kwh": {"quelle": "keine", "entity_id": ""}}}}}
        assert self._checker()._check_wechselrichter_pv_altbestand(
            self._wr(), "WR", mapping) == []


def test_es_gibt_genau_drei_pv_energie_quellen():
    """⛔ Der Waechter gegen den naechsten Wirrwarr (Gernots Frage, 24.08.2026).

    „PV-Erzeugung" hiess an **vier** Stellen etwas anderes, und keine Liste hat
    das je zusammen gezeigt — deshalb konnte eine davon jahrelang tot sein, ohne
    dass es auffiel, und deshalb hat die Analyse von #388 drei Anlaeufe
    gebraucht. Diese Probe ist die Liste.

    **Wer hier eine Zeile ergaenzt, trifft eine Entscheidung**: ein neues
    Mitglied der Gruppe ``pv_energie`` verdraengt alle anderen, sobald es belegt
    ist (``datenquellen_validierung.stufe_bedarf_ein``, Fall 2). Genau daran ist
    der Wechselrichter gescheitert — er besetzte die Gruppe und wurde nirgends
    gelesen.

    **Die Gegenfrage vor jedem Eintrag lautet deshalb:** steht der Typ in
    ``PV_ERZEUGER_TYPEN``? Wenn nein, gehoert er nicht in diese Gruppe.
    ``basis`` ist die einzige begruendete Ausnahme — es ist kein Geraet, sondern
    der anlagenweite Zaehler, und er ist ausdruecklich der Eingang von
    ``resolve_pv_je_modul`` (ADR-002/P7).
    """
    from backend.core.berechnungen.spez_ertrag import PV_ERZEUGER_TYPEN
    from backend.core.field_definitions import FELD_BEDARF

    quellen = {k for k, v in FELD_BEDARF.items() if v[1] == "pv_energie"}
    assert quellen == {
        ("basis", "pv_gesamt_kwh"),          # Anlagen-Zaehler → Anlagen-Aggregat
        ("pv-module", "pv_erzeugung_kwh"),   # Messung je String
        ("balkonkraftwerk", "pv_erzeugung_kwh"),  # Messung bzw. Parent-Aggregat
    }, "Neue PV-Energie-Quelle? Docstring lesen — das ist eine Entscheidung."

    geraete_typen = {t for t, _f in quellen if t != "basis"}
    assert geraete_typen == set(PV_ERZEUGER_TYPEN), (
        "Die Eingabe-Registry und der Rechen-Kern sind auseinandergelaufen — "
        "genau diese Differenz war F-57: der Wechselrichter stand in der "
        "Gruppe, aber nicht in PV_ERZEUGER_TYPEN, und wurde deshalb von "
        "niemandem gelesen."
    )
