"""Was eine Kilowattstunde in **dieser** Stunde kostet — die Reihe und ihre Herkunft.

**Der Layer-SoT für den Bezugspreis je Slot** (ADR-001; S3b „Preise und Speicher",
Entscheid Gernot 22.09.2026). Hier steht die Formel, nirgends sonst; die Route
sammelt nur die Eingänge (`services/ha_export_bezugspreis.py`).

## Ein Preis-Regime, und es heißt `ist_dynamisch`

Der Baum kennt **einen** Diskriminator für „der Preis kommt vom Markt":
``Strompreis.vertragsart == "dynamisch"``. Er stand bis zum 22.09.2026 an fünf
Produktivstellen ausgeschrieben (`speicher_wirtschaftlichkeit` ·
`api/routes/datenquellen` · `csv_operations` zweimal · `monatsabschluss/views`).
Fünf Kopien einer Ja/Nein-Frage sind fünf Stellen, an denen eine sechste
Schreibweise („dyn", „variabel") vorbeigeht — deshalb `ist_dynamisch(tarif)`.

⛔ **Nicht zu verwechseln mit `zeittarif.hat_zeitfenster`.** Das ist eine
Eigenschaft des Tarifs (trägt er Hoch-/Niedertarif-Fenster?) und gilt
ausdrücklich **auch für einen festen Bezug** — Bernds Fall. Ein dynamischer
Tarif *mit* gepflegten Fenstern ist messbar, und dort gewinnt `ist_dynamisch`:
der Marktpreis ist die Wirklichkeit, die Fenster sind dann eine Altlast der
Pflege (Attribut `zeitfenster_ignoriert`).

## Ableitbar oder Näherung — nie beides gemischt (Flex §3 T-1)

* **`fest`, `sondervertrag`, leere Vertragsart** ⇒ der Arbeitspreis kommt
  **exakt** aus dem Tarif (`zeittarif.preis_je_slot`), Slot für Slot, für jedes
  Datum und ohne Datenbank. Quelle `vertrag` bzw. `zeitfenster`.
* **`dynamisch`** ⇒ ``(1 + USt) × Börse + Aufschlag``. Der Aufschlag ist
  **abgeleitet**, nicht geraten (s. unten); gibt es keinen, bleibt die **nackte
  Börse** stehen und heißt dann ausdrücklich `boersenpreis` — eine beschriftete
  Näherung, kein Endpreis.
* **kein Tarif** ⇒ kein Preis (`keine`). Ohne Tarif gibt es keinen Preis, den
  eedc behaupten dürfte.

## Der Aufschlag — abgeleitet, mit genannter Stufe

Die Annahme ist schmal und steht ausdrücklich da: *Endpreis = (1 + USt) × Börse
+ ein über den Zeitraum konstanter Anteil*. Sie deckt Tibber, aWATTar & Co.; für
einen Deckel-Tarif liefert sie einen Durchschnitt, und `aufschlag_quelle` sagt,
woher er kommt. **Kein neues Tariffeld** — das Verfahren braucht kein
Tarifmodell, nur zwei Zahlen, die eedc ohnehin hat:

1. **Abrechnung** (`aufschlag_aus_abrechnung`) — der abgerechnete Monats-Ø minus
   ``(1 + USt) ×`` dem **verbrauchsgewichteten** Börsenmittel desselben Monats.
   Verbrauchsgewichtet, weil der Anwender seinen Ø auch so bezahlt hat: eine
   Stunde, in der er nichts bezogen hat, gehört nicht in den Schnitt.
2. **Gemessene Stunden** (`aufschlag_aus_stunden`) — der **Median** über
   ``Endpreis_h − (1 + USt) × Börse_h``. Median und nicht Mittel: eine einzelne
   Stunde mit Zähler-Glitch oder negativer Börse an der Steuergrenze verschiebt
   ein Mittel, einen Median nicht.
3. **keiner** — dann Börse, beschriftet.

⚠ **Wachen mit ``is not None``, nie truthy.** 0 ct ist ein gepflegter Wert (eine
Volleinspeise-Anlage ohne Vergütung, die Vorbelegung eines neuen Tarifs); `if
preis:` würde sie wie „fehlt" behandeln.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Optional, Sequence

from backend.core.berechnungen.zeittarif import preis_je_slot

#: Umsatzsteuersatz, wenn die Anlage keinen gepflegt hat. DE = 19 %; AT pflegt
#: 20 % an der Anlage (`Anlage.ust_satz_prozent`).
UST_DEFAULT_PROZENT = 19.0

#: So viele Paare (Stunde mit Endpreis UND Börse) müssen vorliegen, bevor aus
#: dem Preissensor ein Aufschlag abgeleitet wird. Ein Tag ist zu wenig: er kann
#: vollständig in eine Hochpreisphase fallen. 24 sind mindestens ein voller
#: Tagesgang und damit beide Seiten eines Preistals.
MINDEST_PAARE = 24


# ─────────────────────────────────────────────────────────────────────────────
# Das Regime
# ─────────────────────────────────────────────────────────────────────────────

def ist_dynamisch(tarif: Any) -> bool:
    """Bezieht dieser Tarif seinen Arbeitspreis vom **Markt**?

    Der eine Diskriminator des Baums. ``None`` ist kein dynamischer Tarif —
    ohne Tarif gibt es gar keinen Preis, und das ist eine andere Aussage.
    """
    return bool(tarif is not None and getattr(tarif, "vertragsart", None) == "dynamisch")


@dataclass(frozen=True)
class PreisReihe:
    """Ein Bezugspreis je Slot, samt Herkunft.

    ``preis_cent[s]`` ist ``None``, wo kein Preis vorliegt (ADR-002/P4) — das
    ist nicht dasselbe wie 0 ct.
    """

    preis_cent: list[Optional[float]]
    #: Ist dieser Slot der **günstige** Teil des Tarifs? Für einen Zeittarif die
    #: Slots unter dem Stammpreis (Niedertarif); sonst überall `False`.
    #: ⛔ **Nicht** die Börsen-Günstig-Markierung von `eedc_preis_rang` — die
    #: beantwortet „ist die Stunde am Markt billig", diese hier „zahle ich in
    #: dieser Stunde weniger als sonst".
    guenstig: list[bool]
    #: `vertrag` · `zeitfenster` · `boerse_plus_aufschlag` · `boersenpreis` · `keine`
    quelle: str

    @property
    def hat_preis(self) -> bool:
        return any(p is not None for p in self.preis_cent)

    @property
    def ist_vollstaendig(self) -> bool:
        """Ist das ein **Endpreis** — oder nur eine beschriftete Näherung?

        Entscheidet, ob daraus ein Eigenverbrauchs-Wert gebildet werden darf:
        „Börse minus Vertragsvergütung" wäre keine Näherung, sondern eine
        Differenz aus zwei verschiedenen Preisebenen (Flex P-5).
        """
        return self.quelle in ("vertrag", "zeitfenster", "boerse_plus_aufschlag")


LEERE_REIHE = PreisReihe(preis_cent=[], guenstig=[], quelle="keine")


# ─────────────────────────────────────────────────────────────────────────────
# Die Reihen
# ─────────────────────────────────────────────────────────────────────────────

def bezugspreis_reihe(
    *,
    tarif: Any,
    heute: date,
    laenge: int,
    boerse_backward: Optional[Sequence[Optional[float]]] = None,
    aufschlag_cent: Optional[float] = None,
    ust_prozent: Optional[float] = None,
) -> PreisReihe:
    """Der Bezugspreis je Slot der Achse — die EINE Kaskade.

    Args:
        tarif: die Tarifzeile zum Stichtag, oder `None`.
        heute: der Tag, auf dem die Achse steht (Slot ``s`` beginnt
            ``(s−1)`` Stunden nach dessen Mitternacht).
        laenge: Achsenlänge (25 oder 48, s. `services/ha_export_fenster`).
        boerse_backward: die Börsenreihe, **schon auf der backward-Achse**.
            Nur für den dynamischen Fall; die Verschiebung macht der Aufrufer
            über `slot_konvention.forward_stunde_zu_backward_slot`.
        aufschlag_cent: der abgeleitete Aufschlag (brutto) oder `None`.
        ust_prozent: aus `Anlage.ust_satz_prozent`; `None` ⇒ 19.

    ⭐ **Für den ableitbaren Fall gibt es hier keinen zweiten Endpreis-Rechner.**
    Jeder Slot geht einzeln durch `zeittarif.preis_je_slot` — dieselbe Funktion,
    die Monatsbericht, Speicher-Dashboard und HA-Export schon benutzen. Die
    Symmetrie ist damit keine Absprache, sondern Bauform.
    """
    if tarif is None:
        return PreisReihe([None] * laenge, [False] * laenge, "keine")

    if ist_dynamisch(tarif):
        boerse = list(boerse_backward or [])
        boerse = (boerse + [None] * laenge)[:laenge]
        if aufschlag_cent is None:
            # Nackte Börse — ausdrücklich als Näherung beschriftet.
            return PreisReihe(boerse, [False] * laenge, "boersenpreis")
        return PreisReihe(
            endpreis_reihe(boerse, aufschlag_cent, ust_prozent),
            [False] * laenge,
            "boerse_plus_aufschlag",
        )

    stamm = float(getattr(tarif, "netzbezug_arbeitspreis_cent_kwh", 0.0) or 0.0)
    preise: list[Optional[float]] = []
    guenstig: list[bool] = []
    for s in range(laenge):
        tag = heute + timedelta(days=s // 24)
        p = preis_je_slot(tarif, tag, s % 24)
        preise.append(p)
        # „Günstig" heißt hier: unter dem Stammpreis — also im Niedertarif.
        guenstig.append(p is not None and p < stamm)
    quelle = "zeitfenster" if any(guenstig) else "vertrag"
    return PreisReihe(preise, guenstig, quelle)


def endpreis_reihe(
    boerse_backward: Sequence[Optional[float]],
    aufschlag_cent: float,
    ust_prozent: Optional[float] = None,
) -> list[Optional[float]]:
    """``(1 + USt) × Börse + Aufschlag`` je Slot.

    ⚠ **Eine negative Börse bleibt negativ, und der Endpreis darf unter den
    Aufschlag fallen.** Genau so rechnet ein dynamischer Versorger ab — wer hier
    bei 0 abschnitte, würde die Stunden wegnehmen, in denen sich Verbrauchen am
    meisten lohnt. `None` bleibt `None` (ADR-002/P4).
    """
    faktor = 1.0 + _ust_anteil(ust_prozent)
    return [
        None if b is None else round(faktor * float(b) + float(aufschlag_cent), 2)
        for b in boerse_backward
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Der Aufschlag
# ─────────────────────────────────────────────────────────────────────────────

def _ust_anteil(ust_prozent: Optional[float]) -> float:
    """Der USt-Anteil als Faktor (19 % → 0,19); `None`/Unsinn ⇒ Default."""
    try:
        wert = float(UST_DEFAULT_PROZENT if ust_prozent is None else ust_prozent)
    except (TypeError, ValueError):
        wert = UST_DEFAULT_PROZENT
    if not (0.0 <= wert < 100.0):
        wert = UST_DEFAULT_PROZENT
    return wert / 100.0


def boersenmittel_gewichtet(
    paare: Iterable[tuple[Optional[float], Optional[float]]]
) -> Optional[float]:
    """Das mit dem Netzbezug gewichtete Börsenmittel: ``Σ(Börse × Bezug) ÷ Σ Bezug``.

    Args:
        paare: ``(boerse_cent, bezug_kwh)`` je Stunde. Negativer Bezug wird auf
            0 geklemmt (Zähler-Glitch — dieselbe Behandlung wie in
            `zeittarif.gewichteter_arbeitspreis_cent`); `None` auf einer der
            beiden Seiten zählt nicht mit.

    Returns:
        ct/kWh, oder `None`, wenn **kein** Bezug vorliegt. `None` heißt „nicht
        gewichtbar", nicht „0 ct" — der Aufrufer bildet dann keinen Aufschlag,
        statt einen aus einem ungewichteten Schnitt zu erfinden.

    ⚑ **Warum gewichtet und nicht einfach.** Der abgerechnete Monats-Ø, gegen den
    dieser Wert gehalten wird, ist selbst verbrauchsgewichtet: der Anwender hat
    für jede bezogene Kilowattstunde den Preis ihrer Stunde bezahlt. Ein
    arithmetisches Börsenmittel daneben zöge die Nachtstunden hoch, in denen er
    wenig bezieht — und der abgeleitete Aufschlag wäre systematisch zu klein.
    """
    zaehler = 0.0
    nenner = 0.0
    for boerse, bezug in paare:
        if boerse is None or bezug is None:
            continue
        menge = max(0.0, float(bezug))
        zaehler += float(boerse) * menge
        nenner += menge
    if nenner <= 0:
        return None
    return round(zaehler / nenner, 4)


def aufschlag_aus_abrechnung(
    monats_oe_cent: Optional[float],
    boerse_gewichtet_cent: Optional[float],
    ust_prozent: Optional[float] = None,
) -> Optional[float]:
    """Der Aufschlag brutto aus einer **abgerechneten** Monatszeile.

        Aufschlag = Ø_abgerechnet − (1 + USt) × Börsenmittel_gewichtet

    Beide Eingänge müssen vorliegen (`is not None`); ein fehlender ergibt
    `None`, nicht 0.

    >>> aufschlag_aus_abrechnung(27.66, 8.00, 19.0)
    18.14
    """
    if monats_oe_cent is None or boerse_gewichtet_cent is None:
        return None
    faktor = 1.0 + _ust_anteil(ust_prozent)
    return round(float(monats_oe_cent) - faktor * float(boerse_gewichtet_cent), 2)


def aufschlag_aus_stunden(
    paare: Iterable[tuple[Optional[float], Optional[float]]],
    ust_prozent: Optional[float] = None,
    mindest_paare: int = MINDEST_PAARE,
) -> Optional[float]:
    """Der Aufschlag brutto als **Median** über gemessene Stunden.

    Args:
        paare: ``(endpreis_cent, boerse_cent)`` derselben Stunde — beide aus
            derselben Zeile des Tagesprofils, beide forward beschriftet und
            damit **ohne** Verschiebung paarbar.
        mindest_paare: unter dieser Zahl kein Wert (Default `MINDEST_PAARE`).

    ⭐ **Median, nicht Mittel.** Der Differenzwert ist über den Tag theoretisch
    konstant; in der Messung ist er es nicht (Rundung des Sensors, eine Stunde
    mit Netzentgelt-Sondertarif, ein Zähler-Glitch). Ein einziger Ausreißer
    verschiebt ein Mittel um den Ausreißer ÷ n, einen Median gar nicht.
    """
    werte: list[float] = []
    faktor = 1.0 + _ust_anteil(ust_prozent)
    for endpreis, boerse in paare:
        if endpreis is None or boerse is None:
            continue
        werte.append(float(endpreis) - faktor * float(boerse))
    if len(werte) < mindest_paare:
        return None
    return round(statistics.median(werte), 2)


# ─────────────────────────────────────────────────────────────────────────────
# Was eine Kilowattstunde wert ist
# ─────────────────────────────────────────────────────────────────────────────

def wert_je_kwh(bezug_cent: Optional[float], verguetung_cent: Optional[float]) -> Optional[float]:
    """Was eine selbst verbrauchte Kilowattstunde wert ist: ``Bezug − Vergütung``.

    Die Ersparnis besteht aus zwei Teilen: der Netzbezug, den sie vermeidet,
    **minus** der Einspeisung, die sie verdrängt.

    ⚠ **Beide Seiten müssen auf derselben Preisebene liegen** (Flex P-5). Eine
    nackte Börse gegen eine Vertragsvergütung ergäbe keine Näherung, sondern
    eine Differenz aus zwei verschiedenen Größen; der Aufrufer prüft deshalb
    `PreisReihe.ist_vollstaendig`, bevor er hier hereingeht.

    `None` bei fehlendem Eingang — **nicht** 0 (ADR-002/P4).
    """
    if bezug_cent is None or verguetung_cent is None:
        return None
    return round(float(bezug_cent) - float(verguetung_cent), 2)
