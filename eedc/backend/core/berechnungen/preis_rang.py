"""Börsenpreis-Rang-Berechnung für den HA-Export (#150 Slice B).

Reine Rang-Logik (Berechnungs-Layer, ADR-001): bewertet die stündlichen
Day-Ahead-Börsenpreise eines Tages und ordnet jeder Stunde einen Rang zu.

Tag- und Nacht-Fenster werden **getrennt** bewertet (je eigenes 1–5/99-Ranking).
Welche Stunden zum Tag- bzw. Nacht-Fenster gehören, entscheidet der Aufrufer
solar-basiert (Sonnenauf-/-untergang); diese Funktion ist davon unabhängig und
rein deterministisch testbar.

„Günstig" heißt seit Rainer-PN 2026-06-11: mindestens 10 % unter dem
Tagesdurchschnitt ohne die 3 Peak-Stunden. Ohne diese Schwelle waren die Top-5
rein relativ — die „günstige Stunden"-Anzahl stand praktisch konstant auf 10,
und ein erzwungener Verbrauch / eine Netzladung in einer „günstigen", aber
kaum billigeren Stunde ergibt keinen Sinn.

**Rang und „günstig" sind getrennt (ab v4.0.10, #335/N-103):** Der Rang bleibt die
Anzeige-Größe „eine der fünf billigsten Stunden dieses Fensters"; gezählt wird
als günstig dagegen **jede** Stunde unter der Schwelle. Vorher zählte auch die
Anzahl nur die Ränge und war damit bei 5 gedeckelt — als Divisor in einer
Automation zu klein. Ohne Schwelle (0 % je Anlage) fallen beide zusammen.

eedc liefert damit nur einen **Trigger-Wert** — keine Lade-/Entlade-Strategie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

# Maximal die fünf günstigsten Stunden je Fenster bekommen Rang 1–5
# (1 = billigste), alle übrigen Rang 99 (teuer/Rest).
GUENSTIG_TOP_N = 5
RANG_TEUER = 99

# Günstig-Schwelle: Preis muss ≥10 % unter dem Durchschnitt der Tagespreise
# ohne die PEAK_AUSSCHLUSS_N teuersten Stunden liegen (Rainer-Definition:
# „24 Tagespreise minus 3 Peakpreise, aus den verbleibenden 21 den
# Durchschnitt, günstig = 10 % darunter"). Der Faktor ist der DEFAULT —
# pro Anlage einstellbar (Anlage.guenstig_schwelle_prozent, Folge-Wunsch
# 2026-06-11: z. B. Ø×0,925), die Aufrufer reichen ihn durch.
GUENSTIG_SCHWELLE_FAKTOR = 0.90
PEAK_AUSSCHLUSS_N = 3


@dataclass
class PreisRangErgebnis:
    """Ergebnis der Rang-Bewertung eines Tages."""

    rang_aktuell: Optional[int]                 # Rang der aktuellen Stunde (1–5 oder 99); None wenn kein Preis
    guenstige_stunden_anzahl: int               # Σ als günstig markierter Stunden über beide Fenster
    rang_profil: dict[int, int] = field(default_factory=dict)  # {stunde: rang} aller bewerteten Stunden
    guenstige_stunden_tag: int = 0              # günstige Stunden im Tag-Fenster
    guenstige_stunden_nacht: int = 0            # günstige Stunden im Nacht-Fenster
    schwelle_cent: Optional[float] = None       # Günstig-Schwelle (ct/kWh); None wenn zu wenige Preise
    # ── ab v4.0.10 (#335, rapahl-PN 2026-08-05) ───────────────────────────────
    unter_schwelle_profil: dict[int, bool] = field(default_factory=dict)  # {stunde: günstig?} — UNGEKAPPT
    preis_aktuell_cent: Optional[float] = None          # Preis der aktuellen Stunde
    optimierter_durchschnitt_cent: Optional[float] = None  # Ø ohne die 3 Peaks (Bezugsgröße der Schwelle)
    tages_durchschnitt_cent: Optional[float] = None     # schlichter Ø ALLER Stunden (rapahl-PN 23.08.)
    abstand_prozent: Optional[float] = None             # Abstand des aktuellen Preises zum Ø, negativ = billiger
    abstand_cent: Optional[float] = None                # derselbe Abstand in ct/kWh — aufschlags-invariant (N-173)


def tages_durchschnitt(
    preise_nach_stunde: Mapping[int, Optional[float]],
) -> Optional[float]:
    """Schlichter Ø **aller** Tagespreise — ohne jeden Ausschluss.

    **Warum es das braucht, obwohl direkt darunter schon ein Ø steht**
    (rapahl-PN 2026-08-23): Der Kennzahlenblock trug bis dahin drei Größen, die
    alle auf ``optimierter_durchschnitt`` zeigen — „Ø ohne 3 Peaks", die
    „Günstig-Schwelle" und den „Abstand zum Ø". Der **gewöhnliche**
    Tagesdurchschnitt, nach dem jeder zuerst fragt, existierte im Code gar
    nicht. Rainers Punkt dazu, wörtlich: *„Nicht jeder will ja seinen Akku mit
    Netzstrom laden."*

    ⚠ **Das ist kein Widerspruch zum optimierten Ø und ersetzt ihn nicht.**
    Jener ist die Bezugsgröße der Günstig-Schwelle und stammt aus Rainers
    eigener Definition (#335) — er bleibt, wo er ist. Die beiden beantworten
    verschiedene Fragen: *„Was kostet der Strom heute im Mittel?"* gegen
    *„Ab wann lohnt das Laden?"*

    Returns ``None``, wenn kein einziger Preis vorliegt.
    """
    werte = [p for p in preise_nach_stunde.values() if p is not None]
    return sum(werte) / len(werte) if werte else None


def optimierter_durchschnitt(
    preise_nach_stunde: Mapping[int, Optional[float]],
) -> Optional[float]:
    """Ø der Tagespreise ohne die ``PEAK_AUSSCHLUSS_N`` teuersten Stunden.

    Rainers „optimierter Durchschnitt": 24 Tagespreise minus 3 Peakpreise, aus
    den verbleibenden 21 der Mittelwert. Das ist die **Bezugsgröße** der
    Günstig-Schwelle — bis v4.0 verließ nur ``Ø × faktor`` diese Datei, der Ø
    selbst wurde weggeworfen und war damit auch im HA-Export unerreichbar
    (#335).

    Returns ``None``, wenn nach Peak-Ausschluss keine Basis bleibt (weniger
    als ``PEAK_AUSSCHLUSS_N + 1`` Preise).
    """
    werte = sorted(p for p in preise_nach_stunde.values() if p is not None)
    if len(werte) <= PEAK_AUSSCHLUSS_N:
        return None
    basis = werte[:-PEAK_AUSSCHLUSS_N]
    return sum(basis) / len(basis)


def guenstig_schwelle(
    preise_nach_stunde: Mapping[int, Optional[float]],
    faktor: float = GUENSTIG_SCHWELLE_FAKTOR,
) -> Optional[float]:
    """Günstig-Schwelle des Tages: Ø der Preise ohne die 3 Peaks × ``faktor``.

    Returns ``None``, wenn keine Ø-Basis zustande kommt — dann greift keine
    Schwelle.
    """
    durchschnitt = optimierter_durchschnitt(preise_nach_stunde)
    return None if durchschnitt is None else durchschnitt * faktor


def abstand_zum_durchschnitt_prozent(
    preis: Optional[float],
    durchschnitt: Optional[float],
) -> Optional[float]:
    """Abstand eines Preises zum optimierten Ø in Prozent — negativ = billiger.

    Bezugsgröße ist der **Betrag** des Ø, nicht der Ø selbst: Day-Ahead-Preise
    werden regelmäßig negativ, und ``(preis − Ø) / Ø`` kippt dort das
    Vorzeichen — −5 ct gegen einen Ø von −10 ct ist teurer, ergäbe mit dem
    vorzeichenbehafteten Nenner aber −50 % und damit die Aussage „billiger".
    Bei einem Ø von genau 0 gibt es keinen relativen Abstand ⇒ ``None``.
    """
    if preis is None or durchschnitt is None or durchschnitt == 0:
        return None
    return (preis - durchschnitt) / abs(durchschnitt) * 100.0


def abstand_zum_durchschnitt_cent(
    preis: Optional[float],
    durchschnitt: Optional[float],
) -> Optional[float]:
    """Abstand eines Preises zum optimierten Ø in ct/kWh — negativ = billiger.

    **Warum es diese Größe neben der prozentualen gibt (N-173, rapahl-PN
    2026-08-11):** Wer einen dynamischen Tarif bezieht, zahlt nicht den
    Börsenpreis, sondern Börsenpreis **plus** feste Bestandteile (Netzentgelt,
    Abgaben, Marge). Ein solcher Aufschlag verschiebt jeden Stundenpreis **und**
    den Ø um denselben Betrag — die Differenz bleibt damit exakt gleich, der
    Prozentwert nicht (sein Nenner wächst mit). An Rainers eigenen Zahlen:
    die billigste Stunde liegt auf der Börsenkurve wie auf seiner Realpreis-
    kurve **−9,93 ct** unter dem Ø, während die Prozentangabe von −100,1 % auf
    −33,2 % springt. Eine Prozentzahl, die für beide Welten dasselbe bedeutet,
    kann es folglich nicht geben; diese Größe braucht dafür **kein**
    Eingabefeld für den festen Anteil und keine Konfiguration.

    ``abstand_prozent`` bleibt unverändert daneben stehen — er ist seit v4.0.10
    als Sensor ausgeliefert, und fremde Automationen hängen an seinen Schwellen.
    """
    if preis is None or durchschnitt is None:
        return None
    return preis - durchschnitt


def _bewerte_fenster(
    preise_nach_stunde: Mapping[int, Optional[float]],
    stunden: Iterable[int],
    schwelle: Optional[float],
) -> tuple[dict[int, int], dict[int, bool]]:
    """Rangfolge **und** Günstig-Markierung innerhalb eines Fensters.

    Die beiden Größen sind bewusst getrennt (#335/N-103):

    * **Rang** — die Anzeige-Größe „eine der fünf billigsten Stunden dieses
      Fensters": höchstens ``GUENSTIG_TOP_N`` bekommen 1–N, und nur solange
      ihr Preis die Schwelle unterschreitet.
    * **Günstig** — jede Stunde unter der Schwelle, **ohne** Top-5-Deckel.
      Bis v4.0.9 zählte auch diese Größe nur die Ränge: lagen sieben
      Nachtstunden unter der Schwelle, meldete der Sensor fünf. Als Anzeige
      stimmig, als **Divisor** in einer Automation zu klein — eine daraus
      gerechnete Ladeleistung fiel zu hoch aus.

    Ohne Schwelle (0 % je Anlage oder zu wenige Preise) fallen beide zusammen:
    dann greift wieder allein die Rang-Regel.

    Nur Stunden mit vorhandenem Preis werden bewertet.
    """
    vorhanden = [
        (h, preise_nach_stunde[h])
        for h in stunden
        if h in preise_nach_stunde and preise_nach_stunde[h] is not None
    ]
    # Sekundärschlüssel Stunde: stabile, reproduzierbare Reihenfolge bei Preisgleichheit.
    sortiert = sorted(vorhanden, key=lambda x: (x[1], x[0]))
    raenge: dict[int, int] = {}
    guenstig: dict[int, bool] = {}
    for idx, (h, preis) in enumerate(sortiert):
        unter_schwelle = schwelle is None or preis <= schwelle
        in_top_n = idx < GUENSTIG_TOP_N
        raenge[h] = (idx + 1) if (in_top_n and unter_schwelle) else RANG_TEUER
        guenstig[h] = unter_schwelle if schwelle is not None else in_top_n
    return raenge, guenstig


def berechne_preis_rang(
    preise_nach_stunde: Mapping[int, Optional[float]],
    tag_stunden: Iterable[int],
    nacht_stunden: Iterable[int],
    aktuelle_stunde: int,
    schwelle_faktor: float = GUENSTIG_SCHWELLE_FAKTOR,
) -> PreisRangErgebnis:
    """Bewertet Tag- und Nacht-Fenster getrennt und liest den Rang der aktuellen Stunde.

    Die Günstig-Schwelle wird über ALLE Tagespreise gebildet (nicht je
    Fenster), das Ranking selbst bleibt fensterweise.

    Args:
        preise_nach_stunde: {Stunde 0–23: Börsenpreis ct/kWh}.
        tag_stunden: Stunden des Tag-Fensters (Sonnenauf→-untergang).
        nacht_stunden: Stunden des Nacht-Fensters.
        aktuelle_stunde: Stunde, deren Rang als ``rang_aktuell`` zurückkommt.
        schwelle_faktor: Günstig-Faktor auf den Ø-ohne-Peaks (Default 0,90 =
            10 % darunter; pro Anlage einstellbar).

    Returns:
        PreisRangErgebnis (rang_aktuell, günstige-Stunden-Anzahl gesamt /
        Tag / Nacht, Schwelle, Rang- und Günstig-Profil je Stunde, dazu der
        aktuelle Preis, der optimierte Ø und ihr Abstand zueinander).
    """
    durchschnitt = optimierter_durchschnitt(preise_nach_stunde)
    tages_mittel = tages_durchschnitt(preise_nach_stunde)
    schwelle = None if durchschnitt is None else durchschnitt * schwelle_faktor

    tag_raenge, tag_guenstig = _bewerte_fenster(preise_nach_stunde, tag_stunden, schwelle)
    nacht_raenge, nacht_guenstig = _bewerte_fenster(preise_nach_stunde, nacht_stunden, schwelle)
    raenge: dict[int, int] = {**tag_raenge, **nacht_raenge}

    guenstig_tag = sum(1 for g in tag_guenstig.values() if g)
    guenstig_nacht = sum(1 for g in nacht_guenstig.values() if g)
    preis_aktuell = preise_nach_stunde.get(aktuelle_stunde)
    return PreisRangErgebnis(
        rang_aktuell=raenge.get(aktuelle_stunde),
        guenstige_stunden_anzahl=guenstig_tag + guenstig_nacht,
        rang_profil=raenge,
        guenstige_stunden_tag=guenstig_tag,
        guenstige_stunden_nacht=guenstig_nacht,
        schwelle_cent=round(schwelle, 3) if schwelle is not None else None,
        unter_schwelle_profil={**tag_guenstig, **nacht_guenstig},
        preis_aktuell_cent=preis_aktuell,
        # Auf drei Stellen wie `schwelle_cent`: derselbe Größenart-Kanon, und
        # der Wert reist zugleich als Attribut mit. Die Ausgabe-Rundung macht
        # `runde_exportwert` an der Serialisierungsgrenze (2 Stellen je ct/kWh).
        optimierter_durchschnitt_cent=round(durchschnitt, 3) if durchschnitt is not None else None,
        # Dieselbe Drei-Stellen-Rundung wie jede andere ct/kWh-Größe hier.
        tages_durchschnitt_cent=round(tages_mittel, 3) if tages_mittel is not None else None,
        abstand_prozent=abstand_zum_durchschnitt_prozent(preis_aktuell, durchschnitt),
        # Aus dem UNGERUNDETEN Ø gebildet wie `abstand_prozent` (sonst driften
        # die beiden Größen gegeneinander), erst danach auf drei Stellen wie
        # jede andere ct/kWh-Größe dieser Datei.
        abstand_cent=(
            None
            if (roh := abstand_zum_durchschnitt_cent(preis_aktuell, durchschnitt)) is None
            else round(roh, 3)
        ),
    )
