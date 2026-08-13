"""Hätte ein größerer Speicher etwas gebracht? — die gedeckelte Antwort.

**Warum diese Datei existiert (#358 Phase 2, gemessen 2026-08-12):**
`docs/archive/KONZEPT-SPEICHER-AUSWERTUNG.md` §2 schlug dafür vor::

    ungenutztes_potential_kwh = Σ (einspeisung an Tagen mit SoC_max ≥ 95 %)

Diese Zahl beantwortet ihre eigene Frage **nicht**. An zwölf Junitagen der
Dev-Anlage ergibt sie **471 kWh** „ungenutztes Potential" — die Einspeisung fällt
dort fast vollständig in Stunden mit vollem Speicher. Gleichzeitig fiel der
Speicher in **keiner** dieser Nächte unter **31 %**. Wer daraufhin Kapazität
dazukauft, hat am nächsten Morgen mehr Restladung und gibt sie **nie** ab: der
reale Nutzen ist null, während die Kennzahl 471 kWh ausweist. Im Winter kippt es
in die Gegenrichtung (November: SoC-Maximum 2 %) — dort fehlt die Sonne, nicht
der Speicher.

**Der begrenzende Faktor ist nicht die Sonne, sondern die Nacht.** Zusätzliche
Kapazität nützt nur, wenn beides zusammenkommt:

1. Es war Überschuss da, den der volle Speicher nicht mehr aufnehmen konnte, und
2. der Speicher lief vor dem nächsten Sonnenaufgang **leer**, sodass die
   zusätzliche Ladung auch wieder abgegeben worden wäre.

Deshalb ist die Kennzahl hier ein **Minimum aus beidem**, je Lade-Entlade-Zyklus.
Sie fällt kleiner aus als die naive Summe — das ist ihr Zweck: eine Zahl, an der
eine Kaufentscheidung hängt, darf nicht größer sein als der Nutzen, den sie
verspricht (Gernots Entscheid 2026-08-12; die Alternative „naive Summe mit
Kleingedrucktem" wurde ausdrücklich verworfen).

**Was diese Kennzahl NICHT ist:** eine Simulation. Sie sagt, wie viel ein
beliebig großer Speicher an den beobachteten Tagen **höchstens** zusätzlich
durchgesetzt hätte — nicht, welche Kapazität dafür nötig gewesen wäre und was sie
gekostet hätte. Das ist Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

#: Ab hier gilt der Speicher als voll — Überschuss geht dann zwangsläufig ins Netz.
#: 95 % statt 100 %, weil Hersteller-SoC oben abflacht (Balancing) und ein
#: Speicher praktisch nie exakt 100 % meldet.
SOC_VOLL_PROZENT = 95.0

#: Ab hier gilt er als leer. Symmetrisch gedacht, aber aus einem anderen Grund:
#: unterhalb der Entladetiefe-Reserve gibt das Gerät nichts mehr ab, der
#: gemeldete Rest-SoC ist für das Haus nicht verfügbar.
SOC_LEER_PROZENT = 5.0


@dataclass(frozen=True)
class SpeicherStunde:
    """Eine Stundenzeile, so weit sie hier gebraucht wird.

    Alle Energiemengen in kWh, ``soc_prozent`` in Prozent. ``None`` heißt
    „nicht gemessen" und wird **nicht** als 0 gedeutet — eine Stunde ohne SoC
    kann weder „voll" noch „leer" belegen.
    """

    soc_prozent: Optional[float]
    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0


@dataclass
class ZyklusBefund:
    """Ein Überschuss-Ereignis und das, was die folgende Nacht daraus machte."""

    #: Einspeisung, während der Speicher voll war — die Obergrenze der Aufnahme.
    ueberschuss_kwh: float = 0.0
    #: Netzbezug, nachdem der Speicher leer war — der Bedarf, den er hätte decken können.
    fehlmenge_kwh: float = 0.0
    #: Wurde der Speicher vor dem nächsten Überschuss überhaupt leer?
    lief_leer: bool = False

    @property
    def nutzbar_kwh(self) -> float:
        """Was ein größerer Speicher hier **wirklich** durchgesetzt hätte."""
        return min(self.ueberschuss_kwh, self.fehlmenge_kwh)


@dataclass
class PotentialErgebnis:
    """Auswertung über einen Zeitraum."""

    #: Σ der gedeckelten Werte — die Zahl, die eine Kaufentscheidung tragen darf.
    nutzbares_zusatzpotential_kwh: float = 0.0
    #: Σ der Überschüsse — die naive Zahl aus dem Konzept, als Vergleich mitgeführt.
    ueberschuss_gesamt_kwh: float = 0.0
    #: Stunden, in denen der Speicher voll war (Diagnose, unabhängig vom Nutzen).
    stunden_voll: int = 0
    #: Zyklen, in denen der Speicher vor dem nächsten Überschuss leer lief.
    zyklen_leergelaufen: int = 0
    #: Zyklen mit Überschuss insgesamt.
    zyklen_gesamt: int = 0
    zyklen: list[ZyklusBefund] = field(default_factory=list)

    @property
    def deckelung_greift(self) -> bool:
        """True, wenn die ehrliche Zahl unter der naiven liegt.

        Das ist der Normalfall und der Grund für diese Datei — die Sicht muss
        es sagen können, statt zwei Zahlen kommentarlos nebeneinanderzustellen.
        """
        return self.nutzbares_zusatzpotential_kwh < self.ueberschuss_gesamt_kwh


def _ist_voll(soc: Optional[float]) -> bool:
    return soc is not None and soc >= SOC_VOLL_PROZENT


def _ist_leer(soc: Optional[float]) -> bool:
    return soc is not None and soc <= SOC_LEER_PROZENT


def berechne_zusatzpotential(
    stunden: Sequence[SpeicherStunde] | Iterable[SpeicherStunde],
) -> PotentialErgebnis:
    """Wertet eine **durchgehende** Stundenreihe aus (chronologisch, lückenlos).

    Der Ablauf folgt dem Gerät, nicht dem Kalender: Ein Zyklus beginnt, sobald
    der Speicher voll ist und trotzdem eingespeist wird, und endet mit dem
    nächsten solchen Ereignis. Dazwischen zählt der Netzbezug **ab dem Moment,
    in dem der Speicher leer ist** — vorher hätte auch ein größerer Speicher
    nichts beigetragen, weil der vorhandene noch lieferte.

    Bewusst über die Reihe statt je Kalendertag: die Nacht liegt über
    Mitternacht, und ein tagweiser Schnitt würde jede zweite Fehlmenge
    zerschneiden.
    """
    ergebnis = PotentialErgebnis()
    aktueller: Optional[ZyklusBefund] = None
    leer_erreicht = False
    vorige_war_ueberschuss = False

    for stunde in stunden:
        voll = _ist_voll(stunde.soc_prozent)
        if voll:
            ergebnis.stunden_voll += 1

        einspeisung = stunde.einspeisung_kwh or 0.0
        if voll and einspeisung > 0:
            if not vorige_war_ueberschuss:
                # **Jede** Überschuss-Phase bekommt ihren eigenen Zyklus, nicht
                # erst die nach einem Leerlaufen: sonst sammelt ein Zyklus die
                # Überschüsse mehrerer Tage ein, und die eine Nacht, in der der
                # Speicher tatsächlich leer lief, rechtfertigt sie alle
                # rückwirkend — die Kennzahl fiele zu hoch aus, also genau in
                # die Richtung, gegen die diese Datei gebaut ist. (Der Test
                # `test_zwei_zyklen_werden_getrennt_bewertet` hat den Fehler
                # gefunden, bevor er ausgeliefert war.)
                aktueller = ZyklusBefund()
                ergebnis.zyklen.append(aktueller)
                ergebnis.zyklen_gesamt += 1
                leer_erreicht = False
            aktueller.ueberschuss_kwh += einspeisung
            vorige_war_ueberschuss = True
            continue

        vorige_war_ueberschuss = False

        if aktueller is None:
            # Vor dem ersten Überschuss gibt es nichts zu decken — ein leerer
            # Speicher am Anfang der Reihe belegt keine verpasste Ladung.
            continue

        if _ist_leer(stunde.soc_prozent):
            if not leer_erreicht:
                leer_erreicht = True
                aktueller.lief_leer = True
                ergebnis.zyklen_leergelaufen += 1

        if leer_erreicht:
            aktueller.fehlmenge_kwh += stunde.netzbezug_kwh or 0.0

    ergebnis.ueberschuss_gesamt_kwh = sum(z.ueberschuss_kwh for z in ergebnis.zyklen)
    ergebnis.nutzbares_zusatzpotential_kwh = sum(z.nutzbar_kwh for z in ergebnis.zyklen)
    return ergebnis
