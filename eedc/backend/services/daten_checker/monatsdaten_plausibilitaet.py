"""
Daten-Checker — die Prüfungen der Monatsdaten-Plausibilität (RF-13, Serie „Funktion vor Datei“).

Der Orchestrator `MonatsdatenChecks._check_monatsdaten_plausibilitaet` bleibt in `monatsdaten.py` — dort
rufen ihn die Tests, und dort liest er `date.today()` (Patch-Ziel `daten_checker.monatsdaten.date`).
Hier stehen seine Phasen, wortgleich umgezogen: der Speicher-Index über die Gerätezeilen und je Monat
eine Funktion je Prüfung, in der Reihenfolge des Orchestrators. Meldung, Schwere, Kategorie und Link
jeder Zeile sind Anwender-Verträge; die Reihenfolge der Meldungen ergibt sich aus der Aufrufreihenfolge.
"""

from typing import Optional

from backend.core.field_definitions import get_speicher_netzladung_kwh
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten

from .kategorien import CheckErgebnis, CheckSeverity


# Theoretisches PV-Maximum pro kWp und Monat (kWh) für Mitteleuropa
# Großzügig bemessen um False Positives zu vermeiden – obere Grenze
# für optimale Ausrichtung und überdurchschnittliche Einstrahlung
PV_MAX_KWH_PRO_KWP = {
    1: 55, 2: 75, 3: 110, 4: 140, 5: 170, 6: 180,
    7: 180, 8: 165, 9: 140, 10: 90, 11: 55, 12: 40,
}


def _netzfelder_nicht_erfasst(
    kat, prefix: str, md_link: str, *, einspeisung_erfasst: bool, netzbezug_erfasst: bool,
) -> list[CheckErgebnis]:
    """Prüfung 0 der Plausibilität: ERROR je Netzfeld ohne erfassten Wert (N-734, ``netzfeld_ist_erfasst``)."""
    ergebnisse: list[CheckErgebnis] = []
    for erfasst, feld, folge in (
        (einspeisung_erfasst, "Einspeisung", "Eigenverbrauch und Autarkie"),
        (netzbezug_erfasst, "Netzbezug", "Gesamtverbrauch, Autarkie und Stromkosten"),
    ):
        if erfasst:
            continue
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.ERROR,
            meldung=f"{prefix}: {feld} nicht erfasst",
            details=(
                f"eedc braucht für jeden Monat einen erfassten Wert für {feld} — auch 0 ist ein Wert. "
                f"Für diesen Monat steht keiner in der Monatszeile (etwa nach einem Import, der nur "
                f"Wallbox- oder PV-Werte enthielt). Cockpit → Monat nimmt ihn dann aus der HA-Statistik, "
                f"sofern dort ein Zähler zugeordnet ist; sonst bleiben {folge} des Monats leer. "
                # N-736: die Fakten-Sichten nehmen den Monat aus der Bilanz (`meta.netz_erfasst`), statt mit 0 zu rechnen.
                f"Übersicht, Jahresbericht, HA-Sensoren, Auswertungen → Tabelle und Aussichten → Finanzen "
                f"lassen den Monat bis dahin aus Eigenverbrauch, Autarkie, Ersparnis und CO₂ heraus (seine "
                f"PV-Erzeugung zählen sie weiter), der Community-Upload teilt ihn nicht; tragen die Tageswerte "
                f"des Monats das Feld, können sie es von dort nehmen. "
                # N-739 (c): zuerst der Weg, der den Messwert holt — der Monatsabschluss zeigt das Feld leer.
                f"Abhilfe: zuerst den HA-Statistik-Import für diesen Monat (ohne „Überschreiben“ genügt, "
                f"solange der Monat so gemeldet ist); sonst im Monatsabschluss den gemessenen Wert eintragen "
                f"— ein leeres Feld ist keine 0."
            ),
            link=md_link,
        ))
    return ergebnisse


