"""Finanz-Aggregat: Einspeise-Erlös + EV-/BKW-Ersparnis über die Read-Sites.

Single Source of Truth für die **finanzielle** Monats-Aggregation der
Netto-Ertrags-Kachel (Cockpit, Jahres-/Anlagenbericht-PDF, HA-Export). Die
Formel war an jeder Read-Site dupliziert — und driftete: einige Sites
rechneten `Σ(Eigenverbrauch) × Ø-Netzbezugspreis`, andere
`Σ(eigenverbrauch_m × flexpreis_m)`. Bei Flex-Tarifen (Tibber/aWATTar/EPEX)
laufen beide auseinander, sobald Preis UND EV/Netzbezug-Split monatlich
variieren (rilmor-mhrs #326: Sommer-EV fällt aus der netzbezug-Gewichtung).

Dieser Helper rechnet **ausschließlich per-Monat** und summiert:

    ev_ersparnis   = Σ( eigenverbrauch_m × netzbezug_preis_cent_m / 100 )
    bkw_ersparnis  = Σ( bkw_eigenverbrauch_m × netzbezug_preis_cent_m / 100 )
    einspeise_erloes = Σ einspeise_erloes_euro(...)   (§51-bereinigt)

- Eigenverbrauch pro Monat über den kanonischen `berechne_verbrauchs_kennzahlen`
  (inkl. Speicher- + V2H-Entladung).
- `bkw_eigenverbrauch_kwh` ist **kein Zusatzposten**, sondern der Ersatzträger
  für BKW-Monate ohne erfasste Erzeugung — sonst zählte derselbe Fluss zweimal
  (ADR-002/**P9**, `bkw_finanz_beitrag` entscheidet das je Zeile, s. u.).
- Einspeise-Erlös pro Monat über `einspeise_erloes_euro` (§51 EEG-Abzug).
- `netzbezug_preis_cent` ist der bereits **aufgelöste** Monats-Flexpreis
  (`resolve_netzbezug_preis_cent`) — die Auflösung bleibt beim Caller, weil sie
  ein `Monatsdaten`-Objekt braucht (ADR-001: Layer DB-frei).

WICHTIG zu „Sonstige": Der Helper kennt KEINE Investition und filtert NICHT.
Die Sichtbarkeitsregel (``aktiv`` + Laufzeit-Fenster Anschaffung→Stilllegung)
gilt für Finanzpositionen genauso wie für alles andere — der Caller übergibt das
bereits gefilterte ``sonstige_netto_euro`` als Skalar
(siehe `aggregiere_sonstige_je_monat`, [[feedback_keine_erfundenen_ausnahmeregeln]]).

`netto_ertrag_euro` ist die **naive** Summe aller vier Komponenten. Sites mit
Zusatz-Logik (z. B. Cockpit zieht den USt-Eigenverbrauch ab) nutzen die
Einzel-Komponenten und bauen ihren Netto-Ertrag selbst zusammen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from backend.core.berechnungen.einspeise_erloes import einspeise_erloes_euro
from backend.core.berechnungen.verbrauch import berechne_verbrauchs_kennzahlen


@dataclass
class FinanzMonatsZeile:
    """Neutrale Monats-Zeile für die Finanz-Aggregation (keine ORM-Objekte).

    Energiemengen in kWh, Preise in ct/kWh. ``netzbezug_preis_cent`` ist der
    bereits aufgelöste Monats-Flexpreis (Caller ruft
    ``resolve_netzbezug_preis_cent``). Alle Felder None-tolerant über Defaults.

    **Kontrakt der beiden BKW-Eingänge (ADR-002/P9).** ``pv_erzeugung_kwh`` ist
    die Erzeugung **hinter dem Hauszähler** — PV-Module *und* Balkonkraftwerke;
    aus ihr leitet der Helper den Eigenverbrauch ab.
    ``bkw_eigenverbrauch_kwh`` trägt deshalb **ausschließlich** den gemessenen
    Eigenverbrauch solcher BKW-Monate, deren Erzeugung NICHT in
    ``pv_erzeugung_kwh`` steckt. Die Aufteilung entscheidet je (BKW, Monat)
    ``bkw_finanz_beitrag`` — sie hier selbst zu treffen ist der Fehler, den
    diese Aufteilung abstellt (jede der vier Read-Sites hatte ihn anders
    getroffen, #326-Inventur).
    """

    einspeisung_kwh: float = 0.0
    netzbezug_kwh: float = 0.0
    pv_erzeugung_kwh: float = 0.0
    speicher_ladung_kwh: float = 0.0
    speicher_entladung_kwh: float = 0.0
    v2h_entladung_kwh: float = 0.0
    bkw_eigenverbrauch_kwh: float = 0.0
    netzbezug_preis_cent: float = 0.0
    einspeiseverguetung_cent: float = 0.0
    neg_preis_kwh: Optional[float] = None


@dataclass
class FinanzAggregat:
    """Aggregiertes Finanz-Ergebnis über alle Monatszeilen."""

    einspeise_erloes_euro: float
    ev_ersparnis_euro: float
    bkw_ersparnis_euro: float
    sonstige_netto_euro: float
    #: Konzept §9 Weg 2: Σ der gepflegten Erlöse von Erzeugern mit **eigenem**
    #: Einspeisetarif. Sie stehen NEBEN ``einspeise_erloes_euro``, nicht darin:
    #: dieser Posten bewertet den Anlagenzähler mit dem EINEN Satz der Anlage,
    #: jener trägt einen Betrag, den Home Assistant ausgerechnet hat.
    erzeuger_erloes_euro: float
    netto_ertrag_euro: float
    eigenverbrauch_kwh: float
    nicht_vergueteter_erloes_euro: float
    nicht_verguetete_kwh: float
    hat_neg_preis_daten: bool


def berechne_finanz_aggregat(
    zeilen: Iterable[FinanzMonatsZeile],
    *,
    sonstige_netto_euro: float = 0.0,
    erzeuger_erloes_euro: float = 0.0,
) -> FinanzAggregat:
    """Aggregiert Einspeise-Erlös + EV-/BKW-Ersparnis per-Monat über alle Zeilen.

    Args:
        zeilen: pro Monat eine ``FinanzMonatsZeile`` (bereits gefiltert auf
            sichtbare/aktive Monate durch den Caller).
        sonstige_netto_euro: bereits aggregiertes Sonstige-Netto (Erträge −
            Ausgaben) über die sichtbaren Monate; fließt 1:1 in ``netto_ertrag``.
        erzeuger_erloes_euro: Σ der gepflegten Einspeise-Erlöse einzelner
            Erzeuger (Konzept §9 Weg 2). ⚠ **Kein Abzug von** ``einspeise``:
            zwei Vergütungssätze bedeuten zwei Messungen, im Anlagen-Zähler
            steht ohnehin nur die zum Anlagentarif vergütete Menge. Wer beides
            in denselben Zähler schreibt, hat ein Erfassungs-, kein
            Rechenproblem — und das kann eedc nicht sehen.

    Returns:
        FinanzAggregat mit den Einzel-Komponenten + naivem ``netto_ertrag_euro``
        (= Σ aller fünf Komponenten) + §51-Diagnose + ``hat_neg_preis_daten``
        (True, sobald **eine** Zeile ``neg_preis_kwh is not None`` hat).
    """
    einspeise = 0.0
    ev = 0.0
    bkw = 0.0
    ev_kwh = 0.0
    nicht_verg_erloes = 0.0
    nicht_verg_kwh = 0.0
    hat_neg = False

    for z in zeilen:
        kz = berechne_verbrauchs_kennzahlen(
            pv_erzeugung_kwh=z.pv_erzeugung_kwh,
            einspeisung_kwh=z.einspeisung_kwh,
            netzbezug_kwh=z.netzbezug_kwh,
            speicher_ladung_kwh=z.speicher_ladung_kwh,
            speicher_entladung_kwh=z.speicher_entladung_kwh,
            v2h_entladung_kwh=z.v2h_entladung_kwh,
        )
        ev_kwh += kz.eigenverbrauch_kwh
        ev += kz.eigenverbrauch_kwh * z.netzbezug_preis_cent / 100
        # Nur der Rest-Eigenverbrauch aus BKW-Monaten OHNE erfasste Erzeugung
        # (P9-Kontrakt der Zeile) — mit Erzeugung steckt er bereits in `ev`.
        bkw += (z.bkw_eigenverbrauch_kwh or 0.0) * z.netzbezug_preis_cent / 100

        erloes = einspeise_erloes_euro(
            einspeisung_kwh=z.einspeisung_kwh or 0.0,
            neg_preis_kwh=z.neg_preis_kwh,
            verguetung_ct_kwh=z.einspeiseverguetung_cent,
        )
        einspeise += erloes.erloes_euro
        nicht_verg_erloes += erloes.nicht_vergueteter_erloes_euro
        nicht_verg_kwh += erloes.nicht_verguetete_kwh
        if z.neg_preis_kwh is not None:
            hat_neg = True

    netto = einspeise + ev + bkw + sonstige_netto_euro + erzeuger_erloes_euro

    return FinanzAggregat(
        einspeise_erloes_euro=einspeise,
        ev_ersparnis_euro=ev,
        bkw_ersparnis_euro=bkw,
        sonstige_netto_euro=sonstige_netto_euro,
        erzeuger_erloes_euro=erzeuger_erloes_euro,
        netto_ertrag_euro=netto,
        eigenverbrauch_kwh=ev_kwh,
        nicht_vergueteter_erloes_euro=nicht_verg_erloes,
        nicht_verguetete_kwh=nicht_verg_kwh,
        hat_neg_preis_daten=hat_neg,
    )
