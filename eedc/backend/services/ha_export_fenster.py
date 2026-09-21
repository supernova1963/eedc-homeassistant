"""Der gemeinsame Eingang der Fenster-Sensoren (S3, KONZEPT-EEDC-AT-HA §5).

**Was hier entsteht.** Eine Stundenreihe „was kostet mich eine zusätzliche kWh
in dieser Stunde", dazu Überschuss, Verbrauch, Günstig-Markierung und
Temperatur — alles über **denselben** Slot-Index. Aus ihr rechnen P4, P5, P7,
P8 und P9 ihre Fenster; die Formel selbst steht im Layer
(``core/berechnungen/fenster.py``), hier steht nur das Einsammeln.

**Einmal je Publish-Lauf, nicht einmal je Gerät.** Eine Anlage mit zwei
Wärmepumpen, einer Wallbox und drei sonstigen Verbrauchern riefe sonst
sechsmal dieselbe Rechnung. Der Kontext entsteht in
``calculate_anlage_sensors`` (das die Preis- und Prognosedaten ohnehin holt)
und wird an ``calculate_investition_sensors`` durchgereicht.

## Die Slot-Achse

Slot ``0…23`` ist heute Stunde 0…23, Slot ``24…47`` ist morgen. Die zweite
Hälfte existiert nur, wenn die Day-Ahead-Auktion für morgen veröffentlicht hat
(ab ca. 13:00, ``DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE``).

⚠ **Für morgen gibt es keine Überschuss-Prognose, und das ist bewusst so.**
Modell A liefert das Verbrauchsprofil nur für **heute** (Werktag/Wochenende der
laufenden Uhr, Temperaturkorrektur aus dem heutigen Forecast). Ohne
Verbrauchsreihe gibt es keinen Überschuss, und ein geschätzter wäre eine Zahl,
die aussieht wie eine Rechnung. Die Kosten für morgen sind deshalb der **volle**
Slot-Preis — das ist die vorsichtige Richtung: ein Fenster morgen wird nie
fälschlich billiger gerechnet als eines heute.

## Welcher Preis

⭐ **Der Slot-Preis ist der, den ``eedc_preis_aktuell_cent`` trägt** — die
Börsenpreis-Stundenreihe aus ``services/preis_tag.py::bewerte_preistag``,
weitergereicht über ``rang_profil``/``rang_profil_morgen``. **Gemessen am
21.09.2026:** dieser Weg führt über ``fetch_marktpreise`` und berührt die
Aufschläge der Tarif-Kaskade (``core/berechnungen/zeittarif.py``,
``netzbezug_kosten.py``) an keiner Stelle.

⛔ **Deshalb wird hier auch nichts aufgeschlagen.** Ein zweiter Preis im selben
Export hieße: derselbe Anwender sieht in `eedc_preis_aktuell_cent` 18 ct und im
Fenster-Attribut daneben 32 ct für dieselbe Stunde, ohne dass irgendwo steht,
warum. Für die **Fensterwahl** und für das **Delta gegenüber jetzt** — die
beiden Zahlen, um die es geht — ist ein konstanter Aufschlag ohnehin neutral:
er verschiebt jede Stunde um denselben Betrag. Das Attribut ``preisquelle``
sagt ausdrücklich, was drinsteht.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

#: Wie viele Slots ein Tag auf der Achse belegt. ⚠ Das ist die **Achsen**-Breite,
#: keine Behauptung über die Stundenzahl eines Tages — am Ende der Sommerzeit
#: bleibt ein Slot leer bzw. fällt ein Preis weg, und genau dafür trägt die
#: Preisreihe `None`.
SLOTS_JE_TAG = 24

#: Die vier kanonischen Dauern von P5 (Fachentscheid, abgenommen 21.09.2026).
#: Ein Sensor kann keinen Parameter entgegennehmen — eine HA-Karte liest
#: Zustände, sie ruft keine Services. Deshalb feste Dauern statt einer Eingabe.
P5_DAUERN_H: tuple[int, ...] = (1, 2, 3, 4)


@dataclass(frozen=True)
class FensterKontext:
    """Alles, was die fünf Fenster-Stücke gemeinsam brauchen — einmal erhoben."""

    heute: date
    #: Stunde der laufenden Prozesszeit = erster Slot, der noch in Frage kommt.
    jetzt_slot: int
    #: Slot-Preis in ct/kWh; `None`, wo kein Preis vorliegt (ADR-002/P4).
    preis_cent: list[Optional[float]]
    #: effektiver Preis je zusätzlicher kWh (Überschuss mindert ihn).
    kosten: list[Optional[float]]
    #: prognostizierter Überschuss je Slot in kWh (morgen: 0, s. Modul-Docstring).
    ueberschuss_kwh: list[float]
    #: prognostizierter Gesamtverbrauch je Slot in kWh (Modell A).
    verbrauch_kwh: list[float]
    #: Günstig-Markierung — **dieselbe**, die `eedc_preis_rang` trägt.
    guenstig: list[bool]
    #: Temperaturvorhersage je Slot (nur heute belegt) — P8 sucht darin das Maximum.
    temperatur_c: list[Optional[float]]
    #: Woher der Preis kommt: `"boersenpreis"` oder `"keine"`.
    preisquelle: str
    #: letzter Slot mit Preis — die natürliche Frist von P5.
    frist_slot: Optional[int]
    #: Profilangaben von Modell A, die jeder Sensor mitträgt (N-392).
    profil_attribute: dict = field(default_factory=dict)
    #: der temperaturkorrigierte **WP-Anteil** der Verbrauchsreihe (P7), oder
    #: `None` ohne WP-Profil. ⚠ Teilmenge von `verbrauch_kwh`, kein Summand.
    wp_stundenprofil_kwh: Optional[list[float]] = None

    @property
    def hat_preis(self) -> bool:
        return self.preisquelle != "keine"

    @property
    def hat_ueberschuss(self) -> bool:
        return any(v > 0 for v in self.ueberschuss_kwh)

    def slot_iso(self, slot: int) -> str:
        """Ein Slot als ISO-8601-Zeitstempel **mit Zone** (`device_class: timestamp`).

        Die Zone ist die des Prozesses — dieselbe, in der die Stundenreihen
        gebildet wurden und in der HA läuft (das Add-on übernimmt die Zone von
        Home Assistant, s. Daten-Checker `ZEITZONE_ABWEICHUNG`). Sie wird hier
        **einmal** angehängt; kein Aufrufer baut einen Zeitstempel selbst.
        """
        tag = self.heute + timedelta(days=slot // SLOTS_JE_TAG)
        stunde = slot % SLOTS_JE_TAG
        return datetime.combine(tag, time(hour=stunde)).astimezone().isoformat()

    def fenster_attribute(self, f, *, mit_delta: bool = True) -> dict:
        """Ein ``Fenster`` des Layers in Sensor-Attribute — die EINE Übersetzung."""
        out = {
            "ab": self.slot_iso(f.ab),
            # `bis` ist der Zeitpunkt, zu dem das Fenster ENDET — ein
            # 2-Stunden-Fenster ab 13 Uhr endet um 15:00. `Fenster.bis` ist
            # genau dieser exklusive Slot; `slot_iso` traegt den Tageswechsel
            # selbst (Slot 48 = uebermorgen 00:00).
            "bis": self.slot_iso(f.bis),
            "stunden": f.bis - f.ab,
            "kosten_cent_kwh": round(f.kosten_cent_kwh, 2),
        }
        if mit_delta and f.delta_vs_jetzt is not None:
            out["delta_cent_kwh_vs_jetzt"] = round(f.delta_vs_jetzt, 2)
        return out


def _reihe(werte: Optional[Sequence[float]], laenge: int) -> list[float]:
    """Eine Reihe auf Achsenlänge bringen — fehlende Slots sind 0 kWh."""
    out = [0.0] * laenge
    for i, v in enumerate(werte or []):
        if i < laenge:
            try:
                out[i] = float(v or 0.0)
            except (TypeError, ValueError):
                out[i] = 0.0
    return out


def baue_fenster_kontext(
    prognose: Optional[dict],
    preis: Optional[dict],
    *,
    jetzt: datetime,
) -> Optional[FensterKontext]:
    """Der gemeinsame Eingang aller Fenster-Sensoren — oder ``None``.

    ``None`` genau dann, wenn **beide** Seiten fehlen: ohne Preis **und** ohne
    Überschuss gibt es nichts zu verschieben, und jedes Fenster wäre eine
    erfundene Aussage (ADR-002/P4). Eine Seite allein reicht:

    * **nur Preis** (kein individuelles Verbrauchsprofil, N-332) ⇒ die Fenster
      rechnen rein nach Preis, `ueberschuss_kwh` bleibt 0.
    * **nur Überschuss** (kein Strompreis-Sensor) ⇒ Kosten sind 0 in den
      Überschuss-Stunden und `None` sonst; ein Fenster entsteht dann **nur
      innerhalb** der Überschuss-Blöcke, und `preisquelle` sagt `"keine"`.
    """
    prognose = prognose or {}
    preis = preis or {}

    rang_heute = preis.get("rang_profil") or []
    rang_morgen = preis.get("rang_profil_morgen") or []
    laenge = 2 * SLOTS_JE_TAG if rang_morgen else SLOTS_JE_TAG

    preis_cent: list[Optional[float]] = [None] * laenge
    guenstig: list[bool] = [False] * laenge
    for versatz, rang in ((0, rang_heute), (SLOTS_JE_TAG, rang_morgen)):
        for eintrag in rang:
            h = eintrag.get("stunde")
            if h is None or not (0 <= h < SLOTS_JE_TAG):
                continue
            slot = versatz + h
            if slot >= laenge:
                continue
            preis_cent[slot] = eintrag.get("preis_cent")
            guenstig[slot] = bool(eintrag.get("unter_schwelle"))

    pv = _reihe(prognose.get("stundenprofil_heute"), laenge)
    verbrauch = _reihe(prognose.get("verbrauch_stundenprofil_kwh"), laenge)
    hat_verbrauchsprofil = bool(prognose.get("verbrauch_stundenprofil_kwh"))

    # Überschuss nur dort, wo BEIDE Reihen etwas sagen. Ohne Verbrauchsprofil
    # wäre „PV minus nichts" der ganze PV-Ertrag — eine Überschuss-Behauptung
    # aus einer halben Rechnung (N-332).
    if hat_verbrauchsprofil:
        ueberschuss = [max(0.0, pv[i] - verbrauch[i]) for i in range(laenge)]
        # Morgen kennt Modell A nicht — s. Modul-Docstring.
        for slot in range(SLOTS_JE_TAG, laenge):
            ueberschuss[slot] = 0.0
    else:
        ueberschuss = [0.0] * laenge

    hat_preis = any(p is not None for p in preis_cent)
    if not hat_preis and not any(v > 0 for v in ueberschuss):
        return None

    from backend.core.berechnungen.fenster import kosten_profil

    if hat_preis:
        kosten = kosten_profil(preis_cent, ueberschuss, 1.0)
        preisquelle = "boersenpreis"
    else:
        # Ohne Preisreihe ist nur die Überschuss-Seite bekannt: eine
        # Überschuss-Stunde kostet 0, jede andere ist unbekannt — nicht teuer.
        kosten = [0.0 if ueberschuss[i] > 0 else None for i in range(laenge)]
        preisquelle = "keine"

    mit_preis = [i for i, k in enumerate(kosten) if k is not None]

    return FensterKontext(
        heute=jetzt.date(),
        jetzt_slot=jetzt.hour,
        preis_cent=preis_cent,
        kosten=kosten,
        ueberschuss_kwh=ueberschuss,
        verbrauch_kwh=verbrauch,
        guenstig=guenstig,
        temperatur_c=(
            list(prognose.get("verbrauch_temperatur_c") or []) + [None] * laenge
        )[:laenge],
        wp_stundenprofil_kwh=(
            _reihe(prognose.get("verbrauch_wp_stundenprofil_kwh"), laenge)
            if prognose.get("verbrauch_wp_stundenprofil_kwh") else None
        ),
        preisquelle=preisquelle,
        frist_slot=mit_preis[-1] if mit_preis else None,
        profil_attribute={
            "profil_typ": prognose.get("verbrauch_profil_typ"),
            "profil_tage": prognose.get("verbrauch_profil_tage"),
        } if hat_verbrauchsprofil else {},
    )


def fenster_fuer_menge(
    ctx: FensterKontext,
    menge_kwh: float,
    *,
    dauer_h: int = 2,
    ab_slot: Optional[int] = None,
    frist_slot: Optional[int] = None,
):
    """Das günstigste Fenster für **eine bestimmte Menge** (P4 · P8 · P9).

    Unterschied zu P5: dort ist die Menge unbekannt und das Kostenprofil
    mengenneutral (1 kWh je Slot); hier ist sie bekannt, und der Überschuss
    deckt sie nur **anteilig** — 3 kWh Überschuss machen eine 9-kWh-Ladung
    nicht kostenlos. Deshalb ein eigenes Kostenprofil mit der wirklichen Menge
    je Stunde; die Formel bleibt dieselbe (ADR-001).
    """
    from backend.core.berechnungen.fenster import bestes_fenster, kosten_profil

    if dauer_h < 1 or menge_kwh <= 0:
        return None
    je_slot = menge_kwh / dauer_h
    if ctx.preisquelle == "keine":
        kosten = ctx.kosten            # ohne Preis gibt es nichts zu mischen
    else:
        kosten = kosten_profil(ctx.preis_cent, ctx.ueberschuss_kwh, je_slot)
    return bestes_fenster(
        kosten,
        dauer_h=dauer_h,
        ab_h=ctx.jetzt_slot if ab_slot is None else ab_slot,
        frist_h=frist_slot,
    )