def _speicher_index(
    anlage: Anlage, monatsdaten: list[Monatsdaten],
) -> tuple[
    dict[tuple[int, int], tuple[float, float]],
    dict[tuple[int, int], float],
    set[tuple[int, int]],
    dict[tuple[int, int], list[tuple[str, float]]],
]:
    """Speicher je Monat aus den Gerätezeilen: Ladung/Entladung, Netzladung, aktive Monate, Ladung ohne Entladung je Gerät."""
    # Monate mit Speicher-Daten in InvestitionMonatsdaten (neuer Weg).
    # Legacy-Felder batterie_ladung/entladung_kwh in Monatsdaten sind dann NULL –
    # das ist korrekt und darf keine Warnung auslösen.
    # Werte werden auch für die Energiebilanz gebraucht (aggregiert über alle Speicher).
    speicher_imd_bat: dict[tuple[int, int], tuple[float, float]] = {}  # (jahr,monat) → (ladung, entladung)
    speicher_imd_netzladung: dict[tuple[int, int], float] = {}  # (jahr,monat) → Netzladung
    # Monate, in denen mind. ein Speicher zeitlich aktiv war (Anschaffung erfolgt,
    # noch nicht stillgelegt). Verhindert Warnungen für Monate VOR der ersten
    # Batterie-Installation (Issue #226 JanKgh: PV seit 11/2021, Speicher erst
    # ab 11/2022 — der Datenchecker monierte Batterie-Daten für 11/2021).
    speicher_aktiv_monate: set[tuple[int, int]] = set()
    # (e') Ladung erfasst, Entladung fehlt — JE GERÄT, nicht aggregiert.
    #
    # ⭐ Die Warnung darunter („Batterie-Entladung nicht erfasst") gibt es
    # seit jeher, aber **nur auf dem Legacy-Pfad** (`md.batterie_*`, und
    # auch nur, solange für den Monat gar keine `InvestitionMonatsdaten`
    # vorliegen). Auf dem heutigen Erfassungsweg blieb ein Monat mit
    # `ladung_kwh > 0` und fehlender `entladung_kwh` **stumm** — derselbe
    # Fall, den der HA-Export seit A7 `keine-entladung` nennt.
    #
    # ⚠ Je Gerät, weil die Aggregation darunter (`speicher_imd_bat`) die
    # Lücke gerade verdeckt: zwei Speicher, einer davon vollständig, und
    # die Summe sieht heil aus. Der Anwender muss wissen, an welchem Gerät
    # das Feld fehlt — er füllt es dort.
    speicher_ohne_entladung: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for inv in anlage.investitionen:
        if inv.typ == "speicher" and inv.aktiv:
            start = (inv.anschaffungsdatum.year, inv.anschaffungsdatum.month) if inv.anschaffungsdatum else None
            end = (inv.stilllegungsdatum.year, inv.stilllegungsdatum.month) if inv.stilllegungsdatum else None

            def _aktiv_im(key: tuple[int, int], _s=start, _e=end) -> bool:
                """Zählt dieser Monat für DIESES Gerät? (Anschaffung/Stilllegung)"""
                return not (
                    (_s is not None and key < _s) or (_e is not None and key > _e)
                )

            for md in monatsdaten:
                md_key = (md.jahr, md.monat)
                if not _aktiv_im(md_key):
                    continue
                speicher_aktiv_monate.add(md_key)
            for imd in inv.monatsdaten:
                daten = imd.verbrauch_daten or {}
                ladung = daten.get("ladung_kwh")
                entladung = daten.get("entladung_kwh")
                imd_key = (imd.jahr, imd.monat)
                # `entladung == 0` ist ein WERT und kein Hinweis (ADR-002/P4):
                # ein Speicher, der in einem Monat nichts abgegeben hat, ist
                # erfasst. Nur `None` heißt „Feld leer".
                if (
                    entladung is None
                    and ladung is not None
                    and float(ladung) > 0
                    and _aktiv_im(imd_key)
                ):
                    speicher_ohne_entladung.setdefault(imd_key, []).append(
                        (inv.bezeichnung or f"#{inv.id}", float(ladung))
                    )
                if ladung is not None or entladung is not None:
                    key = imd_key
                    prev = speicher_imd_bat.get(key, (0.0, 0.0))
                    speicher_imd_bat[key] = (
                        prev[0] + (ladung or 0),
                        prev[1] + (entladung or 0),
                    )
                    # Netzladung (Arbitrage) getrennt mitführen: sie kommt
                    # NICHT aus der PV und darf im Verwendungs-Stapel (N51)
                    # nicht gegen die Erzeugung gerechnet werden.
                    speicher_imd_netzladung[key] = (
                        speicher_imd_netzladung.get(key, 0.0)
                        + get_speicher_netzladung_kwh(daten)
                    )
    return speicher_imd_bat, speicher_imd_netzladung, speicher_aktiv_monate, speicher_ohne_entladung


