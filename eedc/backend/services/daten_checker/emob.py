"""
Daten-Checker — E-Mob-Pool-Pflege & Sensor-Doppelmapping (`EmobChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date, timedelta

from sqlalchemy import select

from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


class EmobChecks:
    """Diagnose für parallel gepflegte Wallbox-/E-Auto-Investitionen."""

    # E-Mob-Pool-Pflege (Wallbox + E-Auto parallel gepflegt). Schwellen aus
    # dem Konzept KONZEPT-WALLBOX-EAUTO.md Phase 2a, justiert auf typische
    # Setups (Krümel-Pflege durch evcc-Imports an einer der beiden Quellen
    # darf keinen Fehlalarm auslösen).
    EMOB_POOL_MIN_KWH_PRO_MONAT = 10.0   # unterhalb = Krümel, ignorieren
    EMOB_POOL_AEHNLICHKEITS_RATIO = 0.3  # min/max ≥ 0.3 = beide nennenswert
    EMOB_POOL_PV_INKONSISTENZ = 0.10     # |WB.pv − EA.pv| / max > 10 % auffällig
    EMOB_POOL_MINDEST_MONATE = 3         # eine Monatslücke ist kein Pflege-Muster
    EMOB_POOL_FENSTER_MONATE = 12        # Beobachtungsfenster

    def _check_emob_pool_pflege(self, anlage: Anlage) -> list[CheckErgebnis]:
        """E-Auto- + Wallbox-Investition parallel gepflegt → Pflege-Konflikt.

        Wallbox (Loadpoint-Sicht) und E-Auto (Vehicle-Sicht) messen häufig
        denselben Stromfluss aus zwei Perspektiven. Seit Phase 2a wählen die
        Read-Sites die Quelle strukturell (Wallbox vorhanden → Wallbox) und die
        Migration konsolidiert Bestände in den Wallbox-Slot. Was die Migration
        nicht verlustfrei auflösen kann (z. B. Total auf der einen, PV-Split nur
        auf der anderen Seite) bleibt als Doppel-Pflege stehen.

        Diese Diagnose erkennt das Pflege-Muster („beide Quellen über mehrere
        Monate hinweg nennenswert befüllt") und lenkt den Anwender auf eine
        bewusste Entscheidung — nur eine Quelle pflegen.

        Severities:
        - INFO: ≥ MINDEST_MONATE Monate mit Doppel-Pflege (Pool wirkt).
        - WARNING: zusätzlich PV-Inkonsistenz (`|WB.pv − EA.pv| / max > 10 %`)
          in mindestens einem dieser Monate — Indiz für *echte* Doppelung,
          nicht nur zweifache Pflege identischer Werte.
        """
        from backend.core.field_definitions import (
            get_eauto_ladung_kwh,
            get_emob_pv_netz_kwh,
        )
        from backend.core.investition_parameter import ist_dienstlich

        kat = CheckKategorie.EMOB_POOL_PFLEGE.value
        ergebnisse: list[CheckErgebnis] = []

        eautos = [
            i for i in anlage.investitionen
            if i.typ == "e-auto" and not ist_dienstlich(i)
        ]
        wallboxen = [
            i for i in anlage.investitionen
            if i.typ == "wallbox" and not ist_dienstlich(i)
        ]
        if not eautos or not wallboxen:
            return ergebnisse  # Pflege-Konflikt unmöglich ohne beide Seiten.

        # Wallbox-Schwäche A (KONZEPT-WALLBOX-EAUTO.md »Bekannte Schwächen«):
        # Für die E-Auto-Seite NICHT der `verbrauch_kwh`-Fallback aus
        # get_eauto_ladung_kwh — bei einem E-Auto ist `verbrauch_kwh` der
        # Fahrverbrauch, nicht die Heimladung. Sonst wertet der Pflege-Check ein
        # E-Auto mit gepflegtem Fahrverbrauch fälschlich als „Heimladung tragend"
        # und feuert einen Konflikt, obwohl die Wallbox die einzige Heimladungs-
        # Quelle ist. Nur das explizite `ladung_kwh` zählt hier als Heimladung.
        def _ea_heimladung_kwh(data: dict) -> float:
            return float((data or {}).get("ladung_kwh") or 0)

        # Beobachtungsfenster: die letzten N Monate, in denen mindestens eine
        # Investition aktiv war.
        from datetime import date

        heute = date.today()
        fenster_monate: list[tuple[int, int]] = []
        for offset in range(self.EMOB_POOL_FENSTER_MONATE):
            jahr = heute.year + ((heute.month - 1 - offset) // 12)
            monat = ((heute.month - 1 - offset) % 12) + 1
            fenster_monate.append((jahr, monat))

        doppel_monate: list[tuple[int, int, float, float]] = []
        inkonsistenz_monate: list[tuple[int, int, float, float]] = []

        for jahr, monat in fenster_monate:
            ea_ladung = ea_pv = 0.0
            wb_ladung = wb_pv = 0.0
            for inv in eautos:
                if not inv.ist_aktiv_im_monat(jahr, monat):
                    continue
                for imd in inv.monatsdaten:
                    if imd.jahr != jahr or imd.monat != monat:
                        continue
                    data = imd.verbrauch_daten or {}
                    total = _ea_heimladung_kwh(data)
                    pv, _netz = get_emob_pv_netz_kwh(data, total_kwh=total)
                    ea_ladung += total
                    ea_pv += pv
            for inv in wallboxen:
                if not inv.ist_aktiv_im_monat(jahr, monat):
                    continue
                for imd in inv.monatsdaten:
                    if imd.jahr != jahr or imd.monat != monat:
                        continue
                    data = imd.verbrauch_daten or {}
                    total = get_eauto_ladung_kwh(data)
                    pv, _netz = get_emob_pv_netz_kwh(data, total_kwh=total)
                    wb_ladung += total
                    wb_pv += pv

            min_ladung = min(ea_ladung, wb_ladung)
            max_ladung = max(ea_ladung, wb_ladung)
            if min_ladung < self.EMOB_POOL_MIN_KWH_PRO_MONAT:
                continue  # Krümel-Pflege auf einer Seite — kein Konflikt.
            ratio = min_ladung / max_ladung if max_ladung > 0 else 0.0
            if ratio < self.EMOB_POOL_AEHNLICHKEITS_RATIO:
                continue  # eine Seite dominant — Pool-Heuristik wählt klar.

            doppel_monate.append((jahr, monat, ea_ladung, wb_ladung))

            # PV-Konsistenz: beide Sichten sollen denselben Stromfluss messen,
            # also auch denselben PV-Anteil. Abweichung > 10 % ist Pflege-
            # Konflikt, nicht nur Doppel-Pflege.
            max_pv = max(ea_pv, wb_pv)
            if max_pv > 0:
                pv_diff = abs(ea_pv - wb_pv) / max_pv
                if pv_diff > self.EMOB_POOL_PV_INKONSISTENZ:
                    inkonsistenz_monate.append((jahr, monat, ea_pv, wb_pv))

        if len(doppel_monate) < self.EMOB_POOL_MINDEST_MONATE:
            return ergebnisse

        beispiel_monate = ", ".join(
            f"{m:02d}/{j} (EA {ea:.0f} kWh / WB {wb:.0f} kWh)"
            for j, m, ea, wb in doppel_monate[:3]
        )

        if inkonsistenz_monate:
            j, m, ea_pv, wb_pv = inkonsistenz_monate[0]
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung=(
                    "Pflege-Konflikt: E-Auto- und Wallbox-PV-Anteil "
                    "weichen voneinander ab"
                ),
                details=(
                    f"In {len(doppel_monate)} Monaten der letzten "
                    f"{self.EMOB_POOL_FENSTER_MONATE} sind sowohl die "
                    "E-Auto- als auch die Wallbox-Investition mit "
                    "Heimladung gepflegt (Beispiele: "
                    f"{beispiel_monate}). Im Monat {m:02d}/{j} liegt der "
                    f"PV-Anteil bei EA={ea_pv:.0f} kWh, WB={wb_pv:.0f} kWh "
                    f"— Abweichung > {int(self.EMOB_POOL_PV_INKONSISTENZ*100)} %, "
                    "obwohl beide Sichten denselben Stromfluss messen "
                    "sollten. eedc führt die Heimladung kanonisch an der "
                    "Wallbox (sie misst den Ladepunkt); der parallel am "
                    "E-Auto gepflegte Wert wird in den Auswertungen ignoriert. "
                    "Damit dein PV-Anteil stimmt: pflege die Heimladung nur an "
                    "der Wallbox und lasse die E-Auto-Heimladung leer "
                    "(km, Verbrauch, Extern und V2H bleiben am E-Auto)."
                ),
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.INFO.value,
                meldung=(
                    "E-Auto- und Wallbox-Investition tragen beide Heimladung "
                    "— die Wallbox ist die Quelle"
                ),
                details=(
                    f"In {len(doppel_monate)} Monaten der letzten "
                    f"{self.EMOB_POOL_FENSTER_MONATE} sind beide Sichten "
                    "mit Heimladung gepflegt (Beispiele: "
                    f"{beispiel_monate}). Wallbox- und E-Auto-Investition "
                    "messen oft denselben Stromfluss aus zwei Perspektiven; "
                    "eedc führt die Heimladung kanonisch an der Wallbox, die "
                    "parallel am E-Auto gepflegte Heimladung wird in den "
                    "Auswertungen nicht verwendet. Sauberer ist, nur die "
                    "Wallbox zu pflegen und die E-Auto-Heimladung leer zu "
                    "lassen (km/Verbrauch/Extern/V2H bleiben am E-Auto)."
                ),
            ))

        return ergebnisse

    #: #331: unterhalb dieser Monatszahl ohne Fahrverbrauch ist eine Lücke
    #: kein Muster — ein einzelner nachzupflegender Monat wird nicht gemeldet.
    PHEV_MINDEST_MONATE_OHNE_VERBRAUCH = 2

    # N-201: Ab welcher Abweichung ist `ladung_pv_kwh > ladung_kwh` ein
    # Widerspruch und nicht Rundung? Beide Werte werden in kWh mit einer
    # Nachkommastelle gepflegt bzw. importiert; 0,1 kWh deckt die Rundung ab,
    # ohne einen echten Fall zu verschlucken (der gemessene Anlassfall liegt
    # 14,5 kWh auseinander).
    EMOB_PV_UEBERHANG_TOLERANZ_KWH = 0.1

    def _check_emob_pv_ueber_gesamt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Eine Monatszeile, in der die PV-Ladung größer ist als die Ladung (N-201).

        **Was hier schiefsteht.** ``ladung_pv_kwh`` ist ein *Teil* von
        ``ladung_kwh`` — es kann nicht mehr Strom aus PV geladen worden sein,
        als insgesamt geladen wurde. An Anlage 1 stand für 06/2026 real
        ``100,5 kWh PV`` bei ``86,0 kWh Gesamt``.

        **Warum trotzdem nirgends eine falsche Zahl steht.** Die Rechenkette
        fängt den Widerspruch strukturell ab: ``summiere_emob_quelle``
        konstruiert ``ladung_kwh`` als ``pv + netz``, statt das Feld zu lesen,
        und ``get_emob_pv_netz_kwh`` klemmt den abgeleiteten Netz-Anteil mit
        ``max(0, total − pv)``. Damit gilt ``ladung_kwh ≥ pv`` immer (#262,
        gewächtert in ``test_n314_pv_ladeanteil_spanne.py``).

        ⭐ **Und genau das ist der Grund, warum es eine Meldung braucht.** Die
        Garantie repariert die *Rechnung*, nicht die *Zeile*: Der gepflegte Wert
        ``ladung_kwh = 86,0`` wird dabei stillschweigend verworfen und durch
        ``pv + netz`` ersetzt. Der Anwender sieht eine Gesamtladung, die er nie
        eingetragen hat, und erfährt nie, dass einer seiner beiden Werte falsch
        ist. ``monats_fakten.pv_ladeanteil_prozent`` hält das im Docstring als
        offene Lücke fest — diese Prüfung schließt sie.

        **WARNING, nicht ERROR** und ohne Reparatur-Knopf: eedc kann nicht
        wissen, welcher der beiden Werte der richtige ist — raten wäre hier
        dasselbe wie beim Reihenbruch eines Zählerstands. Der Weg steht daneben
        (``feedback_kein_grosser_heiler_knopf``).

        ⚠ **Nur wenn BEIDE Felder gepflegt sind.** Fehlt ``ladung_kwh``, ist die
        Zeile unvollständig, nicht widersprüchlich — das ist die Frage der
        Vollständigkeits-Prüfungen, kein zweiter Turm darüber.
        """
        kat = CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value
        ergebnisse: list[CheckErgebnis] = []

        # Checker-Pfad: liest die Rohzeile bewusst selbst (ADR-002/P10 nimmt
        # Schreib-, Import- und Checker-Pfade aus). Der Sinn dieser Prüfung ist
        # ja gerade, den Zustand VOR der SoT-Auflösung zu sehen — über die
        # Fakten-Schicht gelesen wäre der Widerspruch bereits weggeklemmt.
        treffer: list[tuple[int, str, int, int, float, float]] = []
        for inv in anlage.investitionen:
            if inv.typ not in ("wallbox", "e-auto"):
                continue
            name = inv.bezeichnung or f"#{inv.id}"
            for imd in inv.monatsdaten:
                daten = imd.verbrauch_daten or {}
                gesamt = daten.get("ladung_kwh")
                pv = daten.get("ladung_pv_kwh")
                if gesamt is None or pv is None:
                    continue
                try:
                    gesamt_f, pv_f = float(gesamt), float(pv)
                except (TypeError, ValueError):
                    continue
                if pv_f > gesamt_f + self.EMOB_PV_UEBERHANG_TOLERANZ_KWH:
                    treffer.append(
                        (inv.id, name, imd.jahr, imd.monat, gesamt_f, pv_f)
                    )

        if not treffer:
            return ergebnisse

        # Datums-Listen absteigend (Regel 0a), Gerät als zweites Kriterium.
        treffer.sort(key=lambda t: (-t[2], -t[3], t[1]))
        MAX_EINZEL = 10
        for inv_id, name, jahr, monat, gesamt_f, pv_f in treffer[:MAX_EINZEL]:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=(
                    f"{name}: PV-Ladung größer als Gesamtladung "
                    f"({monat:02d}/{jahr}: {pv_f:.1f} kWh von {gesamt_f:.1f} kWh)"
                ),
                details=(
                    "Die PV-Ladung ist ein Teil der Gesamtladung und kann nicht "
                    "größer sein. eedc rechnet deshalb mit PV + Netz weiter und "
                    f"legt die eingetragenen {gesamt_f:.1f} kWh beiseite — die "
                    "Zahl, die du siehst, ist dann nicht die, die du erfasst "
                    "hast. Welcher der beiden Werte stimmt, kann eedc nicht "
                    "wissen: Trage den Monat noch einmal nach."
                ),
                link=f"/einstellungen/daten?erfassen={jahr}-{monat:02d}",
                investition_id=inv_id,
            ))

        if len(treffer) > MAX_EINZEL:
            rest = len(treffer) - MAX_EINZEL
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=f"… plus {rest} weitere(r) Monat(e) mit demselben Widerspruch",
            ))

        return ergebnisse

    def _check_phev_anteil_unbestimmt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """PHEV gepflegt, aber der elektrische Anteil ist nicht bestimmbar.

        Trägt ein Fahrzeug einen `eigener_verbrauch_l_100km`, hat es laut
        Entscheidung 3 des Konzepts einen Verbrenner. Um seine Kilometer
        aufzuteilen, braucht eedc **eine** von zwei Angaben: den monatlich
        erfassten Fahrverbrauch (`verbrauch_kwh`, der gemessene Weg) oder einen
        gepflegten `elektrischer_fahranteil_prozent` (der geschätzte).

        Fehlen beide, rechnet eedc **100 % elektrisch** — das heutige Verhalten,
        bewusst gewählt statt eines erfundenen Richtwerts. Ersparnis und
        CO₂-Bilanz fallen dadurch zu gut aus, und genau das darf nicht still
        passieren ([[feedback_daten_checker_kein_akzeptiert]]).
        """
        from backend.core.investition_parameter import ist_dienstlich
        from backend.services.eauto_wirtschaftlichkeit import (
            eigener_verbrauch_l_100km,
            fahranteil_prozent,
        )

        kat = CheckKategorie.PHEV_ANTEIL_UNBESTIMMT.value
        ergebnisse: list[CheckErgebnis] = []

        for inv in anlage.investitionen:
            if inv.typ != "e-auto" or ist_dienstlich(inv):
                continue
            if eigener_verbrauch_l_100km(inv.parameter) is None:
                continue  # BEV — nichts aufzuteilen.
            # Über den SoT-Helper, nicht über den Rohwert: „nicht gepflegt"
            # heißt auch ein geleertes Feld (`""`) oder ein unbrauchbarer Wert.
            # `is not None` auf dem Rohwert sah in beiden Fällen einen Wert und
            # ließ den Check schweigen, während `teile_fahrleistung` mangels
            # Zahl auf „100 % elektrisch" fiel — der Check verstummte genau in
            # der Lage, für die er gebaut ist. `0` bleibt ein gepflegter Wert.
            if fahranteil_prozent(inv.parameter) is not None:
                continue  # geschätzter Weg ist gepflegt.

            # Monate MIT gefahrenen km, aber OHNE erfassten Fahrverbrauch —
            # nur die sind unbestimmt. Ein Monat ohne km teilt nichts auf.
            monate_ohne = [
                imd for imd in getattr(inv, "monatsdaten", []) or []
                if ((imd.verbrauch_daten or {}).get("km_gefahren") or 0) > 0
                and not ((imd.verbrauch_daten or {}).get("verbrauch_kwh") or 0)
            ]
            if len(monate_ohne) < self.PHEV_MINDEST_MONATE_OHNE_VERBRAUCH:
                continue

            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung=(
                    f"{inv.bezeichnung}: Verbrenner-Verbrauch gepflegt, aber "
                    "der elektrische Fahranteil ist nicht bestimmbar"
                ),
                details=(
                    f"In {len(monate_ohne)} Monaten sind Kilometer erfasst, "
                    "aber kein elektrischer Fahrverbrauch (Monatsfeld "
                    "Verbrauch in kWh). Ohne ihn und ohne gepflegten "
                    "elektrischen Fahranteil in Prozent rechnet eedc diese "
                    "Monate mit 100 % elektrisch gefahrenen Kilometern — "
                    "Ersparnis und "
                    "CO₂-Einsparung fallen dadurch zu gut aus. Abhilfe: "
                    "entweder den monatlichen Fahrverbrauch erfassen (dann "
                    "rechnet eedc den Anteil gemessen) oder in der "
                    "Investition einen geschätzten Fahranteil eintragen."
                ),
                investition_id=inv.id,
            ))

        return ergebnisse

    def _check_emob_sensor_doppelmapping(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Gleiche Sensor-Entity an Wallbox UND E-Auto gemappt → Doppelzählung.

        Ist dieselbe HA-Entity (Live-`leistung_w` oder ein kWh-Zähler) sowohl
        einer Wallbox- als auch einer E-Auto-Investition zugeordnet, messen beide
        denselben Ladestrom. Der Live-Energiefluss dedupliziert das (Wallbox-
        Priorität), aber die Monats-/Stunden-Aggregation poolt nur über
        `parent_investition_id` — ohne gesetzten Link zählt sie die Ladung
        DOPPELT (#314-Untersuchung). Deterministische Diagnose aus dem
        `sensor_mapping`: lenkt den Anwender darauf, eine der beiden Zuordnungen
        zu entfernen. Brücke vor Phase 2a (kanonische Quelle),
        docs/KONZEPT-WALLBOX-EAUTO.md.
        """
        kat = CheckKategorie.EMOB_POOL_PFLEGE.value
        mapping = anlage.sensor_mapping or {}
        inv_mapping = mapping.get("investitionen", {}) or {}
        typ_by_id = {str(i.id): i.typ for i in anlage.investitionen}
        name_by_id = {str(i.id): i.bezeichnung for i in anlage.investitionen}

        # Alle einer Investition zugeordneten Entity-IDs einsammeln (Live-Strings
        # + Zähler-`sensor_id`), dann Entity → nutzende Investitionen invertieren.
        entity_use: dict[str, set[str]] = {}
        for inv_id, inv_data in inv_mapping.items():
            if not isinstance(inv_data, dict):
                continue
            entities: set[str] = set()
            live = inv_data.get("live")
            if isinstance(live, dict):
                entities.update(str(v) for v in live.values() if v)
            felder = inv_data.get("felder")
            if isinstance(felder, dict):
                for cfg in felder.values():
                    if (isinstance(cfg, dict) and cfg.get("strategie") == "sensor"
                            and cfg.get("sensor_id")):
                        entities.add(str(cfg["sensor_id"]))
            for eid in entities:
                entity_use.setdefault(eid, set()).add(str(inv_id))

        ergebnisse: list[CheckErgebnis] = []
        for eid, inv_ids in entity_use.items():
            typen = {typ_by_id.get(iid) for iid in inv_ids}
            if "wallbox" not in typen or "e-auto" not in typen:
                continue
            wb = sorted(name_by_id.get(i, i) for i in inv_ids
                        if typ_by_id.get(i) == "wallbox")
            ea = sorted(name_by_id.get(i, i) for i in inv_ids
                        if typ_by_id.get(i) == "e-auto")
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung="Gleicher Sensor an Wallbox und E-Auto zugeordnet",
                details=(
                    f"Die Entity „{eid}“ ist sowohl der Wallbox "
                    f"({', '.join(wb)}) als auch dem E-Auto ({', '.join(ea)}) "
                    "zugeordnet — beide messen denselben Ladestrom. In Monats-/"
                    "Jahresauswertungen wird die Ladung dadurch doppelt gezählt "
                    "(im Live-Energiefluss nicht). Bitte die Zuordnung an einer "
                    "der beiden Investitionen entfernen — Faustregel: die Wallbox "
                    "misst den Stromfluss, das E-Auto trägt Nutzung/Kilometer."
                ),
            ))
        return ergebnisse

    # ── N-186: die Alt-Tage von F-14 ────────────────────────────────────────
    #: Unterhalb dieser Schwelle ist die Überschneidung Krümel (Rundung,
    #: Standby) und kein doppelt gezählter Ladevorgang.
    EMOB_DOPPEL_MIN_KWH_PRO_TAG = 1.0
    #: Fenster der Rückschau — dieselbe Größenordnung wie der Drift-Check.
    EMOB_DOPPEL_FENSTER_TAGE = 180

    async def _check_emob_doppelzaehlung_tage(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Gespeicherte Tage, an denen Wallbox UND E-Auto dieselbe Ladung tragen.

        F-14 (#356) hat die strukturelle Quellen-Regel gebaut: trägt eine
        Wallbox die Ladeenergie, ist sie die Quelle. Das gilt für **neue**
        Tage. Was vorher geschrieben wurde, steht weiter in
        ``TagesZusammenfassung.komponenten_kwh`` — an Gernots Anlage am
        2026-08-06 mit 29,32 statt 12,00 kWh.

        ⚠ **Warum ein Checker und keine Start-Migration:** die Heilung
        überschreibt Tages- und Stundenwerte. Ein Lauf, der beim Hochfahren
        ungefragt Messwerte ersetzt, ist genau der „große Heiler-Knopf", den
        dieses Projekt nicht will ([[feedback_kein_grosser_heiler_knopf]] ·
        [[feedback_reparatur_statt_loesch_features]]). Der Anwender sieht den
        Befund, die betroffenen Tage und entscheidet.

        ⚠ **Kein Befund heißt hier nicht „geprüft und sauber", sondern
        „geprüft, soweit Tageswerte vorliegen"** — Tage ohne
        ``komponenten_kwh`` kann diese Prüfung nicht bewerten.
        """
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS

        kat = CheckKategorie.EMOB_DOPPELZAEHLUNG_TAGE.value

        eautos = [i for i in anlage.investitionen if i.typ == "e-auto"]
        wallboxen = [i for i in anlage.investitionen if i.typ == "wallbox"]
        if not eautos or not wallboxen:
            return []

        bis = date.today()
        von = bis - timedelta(days=self.EMOB_DOPPEL_FENSTER_TAGE)
        rows = (await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            ).order_by(TagesZusammenfassung.datum)
        )).scalars().all()

        wb_keys = {f"wallbox_{w.id}" for w in wallboxen}
        ea_keys = {f"eauto_{e.id}" for e in eautos}

        befunde: list[tuple[date, float, float]] = []
        for tz in rows:
            komp = tz.komponenten_kwh or {}
            # Senken stehen negativ im JSON (Butterfly-Konvention) — der Betrag
            # ist die Energie. Genau diese Vorzeichenfrage hat bei #356 eine
            # Invariante blind gemacht, deshalb hier ausdrücklich `abs`.
            wb = sum(abs(v) for k, v in komp.items()
                     if k in wb_keys and isinstance(v, (int, float)))
            ea = sum(abs(v) for k, v in komp.items()
                     if k in ea_keys and isinstance(v, (int, float)))
            if min(wb, ea) >= self.EMOB_DOPPEL_MIN_KWH_PRO_TAG:
                befunde.append((tz.datum, wb, ea))

        if not befunde:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung=(
                    f"Keine doppelt gezählten Ladetage in den letzten "
                    f"{self.EMOB_DOPPEL_FENSTER_TAGE} Tagen"
                ),
            )]

        summe_zuviel = sum(min(wb, ea) for _d, wb, ea in befunde)
        aeltester, neuester = befunde[0][0], befunde[-1][0]
        range_von = max(
            aeltester, neuester - timedelta(days=REAGGREGATE_RANGE_MAX_DAYS - 1)
        )
        rest_aelter = sum(1 for d, _w, _e in befunde if d < range_von)

        details = (
            f"An {len(befunde)} Tag(en) tragen Wallbox und E-Auto beide eine "
            f"Ladung — insgesamt rund {summe_zuviel:.0f} kWh, die im "
            f"Tagesverlauf doppelt erscheinen. eedc zählt eine Ladung "
            f"inzwischen nur noch einmal (die Wallbox ist die Quelle); diese Tage "
            f"wurden vorher geschrieben und bleiben stehen, bis sie neu "
            f"berechnet werden. "
            f"„Zeitraum neu aggregieren“ holt {range_von.isoformat()} bis "
            f"{neuester.isoformat()} nach (max. "
            f"{REAGGREGATE_RANGE_MAX_DAYS} Tage/Lauf)."
        )
        if rest_aelter > 0:
            details += (
                f" {rest_aelter} ältere(r) Tag(e) liegen außerhalb des "
                f"Fensters — nach dem Lauf erneut prüfen."
            )
        details += (
            " Reichweite: der Lauf heilt Tages- und Stundenwerte, NICHT die "
            "Monatswerte."
        )

        beispiele = ", ".join(
            f"{d.isoformat()} (Wallbox {wb:.1f} + E-Auto {ea:.1f} kWh)"
            for d, wb, ea in sorted(befunde, key=lambda x: min(x[1], x[2]),
                                    reverse=True)[:3]
        )
        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(befunde)} Tag(e) zählen dieselbe Ladung doppelt "
                f"({aeltester.isoformat()} … {neuester.isoformat()})"
            ),
            details=f"{details} Größte Fälle: {beispiele}.",
            link="/einstellungen/energieprofil",
            action_kind="reaggregate_range",
            action_params={
                "anlage_id": anlage.id,
                "von": range_von.isoformat(),
                "bis": neuester.isoformat(),
            },
            action_label="Zeitraum neu aggregieren",
        )]

    async def _check_vergleichspreis_fehlt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Monatszeilen ohne Ø-Benzinpreis — der E-Auto-Vergleich rechnet dann still weiter.

        **Der Melder-Fall (Discussion #394, gruaGit, 23.08.2026):** Er fragte
        nach historischen Benzinpreisen für die Amortisation, bekam die Antwort
        „eedc trägt jeden Monat ohne Preis automatisch nach" — und fand für
        Juni 2026 ein leeres Feld. Die Automatik gab es, sie lief nur
        **wöchentlich** und ohne Startlauf; eine Monatszeile, die zwischen zwei
        Läufen entsteht (Monatsabschluss, Import, Erst-Einrichtung), blieb
        solange leer. Der Takt ist mit demselben Paket täglich geworden, der
        Startlauf ist dazugekommen — **diese Prüfung ist die zweite Hälfte**:
        Sie sagt es, wenn es doch einmal fehlt, statt es den Anwender an einem
        leeren Feld raten zu lassen.

        **Warum das kein kosmetischer Befund ist:** Ohne Monatspreis fällt
        ``resolve_eauto_benzinpreis`` auf den Investitions-Parameter bzw.
        1,65 €/L zurück — ohne Kennzeichnung. Der Fortschritt behauptet dann
        eine Messung und liefert ein Modell.

        **Nur mit E-Auto** (``typ == "e-auto"``, auch dienstlich — der Vergleich
        ist dort ebenso hinterlegt): ohne E-Auto ist das Feld bedeutungslos, und
        eine Warnung, die niemanden betrifft, ist genau die Sorte, die man nie
        wieder los wird.

        **Erst ab dem Anschaffungsmonat des ältesten E-Autos.** Zwei
        Datums-Ebenen, zwei Fragen: hier zählt „ab wann ist dieses Gerät
        dabei?", also ``anschaffungsdatum`` der Investition — nicht
        ``Anlage.installationsdatum``, das filtert keine Auswertung.

        **Und erst ab 2005:** Weiter zurück reicht das Oil Bulletin nicht. Ein
        Monat davor wäre eine wahre Warnung ohne Weg — die kennen wir aus #389.
        """
        from backend.models.monatsdaten import Monatsdaten

        kat = CheckKategorie.VERGLEICHSPREIS_FEHLT.value

        eautos = [i for i in anlage.investitionen if i.typ == "e-auto"]
        if not eautos:
            return []

        anschaffungen = [
            i.anschaffungsdatum for i in eautos if i.anschaffungsdatum is not None
        ]
        if not anschaffungen:
            return []
        aeltestes = min(anschaffungen)
        ab_jahr, ab_monat = max((aeltestes.year, aeltestes.month), (2005, 1))

        rows = (await self.db.execute(
            select(Monatsdaten).where(
                Monatsdaten.anlage_id == anlage.id,
                Monatsdaten.kraftstoffpreis_euro.is_(None),
            ).order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )).scalars().all()

        offen = [
            md for md in rows
            if (md.jahr, md.monat) >= (ab_jahr, ab_monat)
        ]

        if not offen:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Alle Monate mit E-Auto tragen einen Ø-Benzinpreis",
            )]

        def _mm(md) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in offen[:3])
        if len(offen) > 3:
            beispiele += f" … {_mm(offen[-1])}"

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(offen)} Monat(e) ohne Ø-Benzinpreis "
                f"({_mm(offen[0])} … {_mm(offen[-1])})"
            ),
            details=(
                "Der Monatsdurchschnitt aus dem EU Weekly Oil Bulletin ist die "
                "Grundlage des E-Auto-Vergleichs. Wo er fehlt, rechnet eedc mit "
                "dem Modellwert aus den Investitions-Parametern weiter — die "
                "Ersparnis dieser Monate trägt dann den heutigen Preis statt "
                "des damaligen. Nachpflegen holt die Wochenpreise für alle "
                "offenen Monate; bestehende Werte bleiben unberührt. "
                f"Betroffen: {beispiele}."
            ),
            link="/einstellungen/energieprofil",
            action_kind="kraftstoffpreis_backfill",
            action_params={"anlage_id": anlage.id},
            action_label="Vergleichspreise nachpflegen",
        )]
