"""Daten-Checker — Wärme/Klima: Betriebsmodus-Sensor, Kühlspur und geschätzter Kühlanteil (SOLL Wärme/Klima, K3/R-1).
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

from typing import Optional
from sqlalchemy import select
from backend.core.betriebsmodus import ist_betriebsart_strom_feld, modus_quelle
from backend.core.field_definitions import basis_feld_key
from backend.models.anlage import Anlage
from backend.models.investition import InvestitionMonatsdaten
from backend.core.berechnungen import hat_gemessene_betriebsart
from backend.services.daten_checker.kuehl_zaehler import hat_kuehl_zaehler
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    LINK_DATENQUELLEN,
)


class KlimaChecks:
    """Prüfung des Klima-Modus-Sensors und der Kühl-Zuordnung."""

    async def _check_klima_modus_sensor(self, anlage: Anlage) -> list[CheckErgebnis]:
        """#263 K-2: Split-Klimaanlage ohne zugeordneten Betriebsmodus-Sensor.

        Eine Klimaanlage heizt im Winter und kühlt im Sommer — über **denselben**
        Zähler. eedc sieht deshalb nur eine Zahl „Stromverbrauch" und kann nicht
        sagen, welcher Teil davon ins Heizen ging. **Die Aufteilung ist aus
        keinem vorhandenen Feld rekonstruierbar**; sie entsteht nur, wenn der
        Betriebsmodus zur Messzeit mitgeschrieben wird.

        **INFO, nicht WARNING, und mit einem Weg statt eines Vorwurfs.** Das
        Feld ist optional: ohne es rechnet alles weiter wie bisher, es fehlt
        nur die Aufteilung. Eine Warnung stünde in keinem Verhältnis — und ein
        Hinweis ohne Weg wäre die P-6-Falle.

        **Welche Geräte den Hinweis bekommen — B2 (05.09.2026, R1).** Zwei Wege,
        beide erlaubt: (1) die **Bauart schlägt vor** — an einer Split-Klimaanlage
        (`luft_luft`) ist Heizen und Kühlen über einen Zähler der Regelfall, der
        Hinweis ist ein Angebot, keine Forderung (ADR-002/P13, Gruppe 2);
        (2) die **Beleglage** — jedes Gerät, an dem eine Kühl-Spur zugeordnet
        oder gepflegt ist (Kühl-Leistung live, Kältemenge, Kühl-Betriebsart),
        kühlt nachweislich, egal welcher Bauart. Bis B2 zählte nur (1): eine
        Luft-Wasser-Wärmepumpe mit Kühlfunktion (MartyBr, T89667 #199) bekam
        den Hinweis nie, obwohl ihr Strom genauso ungeteilt blieb. ⛔ *„Ob ein
        Gerät kühlen kann, ist Bauart"* stand hier bis dahin wörtlich — und ist
        genau der Satz, den SOLL §3.2a/E6 verwirft.

        ⛔ **Kein Befund für Altbestand-Zeiträume.** Der Modus lässt sich nicht
        nachtragen (Konzept D9: recorder-Purge, keine LTS für Zustände) — wer
        heute zuordnet, bekommt die Aufteilung ab heute. Ein Hinweis auf die
        Vergangenheit wäre unauflösbar.
        """
        from datetime import date
        from backend.core.berechnungen.betriebsart_gemessen import (
            betriebsart_nutzenergie_kwh,
            betriebsart_strom_kwh,
            modus_strom_zeile,
        )
        from backend.core.betriebsmodus import (
            BETRIEBSART_NUTZENERGIE_FELD,
            BETRIEBSART_STROM_FELD,
            KUEHLEN,
        )
        from backend.core.investition_parameter import ist_luft_luft_waermepumpe
        from backend.models.investition import Investition as _Inv

        _KUEHL_FELDER = {BETRIEBSART_STROM_FELD[KUEHLEN], BETRIEBSART_NUTZENERGIE_FELD[KUEHLEN]}

        kat = CheckKategorie.KLIMA_MODUS_SENSOR.value

        inv_result = await self.db.execute(
            select(_Inv).where(
                _Inv.anlage_id == anlage.id,
                _Inv.typ == "waermepumpe",
            )
        )
        # ⚠ `aktiv` allein reicht nicht: Ein ERSETZTES Geraet wird per
        # `stilllegungsdatum` beendet, nicht per Haken — die Anleitung zum
        # Geraetetausch (HANDBUCH_EINSTELLUNGEN §3.2) verbietet den Haken sogar
        # ausdruecklich. Ohne die Tages-Ebene fordert dieser Check an einem
        # laengst ersetzten Geraet weiter einen Betriebsmodus-Sensor ein — ein
        # Hinweis, den niemand mehr aufloesen kann (P-6-Falle, dieselbe Klasse
        # wie N-313 und der SoC-Check oben).
        heute = date.today()
        sensor_mapping = anlage.sensor_mapping or {}
        mapping = sensor_mapping.get("investitionen", {}) or {}
        quellen_alle = sensor_mapping.get("quellen") or {}
        aktive = [i for i in inv_result.scalars().all() if i.ist_aktiv_an(heute)]

        # Kühl-Spur aus den Monatszeilen: gemessener Kühlstrom oder Kältemenge.
        imd_alle = (await self.db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_([i.id for i in aktive] or [-1])
            )
        )).scalars().all()
        kuehl_in_daten = {
            imd.investition_id for imd in imd_alle
            if betriebsart_strom_kwh(imd.verbrauch_daten or {}, KUEHLEN) is not None
            or betriebsart_nutzenergie_kwh(imd.verbrauch_daten or {}, KUEHLEN) is not None
        }

        def _hat_kuehl_spur(inv_id: int) -> bool:
            """Ist an diesem Gerät irgendeine Kühl-Größe zugeordnet oder gepflegt?"""
            if inv_id in kuehl_in_daten:
                return True
            eintrag = mapping.get(str(inv_id))
            if isinstance(eintrag, dict):
                for k, m in (eintrag.get("felder") or {}).items():
                    if basis_feld_key(k) in _KUEHL_FELDER and isinstance(m, dict) \
                            and m.get("strategie") == "sensor" and m.get("sensor_id"):
                        return True
                for k, v in (eintrag.get("live") or {}).items():
                    if basis_feld_key(k) == "leistung_kuehlen_w" and bool(v):
                        return True
            praefix = f"inv_energy_{inv_id}_"
            for feld_id, q in quellen_alle.items():
                if isinstance(feld_id, str) and feld_id.startswith(praefix) \
                        and basis_feld_key(feld_id[len(praefix):]) in _KUEHL_FELDER:
                    quelle = (q or {}).get("quelle") if isinstance(q, dict) else None
                    if quelle and quelle != "keine":
                        return True
            return False

        # ── WK-06 / SOLL-§9-E7: der Kühlanteil wird geschätzt, nicht gelesen ──
        #
        # ⭐ **Was der Anwender hier erfährt** (`[[feedback_eedc_rechnet_
        # voraussetzungen_handgriff]]`): *was eedc rechnet* — es verteilt den
        # gemessenen Gesamtstrom nach dem Betriebsmodus —, *was es voraussetzt*
        # — dass die zwei Zähler den Kühlbetrieb **nicht** getrennt führen —,
        # und *den einen Handgriff*, der aus der Schätzung eine Messung macht.
        #
        # ⛔ **Kein zweiter Turm** (N-346): Es ist ein INFO-Befund in der
        # **bestehenden** Kategorie `KLIMA_MODUS_SENSOR`, die die Nachbarfrage
        # („ist der Betriebsmodus zugeordnet?") schon trägt. Sie meldet für
        # genau diese Anlagen heute „Betriebsmodus ist zugeordnet — OK"; dass
        # daneben eine Größe geschätzt wird, sagt bisher niemand.
        #
        # ⚠ **Nicht auf `klimas` beschränkt, und das ist der Kern.** `klimas`
        # verlangt eine **Kühl-Spur** (gemessener Kühlstrom, Kältemenge oder
        # eine Zuordnung) — und genau die fehlt in dieser Lage. Eine
        # Luft-Wasser-WP mit F5 und Betriebsmodus-Sensor stünde sonst nie in
        # der Liste, obwohl sie der Anlass ist.
        def _hat_kuehl_zaehler(inv_id: int) -> bool:
            """Ist ein **Stromzähler Kühlbetrieb** zugeordnet oder gepflegt?

            ⚠ Enger als {@link _hat_kuehl_spur}: Eine Kältemenge und erst recht
            ein `leistung_kuehlen_w` sind **kein** kWh-Zähler und lösen den
            Fall nicht auf. Wer nur sie hat, soll den Hinweis bekommen.

            ⭐ **Die Regel steht seit dem 21.09.2026 auf Modulebene**
            (`daten_checker/kuehl_zaehler.py`): das Kühlfenster des HA-Exports
            (S3/P8) stellt dieselbe Frage, und ein Nachbau dort hieße, dass der
            Checker „Kühlanteil wird geschätzt" sagt, während der Sensor
            daneben so tut, als wäre er gemessen. Hier bleibt nur die Bindung
            an die drei lokalen Namen.
            """
            return hat_kuehl_zaehler(
                inv_id, imd_zeilen=imd_alle, mapping=mapping, quellen=quellen_alle,
            )

        geschaetzter_kuehlanteil = []
        for i in aktive:
            if not (i.parameter or {}).get("getrennte_strommessung"):
                continue
            if _hat_kuehl_zaehler(i.id):
                continue
            # Die Aufteilung über denselben SoT, den auch die Rechnung befragt:
            # abgeleitet (nicht gemessen), mit Modus-Abdeckung und Kühlanteil.
            if not any(
                imd.investition_id == i.id
                and not (_z := modus_strom_zeile(imd.verbrauch_daten or {})).gemessen
                and _z.abdeckung_h > 0
                and _z.kuehlen_kwh > 0
                for imd in imd_alle
            ):
                continue
            geschaetzter_kuehlanteil.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"„{i.bezeichnung}“: Kühlanteil wird geschätzt — "
                    f"es fehlt ein Stromzähler für den Kühlbetrieb"
                ),
                details=(
                    "Deine Wärmepumpe misst Heizen und Warmwasser getrennt und "
                    "teilt zusätzlich aus dem Betriebsmodus auf. Für den "
                    "Kühlbetrieb gibt es aber keinen eigenen Stromzähler — eedc "
                    "muss den Kühlanteil deshalb aus der Summe der beiden "
                    "anderen Zähler schätzen. "
                    "Die Mengen stimmen weiterhin: Verbrauch, Kosten und CO₂ "
                    "rechnen mit dem vollen Strom. Nur die Aufteilung nach "
                    "Betriebsart ist eine Verteilung und keine Messung, und "
                    "deshalb kürzt sie die Arbeitszahl nicht. "
                    "Ordne „Strom Kühlbetrieb“ zu, dann liest eedc ab, statt zu "
                    "verteilen: Einstellungen → Datenquellen, beim Gerät das "
                    "Feld „Strom Kühlbetrieb“. "
                    "Das ist freiwillig — ohne die Zuordnung bleibt alles wie "
                    "bisher."
                ),
                link=LINK_DATENQUELLEN,
                investition_id=i.id,
            ))

        klimas = [
            i for i in aktive
            if ist_luft_luft_waermepumpe(i) or _hat_kuehl_spur(i.id)
        ]
        if not klimas:
            return geschaetzter_kuehlanteil

        def _hat_modus(inv_id: int) -> bool:
            """Hat dieses Gerät IRGENDEINE Modus-Zuordnung?

            ⚠ **Nicht `live["betriebsmodus"]` allein** (#263): Mit einer
            Innengeräte-Liste heißt der Key `betriebsmodus-3`. Wer nur den
            nackten Namen prüft, meldet „Betriebsmodus nicht zugeordnet" an
            einer Anlage, an der alle drei Innengeräte zugeordnet sind.
            """
            eintrag = mapping.get(str(inv_id))
            if not isinstance(eintrag, dict):
                return False
            live = eintrag.get("live") or {}
            return any(
                bool(v) and basis_feld_key(k) == "betriebsmodus"
                for k, v in live.items()
            )

        # ── F-60: der ZWEITE Weg zu derselben Aufteilung ─────────────────────
        #
        # Seit v4.0.24 kann der Verbrauch je Betriebsart **gemessen** ankommen
        # (vier Zähler, am Gerät oder je Innengerät). Wo er das tut, gilt
        # `betriebsart_gemessen.modus_strom_zeile`: **gemessen schlägt
        # abgeleitet, ganz oder gar nicht je Zeile** — der aus dem Betriebsmodus
        # gerechnete Split wird dann gar nicht erst angewandt.
        #
        # ⛔ Ohne diese Weiche log der Hinweis doppelt: „Heiz- und Kühlstrom
        # bleiben zusammen" war falsch, UND er riet zu einer Zuordnung, deren
        # Ergebnis eedc anschließend verwirft — ein Weg ohne Wirkung. Betroffen
        # war genau die Zielgruppe, für die v4.0.24 gebaut wurde.
        quellen = sensor_mapping.get("quellen") or {}

        def _hat_gemessene_zuordnung(inv_id: int) -> bool:
            """Ist für dieses Gerät ein Betriebsart-Zähler EINGERICHTET?

            Zwei Ablagen, beide zählen: `felder` trägt die HA-Sensor-Zuordnung,
            `quellen` die feld-zentrische Zuordnung der Datenquellen-Fläche
            (MQTT, Connector). Nur `felder` zu prüfen hieße, die Falschmeldung
            für jeden MQTT-Nutzer stehen zu lassen.
            """
            eintrag = mapping.get(str(inv_id))
            if isinstance(eintrag, dict):
                for feld, m in (eintrag.get("felder") or {}).items():
                    if not ist_betriebsart_strom_feld(feld):
                        continue
                    if isinstance(m, dict) and m.get("strategie") == "sensor" and m.get("sensor_id"):
                        return True
            praefix = f"inv_energy_{inv_id}_"
            for feld_id, eintrag_q in quellen.items():
                if not isinstance(feld_id, str) or not feld_id.startswith(praefix):
                    continue
                if not ist_betriebsart_strom_feld(feld_id[len(praefix):]):
                    continue
                # „keine" ist eine ausdrückliche Absage, keine Zuordnung.
                quelle = (eintrag_q or {}).get("quelle") if isinstance(eintrag_q, dict) else None
                if quelle and quelle != "keine":
                    return True
            return False

        # Und die Gegenrichtung: eingerichtet ist nicht dasselbe wie angekommen.
        # Wer die vier Werte im Monatsabschluss von Hand pflegt, hat gar keine
        # Zuordnung — und trotzdem die Aufteilung. Deshalb zusätzlich am Datum
        # gemessen, über denselben SoT-Helfer, den auch die Rechnung befragt.
        klima_ids = [i.id for i in klimas]
        imd_result = await self.db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(klima_ids)
            )
        )
        mit_gemessenen_daten = {
            imd.investition_id
            for imd in imd_result.scalars().all()
            if hat_gemessene_betriebsart(imd.verbrauch_daten or {})
        }

        def _quelle(inv_id: int) -> Optional[str]:
            """Die EINE Modus-Quelle dieses Geräts — oder ``None`` (N-340)."""
            eintrag = mapping.get(str(inv_id))
            return modus_quelle(eintrag.get("live") if isinstance(eintrag, dict) else None)

        def _hat_aufteilung(inv) -> tuple[bool, bool]:
            """(hat Aufteilung, ist sie gemessen?) — die Herkunft gehört dazu."""
            if _hat_gemessene_zuordnung(inv.id) or inv.id in mit_gemessenen_daten:
                return True, True
            # ⚠ **`_hat_modus` reicht hier NICHT** (N-340): Es sagt „irgendeine
            # Zuordnung", die Aufteilung braucht aber **eine eindeutige Quelle**.
            # Wer drei Innengeräte auf drei verschiedene `climate`-Entitäten
            # legt, hatte bis zum 27.08.2026 eine grün gemeldete Zuordnung und
            # trotzdem keine Aufteilung — die Meldung log den Anwender an.
            return _quelle(inv.id) is not None, False

        zustand = {i.id: _hat_aufteilung(i) for i in klimas}
        ohne = [i for i in klimas if not zustand[i.id][0]]
        if not ohne:
            gemessen = sum(1 for i in klimas if zustand[i.id][1])
            if gemessen == len(klimas):
                herkunft = (
                    "Der Verbrauch je Betriebsart kommt gemessen aus deinen Zählern — "
                    "eedc rechnet ihn nicht aus dem Betriebsmodus, sondern liest ihn ab."
                )
                titel = "Betriebsart wird gemessen"
            elif gemessen:
                herkunft = (
                    "Bei einem Teil der Geräte kommt der Verbrauch je Betriebsart "
                    "gemessen aus Zählern, beim Rest leitet eedc ihn stündlich aus "
                    "dem Betriebsmodus ab."
                )
                titel = "Heiz- und Kühlstrom werden getrennt"
            else:
                herkunft = (
                    "eedc schreibt damit stündlich mit, ob das Gerät geheizt oder "
                    "gekühlt hat, und kann den Stromverbrauch entsprechend aufteilen."
                )
                titel = "Betriebsmodus ist zugeordnet"
            return geschaetzter_kuehlanteil + [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung=(
                    f"{titel} bei {'allen ' if len(klimas) > 1 else ''}"
                    f"{len(klimas)} heizend-kühlenden Gerät(en)"
                ),
                details=herkunft,
            )]

        # N-340: Wer zugeordnet hat, aber mehrdeutig, braucht eine ANDERE
        # Auskunft als wer gar nicht zugeordnet hat. Ihm zu sagen „ordne den
        # Betriebsmodus zu" wäre die Meldung, die in die Irre führt — er hat es
        # getan. Ihm fehlt die **Eindeutigkeit**, und der Weg dorthin ist ein
        # Template-Sensor, der seine Innengeräte zu einer Aussage über die
        # ANLAGE zusammenfasst (Handbuch „Wärme & Klima").
        # ⚠ Beide Listen werden gemeldet, nicht die eine STATT der anderen: Eine
        # Anlage kann ein mehrdeutiges und ein gar nicht zugeordnetes Gerät haben.
        mehrdeutig = [i for i in ohne if _hat_modus(i.id)]
        gar_nicht = [i for i in ohne if not _hat_modus(i.id)]
        meldungen_mehrdeutig = [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=(
                    f"„{i.bezeichnung}“: mehrere verschiedene Modus-Quellen — "
                    f"eedc teilt den Strom nicht auf"
                ),
                details=(
                    "Du hast den Betriebsmodus an mehreren Innengeräten zugeordnet, "
                    "und sie zeigen auf verschiedene Entitäten. Der Stromzähler "
                    "dieses Geräts ist aber einer — für die Aufteilung braucht eedc "
                    "deshalb genau eine Aussage darüber, was die ANLAGE gerade tut. "
                    "Aus mehreren Innengeräte-Zuständen einen Anlagen-Zustand zu "
                    "bilden, hängt an deiner Anlage: ob ein Innengerät lüften kann, "
                    "während ein anderes heizt, ob das Außengerät beim Enteisen "
                    "etwas meldet. Das weiß eedc nicht, und es rät nicht. "
                    "Zwei Wege: Ordne dieselbe climate-Entität bei allen "
                    "Innengeräten zu — dann ist es eine Quelle (bei einer "
                    "Ein-Kreis-Anlage gibt ohnehin das Außengerät die Richtung vor). "
                    "Oder baue in Home Assistant einen Template-Sensor, der deine "
                    "Innengeräte zu einer Aussage zusammenfasst, und ordne dessen "
                    "Ergebnis zu — die Vorlage steht im Handbuch unter „Wärme & Klima“. "
                    "Bis dahin bleibt alles wie bisher, der Stromverbrauch zählt "
                    "vollständig."
                ),
                link=LINK_DATENQUELLEN,
                investition_id=i.id,
            ) for i in mehrdeutig]

        return geschaetzter_kuehlanteil + meldungen_mehrdeutig + [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.INFO.value,
            meldung=(
                f"„{i.bezeichnung}“: Betriebsmodus nicht zugeordnet — "
                f"Heiz- und Kühlstrom bleiben zusammen"
            ),
            details=(
                "Dieses Gerät heizt und kühlt über denselben Zähler. eedc "
                "sieht deshalb nur eine Zahl und kann nicht sagen, welcher Teil "
                "des Stroms ins Heizen ging und welcher ins Kühlen — aus den "
                "vorhandenen Werten lässt sich das nicht nachrechnen. "
                "Ordne dafür die climate-Entität des Geräts zu (in Home Assistant "
                "meist „climate.…“, sie zeigt Heizen/Kühlen/Aus): Einstellungen → "
                "Datenquellen, beim Gerät das Feld „Betriebsmodus“. "
                "Das ist freiwillig — ohne die Zuordnung bleibt alles wie bisher, "
                "der Stromverbrauch zählt vollständig. "
                "Ein Hinweis zur Erwartung: Die Aufteilung beginnt mit der "
                "Zuordnung und lässt sich nicht rückwirkend nachtragen."
            ),
            link=LINK_DATENQUELLEN,
            investition_id=i.id,
        ) for i in gar_nicht]