def _batterie_legacy_fehlt(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    hat_speicher: bool, speicher_aktiv_monate: set, speicher_imd_monate: set,
) -> list[CheckErgebnis]:
    """Batterie-Felder der Monatszeile fehlen (Legacy-Pfad, nur ohne Gerätezeilen im Monat)."""
    ergebnisse: list[CheckErgebnis] = []
    if (
        hat_speicher
        and (md.jahr, md.monat) in speicher_aktiv_monate
        and (md.jahr, md.monat) not in speicher_imd_monate
    ):
        # Legacy-Felder nur prüfen wenn keine InvestitionMonatsdaten vorhanden
        if md.batterie_ladung_kwh is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{prefix}: Batterie-Ladung nicht erfasst (Speicher vorhanden)",
                details="Ohne Batterie-Daten wird der Gesamtverbrauch falsch berechnet",
                link=md_link,
            ))
        if md.batterie_entladung_kwh is None:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{prefix}: Batterie-Entladung nicht erfasst (Speicher vorhanden)",
                details="Ohne Batterie-Daten wird der Gesamtverbrauch falsch berechnet",
                link=md_link,
            ))
    return ergebnisse


def _speicher_entladung_fehlt(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    speicher_ohne_entladung: dict,
) -> list[CheckErgebnis]:
    """(e') Ladung erfasst, Entladung fehlt — je Gerät (N-550)."""
    ergebnisse: list[CheckErgebnis] = []
    # (e') Derselbe Befund auf dem HEUTIGEN Erfassungsweg — je Gerät.
    #
    # ⛔ **Er steht bewusst AUSSERHALB des `not in speicher_imd_monate`-
    # Zweigs darüber.** Genau dieser Zweig ist der Grund, warum es den
    # Fall bisher nicht gab: sobald für den Monat irgendein
    # `InvestitionMonatsdaten`-Wert vorliegt, schweigt die
    # Legacy-Prüfung — und der neue Weg hatte gar keine. Ein Monat
    # bekommt deshalb entweder die Legacy-Warnung ODER diese hier, nie
    # beide: `speicher_ohne_entladung` ist nur befüllt, wo eine
    # IMD-Zeile mit Ladung existiert, und dann ist der Monat in
    # `speicher_imd_monate`.
    for geraet, ladung_kwh in speicher_ohne_entladung.get((md.jahr, md.monat), []):
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING,
            meldung=(
                f"{prefix}: {geraet}: Entladung nicht erfasst "
                f"(Ladung {fmt_zahl(ladung_kwh, 1)} kWh vorhanden)"
            ),
            details=(
                "Ohne Entladung gibt es keinen gemessenen Wirkungsgrad "
                "und keine Speicher-Ersparnis"
            ),
            link=md_link,
        ))
    return ergebnisse


def _negative_werte(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    pv_erzeugung: Optional[float],
) -> list[CheckErgebnis]:
    """Prüfung 1: negative Werte."""
    ergebnisse: list[CheckErgebnis] = []
    # 1. Negative Werte
    for feld, wert in [
        ("Einspeisung", md.einspeisung_kwh),
        ("Netzbezug", md.netzbezug_kwh),
        ("PV-Erzeugung", pv_erzeugung),
        ("Batterie-Ladung", md.batterie_ladung_kwh),
        ("Batterie-Entladung", md.batterie_entladung_kwh),
    ]:
        if wert is not None and wert < 0:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=f"{prefix}: {feld} ist negativ ({fmt_zahl(wert, 1)} kWh)",
                link=md_link,
            ))
    return ergebnisse


