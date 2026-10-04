"""Heizgradtage — das Wetter als Nenner einer Verbrauchsgröße (ADR-001).

**Wozu.** Ein kalter Winter braucht mehr Strom als ein milder, ohne dass die
Anlage schlechter arbeitet. Wer zwei Heizperioden vergleichen will, muss das
Wetter herausrechnen: Nicht „kWh", sondern „kWh je Heizgradtag".

**Die Definition — eine einzige, für die ganze Anwendung** (Entscheid Gernot
2026-09-12, SOLL Wärme/Klima §4.1 „SOLL — Wetternormierung", SOLL-§9-E8):

    HDD_Tag = max(0; 15 °C − Tagesmittel der Außentemperatur)

``HEIZGRENZE_C`` ist die **Heizgrenze** nach Gradtag-Konvention, **nicht** eine
Innenraum-Solltemperatur: Unterhalb 15 °C Außentemperatur wird geheizt, darüber
tragen die inneren Gewinne das Haus. Dieselbe Konstante trägt die
Temperaturkorrektur der Verbrauchsprognose (``wp_tagesfaktor``, seit N-593 aus
Tagesmitteln wie jede andere Gradtag-Rechnung) — dass es bei **einer**
Definition bleibt, hält
``test_berechnungs_layer_konformitaet.py::test_heizgrenze_nur_im_layer`` fest.

⛔ **Der Eingang sind TAGESmittel, nie ein Monatsmittel** (K-2, gemessen).
``max(0; 15 − T)`` ist **konvex**: In einem Übergangsmonat mit Tagen beidseits
der Heizgrenze unterschätzt der Weg über den Monatsmittelwert die Summe — im
Mai 2026 der Demo-Anlage um **−26,6 %** (22,1 statt 30,1 Kd). Ein gepflegter
``Monatsdaten.durchschnittstemperatur`` ist deshalb **keine** Heizgradtag-Quelle;
er bleibt die Ø-Anzeige, die er ist. Den Eingabe-Builder stellt
``services/mitteltemperatur.py::lade_heizgradtage_je_monat``.

⚠ **Ein Monat ohne einen einzigen Temperaturtag fehlt, statt 0 Kd zu sein**
(ADR-002/P4): „keine Messung" und „kein Heizbedarf" sind zwei verschiedene
Aussagen, und die zweite wäre im Januar eine Falschaussage. ``tage_mit_temperatur``
und ``tage_im_monat`` reisen deshalb mit jedem Wert mit — wer sie summiert, sieht
seiner Summe an, wie vollständig sie ist.

⛔ **Kein DB-Zugriff** (ADR-001): reine Formeln über eine übergebene Tagesreihe.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Final, Mapping, Optional, Sequence

#: Heizgrenze in °C — die EINE Definitionsstelle (G-G, 12.09.2026).
#: Unterhalb dieser Außentemperatur wird geheizt (Gradtag-Konvention, DACH).
HEIZGRENZE_C: Final[float] = 15.0

#: Unterhalb dieser Referenz (Kd je Tag der Lernwoche) gilt die Lernwoche als **mild**: die Wärmepumpe lief
#: praktisch nur für Warmwasser (und Kühlen), ein Verhältnis der Heizgradtage liefe gegen unendlich. Die
#: Entscheidung mild/normal steht NUR hier (``_referenz_mild``) — ``wp_tagesfaktor`` und ``wp_strom_skaliert``
#: fragen dieselbe Funktion (N-594).
MILDE_REFERENZ_KD: Final[float] = 1.0
#: Zuschlag je Heizgradtag über der Referenz im milden Zweig (C-F3).
MILDER_ZUSCHLAG_JE_KD: Final[float] = 0.15


def _referenz_mild(referenz_hdd_kd: Optional[float]) -> bool:
    """Ist die Lernwoche mild (Referenz unter ``MILDE_REFERENZ_KD``)? ``None`` ist nicht mild."""
    return referenz_hdd_kd is not None and float(referenz_hdd_kd) < MILDE_REFERENZ_KD


def heizgradtage_tag(tagesmittel_c: float) -> float:
    """Heizgradtage eines Tages: ``max(0; 15 °C − Tagesmittel)``.

    Die Grenze selbst zählt **nicht** mit (15,0 °C ⇒ 0,0 Kd) — ein Tag genau an
    der Heizgrenze hat definitionsgemäß keinen Heizbedarf.
    """
    return max(0.0, HEIZGRENZE_C - float(tagesmittel_c))


def referenz_heizgradtage(
    temperaturen_je_tag: Mapping[object, Sequence[float]],
) -> Optional[float]:
    """Die Heizgradtage der Referenzperiode: **Mittel der Tages-Heizgradtage** (K-2).

    Die Referenzperiode ist die Lernwoche des Verbrauchsprofils (7 volle
    Tage). Je Tag wird das Tagesmittel aus seinen Stundentemperaturen gebildet,
    daraus die Heizgradtage dieses Tages, und über die Tage gemittelt.

    ⛔ **Nicht** die Heizgradtage des Wochenmittels — ``max(0; 15 − T)`` ist
    konvex (Modul-Docstring, K-2): eine Woche mit Tagen beidseits der
    Heizgrenze hat mehr Heizbedarf, als ihr Mittelwert verrät. Derselbe Grund,
    aus dem ein Monatsmittel keine Heizgradtag-Quelle ist.

    Bewusst **ungerundet** — sonst ergäbe ein Prognosetag mit genau dem Wetter
    der Referenzwoche einen Faktor knapp neben 1,0 (Invarianz, N-593).

    Args:
        temperaturen_je_tag: ``{tag: [Stundentemperaturen °C]}``. Ein Tag ohne
            einen einzigen Wert zählt nicht mit.

    Returns:
        Kd je Tag im Mittel, oder ``None``, wenn kein Tag eine Temperatur trägt.
    """
    tages_hdd = [
        heizgradtage_tag(sum(werte) / len(werte))
        for werte in temperaturen_je_tag.values()
        if werte
    ]
    if not tages_hdd:
        return None
    return sum(tages_hdd) / len(tages_hdd)


def wp_tagesfaktor(
    referenz_hdd_kd: Optional[float],
    stunden_temperaturen_c: Sequence[Optional[float]],
) -> float:
    """Skalierungsfaktor für den **Wärmepumpen-Anteil** eines Tagesprofils (N-593).

    **Ein Faktor je Tag, für alle Stunden gleich:** das Verhältnis der
    Heizgradtage des Prognosetags (aus dem **Tagesmittel** seiner
    Stundentemperaturen) zu den Heizgradtagen der Referenzperiode
    (``referenz_heizgradtage``: Mittel der Tages-Heizgradtage). Bei
    Referenz 10 Kd und einem Tag mit Ø 0 °C also ``15 / 10 = 1,5`` — für jede
    Stunde dieses Tages.

    ⛔ **Was hier bis zum 01.10.2026 stand** (``wp_temperatur_faktor``): die
    Heizgradtage **jeder Stunde** gegen die Heizgradtage des **Mittels aller
    Stunden** der Referenzwoche. Das verletzte zweierlei. (1) K-2 — der
    Eingang einer Gradtag-Rechnung sind Tagesmittel, nie Stundenwerte.
    (2) **Invarianz** — bei genau dem Wetter der Referenzwoche muss das
    gelernte Profil unverändert bleiben; die Stundenformel gab bei einem
    Tagesgang 7–17 °C (Ø 12 °C) der 7-°C-Stunde ×2,67 und der 17-°C-Stunde
    ×0,1, verteilte also den Wärmepumpen-Strom bei *unverändertem* Wetter
    in die Nacht um. Der Tagesgang steckt aber schon im gelernten Profil;
    die Korrektur hat nur die Frage „ist dieser Tag kälter als die
    Referenzwoche?" zu beantworten — und die hat je Tag genau eine Antwort.

    ⚠ **Zwei Fälle, und der zweite ist der, an dem eine reine Division
    scheitert.** War die Referenzperiode **mild** (``referenz_hdd_kd < 1``, die
    Wärmepumpe lief praktisch nur für Warmwasser), liefe ein Verhältnis gegen
    unendlich — und hochskalieren ergäbe keinen Sinn, weil im Referenzprofil
    gar kein Heizanteil steckt, den man strecken könnte. Für diesen Fall ein
    sanfter Zuschlag von 15 % je Heizgradtag **über der Referenz**:
    ``1 + max(0; HDD_Tag − HDD_Ref) × 0,15`` (N-594, C-F3). Beides gekappt
    auf ``0,1…3,0``, damit kein Ausreißertag das Profil kippt.

    ⛔ **Bis 04.10.2026 rechnete der milde Zweig ``1 + HDD_Tag × 0,15``** — der
    Zuschlag auf die Heizgradtage des Prognosetags, nicht auf ihre Differenz zur
    Referenz. Das verletzte die Invarianz: bei **unverändertem** Wetter einer
    Lernwoche mit 0,5 Kd stieg der Wärmepumpen-Strom um 7,5 % (9,0 ⇒ 9,64 kWh),
    bei 0,9 Kd um 13,5 % (⇒ 10,18). Mit der Differenz bleibt das gelernte Profil
    bei gleichem Wetter unverändert, wie im normalen Zweig.

    Was der Faktor skaliert, entscheidet ``wp_strom_skaliert`` — nur den Teil
    der Stunde, der von der Außentemperatur abhängt.

    ⭐ **Warum das hier steht und nicht in einem Leser:** Kachel und Live-Kurve
    (``api/routes/live_wetter.py::_berechne_verbrauchsprofil``), die
    WP-Stundenreihe des HA-Exports (``services/verbrauchsprognose_heute.py``,
    gelesen vom P7-Heizfenster) und die Verbrauchsprognose für morgen rechnen
    denselben Heizstrom — zwei Nachbauten hießen zwei Heizstrom-Zahlen unter
    einem Namen (Wächter ``test_heizgrenze_nur_im_layer``).

    Args:
        referenz_hdd_kd: Heizgradtage der Referenzperiode
            (``referenz_heizgradtage``).
        stunden_temperaturen_c: die vorhergesagten Stundentemperaturen **eines**
            Tages; fehlende Werte (``None``) zählen nicht ins Tagesmittel.

    Returns:
        ``1.0``, wenn die Referenz fehlt oder der Tag keine einzige Temperatur
        trägt — dann gibt es nichts zu skalieren, und ein erfundener Faktor
        wäre schlechter als keiner.
    """
    werte = [float(t) for t in stunden_temperaturen_c if t is not None]
    if referenz_hdd_kd is None or not werte:
        return 1.0
    hdd_ref = float(referenz_hdd_kd)
    hdd_tag = heizgradtage_tag(sum(werte) / len(werte))
    if not _referenz_mild(hdd_ref):
        faktor = hdd_tag / hdd_ref
    else:
        faktor = 1.0 + max(0.0, hdd_tag - hdd_ref) * MILDER_ZUSCHLAG_JE_KD
    return max(0.1, min(3.0, faktor))


def wp_strom_skaliert(
    wp_kw: float,
    faktor: float,
    referenz_hdd_kd: Optional[float],
    *,
    warmwasser_kw: float = 0.0,
    kuehlen_kw: float = 0.0,
) -> float:
    """Der Wärmepumpen-Strom EINER Prognosestunde: nur der wetterabhängige Teil wird mit ``faktor`` skaliert (N-594).

    **Regel (C-F1).** Unverändert bleiben gemessenes Warmwasser und Kühlen — beides hängt nicht von den
    Heizgradtagen ab: ein Warmwasser-Zyklus läuft an einem warmen Oktobertag wie an einem kalten, und Kühlstrom
    ist an einem kühleren Tag nicht 30 % höher. Im **milden** Zweig (``referenz_hdd_kd < 1``, C-F3 b) bleibt nur
    das Kühlen fest: eine milde Lernwoche trägt keinen Heizanteil, den der Zuschlag strecken könnte — er wirkt dort
    auf Warmwasser und Rest gemeinsam. **Keine Kühlgrenze** — Kühlen bleibt in jedem Zweig fest, statt an einer
    erfundenen Grenztemperatur zu wachsen.

    ``warmwasser_kw`` und ``kuehlen_kw`` sind **Teilmengen** von ``wp_kw`` (der Lerner bildet sie über denselben
    Nenner); hier noch einmal auf ``wp_kw`` gedeckelt, damit ein Aufrufer mit anderer Herkunft nie mehr festhält, als
    die Stunde trägt.

    Ergebnis ``fest + (wp_kw − fest) × faktor``. Ohne Teilmengen (0, 0) ist das ``wp_kw × faktor`` — bitgleich zur
    Skalierung vor N-594.

    Gemessen (Lernwoche Ø 10 °C, Heizen 7 × 1,0 kWh, Warmwasser 2,0 kWh um 14 Uhr): Übergangstag 16 °C 0,9 ⇒ 2,7
    kWh; kalter Tag 0 °C 27 ⇒ 23 kWh.
    """
    wp = max(0.0, float(wp_kw or 0.0))
    fest = max(0.0, float(kuehlen_kw or 0.0))
    if not _referenz_mild(referenz_hdd_kd):
        fest += max(0.0, float(warmwasser_kw or 0.0))
    fest = min(fest, wp)
    return fest + (wp - fest) * faktor


@dataclass(frozen=True)
class HeizgradtageMonat:
    """Die Heizgradtage eines Kalendermonats — **mit ihrer Vollständigkeit**.

    ``kd`` ist die Σ der Tages-HDD über die Tage, für die eine Temperatur
    vorlag. Wie viele das waren, sagt ``tage_mit_temperatur``; wie viele es
    hätten sein können, ``tage_im_monat``. Ohne dieses Paar wäre ein Monat mit
    zwei erfassten Tagen von einem vollständigen nicht zu unterscheiden — und
    eine Fenster-Summe daraus behauptete eine Abdeckung, die sie nicht hat
    (ADR-002/P4).
    """

    jahr: int
    monat: int
    kd: float
    tage_mit_temperatur: int
    tage_im_monat: int

    @property
    def vollstaendig(self) -> bool:
        """Jeder Kalendertag des Monats trägt eine Temperatur."""
        return self.tage_mit_temperatur >= self.tage_im_monat


def heizgradtage_je_monat(
    je_tag: Mapping[date, float],
) -> dict[tuple[int, int], HeizgradtageMonat]:
    """Σ der Tages-Heizgradtage je Kalendermonat.

    Args:
        je_tag: ``{datum: Tagesmittel °C}`` — Tage ohne Temperaturspur sind
            **nicht enthalten** (so liefert es ``lade_tagesmittel_temperatur``).

    Returns:
        ``{(jahr, monat): HeizgradtageMonat}``. Ein Monat ohne einen einzigen
        Tag **fehlt im Ergebnis** — er ist kein Monat mit 0 Kd.
    """
    summe: dict[tuple[int, int], float] = {}
    tage: dict[tuple[int, int], int] = {}
    for datum, temperatur in je_tag.items():
        schluessel = (datum.year, datum.month)
        summe[schluessel] = summe.get(schluessel, 0.0) + heizgradtage_tag(temperatur)
        tage[schluessel] = tage.get(schluessel, 0) + 1
    return {
        (jahr, monat): HeizgradtageMonat(
            jahr=jahr,
            monat=monat,
            kd=round(summe[(jahr, monat)], 1),
            tage_mit_temperatur=tage[(jahr, monat)],
            tage_im_monat=calendar.monthrange(jahr, monat)[1],
        )
        for (jahr, monat) in sorted(summe)
    }


#: Es gibt überhaupt keine Temperaturspur — die Normierung hat keinen Nenner.
GRUND_KEINE_TEMPERATURREIHE: Final[str] = (
    "Für diesen Zeitraum liegt keine gemessene Außentemperatur vor — "
    "ohne sie gibt es keine Heizgradtage."
)


def heizgradtage_grund(
    je_monat: Mapping[tuple[int, int], HeizgradtageMonat],
    *,
    erster_monat_mit_bedarf: Optional[tuple[int, int]] = None,
) -> Optional[str]:
    """Warum die Wetternormierung weniger zeigt als die Sicht daneben (S3).

    ⭐ **Der Fall, für den es diesen Satz gibt** (gemessen an der Demo-Anlage):
    Winter 24/25 hat **vollständige** Wärmepumpen-Daten — vier von vier Monaten,
    1.215 kWh Heizstrom, im Strom-Modus sichtbar — und trotzdem keinen
    normierten Balken. Es fehlt die **Außentemperatur**, nicht die Wärmepumpe.
    Ohne den Satz liest der Anwender „eedc hat meine Daten von 2024 verloren".

    Args:
        je_monat: das Ergebnis von {@link heizgradtage_je_monat}.
        erster_monat_mit_bedarf: ältester ``(jahr, monat)``, für den es
            überhaupt Verbrauchszeilen gibt. ``None`` ⇒ es gibt nichts zu
            vergleichen, dann bleibt auch der Satz aus.

    Returns:
        Der Grund, oder ``None``, wenn die Temperaturreihe so weit zurückreicht
        wie die Verbrauchshistorie.
    """
    if not je_monat:
        return GRUND_KEINE_TEMPERATURREIHE
    if erster_monat_mit_bedarf is None:
        return None
    erster_mit_temperatur = min(je_monat)
    if erster_mit_temperatur <= erster_monat_mit_bedarf:
        return None
    jahr, monat = erster_mit_temperatur
    return (
        "Für ältere Zeiträume liegt keine gemessene Außentemperatur vor — "
        f"die Messreihe beginnt mit {monat:02d}/{jahr}."
    )


def normiert(
    menge_kwh: Optional[float],
    kd: Optional[float],
) -> Optional[float]:
    """Die wetternormierte Größe: Menge je Heizgradtag (kWh/Kd).

    ``None``, sobald eine Seite fehlt **oder** ``kd <= 0`` — nie ∞ und nie 0.
    Ein Sommerfenster hat keine Heizgradtage; dort ist die Normierung nicht
    „null je Kältegrad", sondern **ohne Aussage**, und die Anzeige nennt den
    Grund (SOLL §3.3/S3) statt einen Balken zu zeichnen.
    """
    if menge_kwh is None or kd is None or kd <= 0:
        return None
    return menge_kwh / kd
