"""
Hub-Leer-Grund — warum der Komponenten-Reiter eines Geräts ohne Zahlen dasteht.

**Der Fund (N-247, gemeldet von CHI3fx117, Forum T89667 #152):** Ein Speicher mit
Anschaffungsdatum im laufenden Monat erscheint in *Cockpit → Tag* und
*Cockpit → Monat*, im Reiter *Komponenten* stehen dagegen nur Nullen — ohne ein
Wort dazu. Sein eigener Satz ist der Beleg, dass die Sicht schweigt statt zu
antworten: *„Habe ich etwas falsch gemacht oder sind diese erst nach dem ersten
Monatsabschluss dort zu finden?"*

**Es ist kein Rechenfehler, sondern die Bauart der Sicht.** Die Hub-Dashboards
lesen ``InvestitionMonatsdaten``, und deren Schreiber sind ausnahmslos
anwendergetrieben (Monatsabschluss · die drei Import-Wege · JSON-Restore ·
Demo-Daten). Vor dem ersten Abschluss existiert die Zeile schlicht nicht. Dass
*Cockpit → Tag/Monat* das Gerät trotzdem zeigen, liegt an den Sensor-Snapshots —
Hub = Lebensdauer, Cockpit = Zeitraum ([[feedback_ort_analytischer_sichten_zeitraum]]).

**Rein (keine DB, keine Uhr)** — ``heute`` kommt vom Aufrufer, damit dieselbe
Lage in jeder Zeitzone dasselbe Ergebnis hat (Lehre aus dem CI-Lauf zu v4.0.14).

**Grund immer, Handlung nur wo sie wirkt** — dieselbe Linie wie ``TagLeerGrund``
und #368/P-8: Ein Gerät, das jünger ist als der erste abschließbare Monat, hat
*nichts* abzuschließen; dort steht deshalb bewusst **kein** Knopf zum
Monatsabschluss, sondern der Verweis auf die Sicht, die das Gerät heute schon
zeigt. Ein Knopf, der garantiert nichts bewirkt, ist schlimmer als keiner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from backend.core.monats_luecken import monat_index


class LeerGrundArt(str, Enum):
    """Warum das Gerät keine Monatswerte hat — genau eine Art je Lage."""

    NICHT_AKTIV = "nicht_aktiv"
    STILLGELEGT = "stillgelegt"
    ZU_JUNG = "zu_jung"
    ERFASSUNG_FEHLT = "erfassung_fehlt"
    UNBEKANNT = "unbekannt"


@dataclass(frozen=True)
class LeerGrund:
    """Antwort der Sicht: Grund immer, Weg nur wo er trägt."""

    art: LeerGrundArt
    meldung: str
    details: str | None = None
    #: Ziel-Route für den „dahin"-Knopf; ``None`` = kein Knopf.
    link: str | None = None
    link_label: str | None = None


def _formatiere(d: date) -> str:
    """de-DE-Datum ohne Locale-Abhängigkeit (Backend-Meldungen sehen die
    `check:de-de`-Prüfer nicht — N-203)."""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def bestimme_leer_grund(
    *,
    aktiv: bool,
    anschaffungsdatum: date | None,
    stilllegungsdatum: date | None,
    heute: date,
) -> LeerGrund:
    """
    Der Grund für einen Hub-Reiter **ohne** Monatswerte.

    Aufrufer-Vertrag: Es steht bereits fest, dass das Gerät keine
    ``InvestitionMonatsdaten`` in seinem aktiven Zeitraum hat. Diese Funktion
    beantwortet nur noch das *Warum*.

    Die Reihenfolge der Zweige ist nicht beliebig — ``aktiv``,
    ``stilllegungsdatum`` und ``anschaffungsdatum`` sind **drei getrennte
    Achsen** ([[feedback_aktiv_inaktiv_semantik]]); ein stillgelegtes Gerät ist
    nicht dasselbe wie ein abgeschaltetes, und beide sind nicht dasselbe wie ein
    zu junges.
    """
    laufender = monat_index(heute.year, heute.month)

    if not aktiv:
        return LeerGrund(
            art=LeerGrundArt.NICHT_AKTIV,
            meldung="Dieses Gerät ist auf inaktiv gesetzt und hat keine erfassten Monatswerte.",
            details=(
                "Der Reiter Komponenten ist die Lebenslauf-Sicht eines Geräts — "
                "er rechnet mit abgeschlossenen Monaten. Für ein inaktives Gerät "
                "ohne erfasste Monate gibt es nichts zu zeigen."
            ),
        )

    if stilllegungsdatum is not None and monat_index(
        stilllegungsdatum.year, stilllegungsdatum.month
    ) < laufender:
        return LeerGrund(
            art=LeerGrundArt.STILLGELEGT,
            meldung="Dieses Gerät ist stillgelegt und hat keine erfassten Monatswerte.",
            details=(
                f"Stillgelegt am {_formatiere(stilllegungsdatum)}. Nachtragen lässt "
                "sich das über den Monatsabschluss der betroffenen Monate."
            ),
            link="/einstellungen/daten",
            link_label="Zum Monatsabschluss",
        )

    if anschaffungsdatum is None:
        return LeerGrund(
            art=LeerGrundArt.UNBEKANNT,
            meldung="Für dieses Gerät sind noch keine Monatswerte erfasst.",
            details=(
                "Ohne Anschaffungsdatum lässt sich nicht sagen, ab wann Werte zu "
                "erwarten wären. Das Datum steht in den Einstellungen der Komponente."
            ),
            link="/einstellungen/daten",
            link_label="Zum Monatsabschluss",
        )

    angeschafft = monat_index(anschaffungsdatum.year, anschaffungsdatum.month)

    if angeschafft >= laufender:
        # Der Kern des Fundes: nichts ist falsch, es ist nur noch nichts fertig.
        # Bewusst OHNE Knopf zum Monatsabschluss — es gibt keinen Monat, den man
        # abschließen könnte (P-6: kein Hinweis, den niemand auflösen kann).
        return LeerGrund(
            art=LeerGrundArt.ZU_JUNG,
            meldung="Für dieses Gerät gibt es noch keinen abgeschlossenen Monat.",
            details=(
                f"Angeschafft am {_formatiere(anschaffungsdatum)}. Der Reiter "
                "Komponenten ist die Lebenslauf-Sicht eines Geräts: Er rechnet "
                "Dinge wie Zyklen, Wirtschaftlichkeit und Amortisation über "
                "abgeschlossene Monate. Der erste Monatsabschluss steht noch aus — "
                "bis dahin siehst du das Gerät in Cockpit → Tag und Cockpit → Monat, "
                "die aus den laufenden Sensorwerten rechnen."
            ),
            link="/cockpit/monat",
            link_label="Zu Cockpit → Monat",
        )

    # Anschaffung liegt vor dem laufenden Monat ⇒ es GIBT abschließbare Monate.
    offene = laufender - angeschafft
    monate = "ein abgeschlossener Monat" if offene == 1 else f"{offene} abgeschlossene Monate"
    verb = "liegt" if offene == 1 else "liegen"
    return LeerGrund(
        art=LeerGrundArt.ERFASSUNG_FEHLT,
        meldung="Für dieses Gerät sind noch keine Monatswerte erfasst.",
        details=(
            f"Angeschafft am {_formatiere(anschaffungsdatum)} — seitdem {verb} "
            f"{monate} zurück, für dieses Gerät ist keiner davon erfasst. "
            "Gerätewerte entstehen im Monatsabschluss oder über einen der "
            "Import-Wege."
        ),
        link="/einstellungen/daten",
        link_label="Zum Monatsabschluss",
    )