def _pv_ueber_maximum(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    pv_erzeugung: Optional[float], gesamt_kwp: float, pvgis_monat_map: dict, pr: float, pr_count: int,
) -> list[CheckErgebnis]:
    """Prüfung 2: PV-Erzeugung über der Obergrenze (PVGIS × Performance Ratio, sonst statisch)."""
    ergebnisse: list[CheckErgebnis] = []
    # 2. PV-Produktion > Maximum (PVGIS + Performance Ratio oder statisch)
    if pv_erzeugung is not None and gesamt_kwp > 0:
        pvgis_soll = pvgis_monat_map.get(md.monat)
        if pvgis_soll is not None:
            # Dynamische Obergrenze: PVGIS × Performance Ratio × 1.45
            # Der 1.45-Faktor deckt die natürliche Monatsvariation ab
            # (±40% um den Anlagen-Durchschnitt ist typisch)
            # Mindestens PVGIS × 1.5 (für Anlagen ohne genug Historie)
            pr_faktor = max(pr, 1.0) * 1.45 if pr_count >= 6 else 1.5
            max_kwh = pvgis_soll * max(pr_faktor, 1.5)
        else:
            # Statischer Fallback
            max_kwh = gesamt_kwp * PV_MAX_KWH_PRO_KWP.get(md.monat, 180)

        if pv_erzeugung > max_kwh:
            if pvgis_soll is not None:
                details = (
                    f"PVGIS-Prognose: {fmt_zahl(pvgis_soll, 0)} kWh, "
                    f"Obergrenze (×{fmt_zahl(max_kwh / pvgis_soll, 1)}): {fmt_zahl(max_kwh, 0)} kWh"
                )
            else:
                details = (
                    f"Statisches Maximum für {fmt_zahl(gesamt_kwp, 1)} kWp "
                    f"im Monat {md.monat}: ca. {fmt_zahl(max_kwh, 0)} kWh"
                )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING,
                meldung=f"{prefix}: PV-Erzeugung ungewöhnlich hoch ({fmt_zahl(pv_erzeugung, 0)} kWh)",
                details=details,
                link=md_link,
            ))
    return ergebnisse


def _beide_kernfelder_null(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    einspeisung_erfasst: bool, netzbezug_erfasst: bool,
) -> list[CheckErgebnis]:
    """Prüfung 4: Einspeisung und Netzbezug beide als 0 erfasst."""
    ergebnisse: list[CheckErgebnis] = []
    # 4. Beide Kernfelder 0
    # ⚑ Der Text sagt seit 2026-08-16, was gilt, WENN MAN NICHTS TUT
    # (P-6). Vorher stand hier als vollständige Begründung
    # „Wahrscheinlich fehlende Daten" — für eine Anlage ohne
    # Netzanschluss oder einen Monat außer Betrieb ist die 0 aber
    # richtig, und der Befund war für sie durch keine Eingabe
    # abstellbar: die P-6-Falle. Dasselbe Muster wie beim
    # WP-Spezialtarif-Hinweis und bei „Tarif ohne Einspeisevergütung"
    # — der Befund bleibt stehen, sagt aber, dass er in diesem Fall
    # eine Auskunft ist und kein Mangel.
    #
    # ⚠ Bewusst KEIN Stammdaten-Schalter „Inselanlage": Er wäre die
    # richtige Bauform (Tatsachenaussage, widerlegbar über Netzbezug
    # > 0 — das N-235-Muster), zöge aber die Finanzseite nach sich
    # (eedc bewertet Eigenverbrauch als eingesparten Netzbezug; eine
    # Insel spart nichts ein) und bedient eine Gruppe, für die es
    # keinen einzigen bekannten Anwender gibt (Gernot, 16.08.).
    # Trigger für den Schalter: ein echter Melder mit Insel- oder
    # Notstromanlage, oder ein zweiter Check, der dieselbe Erklärung
    # bräuchte — ab dem zweiten Abnehmer trägt sich eine
    # Stammdaten-Angabe, für einen Textfall nicht.
    # N-734: nur für zwei ERFASSTE 0 — fehlt die Herkunft, meldet Prüfung 0 „nicht erfasst", sonst doppelt.
    if (
        einspeisung_erfasst and netzbezug_erfasst
        and md.einspeisung_kwh == 0 and md.netzbezug_kwh == 0
    ):
        ergebnisse.append(CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING,
            meldung=f"{prefix}: Einspeisung und Netzbezug sind beide 0",
            details=(
                "In den allermeisten Fällen fehlen hier schlicht die "
                "Zählerwerte — dann trag sie nach, der Link führt direkt "
                "in diesen Monat. Sind beide Werte bei dir tatsächlich 0 "
                "— weil die Anlage keinen Netzanschluss hat (Inselbetrieb) "
                "oder den ganzen Monat außer Betrieb war (Umzug, Defekt) —, "
                "dann ist 0 richtig und es ist nichts zu tun: Der Hinweis "
                "bleibt dann als Auskunft stehen und sagt, womit eedc für "
                "diesen Monat rechnet."
            ),
            link=md_link,
        ))
    return ergebnisse


