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

## Die Slot-Achse — **backward**, seit N-544 (22.09.2026)

**Slot ``s`` ist die Stunde, die ``(s−1)`` Stunden nach Mitternacht des heutigen
Tages beginnt** — also das Intervall ``[Mitternacht + (s−1) h, Mitternacht + s h)``.
Das ist dieselbe Konvention wie überall sonst im Baum (``core/berechnungen/
slot_konvention.py``, #144): Slot ``h`` deckt ``[h−1, h)``, Slot 0 ist gestern
23 Uhr, und ``s // 24`` ist der Tag-Offset, ``s % 24`` der Backward-Slot dieses
Tages. ``zeittarif.uhrzeit_des_slots(tag, s)`` ist die **einzige** Slot→Uhr-
Funktion des Baums; dieses Modul baut keine zweite.

⛔ **Bis zum 21.09.2026 stand hier: „Slot 0…23 ist heute Stunde 0…23"** — die
Achse war **forward**, weil ihr Hauptlieferant (``rang_profil`` aus
``strompreis_markt_service``) es ist. Die anderen Reihen auf derselben Achse
sind es nicht: ``stundenprofil_heute`` der PV-Prognose ist backward, das
Verbrauchsprofil von Modell A ist backward, die Temperaturreihe auch. **Vier
Zeitangaben lagen dadurch eine Stunde daneben** (E2 ``seit``, E5
``stunde_max_mittel``, P2 ``fenster[].ab/bis``, P7 ``guenstige_heizstunden``)
und eine eine Stunde voraus (E1 ``stand``); der Preis einer Stunde wurde gegen
den Überschuss der **Nachbarstunde** verrechnet. Genau die Klasse N-387.

**Die Länge der Achse:**

* **48** Slots (heute + morgen), sobald für morgen etwas vorliegt — bei einem
  ableitbaren Tarif immer (``preis_je_slot`` braucht keine Daten, nur ein
  Datum), bei der Börse ab der Veröffentlichung (``DAY_AHEAD_VEROEFFENTLICHUNG_STUNDE``,
  13:00).
* **25** Slots, wenn nur die heutige Börse vorliegt. ⚠ **Nicht 24.** Die
  backward-Achse eines Tages endet mit Slot 23 = ``[22, 23)``; die Stunde
  ``[23, 24)`` ist Slot **24**. Sie liegt heute im Rahmen (``frist_slot`` ist
  inklusiv) und fiele bei einer 24er-Achse weg — ein 2-Stunden-Fenster um 22 Uhr
  wäre nicht mehr findbar.
* **Slot 0** ist gestern 23 Uhr. Für die Börse kommt er aus dem persistierten
  Tagesprofil des Vortags (``preis_tag.persistierte_preise``, Zeile
  ``stunde=23``, forward); liegt dort nichts, bleibt er ``None`` — und ``ab_h =
  jetzt_slot`` schließt ihn ohnehin aus, sobald es nach 0 Uhr ist.

⚠ **Für morgen gibt es keine Überschuss-Prognose, und das ist bewusst so.**
Modell A liefert das Verbrauchsprofil nur für **heute** (Werktag/Wochenende der
laufenden Uhr, Temperaturkorrektur aus dem heutigen Forecast). Ohne
Verbrauchsreihe gibt es keinen Überschuss, und ein geschätzter wäre eine Zahl,
die aussieht wie eine Rechnung. Die Kosten für morgen sind deshalb der **volle**
Slot-Preis — das ist die vorsichtige Richtung: ein Fenster morgen wird nie
fälschlich billiger gerechnet als eines heute.

## Welcher Preis — der, den der Haushalt zahlt (S3b, Entscheid Gernot 22.09.2026)

⭐ **Der Slot-Preis kommt aus der Bezugspreis-Reihe** (``services/ha_export_bezugspreis.py``,
Layer ``core/berechnungen/preis_reihe.py``), nicht aus der Börse:

* **Festpreis / Zeitfenster / leere Vertragsart** — der Arbeitspreis **exakt**
  aus dem Tarif zum Stichtag (``zeittarif.preis_je_slot``). Für den
  Festtarif-Haushalt entstehen die Fenster damit **erstmals mit dem Preis, den
  er zahlt**; vorher bekam er die Börse, die er nie sieht.
* **Dynamischer Tarif** (``vertragsart == "dynamisch"``) — ``(1 + USt) × Börse +
  abgeleiteter Aufschlag``; ohne ableitbaren Aufschlag die **nackte Börse** als
  beschriftete Näherung. ``preisquelle`` sagt, welcher Fall vorliegt.
* **Kein Tarif** — kein Preis (``preisquelle: "keine"``); Fenster entstehen dann
  nur innerhalb der Überschuss-Blöcke.

⛔ **Hier stand bis zum 22.09.2026 das Gegenteil** („der Slot-Preis ist der, den
``eedc_preis_aktuell_cent`` trägt … deshalb wird hier auch nichts
aufgeschlagen"). Die Begründung war, ein konstanter Aufschlag sei für die
**Fensterwahl** und das **Delta** neutral. Das hält aus zwei Gründen nicht:

1. **Er ist nicht neutral, sobald Überschuss im Spiel ist.** ``kosten_profil``
   mischt Slot-Preis und Überschussanteil; ein Aufschlag verschiebt gerade
   **nicht** jede Stunde um denselben Betrag, sondern die Überschuss-Stunden
   weniger als die übrigen. Die Reihenfolge der Fenster kann damit kippen.
2. **Für einen Festtarif-Haushalt war die Börse schlicht der falsche Preis**
   (KONZEPT-FLEX-TARIFE §3 T-1: ein Endpreis ist kein Börsenpreis, es sei denn
   ausdrücklich dynamisch **und** als Näherung beschriftet).

``eedc_preis_aktuell_cent`` und ``eedc_guenstige_stunde`` bleiben unverändert die
**Börsen**-Sicht — sie beantworten eine andere Frage („ist diese Stunde am Markt
billig?"), und ihre Attribute sind seit v4.0.10 Vertrag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:          # nur fuer die Typangabe — kein Laufzeit-Import (Zyklus)
    from backend.services.ha_export_bezugspreis import Bezugspreise

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
    #: Der Slot der **laufenden** Stunde = erster Slot, der noch in Frage kommt.
    #: Backward: um 14:30 läuft ``[14, 15)``, und das ist Slot **15**
    #: (``jetzt.hour + 1``). Bis N-544 stand hier ``jetzt.hour`` — auf einer
    #: forward-Achse richtig, backward eine Stunde zu früh: ein Fenster durfte
    #: in der bereits **abgelaufenen** Stunde beginnen.
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
    #: S3b: die **Preis**reihe je Verwendung (`allgemein` · `waermepumpe`).
    #: Leer, solange keine Bezugspreis-Reihe vorliegt — dann gilt `preis_cent`
    #: für alle, wie vor S3b.
    preis_je_verwendung: dict = field(default_factory=dict)
    #: dieselbe Aufteilung für die mengenneutrale Kostenreihe (Überschuss schon
    #: eingerechnet) — P7 verteilt darauf.
    kosten_je_verwendung: dict = field(default_factory=dict)
    #: Woher der Preis der jeweiligen Verwendung kommt.
    preisquelle_je_verwendung: dict = field(default_factory=dict)
    #: der temperaturkorrigierte **WP-Anteil** der Verbrauchsreihe (P7), oder
    #: `None` ohne WP-Profil. ⚠ Teilmenge von `verbrauch_kwh`, kein Summand.
    wp_stundenprofil_kwh: Optional[list[float]] = None

    @property
    def hat_preis(self) -> bool:
        return self.preisquelle != "keine"

    def hat_preis_fuer(self, verwendung: str) -> bool:
        """Gibt es für DIESE Verwendung einen Preis?

        ⭐ **Der Fall, den es ohne die Frage nicht gäbe:** eine Anlage mit
        gepflegtem Wärmepumpentarif, aber **ohne** allgemeine Tarifzeile.
        `tarife_zum_stichtag` lässt `allgemein` dann auf `None` (der Fallback
        geht nur in die andere Richtung) — anlagenweit gibt es also keinen
        Preis, für die Wärmepumpe aber sehr wohl. Ein einzelnes `hat_preis`
        hätte das Heizfenster mit abgeschaltet.
        """
        if verwendung in self.preisquelle_je_verwendung:
            return self.preisquelle_je_verwendung[verwendung] != "keine"
        return self.hat_preis

    def kosten_fuer(self, verwendung: str) -> list:
        """Die Kostenreihe dieser Verwendung — sonst die anlagenweite."""
        return self.kosten_je_verwendung.get(verwendung, self.kosten)

    def preis_fuer(self, verwendung: str) -> list:
        """Die Preisreihe dieser Verwendung — sonst die anlagenweite."""
        return self.preis_je_verwendung.get(verwendung, self.preis_cent)

    def preisquelle_fuer(self, verwendung: str) -> str:
        """Woher der Preis dieser Verwendung kommt — für das Attribut."""
        return self.preisquelle_je_verwendung.get(verwendung, self.preisquelle)

    @property
    def hat_ueberschuss(self) -> bool:
        return any(v > 0 for v in self.ueberschuss_kwh)

    def slot_iso(self, slot: int) -> str:
        """Der **Beginn** eines Slots als ISO-8601-Zeitstempel **mit Zone**.

        Slot ``s`` beginnt ``(s−1)`` Stunden nach Mitternacht des heutigen Tages
        — die Rechnung steht in ``zeittarif.uhrzeit_des_slots`` und wird hier
        **importiert, nicht nachgebaut**: sie ist die einzige Slot→Uhr-Funktion
        des Baums, und eine zweite wäre genau die Drift, gegen die N-544 steht.
        Den Tagesübergang trägt sie selbst (Slot 25 = morgen 00:00, Slot 0 =
        gestern 23:00).

        Die Zone ist die des Prozesses — dieselbe, in der die Stundenreihen
        gebildet wurden und in der HA läuft (das Add-on übernimmt die Zone von
        Home Assistant, s. Daten-Checker `ZEITZONE_ABWEICHUNG`). Sie wird hier
        **einmal** angehängt; kein Aufrufer baut einen Zeitstempel selbst.

        ⚠ **DST-Fold:** Am Ende der Sommerzeit gibt es 02:00 zweimal.
        `astimezone()` auf einer naiven Zeit nimmt die **erste** (``fold=0``) —
        dieselbe Wahl, die `strompreis_markt_service` für die Börse trifft
        („die erste gewinnt"). Die zweite 02:00 ist über diese Achse nicht
        adressierbar; das ist bewusst und einheitlich, nicht übersehen.
        """
        from backend.core.berechnungen.zeittarif import uhrzeit_des_slots

        return uhrzeit_des_slots(self.heute, slot).astimezone().isoformat()

    def slot_ende_iso(self, slot: int) -> str:
        """Das **Ende** eines Slots — der Beginn des nächsten.

        Eigene Funktion, weil die Unterscheidung der ganze Punkt von N-544 ist:
        ``ab``/``seit``/``stunden`` sind Beginn-Angaben, ``bis``/``*_um``/
        ``frist``/``stand`` sind End-Angaben. Wer beides über dieselbe Funktion
        ausgibt, hat die Unterscheidung wieder verloren.
        """
        return self.slot_iso(slot + 1)

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
    """Eine **backward** indizierte Tagesreihe auf die Achse bringen — fehlend = 0 kWh.

    Index ``i`` der Quelle ist der Backward-Slot ``i`` des heutigen Tages, und
    der ist auf dieser Achse ebenfalls Slot ``i`` (beide zählen ab „gestern
    23 Uhr"). Deshalb 1:1, ohne Versatz — anders als bei den **forward**
    beschrifteten Börsenreihen, die über ``forward_stunde_zu_backward_slot``
    gehen. Für ``stundenprofil_heute`` heißt das: Slot 24 (heute 23–24 Uhr)
    bleibt 0, die 24er-Reihe endet bei Slot 23.
    """
    out = [0.0] * laenge
    for i, v in enumerate(werte or []):
        if i < laenge:
            try:
                out[i] = float(v or 0.0)
            except (TypeError, ValueError):
                out[i] = 0.0
    return out


def _reihe_nach_label(
    werte: Optional[Sequence], labels: Optional[Sequence[int]], laenge: int,
    *, fuellwert=0.0,
) -> list:
    """Eine Reihe von Modell A **nach ihrem Stunden-Label** einordnen (N-544).

    ⚠ **Warum nicht nach Position.** `verbrauchsprognose_heute` rechnet über die
    Länge des **Forecasts**, nicht über `range(24)`: am Ende der Sommerzeit hat
    der Tag 25 Einträge, am Anfang 23. Ab der Umstellungsstunde sind Position
    und Stunde dann auseinander, und „Position i = Slot i" verschiebt die halbe
    Reihe. Das Label (`stunden_label`, aus `profil[i]["zeit"]`) sagt es genau.

    **Label ``h`` → Slot ``h``** — beide backward (`live_wetter`
    `individuelles_profil.get(h)` liefert den Wert des Backward-Slots ``h``).
    Kommt ein Label zweimal vor (zweite 02:00 im Herbst), **gewinnt das erste**:
    dieselbe Regel, die `strompreis_markt_service` für die Börse anwendet.
    Fehlt ein Label (Frühjahr: die Stunde 2 gibt es nicht), bleibt der Slot auf
    `fuellwert`.

    Ohne `labels` (ältere Prognose-Dicts, eine Quelle ohne das Feld) fällt die
    Funktion auf die Position zurück — das ist das Verhalten von vorher und am
    Normaltag identisch.
    """
    if not labels:
        return _reihe(werte, laenge) if fuellwert == 0.0 else [
            (werte[i] if werte and i < len(werte) else fuellwert) for i in range(laenge)
        ]
    out = [fuellwert] * laenge
    gesetzt: set[int] = set()
    for i, label in enumerate(labels):
        if werte is None or i >= len(werte):
            break
        if not (0 <= label < laenge) or label in gesetzt:
            continue          # zweite 02:00 (Herbst): die erste gewinnt
        out[label] = werte[i]
        gesetzt.add(label)
    return out


def baue_fenster_kontext(
    prognose: Optional[dict],
    preis: Optional[dict],
    bezugspreise: Optional["Bezugspreise"] = None,
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
    from backend.core.berechnungen.slot_konvention import forward_stunde_zu_backward_slot

    prognose = prognose or {}
    preis = preis or {}

    rang_heute = preis.get("rang_profil") or []
    rang_morgen = preis.get("rang_profil_morgen") or []
    # 48 mit Morgen-Satz, sonst 25 — die 25. ist heute 23–24 Uhr (Slot 24), die
    # auf einer 24er-Achse herausfiele, obwohl sie noch im Rahmen liegt.
    laenge = 2 * SLOTS_JE_TAG if rang_morgen else SLOTS_JE_TAG + 1

    preis_cent: list[Optional[float]] = [None] * laenge
    guenstig: list[bool] = [False] * laenge
    for versatz, rang in ((0, rang_heute), (SLOTS_JE_TAG, rang_morgen)):
        for eintrag in rang:
            h = eintrag.get("stunde")
            if h is None or not (0 <= h < SLOTS_JE_TAG):
                continue
            # ⭐ N-544: `rang_profil` ist FORWARD beschriftet (Stunde `h` meint
            # `[h, h+1)`, `strompreis_markt_service` nimmt `lokal.hour` aus dem
            # `start_timestamp`). Auf der backward-Achse ist das Slot `h + 1`.
            slot = versatz + forward_stunde_zu_backward_slot(h)
            if slot >= laenge:
                continue
            preis_cent[slot] = eintrag.get("preis_cent")
            guenstig[slot] = bool(eintrag.get("unter_schwelle"))

    pv = _reihe(prognose.get("stundenprofil_heute"), laenge)
    # Modell A nach LABEL, nicht nach Position (N-544, s. `_reihe_nach_label`).
    labels = prognose.get("verbrauch_stunden_label")
    verbrauch = _reihe_nach_label(
        prognose.get("verbrauch_stundenprofil_kwh"), labels, laenge
    )
    hat_verbrauchsprofil = bool(prognose.get("verbrauch_stundenprofil_kwh"))

    # Überschuss nur dort, wo BEIDE Reihen etwas sagen. Ohne Verbrauchsprofil
    # wäre „PV minus nichts" der ganze PV-Ertrag — eine Überschuss-Behauptung
    # aus einer halben Rechnung (N-332).
    if hat_verbrauchsprofil:
        ueberschuss = [max(0.0, pv[i] - verbrauch[i]) for i in range(laenge)]
        # Morgen kennt Modell A nicht — s. Modul-Docstring. ⚠ Die Grenze liegt
        # backward bei Slot **25** (= morgen 00–01 Uhr), nicht bei 24: Slot 24
        # ist heute 23–24 Uhr und gehört noch zu heute. Vor N-544 stand hier
        # `SLOTS_JE_TAG` — auf der forward-Achse dieselbe Grenze, backward eine
        # Stunde zu früh (sie hätte die letzte Stunde von heute genullt).
        for slot in range(SLOTS_JE_TAG + 1, laenge):
            ueberschuss[slot] = 0.0
    else:
        ueberschuss = [0.0] * laenge

    # ⭐ **S3b: der Preis, den der Haushalt zahlt — nicht die Börse für alle.**
    # Liegt eine Bezugspreis-Reihe vor, ersetzt sie die Börsenreihe VOLLSTÄNDIG
    # (auch ihre `guenstig`-Markierung: „ich zahle jetzt weniger als sonst" ist
    # eine andere Frage als „die Stunde ist am Markt billig"). Ohne Reihe bleibt
    # es bei der Börse — der Stand vor S3b, und der Weg für jeden, der noch
    # keinen Tarif gepflegt hat.
    preis_je_verwendung: dict[str, list[Optional[float]]] = {}
    kosten_je_verwendung: dict[str, list[Optional[float]]] = {}
    preisquelle_je_verwendung: dict[str, str] = {}
    if bezugspreise is not None:
        reihe = bezugspreise.allgemein
        if reihe.hat_preis:
            preis_cent = (list(reihe.preis_cent) + [None] * laenge)[:laenge]
            guenstig = (list(reihe.guenstig) + [False] * laenge)[:laenge]

    hat_preis = any(p is not None for p in preis_cent)
    if not hat_preis and not any(v > 0 for v in ueberschuss):
        return None

    from backend.core.berechnungen.fenster import kosten_profil

    if hat_preis:
        kosten = kosten_profil(preis_cent, ueberschuss, 1.0)
        preisquelle = (
            bezugspreise.allgemein.quelle
            if bezugspreise is not None and bezugspreise.allgemein.hat_preis
            else "boersenpreis"
        )
    else:
        # Ohne Preisreihe ist nur die Überschuss-Seite bekannt: eine
        # Überschuss-Stunde kostet 0, jede andere ist unbekannt — nicht teuer.
        kosten = [0.0 if ueberschuss[i] > 0 else None for i in range(laenge)]
        preisquelle = "keine"

    # ── Der Tarif der VERWENDUNG (Frage 1, entschieden 22.09.) ──────────────
    #
    # Ein §14a- oder HT/NT-Wärmepumpentarif ist der klassische Zeitfenster-Fall,
    # und ein Heizfenster mit dem Haushaltspreis wäre dort die falsche Zahl.
    # `resolve_tarif_for_komponente` beantwortet die Frage längst; hier landet
    # nur ihr Ergebnis als zweite Kostenreihe.
    if bezugspreise is not None:
        for verwendung in ("allgemein", "waermepumpe"):
            r = bezugspreise.reihe(verwendung)
            if not r.hat_preis:
                continue
            p_v = (list(r.preis_cent) + [None] * laenge)[:laenge]
            preis_je_verwendung[verwendung] = p_v
            kosten_je_verwendung[verwendung] = kosten_profil(p_v, ueberschuss, 1.0)
            preisquelle_je_verwendung[verwendung] = r.quelle

    mit_preis = [i for i, k in enumerate(kosten) if k is not None]

    return FensterKontext(
        heute=jetzt.date(),
        # N-544: die LAUFENDE Stunde `[jetzt.hour, jetzt.hour + 1)` ist backward
        # der Slot `jetzt.hour + 1`.
        jetzt_slot=jetzt.hour + 1,
        preis_cent=preis_cent,
        kosten=kosten,
        ueberschuss_kwh=ueberschuss,
        verbrauch_kwh=verbrauch,
        guenstig=guenstig,
        temperatur_c=_reihe_nach_label(
            prognose.get("verbrauch_temperatur_c"), labels, laenge, fuellwert=None
        ),
        wp_stundenprofil_kwh=(
            _reihe_nach_label(
                prognose.get("verbrauch_wp_stundenprofil_kwh"), labels, laenge
            )
            if prognose.get("verbrauch_wp_stundenprofil_kwh") else None
        ),
        preisquelle=preisquelle,
        frist_slot=mit_preis[-1] if mit_preis else None,
        preis_je_verwendung=preis_je_verwendung,
        kosten_je_verwendung=kosten_je_verwendung,
        preisquelle_je_verwendung=preisquelle_je_verwendung,
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
    verwendung: str = "allgemein",
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
    if not ctx.hat_preis_fuer(verwendung):
        # Ohne Preis gibt es nichts zu mischen — das Fenster entsteht dann
        # allein aus den Überschuss-Blöcken.
        kosten = ctx.kosten_fuer(verwendung)
    else:
        # ⭐ S3b: die Preisreihe **dieser Verwendung**. Eine Wärmepumpe mit
        # eigenem §14a-Tarif rechnet mit ihrem Preis, nicht mit dem des
        # Haushalts — sonst stünde das Heizfenster auf einer Zahl, die für
        # dieses Gerät nie gilt.
        kosten = kosten_profil(ctx.preis_fuer(verwendung), ctx.ueberschuss_kwh, je_slot)
    return bestes_fenster(
        kosten,
        dauer_h=dauer_h,
        ab_h=ctx.jetzt_slot if ab_slot is None else ab_slot,
        frist_h=frist_slot,
    )
