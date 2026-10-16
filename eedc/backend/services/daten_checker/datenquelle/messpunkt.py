"""Daten-Checker — Messpunkt: Anlagenzähler gegen String-Zähler (N-588 F5, Vorlage Fassung 2, Entscheide 10.10.2026).

**Warum es das gibt.** Seit N-588 bewerten Ersparnis, USt und CO₂ den Eigenverbrauch ohne die Wandlungsverluste
(``Σ String-Zähler − Anlagenzähler``), wenn der **Messpunkt-Vertrag** hält (``core/berechnungen/pv_verteilung.
wandlungsverluste_grund``). Hält er nicht, zieht eedc nichts ab — still wäre das eine Zahl ohne Begründung, und eine
Fehlzuordnung des Anlagenzählers bliebe unentdeckt (Tor 3 von N-588 war ungedeckt: keine Kategorie zu Eigenverbrauch
oder Messpunkt). Diese Kategorie nennt den Grund und den Handgriff; sie rechnet nichts selbst, sie liest die
Komposition der Kanal-Monate (``kanal/bilanz_leser.monate_bilanz``) — dieselbe, aus der die Fakten ihre Verluste haben.

**Die Regeln** (alle nur in abgeschlossenen Kanal-Monaten; (a)–(c') nur, wenn F1 (i) und (ii) gelten — Anlagenzähler
mit voller Deckung, kein Rest des Anlagenzählers an ein Gerät ohne eigenen Zähler verteilt):

* (a) Verluste > ``WANDLUNGSVERLUSTE_SCHWELLE_PROZENT`` der Σ Strings ⇒ WARNING.
* (a') Verluste ≥ ``WANDLUNGSVERLUSTE_BKW_ANTEIL_PROZENT`` der Σ Balkonkraftwerk-Δ bei mindestens einem Balkonkraftwerk
  mit eigenem Δ ⇒ WARNING (der Anlagenzähler misst das Balkonkraftwerk offenbar nicht).
* (b) Σ Strings < Anlagenzähler um mehr als ``MEHR_ALS_STRINGS_PROZENT`` ⇒ INFO (bis N-588 stumm auf 0 geklemmt) —
  **nicht** bei aktivem DC-Speicher (gepflegt oder angenommen, Entscheid Master 10.10.2026): dort läuft die
  Netzladung der Batterie durch den Wechselrichter, und der Anlagenzähler zählt sie beim Entladen mit — mehr als die
  Strings ist dann kein Messpunkt-Fehler (gemessen an der Demo-Anlage, 10–12/2014 +5,3 %).
* (c') DC-gekoppelter Speicher und Anlagenzähler, mit Verlusten ⇒ INFO; ist die Kopplung nur abgeleitet (Speicher am
  Wechselrichter, nicht gepflegt), nennt der Text den Handgriff „Kopplung eintragen".
* (d) Kein Anlagenzähler, und in jedem der letzten drei abgeschlossenen Kanal-Monate ``Σ Strings − Einspeisung ≤ 10 %
  Σ Strings`` ⇒ INFO „Sieht nach Volleinspeisung aus" mit dem Handgriff AC-Ertragszähler als *PV gesamt (kWh)*
  (Entscheid §7.2, zweite Fassung: kein Sensor in zwei Feldern — ``datenquellen_validierung`` bleibt unverändert).
* (e) GitHub #428 (16.10.2026), nur Stammdaten und Zuordnung: Anlagenzähler „PV gesamt“, ein aktives PV-Modul ohne eigenen
  Zähler und ein Balkonkraftwerk mit eigenem Zähler ⇒ INFO (``_messpunkt_pv_gesamt_neben_bkw``) — genau die Lage, in der
  (a)–(c') wegen des verteilten Rests schweigen.

⛔ Kein Reparatur-Knopf, keine Schätzung, kein Verlustfaktor (F3). Die Schwellen sind konservativ gesetzt und nicht an
einer realen Anlage gemessen — die Konstanten stehen im Layer neben dem Vertrag, nicht hier.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.berechnungen.pv_verteilung import (
    VERLUSTE_GRUND_DC_SPEICHER,
    VERLUSTE_GRUND_DC_SPEICHER_ANGENOMMEN,
    WANDLUNGSVERLUSTE_BKW_ANTEIL_PROZENT,
    WANDLUNGSVERLUSTE_SCHWELLE_PROZENT,
    wandlungsverluste_prozent,
)
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

#: (b) Ab dieser Differenz (Prozent der Σ Strings) zählt der Anlagenzähler „mehr als die Strings" — darunter ist es
#: Zählertoleranz und Ablesezeitpunkt.
MEHR_ALS_STRINGS_PROZENT = 2.0
#: (d) Höchstens dieser Anteil der Σ Strings darf in drei Monaten NICHT eingespeist sein, damit die Anlage nach
#: Volleinspeisung aussieht (die Wandlungsverluste eines Volleinspeisers liegen typisch bei wenigen Prozent).
VOLLEINSPEISUNG_REST_PROZENT = 10.0
#: (d) So viele abgeschlossene Kanal-Monate in Folge müssen das Muster zeigen.
VOLLEINSPEISUNG_MONATE = 3
#: Wie viele Monate eine Meldung beim Namen nennt.
BEISPIELE = 6


def _monat(m: tuple[int, int]) -> str:
    return f"{m[1]:02d}/{m[0]}"


def _liste(eintraege: list[str]) -> str:
    text = ", ".join(eintraege[:BEISPIELE])
    if len(eintraege) > BEISPIELE:
        text += f" (+{len(eintraege) - BEISPIELE} weitere)"
    return text


class MesspunktChecks:
    """Prüfung: Messpunkt-Vertrag der Wandlungsverluste (Anlagenzähler gegen String-Zähler)."""

    async def _check_messpunkt(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.services.kanal import bilanz_leser

        heute = datetime.fromtimestamp(bilanz_leser.uhr()).date()
        # #428: Stammdaten-Hinweis, unabhängig von Monatszahlen (auch ohne einen einzigen Kanal-Monat).
        stamm = await self._messpunkt_pv_gesamt_neben_bkw(anlage, heute)
        # Abgeschlossen = vor dem laufenden Monat.
        bis = (heute.year - 1, 12) if heute.month == 1 else (heute.year, heute.month - 1)
        kanal = {m: k for m, k in (await bilanz_leser.kanal_kompositionen(self.db, anlage.id, bis=bis)).items()
                 if k.pv is not None}
        if not kanal:
            return stamm

        ueber, bkw_aussen, mehr, dc_gepflegt, dc_angenommen = [], [], [], [], []
        for m, k in kanal.items():
            pv = k.pv
            if pv.anlagenzaehler_kwh is None or pv.verteilter_rest_kwh > 0:
                continue          # F1 (i)/(ii) gelten nicht — keine Aussage über den Messpunkt
            strings, verluste, az = pv.geraete_kwh, pv.wandlungsverluste_kwh or 0.0, pv.anlagenzaehler_kwh
            quote = wandlungsverluste_prozent(verluste, strings)
            if quote is not None and verluste > 0 and quote > WANDLUNGSVERLUSTE_SCHWELLE_PROZENT:
                ueber.append(f"{_monat(m)} ({fmt_zahl(quote, 1)} %)")
            if pv.bkw_kwh > 0 and verluste > 0 and verluste >= pv.bkw_kwh * WANDLUNGSVERLUSTE_BKW_ANTEIL_PROZENT / 100:
                bkw_aussen.append(f"{_monat(m)} ({fmt_zahl(verluste, 1)} kWh Verluste, "
                                  f"{fmt_zahl(pv.bkw_kwh, 1)} kWh Balkonkraftwerk)")
            if pv.dc_grund is None and strings > 0 and az - strings > strings * MEHR_ALS_STRINGS_PROZENT / 100:
                mehr.append(f"{_monat(m)} (+{fmt_zahl((az - strings) / strings * 100, 1)} %)")
            if verluste > 0 and pv.verluste_grund == VERLUSTE_GRUND_DC_SPEICHER:
                dc_gepflegt.append(_monat(m))
            if verluste > 0 and pv.verluste_grund == VERLUSTE_GRUND_DC_SPEICHER_ANGENOMMEN:
                dc_angenommen.append(_monat(m))

        out: list[CheckErgebnis] = list(stamm)
        if ueber:
            out.append(CheckErgebnis(
                kategorie=CheckKategorie.MESSPUNKT.value,
                schwere=CheckSeverity.WARNING,
                meldung=(f"Anlagenzähler und String-Zähler messen verschiedene Dinge — Ersparnis rechnet ohne Abzug "
                         f"({len(ueber)} Monat(e))"),
                details=(
                    f"In diesen Monaten liegt die Summe der String-Zähler um mehr als "
                    f"{fmt_zahl(WANDLUNGSVERLUSTE_SCHWELLE_PROZENT, 0)} % über dem Anlagenzähler (Feld „PV gesamt“): "
                    f"{_liste(ueber)}. Wechselrichterverluste dieser Höhe sind nicht plausibel — meist misst der "
                    "Anlagenzähler nicht dieselbe Anlage wie die Strings (ein String fehlt in ihm, oder er misst nach "
                    "dem Speicher). eedc zeigt die Differenz als Wandlungsverluste, zieht sie aber nicht von Ersparnis, "
                    "USt und CO₂ ab. Prüfe unter Datenquellen, welcher Sensor im Feld „PV gesamt (kWh)“ steht."
                ),
                link="/einstellungen/datenquellen",
            ))
        if bkw_aussen:
            out.append(CheckErgebnis(
                kategorie=CheckKategorie.MESSPUNKT.value,
                schwere=CheckSeverity.WARNING,
                meldung=f"Der Anlagenzähler misst das Balkonkraftwerk offenbar nicht ({len(bkw_aussen)} Monat(e))",
                details=(
                    "In diesen Monaten ist die Differenz zwischen den Zählern der PV-Quellen und dem Anlagenzähler fast "
                    f"so groß wie die Erzeugung des Balkonkraftwerks (mindestens "
                    f"{fmt_zahl(WANDLUNGSVERLUSTE_BKW_ANTEIL_PROZENT, 0)} %): {_liste(bkw_aussen)}. Das Balkonkraftwerk "
                    "speist dann offenbar an einer Stelle ein, die der Anlagenzähler nicht sieht. eedc zieht deshalb "
                    "nichts als Wandlungsverluste ab — sonst wäre die Ersparnis des Balkonkraftwerks weg. Misst dein "
                    "Anlagenzähler das Balkonkraftwerk doch mit, prüfe den Zähler des Balkonkraftwerks."
                ),
                link="/einstellungen/datenquellen",
            ))
        if mehr:
            out.append(CheckErgebnis(
                kategorie=CheckKategorie.MESSPUNKT.value,
                schwere=CheckSeverity.INFO,
                meldung=f"Anlagenzähler zählt mehr als die Strings — Messpunkt prüfen ({len(mehr)} Monat(e))",
                details=(
                    "In diesen Monaten liegt der Anlagenzähler (Feld „PV gesamt“) über der Summe der String-Zähler: "
                    f"{_liste(mehr)}. Nach dem Wechselrichter kann nicht mehr ankommen, als die Strings davor liefern — "
                    "meist zählt der Anlagenzähler eine weitere Quelle mit (ein Balkonkraftwerk, ein zweiter "
                    "Wechselrichter) oder ein String-Zähler misst zu wenig. eedc rechnet mit der Summe der Strings; "
                    "Wandlungsverluste gibt es in diesen Monaten keine."
                ),
                link="/einstellungen/datenquellen",
            ))
        if dc_gepflegt or dc_angenommen:
            text = (
                "Bei einem DC-gekoppelten Speicher misst der Anlagenzähler (nach dem Wechselrichter) die Ladung und "
                "Entladung der Batterie mit — die Differenz zu den String-Zählern ist dann nicht nur Wandlungsverlust. "
                "eedc zeigt sie an, bewertet sie aber nicht: Ersparnis, USt und CO₂ rechnen ohne Abzug. "
                f"Betroffene Monate: {_liste(dc_gepflegt + dc_angenommen)}."
            )
            if dc_angenommen and not dc_gepflegt:
                text += (
                    " Die Kopplung ist an deinem Speicher nicht eingetragen — eedc nimmt DC an, weil er einem "
                    "Wechselrichter zugeordnet ist. Ist dein Speicher AC-gekoppelt, trage die Kopplung am Speicher "
                    "ein, dann rechnet eedc die Ersparnis ohne Wandlungsverluste."
                )
            out.append(CheckErgebnis(
                kategorie=CheckKategorie.MESSPUNKT.value,
                schwere=CheckSeverity.INFO,
                meldung=("Bei DC-gekoppeltem Speicher misst der AC-Zähler die Batterie mit — Verluste werden "
                         "angezeigt, nicht bewertet"),
                details=text,
                link="/einstellungen/investitionen",
            ))
        out.extend(await self._messpunkt_volleinspeisung(anlage, kanal))
        return out

    async def _messpunkt_pv_gesamt_neben_bkw(self, anlage: Anlage, heute) -> list[CheckErgebnis]:
        """(e) GitHub #428 (chuck2941, 16.10.2026): Anlagenzähler „PV gesamt“, mindestens ein aktives PV-Modul OHNE eigenen
        Zähler und mindestens ein Balkonkraftwerk MIT eigenem Zähler ⇒ INFO. eedc liest den Anlagenzähler als Zähler der
        ganzen Erzeugung einschließlich Balkonkraftwerk und verteilt seinen Rest auf die Module ohne Zähler — sitzt er am
        Wechselrichter, fehlt das Balkonkraftwerk in „PV gesamt“ (Melder: Tag 11,7 statt 14,5 kWh). Die Regeln (a)–(c')
        schweigen dort absichtlich (``verteilter_rest_kwh > 0``), und aus den Zahlen ist der Messpunkt nicht zu erkennen;
        die Stammdaten und die Zuordnung genügen für den Hinweis. Ein Modul, das einem Balkonkraftwerk gehört (N-266),
        zählt nicht als Modul ohne Zähler — der Zähler des Balkonkraftwerks misst es mit."""
        from backend.core.berechnungen.erzeuger_traeger import abgetretene_bkw_ids
        from backend.services.snapshot.keys import extract_quellen_energy, feld_hat_zaehler
        from backend.services.snapshot.reader import mqtt_zaehler_keys

        aktiv = [i for i in (getattr(anlage, "investitionen", None) or []) if i.aktiv and i.ist_aktiv_an(heute)]
        if not {"balkonkraftwerk", "pv-module"} <= {i.typ for i in aktiv}:
            return []             # ohne beide Typen keine Lage — und keine Abfrage
        mapping = anlage.sensor_mapping if isinstance(anlage.sensor_mapping, dict) else {}
        quellen = extract_quellen_energy(anlage)
        mqtt_keys = await mqtt_zaehler_keys(self.db, anlage.id)
        if not feld_hat_zaehler((mapping.get("basis") or {}).get("pv_gesamt"), "basis:pv_gesamt", quellen, mqtt_keys):
            return []
        inv_map = mapping.get("investitionen") or {}

        def hat_zaehler(inv) -> bool:
            felder = (inv_map.get(str(inv.id)) or {}).get("felder") or {}
            return feld_hat_zaehler(felder.get("pv_erzeugung_kwh"), f"inv:{inv.id}:pv_erzeugung_kwh", quellen, mqtt_keys)

        # P11 (N-266): ein Modul-Kind eines Balkonkraftwerks ist kein Modul ohne Zähler — der Zähler des BKW misst es.
        abgetreten = abgetretene_bkw_ids(aktiv)
        bkw_mit = [i for i in aktiv if i.typ == "balkonkraftwerk" and hat_zaehler(i)]
        module_ohne = [i for i in aktiv if i.typ == "pv-module" and i.parent_investition_id not in abgetreten
                       and not hat_zaehler(i)]
        if not bkw_mit or not module_ohne:
            return []
        return [CheckErgebnis(
            kategorie=CheckKategorie.MESSPUNKT.value,
            schwere=CheckSeverity.INFO,
            meldung="„PV gesamt“ gilt als Zähler der ganzen Erzeugung einschließlich Balkonkraftwerk",
            details=(
                "Der Anlagenzähler „PV gesamt“ gilt als Zähler der ganzen Erzeugung einschließlich Balkonkraftwerk "
                f"({', '.join(sorted(i.bezeichnung or f'#{i.id}' for i in bkw_mit))}); den Rest nach dem Zähler des "
                "Balkonkraftwerks verteilt eedc auf die PV-Module ohne eigenen Zähler "
                f"({', '.join(sorted(i.bezeichnung or f'#{i.id}' for i in module_ohne))}). Misst er nur den "
                "Wechselrichter, ordne ihn dem PV-Modul als Erzeugungszähler zu (Einstellungen → Datenquellen); sonst "
                "fehlt die Erzeugung der Balkonkraftwerke in PV gesamt."
            ),
            link="/einstellungen/datenquellen",
        )]

    async def _messpunkt_volleinspeisung(self, anlage: Anlage, kanal: dict) -> list[CheckErgebnis]:
        """(d): ohne Anlagenzähler drei abgeschlossene Kanal-Monate in Folge fast ohne Eigenverbrauch."""
        from backend.services.kanal.bilanz_leser import hat_anlagenzaehler_kanal

        if await hat_anlagenzaehler_kanal(self.db, anlage.id):
            return []
        letzte = list(kanal.items())[-VOLLEINSPEISUNG_MONATE:]
        if len(letzte) < VOLLEINSPEISUNG_MONATE:
            return []
        for _m, k in letzte:
            pv = k.pv
            einsp = k.bilanz.einspeisung_kwh if k.bilanz.einspeisung_erfasst else None
            if pv.anlagenzaehler_kwh is not None or pv.fehlt or einsp is None or pv.geraete_kwh <= 0:
                return []
            if pv.geraete_kwh - einsp > pv.geraete_kwh * VOLLEINSPEISUNG_REST_PROZENT / 100:
                return []
        monate = ", ".join(_monat(m) for m, _k in letzte)
        return [CheckErgebnis(
            kategorie=CheckKategorie.MESSPUNKT.value,
            schwere=CheckSeverity.INFO,
            meldung="Sieht nach Volleinspeisung aus — der AC-Ertragszähler deines Wechselrichters fehlt",
            details=(
                f"In den letzten {VOLLEINSPEISUNG_MONATE} abgeschlossenen Monaten ({monate}) ging fast die ganze "
                "Erzeugung der String-Zähler ins Netz. Was dazwischen fehlt, sind bei einer Volleinspeisung vor allem "
                "die Verluste im Wechselrichter — die kennt eedc nur mit einem Zähler nach dem Wechselrichter. Ordne "
                "den AC-Ertragszähler deines Wechselrichters (Gesamtertrag nach dem Wechselrichter) als „PV gesamt "
                "(kWh)“ zu, dann kennt eedc die Wandlungsverluste und rechnet keine Ersparnis aus ihnen."
            ),
            link="/einstellungen/datenquellen",
        )]


__all__ = [
    "BEISPIELE", "MEHR_ALS_STRINGS_PROZENT", "MesspunktChecks", "VOLLEINSPEISUNG_MONATE",
    "VOLLEINSPEISUNG_REST_PROZENT",
]