def _energiebilanz_negativ(
    kat, prefix: str, md_link: str, md: Monatsdaten, *,
    pv_erzeugung: Optional[float], speicher_imd_bat: dict, hat_speicher: bool,
) -> list[CheckErgebnis]:
    """Prüfung 6: die Energiebilanz des Monats ergibt einen negativen Gesamtverbrauch."""
    ergebnisse: list[CheckErgebnis] = []
    # 6. Energiebilanz: Hausverbrauch = PV - Einspeisung + Netzbezug ± Batterie
    # Nur prüfbar wenn alle Kernfelder vorhanden — die PV gehört dazu.
    # `pv_erzeugung or 0` stand hier bis 2026-07-29 und machte aus einer
    # unauflösbaren PV eine 0; bei erfasster Einspeisung ergab das einen
    # negativen Hausverbrauch und damit einen ERROR über eine Bilanz,
    # die schlicht nicht prüfbar ist.
    if (
        md.einspeisung_kwh is not None
        and md.netzbezug_kwh is not None
        and pv_erzeugung is not None
    ):
        pv = pv_erzeugung
        # Batterie: InvestitionMonatsdaten bevorzugen (neuer Weg), Legacy als Fallback
        imd_key = (md.jahr, md.monat)
        if imd_key in speicher_imd_bat:
            bat_ladung, bat_entladung = speicher_imd_bat[imd_key]
        else:
            bat_ladung = md.batterie_ladung_kwh or 0
            bat_entladung = md.batterie_entladung_kwh or 0
        hausverbrauch = pv - md.einspeisung_kwh + md.netzbezug_kwh + bat_entladung - bat_ladung

        if hausverbrauch < -0.5:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=f"{prefix}: Energiebilanz ergibt negativen Gesamtverbrauch ({fmt_zahl(hausverbrauch, 1)} kWh)",
                details=(
                    f"PV {fmt_zahl(pv, 0)} – Einspeisung {fmt_zahl(md.einspeisung_kwh, 0)} "
                    f"+ Netzbezug {fmt_zahl(md.netzbezug_kwh, 0)} "
                    f"+ Bat.Entladung {fmt_zahl(bat_entladung, 0)} "
                    f"– Bat.Ladung {fmt_zahl(bat_ladung, 0)} = {fmt_zahl(hausverbrauch, 1)} kWh. "
                    f"Häufige Ursachen: vertauschte Einspeisungs-/Netzbezugs-Sensoren "
                    f"im Mapping oder fehlende Batterie-Daten."
                ),
                link=md_link,
            ))
        elif hat_speicher and (md.batterie_ladung_kwh is None or md.batterie_entladung_kwh is None):
            # Bilanz rechnerisch positiv, aber Batterie-Daten fehlen → Warnung dass Wert unzuverlässig
            pass  # bereits durch Check 0 abgedeckt
    return ergebnisse


