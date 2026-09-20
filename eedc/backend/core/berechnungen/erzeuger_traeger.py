"""Wer trägt seine PV-Erzeugungsgrößen selbst? — der Selektor vor jeder Σ.

**Der Anlass (N-266).** Seit dieser Etappe darf ein `balkonkraftwerk` Parent von
`pv-module` sein — der Weg, auf dem ein BKW mit zwei Modulen über Eck endlich
zwei Ausrichtungen tragen kann (Melder: azywietz-web in Discussion #366, Daniel
in Forum T89667 #172/#175). Damit entsteht zum ersten Mal ein Zustand, in dem
**Eltern und Kind im selben Typ-Filter** liegen: die Menge
``PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")`` wird baumweit an rund
zwanzig Stellen gebildet und **flach summiert**. Bisher zählte dort nichts
doppelt, *weil* PV-Module unter einem `wechselrichter` hängen — und der ist kein
PV-Erzeuger-Typ. Unter einem BKW wären beide in derselben Menge.

**Die Regel in einem Satz:** Ein Balkonkraftwerk mit `pv-module`-Kindern **in der
übergebenen Menge** tritt seine Erzeugungsgrößen an die Kinder ab und fällt hier
heraus; ohne Kinder trägt es sie weiter selbst.

**Drei Größen, eine Bedingung — deshalb EIN Selektor und nicht drei.** Der
Arbeitsname des Auftrags war ``kwp_traeger``, aus der Zeit, als nur die
kWp-Achse bekannt war. Die Vollerhebung (E0) hat gezeigt, dass dieselbe
Abtretung drei Größen betrifft, und zwar immer gemeinsam:

1. **kWp** — Nennleistung (``get_erzeuger_kwp``). Zählt sie doppelt, halbiert
   sich der spezifische Ertrag, und die drei Verteilungsnenner in
   ``cockpit/pv_strings.py`` / ``pdf/jahresbericht.py`` geben jedem String zu
   wenig SOLL.
2. **Erzeugung** — ``pv_erzeugung_kwh`` je Monat. Zählt sie doppelt, sind
   Autarkie, Eigenverbrauchsquote, CO₂, Finanzen, Community-Payload und
   HA-Export betroffen (``monats_fakten/``: ``pv_kwh = pv_modul_summe +
   bkw_erzeugung``).
3. **Ausrichtung/Neigung** — der Fan-out der Prognose gruppiert danach
   (``pv_orientation.orientierungs_gruppen``). Bliebe das BKW drin, brächte es
   seine EINE Ausrichtung als eigene Gruppe mit — also genau die Zahl, die der
   Melder loswerden wollte, zusätzlich zu den Kindern.

Ein Selektor, der nur die kWp kennte, hätte die Energie-Achse offengelassen; ein
zu eng benannter SoT ist eine Klasse, die dieses Projekt mehrfach eingeholt hat
(vgl. ``KUMULATIVE_ZAEHLER_FELDER`` in N-259).

**Was das BKW NICHT abtritt: seine AC-Grenze.** Die 800 VA sind eine Eigenschaft
des Wechselrichters, nicht der Module — sie ergeben sich gerade *nicht* aus den
Kindern. Das BKW bleibt Träger seiner Grenze, und die Kinder teilen sie sich
über ``wr_kappung.zuordne_grenzen`` (dieselbe Rolle, die ein `wechselrichter`
für seine Strings hat). Zwei unabhängige Grenzen — 800 VA AC am
Wechselrichter-Ausgang, 2.000 Wp DC an den Modulen — und nur die zweite wächst
mit den Kindern.

**Warum die Signatur auf der MENGE steht und nicht auf ``inv``.** ``children``
ist ein Lazy-Backref (``models/investition.py``); ein Helper ``f(inv)`` liefe in
async SQLAlchemy auf ``MissingGreenlet``. ``parent_investition_id`` ist dagegen
eine **Spalte**, und jede Σ-Stelle hat die Menge bereits geladen (gemessen an
``prognosen.py::_lade_anlage_mit_pv`` und ``cockpit/pv_strings.py``, die beide
Typen in EINER Query holen). Eltern-Kind ist damit **innerhalb der übergebenen
Menge** vollständig auflösbar — ohne einen einzigen Lazy-Zugriff. Genau die
Bauform, die P10 mit den Monats-Fakten gewählt hat.

**Grenze, und sie ist wichtig:** „in der übergebenen Menge" ist keine
Nachlässigkeit, sondern die einzige Aussage, die dieser Selektor überhaupt
treffen kann. Wer eine Teilmenge übergibt (etwa nur die Geschwister *eines*
Wechselrichters), bekommt eine Antwort über diese Teilmenge. Deshalb ist die
Bedingung so gewählt, dass die Teilmenge in die **sichere** Richtung irrt: ohne
sichtbare Kinder trägt das BKW seine Größen selbst — also so, wie es sich vor
dieser Etappe verhalten hat.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

BKW_TYP = "balkonkraftwerk"
PV_MODUL_TYP = "pv-module"


def abgetretene_bkw_ids(investitionen: Sequence[Any]) -> frozenset:
    """IDs der Balkonkraftwerke, die ihre Erzeugungsgrößen abgetreten haben.

    Abgetreten heißt: in ``investitionen`` steht mindestens ein `pv-module`,
    dessen ``parent_investition_id`` auf dieses BKW zeigt.

    Bewusst **ohne** Aktiv-/Datumsfilter: die Abtretung ist eine Aussage über
    die *Struktur*, nicht über einen Zeitraum. Wer im Monat 03/2025 rechnet,
    filtert seine Menge vorher — dann ist ein erst später angeschafftes Modul
    gar nicht dabei und das BKW trägt seine Größen für diesen Monat noch selbst.
    Genau so soll es sein, und genau deshalb steht der Filter beim Aufrufer.
    """
    return frozenset(
        parent_id
        for inv in investitionen or ()
        if getattr(inv, "typ", None) == PV_MODUL_TYP
        and (parent_id := getattr(inv, "parent_investition_id", None)) is not None
    ) & frozenset(
        inv_id
        for inv in investitionen or ()
        if getattr(inv, "typ", None) == BKW_TYP
        and (inv_id := getattr(inv, "id", None)) is not None
    )


def traegt_erzeugungsgroessen_selbst(inv: Any, investitionen: Sequence[Any]) -> bool:
    """Trägt ``inv`` seine kWp/Erzeugung/Ausrichtung selbst?

    ``True`` für alles außer einem Balkonkraftwerk mit sichtbaren
    `pv-module`-Kindern. Für den Einzelfall gedacht (eine Anzeige, ein
    Daten-Checker-Zweig); wer eine Summe bildet, nimmt ``erzeuger_traeger``.
    """
    if getattr(inv, "typ", None) != BKW_TYP:
        return True
    inv_id = getattr(inv, "id", None)
    return inv_id is None or inv_id not in abgetretene_bkw_ids(investitionen)


def erzeuger_traeger(investitionen: Sequence[Any]) -> list:
    """Die Menge ohne die Balkonkraftwerke, die ihre Größen abgetreten haben.

    **Der Drop-in für jede Σ-Stelle.** Reihenfolge und alle übrigen Einträge
    bleiben unverändert — auch Typen, die gar keine Erzeuger sind. Das ist
    Absicht: die Σ-Stellen filtern Typ und Zeitraum selbst (und tun das
    unterschiedlich), und ein Selektor, der ihnen ihren Filter abnimmt, würde
    an jeder von ihnen etwas anderes ändern als die Abtretung.

    Ohne ein einziges abtretendes BKW ist das Ergebnis eine Kopie der Eingabe —
    für jede Bestandsanlage bleibt die Rechnung damit **bitgleich** zu vorher.
    """
    abgetreten = abgetretene_bkw_ids(investitionen)
    if not abgetreten:
        return list(investitionen or ())
    return [
        inv for inv in investitionen
        if not (
            getattr(inv, "typ", None) == BKW_TYP
            and getattr(inv, "id", None) in abgetreten
        )
    ]


def modul_kinder(bkw_id: Any, investitionen: Sequence[Any]) -> list:
    """Die `pv-module` aus ``investitionen``, die an ``bkw_id`` hängen.

    Gegenstück zu ``abgetretene_bkw_ids`` für die Energie-Achse: dort füllt der
    BKW-Monatswert die **Lücken seiner Kinder** (P7-Leserichtung), und dafür
    braucht der Aufrufer die Kinder namentlich, nicht nur die Elternschaft.
    """
    if bkw_id is None:
        return []
    return [
        inv for inv in investitionen or ()
        if getattr(inv, "typ", None) == PV_MODUL_TYP
        and getattr(inv, "parent_investition_id", None) == bkw_id
    ]



def bkw_restwerte(
    investitionen: Sequence[Any],
    werte_je_inv: Any,
) -> dict[str, float]:
    """Je abtretendem Balkonkraftwerk: der **Rest**, den es noch selbst trägt.

    ``werte_je_inv`` bildet ``str(inv.id)`` auf eine gemessene Größe ab —
    Momentanleistung in W, Tagesenergie in kWh, Slot-Delta. Die Einheit ist der
    Funktion gleich; sie rechnet nur ``Wert − Σ Werte der Kinder``.

    **Die Regel (N-536).** Ein Balkonkraftwerk mit `pv-module`-Kindern ist
    Träger wie ein Wechselrichter: seine Kinder tragen die Erzeugung. Ohne
    Lücke bei ihnen trägt es **nichts** mehr (Rest 0); mit Lücke trägt es genau
    das, was seine Kinder nicht messen. Ohne Kinderwerte ist der Rest sein
    ganzer Wert — dann ändert sich gegenüber vorher nichts, und genau darauf
    beruht der Kern der P11-Ausnahme 4b: der Wechselrichter eines
    Balkonkraftwerks ist bei den meisten Anlagen die EINZIGE Live-Quelle.

    ⛔ **Der Rest wird hier NICHT verteilt.** Die kWp-Gewichtung ist eine
    Tages-Aussage (``snapshot/komponenten_beitraege``: über einen Tag mittelt
    sich Ost/West aus, über eine Stunde nicht). Wer einen Momentan- oder
    Stundenwert kWp-gewichtet auf die Kinder legt, erfindet Messwerte. Auf der
    Tages- und Monatsachse verteilt ``resolve_pv_je_modul`` ihn — mit
    demselben Rest als Eingang.

    Negativ wird der Rest nie: messen die Kinder zusammen mehr als ihr
    Balkonkraftwerk (verschiedene Abtastzeitpunkte, Messrauschen), ist der Rest
    ``0.0`` — dieselbe Klemmung wie in ``pv_verteilung.resolve_pv_je_modul``.

    Ein Balkonkraftwerk **ohne** eigenen Wert steht nicht im Ergebnis: es gibt
    nichts zu kürzen, und ``0.0`` wäre eine Aussage über eine Messung, die es
    nicht gibt (``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``).
    """
    abgetreten = abgetretene_bkw_ids(investitionen)
    if not abgetreten:
        return {}
    out: dict[str, float] = {}
    for bkw_id in abgetreten:
        eigen = werte_je_inv.get(str(bkw_id))
        if eigen is None:
            continue
        kinder_summe = 0.0
        for kind in modul_kinder(bkw_id, investitionen):
            wert = werte_je_inv.get(str(getattr(kind, "id", None)))
            if wert is not None:
                kinder_summe += float(wert)
        out[str(bkw_id)] = max(0.0, float(eigen) - kinder_summe)
    return out


def bkw_kinder_decken_vollstaendig(
    investitionen: Sequence[Any],
    hat_wert: Any,
) -> frozenset:
    """IDs der abtretenden BKW, deren Kinder **alle** eine eigene Quelle haben.

    Für die Stellen, die keine Werte kennen, sondern nur Zuordnungen — die
    Entity-Sammler des Live-Pfads. Dort ist die Frage nicht „wie groß ist der
    Rest", sondern „darf die Entity des Balkonkraftwerks überhaupt in die
    Summe". Sie darf genau dann nicht, wenn jedes Kind selbst misst.

    ``hat_wert`` ist ein Prädikat über ``str(inv.id)``. Ein abtretendes BKW
    **ohne** Kinder mit eigener Quelle bleibt drin — sonst verlöre die Anlage
    ihre einzige Messung.
    """
    abgetreten = abgetretene_bkw_ids(investitionen)
    if not abgetreten:
        return frozenset()
    voll = set()
    for bkw_id in abgetreten:
        kinder = modul_kinder(bkw_id, investitionen)
        if kinder and all(hat_wert(str(getattr(k, "id", None))) for k in kinder):
            voll.add(str(bkw_id))
    return frozenset(voll)


def kuerze_bkw_in_werte_map(
    werte: Any,
    investitionen: Sequence[Any],
    *,
    praefixe: Optional[Sequence[str]] = None,
) -> dict:
    """Kürzt in einer Komponenten-Map jedes abtretende BKW auf seinen Rest.

    Für die Stellen, die ihre Erzeugung als ``{"<praefix><id>": wert}`` führen —
    der Live-Keyspace (``pv_<id>`` für ALLE Erzeuger, auch Balkonkraftwerke),
    der MQTT-Pfad und der Boundary-Keyspace (``pv_<id>`` · ``bkw_<id>``). Beide
    Keyspaces gleichzeitig zu bedienen ist Absicht: dieselbe Investition trägt
    je nach Schreibpfad ein anderes Präfix, und genau dieser Mismatch war der
    BKW-Doppelzählungs-Bug vom 2026-05-19 (``energie.py``, Rainer-PN).

    Der Rest kommt aus ``bkw_restwerte`` — dieselbe Regel, dieselbe Klemmung.
    Ist er 0, **fällt der Key heraus**: er behauptete sonst eine Messung von 0,
    wo das Gerät nur nichts mehr beizutragen hat. Keys ohne numerische ID
    (``pv_gesamt``) bleiben unberührt; die Wahl zwischen Anlagen-Aggregat und
    Einzelwerten trifft eine andere Schicht.

    ⛔ **Kein Verteilen.** Der Rest bleibt beim Balkonkraftwerk. Auf der
    Tages- und Monatsachse übernimmt ``resolve_pv_je_modul`` ihn als Aggregat
    seiner Kinder und verteilt ihn kWp-gewichtet — dort, und nur dort, ist die
    kWp-Gewichtung eine zulässige Aussage.
    """
    # Die Präfix-Whitelist ist der Layer-SoT (ADR-001, `energie.py`) — sie hier
    # als Literal zu wiederholen ist genau die Drift, die
    # `test_pv_bkw_whitelist_tuple_nur_im_layer` verbietet. Lokaler Import wie
    # bei `bkw_kwp_aus_kindern`: dieses Modul kettet sich nicht an ein zweites.
    if praefixe is None:
        from backend.core.berechnungen.energie import PV_KOMPONENTEN_PREFIXE

        praefixe = PV_KOMPONENTEN_PREFIXE
    if not werte:
        return dict(werte or {})

    def _id_aus_key(key: str) -> Optional[str]:
        for p in praefixe:
            if key.startswith(p):
                rest = key[len(p):]
                if rest.isdigit():
                    return rest
        return None

    werte_je_inv: dict[str, float] = {}
    key_je_inv: dict[str, str] = {}
    for key, wert in werte.items():
        inv_id = _id_aus_key(str(key))
        if inv_id is None or not isinstance(wert, (int, float)):
            continue
        werte_je_inv[inv_id] = werte_je_inv.get(inv_id, 0.0) + float(wert)
        key_je_inv[inv_id] = str(key)

    reste = bkw_restwerte(investitionen, werte_je_inv)
    if not reste:
        return dict(werte)

    out = dict(werte)
    for inv_id, rest in reste.items():
        key = key_je_inv.get(inv_id)
        if key is None:
            continue
        if rest > 0:
            out[key] = rest
        else:
            out.pop(key, None)
    return out


def ergaenze_kinder_deckung(
    gedeckte_ids: Any,
    investitionen: Sequence[Any],
) -> set:
    """Ein Kind gilt als gedeckt, wenn es selbst **oder** sein BKW liefert.

    Die Deckungsfrage der Stundenachse (``pv_tages_praezedenz.einzel_deckt_den_tag``)
    lautet „tragen die Einzelzähler den ganzen Tag?". Sie ist auf der **Träger**-
    Ebene zu stellen, seit ein Balkonkraftwerk Kinder haben kann: Sein Zähler
    misst dieselbe Energie wie sie. Ohne diese Ergänzung fiele eine Anlage mit
    BKW-Zähler und Modul-Kindern ohne eigene Zähler dauerhaft auf das
    Anlagen-Aggregat zurück — oder, wenn es keines gibt, auf eine Teilsumme.

    ⚠ Sie ergänzt nur, sie streicht nie: ein Kind mit eigenem Zähler bleibt
    gedeckt, auch wenn sein Balkonkraftwerk in dieser Stunde nichts liefert.
    """
    gedeckt = set(gedeckte_ids or ())
    for bkw_id in abgetretene_bkw_ids(investitionen):
        if str(bkw_id) not in gedeckt:
            continue
        for kind in modul_kinder(bkw_id, investitionen):
            kind_id = getattr(kind, "id", None)
            if kind_id is not None:
                gedeckt.add(str(kind_id))
    return gedeckt

def bkw_kwp_aus_kindern(bkw: Any, investitionen: Sequence[Any]) -> Optional[float]:
    """Σ kWp der Modul-Kinder — oder ``None``, wenn das BKW nichts abgetreten hat.

    Gernots Entscheid vom 17.08.2026: *„das BKW leitet aus den Kindern ab, damit
    kein Zustand entsteht, in dem zwei Zahlen dasselbe behaupten."* ``None``
    heißt „nicht abgeleitet, die eigene Pflege gilt" — die 0-Werte-Falle
    umgekehrt: ein BKW *mit* Kindern, die alle 0 kWp tragen, liefert hier
    ``0.0`` und nicht ``None``.
    """
    # Import lokal: `investition_kennwerte` importiert nichts aus `berechnungen`,
    # aber der Layer-Wächter (ADR-001) prüft die Importrichtung, und ein
    # Modul-Import würde diesen Selektor an den Kennwert-SoT ketten, obwohl
    # jede andere Funktion hier ohne ihn auskommt.
    from backend.core.investition_kennwerte import get_erzeuger_kwp

    kinder = modul_kinder(getattr(bkw, "id", None), investitionen)
    if not kinder:
        return None
    return sum(get_erzeuger_kwp(k) for k in kinder)