class MonatsdatenPlausibilitaetChecks:
    """Die zwei Prüfungen, die den Checker brauchen (Tageswerte aus der DB, Ausbau-Helfer von `MonatsdatenChecks`)."""

    async def _erzeugung_gegen_verwendung(
        self, kat, prefix: str, md_link: str, anlage: Anlage, md: Monatsdaten, *,
        pv_erzeugung: Optional[float], speicher_imd_bat: dict, speicher_imd_netzladung: dict,
    ) -> list[CheckErgebnis]:
        """Prüfungen 3 und 3b mit dem gemeinsamen, faulen Nachzug-Hinweis (eine Tageswert-Abfrage je Monat höchstens)."""
        ergebnisse: list[CheckErgebnis] = []
        # Diskriminator für 3 + 3b: stehen in den Tageswerten deutlich mehr
        # kWh als im Monatswert, wurde der Monat schlicht nie nachgezogen —
        # dann ist die sonst zuerst genannte Ursache falsch (coolxmad #353).
        # Lazy: nur berechnen, wenn eine der beiden Prüfungen anschlägt.
        nachzug: Optional[str] = None
        nachzug_geprueft = False

        async def _hole_nachzug_hinweis() -> Optional[str]:
            nonlocal nachzug, nachzug_geprueft
            if not nachzug_geprueft:
                nachzug_geprueft = True
                nachzug = self._nachzug_hinweis(
                    await self._tages_pv_summe_monat(anlage.id, md.jahr, md.monat),
                    pv_erzeugung,
                )
            return nachzug

        # 3. Einspeisung > PV-Erzeugung
        if (
            pv_erzeugung is not None
            and pv_erzeugung > 0
            and md.einspeisung_kwh is not None
            and md.einspeisung_kwh > pv_erzeugung
        ):
            details_3 = (
                "Einspeisung kann nicht höher als die Erzeugung sein. "
                "Häufigste Ursache: Einspeisungs- und Netzbezugs-Sensor "
                "sind im Sensor-Mapping vertauscht (oder das Vorzeichen "
                "eines kombinierten Netz-Sensors ist invertiert)."
            )
            vorspann = await _hole_nachzug_hinweis()
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.ERROR,
                meldung=f"{prefix}: Einspeisung ({fmt_zahl(md.einspeisung_kwh, 0)} kWh) > PV-Erzeugung ({fmt_zahl(pv_erzeugung, 0)} kWh)",
                details=(vorspann or "") + details_3,
                link=md_link,
            ))

        # 3b. Verwendungs-Stapel > Erzeugung (N51, Gernot 2026-07-29)
        #
        # Prüfung 3 vergleicht nur die Einspeisung mit der Erzeugung. Was
        # in den Speicher geladen wurde, kam aber ebenfalls aus der PV —
        # AUSSER dem Arbitrage-Anteil, der aus dem Netz stammt. Übersteigt
        # `Einspeisung + (Speicherladung − Netzladung)` die Erzeugung, ist
        # eine der drei Zahlen falsch.
        #
        # **Bewusst als FRAGE und als WARNING**, nicht als Fehler: der
        # häufigste Auslöser ist eine ungepflegte Netzladung — wer nachts
        # billig lädt und das nicht erfasst, bekommt hier einen ehrlichen
        # Hinweis statt einer Anschuldigung. Rein diagnostisch: die Meldung
        # ändert keine Berechnung und keine Anzeige.
        #
        # Nur wenn PV-Ladung > 0, sonst wäre es eine zweite (und schwächere)
        # Meldung über denselben Sachverhalt wie Prüfung 3.
        bat_ladung_monat, _ = speicher_imd_bat.get((md.jahr, md.monat), (0.0, 0.0))
        pv_ladung_speicher = max(
            0.0,
            bat_ladung_monat - speicher_imd_netzladung.get((md.jahr, md.monat), 0.0),
        )
        if (
            pv_erzeugung is not None
            and pv_erzeugung > 0
            and md.einspeisung_kwh is not None
            and pv_ladung_speicher > 0
        ):
            stapel = md.einspeisung_kwh + pv_ladung_speicher
            # Toleranz: Zählerstände werden je Quelle gerundet, und die drei
            # Zahlen kommen aus verschiedenen Sensoren mit eigenen Messfehlern.
            toleranz = max(5.0, pv_erzeugung * 0.02)
            if stapel > pv_erzeugung + toleranz:
                vorspann = await _hole_nachzug_hinweis()
                ergebnisse.append(CheckErgebnis(
                    kategorie=kat, schwere=CheckSeverity.WARNING,
                    meldung=(
                        f"{prefix}: mehr PV verwendet als erzeugt? "
                        f"Einspeisung ({fmt_zahl(md.einspeisung_kwh, 0)}) + Speicherladung aus PV "
                        f"({fmt_zahl(pv_ladung_speicher, 0)}) = {fmt_zahl(stapel, 0)} kWh, "
                        f"erzeugt wurden {fmt_zahl(pv_erzeugung, 0)} kWh"
                    ),
                    details=(vorspann or "") + (
                        "Beides kommt aus derselben Erzeugung — zusammen kann es "
                        "nicht mehr sein als die PV geliefert hat. Drei häufige "
                        "Ursachen, in dieser Reihenfolge: (1) Der Speicher wird "
                        "auch aus dem Netz geladen (Arbitrage/Notladung), aber das "
                        "Feld „Ladung aus Netz“ ist nicht gepflegt — dann ist nur "
                        "die Zuordnung unvollständig, nicht die Energie. "
                        "(2) Die Erzeugung ist zu niedrig erfasst, etwa weil ein "
                        "String-Sensor im Monat ausgesetzt hat. (3) Einspeisung "
                        "und Netzbezug sind vertauscht (dann meldet die Prüfung "
                        "darüber meist zusätzlich). Rein diagnostisch — es wird "
                        "nichts automatisch korrigiert."
                    ),
                    link=md_link,
                ))
        return ergebnisse

    def _vorjahressprung(
        self, kat, prefix: str, md_link: str, anlage: Anlage, md: Monatsdaten, *,
        md_map: dict,
    ) -> list[CheckErgebnis]:
        """Prüfung 5: Einspeisung bzw. Netzbezug über dem Dreifachen des Vorjahresmonats."""
        ergebnisse: list[CheckErgebnis] = []
        # 5. Extreme Sprünge zum Vorjahr
        # #240 NongJoWo: Wenn der Vorjahresmonat der Inbetriebnahme-Monat
        # der Anlage (oder davor) ist, sind die Werte nur Bruchteil-
        # Erfassung — keine valide Vergleichsbasis. Beispiel: Anlage seit
        # Ende März 2022 → März 2022 = ein paar Tage, der März-2023-
        # Vergleich (3× höher) ist deshalb keine Anomalie.
        vorjahr = md_map.get((md.jahr - 1, md.monat))
        inst = anlage.installationsdatum
        if (
            vorjahr
            and not (inst and (vorjahr.jahr, vorjahr.monat) <= (inst.year, inst.month))
        ):
            # #362 kingcap1: Eine in Stufen ausgebaute Anlage erzeugt den
            # Sprung selbst — 2024 hingen mehr Module am Netz als 2023.
            # Für die Einspeisung setzt die Prüfung dann aus (Begründung
            # in `_erzeugung_ausgebaut`). Der Netzbezug hat sein eigenes
            # Gegenstück: er sinkt mit mehr PV — der Erzeuger-Zubau wäre
            # dort die falsche Erklärung —, aber er wächst mit neuen
            # Verbrauchern (WP, E-Auto, Wallbox). Jede Seite bekommt also
            # die Ausnahme, die zu ihrer Ursache gehört.
            ausgebaut = self._erzeugung_ausgebaut(anlage, vorjahr, md)
            verbraucher_zugebaut = self._verbrauch_ausgebaut(anlage, vorjahr, md)
            for feld, wert, vj_wert in [
                ("Einspeisung", md.einspeisung_kwh, vorjahr.einspeisung_kwh),
                ("Netzbezug", md.netzbezug_kwh, vorjahr.netzbezug_kwh),
            ]:
                if feld == "Einspeisung" and ausgebaut:
                    continue
                if feld == "Netzbezug" and verbraucher_zugebaut:
                    continue
                if vj_wert and vj_wert > 50 and wert is not None and wert > 3 * vj_wert:
                    ergebnisse.append(CheckErgebnis(
                        kategorie=kat, schwere=CheckSeverity.WARNING,
                        meldung=f"{prefix}: {feld} > 3× Vorjahr ({fmt_zahl(wert, 0)} vs. {fmt_zahl(vj_wert, 0)} kWh)",
                        details="Deutliche Abweichung zum Vorjahresmonat",
                        link=md_link,
                    ))
        return ergebnisse
