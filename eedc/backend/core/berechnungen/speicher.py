"""Speicher-Aggregate — Effizienz aus InvestitionMonatsdaten.

Single Source of Truth für die Speicher-Round-Trip-Effizienz.

Round-Trip-Effizienz η = Entladung / Ladung ist nur über ein geschlossenes
Fenster sinnvoll: Ein Akku ist ein *Speicher* (Bestand), Monats-Ladung und
-Entladung sind *Flüsse*. Über eine einzelne Monatsgrenze trägt der SoC einen
Übertrag — ein Monat kann legitim mehr ent- als laden, weil gespeicherte
Energie aus dem Vormonat abfließt (Carry-over). Eine naive Pro-Monats-
Effizienz zappelt dadurch und kann 100 % überschreiten (Rainer-PN 2026-05-22).

Erst über ein langes Fenster mittelt sich ΔSoC aus und entladung/ladung wird
belastbar — vgl. `speicher_wirtschaftlichkeit.WIRKUNGSGRAD_FENSTER_MONATE_MIN`
(dort wird unterhalb von 6 Monaten SoC-korrigiert gerechnet). Dieser Layer
braucht keinen SoC: `gleitende_effizienz` summiert über ein 12-Monats-Fenster,
der einzige Restfehler ist ein ΔSoC über das ganze Fenster — durch die
Kapazität gedeckelt und damit vernachlässigbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Kein Zirkel: `speicher_wirkungsgrad` importiert nichts aus diesem Modul.
from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad

# Fensterbreite, ab der entladung/ladung als belastbare Round-Trip-Effizienz
# gilt (darunter dominiert der SoC-Übertrag).
EFFIZIENZ_FENSTER_MONATE: int = 12


@dataclass
class MonatsEffizienz:
    """Gleitende Speicher-Effizienz für einen Kalendermonat."""

    jahr: int
    monat: int
    effizienz_prozent: Optional[float]
    fenster_monate: int  # Anzahl Monate, die ins gleitende Fenster eingingen


def speicher_effizienz_prozent(
    ladung_kwh: float, entladung_kwh: float
) -> Optional[float]:
    """Round-Trip-Effizienz in % — **Diagnose-Helper, keine Anzeige-Größe.**

    Die Funktion klemmt bewusst NICHT: Sie existiert, damit ein Überschuss
    *sichtbar* wird, statt auf 100 % gerundet zu verschwinden.

    ⚠ **Wer einen Wert für eine Anzeige, einen Sensor oder eine Rechnung
    braucht, nimmt `speicher_wirkungsgrad` aus
    `core/berechnungen/speicher_wirkungsgrad.py`** — dort gilt die Obergrenze,
    und der Rückgabewert trägt seine Herkunft mit. Diese Trennung ist seit
    N-252/N-264 verbindlich und gewächtert
    (`test_n252_speicher_wirkungsgrad_deckung.py`).

    **Einziger Verwender ist deshalb der Daten-Checker** (`daten_checker/
    stammdaten.py`), der den Überschuss meldet und ihn dafür ungekappt
    braucht. Zwischen N-252 und N-264 hatte die Funktion **gar keinen**
    Verwender mehr und stand als zweite, wartende Definition im Baum — genau
    die Ausgangslage, aus der N-252 entstanden war.

    Gibt `None` zurück, wenn keine Ladung vorliegt.
    """
    if ladung_kwh <= 0:
        return None
    return entladung_kwh / ladung_kwh * 100.0


def vollzyklen(
    entladung_kwh: Optional[float], kapazitaet_kwh: Optional[float]
) -> Optional[float]:
    """Vollzyklen-Äquivalent: **entladene** Energie ÷ Kapazität.

    Der Kanon für alle Sichten (Komponenten-Hub, Cockpit Tag/Monat/Jahr,
    PDF-Jahresbericht, HA-Sensor `speicher_zyklen`). Entscheidung Gernot
    2026-07-28 nach der Erhebung zur Rainer-PN 89768.

    **Warum die Entladung und nicht die Ladung:** ein Vollzyklus meint die
    einmal *entnommene* Kapazität — das ist die Größe, auf die sich
    Hersteller-Garantien beziehen, und sie ist unabhängig von den
    Wandlungsverlusten des Ladepfads. Bis 2026-07-28 rechneten vier von fünf
    Stellen mit der **Ladung** und nur der HA-Sensor mit der Entladung; auf
    derselben Anlage standen dadurch zwei Zahlen unter demselben Namen, die
    genau um den Speicher-Wirkungsgrad auseinanderlagen (gemessen: 10,97 vs.
    8,57 bei η 78 %).

    **Warum die BRUTTO-Kapazität im Nenner:** `nutzbare_kapazitaet_kwh` ist
    optional und bei den meisten Anlagen nicht gepflegt — ein Nenner, der je
    nach Pflegezustand wechselt, wäre schlimmer als ein durchgehend etwas
    konservativer. Siehe `docs/BERECHNUNGEN.md` §3.3.

    **Abgrenzung:** Die ΔSoC-Größe aus dem Energieprofil-Aggregator
    (`TagesZusammenfassung.batterie_vollzyklen`) misst etwas anderes — reale
    SoC-Hübe, die eine 10/90-Fahrweise abbilden. Sie ist ein Bestandsmaß und
    damit nicht additiv über Tage; sie heißt deshalb „SoC-Hübe" und ist
    bewusst KEIN Ersatz für diesen Wert.

    Gibt `None` zurück, wenn keine Kapazität gepflegt ist oder keine Entladung
    vorliegt — bewusst kein 0-Ersatz, sonst sähe „nicht gepflegt" wie „nie
    zyklisiert" aus. Ungerundet; die Anzeige rundet.
    """
    if not kapazitaet_kwh or kapazitaet_kwh <= 0:
        return None
    if not entladung_kwh or entladung_kwh <= 0:
        return None
    return entladung_kwh / kapazitaet_kwh


def auslastungs_basis_kwh(
    kapazitaet_kwh: Optional[float], tage: int
) -> Optional[float]:
    """Theoretisch verfügbare Speichermenge eines Zeitraums: Kapazität × Tage.

    Der Nenner der Auslastung (#358 Phase 1) — bewusst als **eigene, additive
    Größe** und nicht als fertiger Prozentsatz: Auslastungen mehrerer Monate
    lassen sich nicht mitteln (ein Februar wiegt weniger als ein Juli), Summen
    dagegen schon. Wer ein Jahr bildet, summiert Entladung und Basis und teilt
    einmal — genau so, wie die Jahres-Sicht alle anderen Quoten bildet. Ein
    nachgebauter Prozent-Mittelwert wäre die Drift-Klasse, die diese Trennung
    verhindert.

    Kapazität = **brutto**, gleiche Wahl und gleiche Begründung wie bei
    `vollzyklen` (der Netto-Wert ist selten gepflegt; ein Nenner, der je nach
    Pflegezustand wechselt, wäre schlimmer als ein konservativer).

    Gibt `None` ohne gepflegte Kapazität — „unbekannt", nicht 0.
    """
    if not kapazitaet_kwh or kapazitaet_kwh <= 0:
        return None
    if tage <= 0:
        return None
    return kapazitaet_kwh * tage


def auslastung_prozent(
    entladung_kwh: Optional[float], basis_kwh: Optional[float]
) -> Optional[float]:
    """Auslastung in % der theoretisch verfügbaren Speichermenge.

    ``Entladung ÷ (Kapazität × Tage) × 100`` — die Antwort auf „wie viel von
    dem, was der Speicher an Durchsatz hergäbe, wird tatsächlich genutzt".
    Anders als die Vollzyklen ist sie zeitraum-normiert und deshalb zwischen
    Monaten und Jahren vergleichbar.

    **Kein Deckel bei 100 %:** ein Speicher, der an einem Tag mehr als eine
    Kapazität durchsetzt (zwei Zyklen), ist real — die Zahl darf über 100
    gehen und sagt dann genau das.

    Gibt `None`, wenn die Basis fehlt (keine Kapazität gepflegt) oder nichts
    entladen wurde.
    """
    if not basis_kwh or basis_kwh <= 0:
        return None
    if entladung_kwh is None or entladung_kwh <= 0:
        return None
    return entladung_kwh / basis_kwh * 100


@dataclass(frozen=True)
class SocSpanne:
    """Wo ein Speicher in einem Zeitraum wirklich stand — als Spanne, nicht als Mittel.

    Ein Monatsmittel von 50 % entsteht sowohl bei einem Speicher, der immer
    halb voll steht, als auch bei einem, der täglich zwischen leer und voll
    durchfährt — und nur der zweite braucht keine größere Kapazität. Deshalb
    P10/P50/P90 statt eines Mittelwerts.
    """

    p10: float
    p50: float
    p90: float


def soc_spanne(werte: list[float]) -> Optional[SocSpanne]:
    """P10/P50/P90 einer SoC-Stichprobe, linear interpoliert.

    **Warum P10/P90 und nicht Minimum/Maximum:** ein einziger Ausreißer — eine
    Stunde Netz-Zwangsladung, ein Sensor-Aussetzer — spannt Min/Max über die
    volle Skala und macht alle Monate gleich aussehen. Genau dieser Effekt war
    der Anlass (Rainer, 2026-08-13: Okt/Nov und Feb/Mär waren in der
    Bin-Heatmap nicht unterscheidbar, weil **ein** Winter-Extremwert die
    globale Normierung bestimmte).

    Gibt `None` bei leerer Stichprobe — „nicht gemessen", nicht 0. Bei einem
    einzigen Wert sind alle drei Quantile dieser Wert; das ist korrekt und
    trägt sich in der Anzeige als Strich statt als Balken.
    """
    if not werte:
        return None
    sortiert = sorted(werte)

    def q(anteil: float) -> float:
        if len(sortiert) == 1:
            return sortiert[0]
        pos = anteil * (len(sortiert) - 1)
        unten = int(pos)
        oben = min(unten + 1, len(sortiert) - 1)
        rest = pos - unten
        return sortiert[unten] + (sortiert[oben] - sortiert[unten]) * rest

    return SocSpanne(p10=q(0.10), p50=q(0.50), p90=q(0.90))


def netz_ladung_stunde_kwh(
    ladung_kwh: Optional[float], netzbezug_kwh: Optional[float]
) -> float:
    """Der Teil einer **Stunden**-Ladung, der nicht aus PV-Überschuss stammen kann.

    ``min(Ladung, Netzbezug)`` — je Stunde, nie über einen längeren Zeitraum.
    Wer den Speicher in einer Stunde lädt und gleichzeitig Strom aus dem Netz
    zieht, kann höchstens so viel Netzstrom in den Akku geschoben haben, wie
    er insgesamt bezogen hat; der Rest der Ladung war Überschuss.

    ⚠ **Das ist eine Obergrenze, keine Messung.** Der Netzbezug derselben
    Stunde versorgt auch das Haus — kein Zähler trennt die beiden Wege. Die
    Zahl darf deshalb „höchstens" sagen und nie „genau". In die andere
    Richtung zu irren wäre schlimmer: eine zu kleine Netzladung ließe einen
    Speicher sauberer aussehen, als er fährt.

    ⚠ **Nur auf Stundenzeilen anwenden.** Über einen Tag oder Monat gebildet
    wäre dasselbe ``min()`` grob falsch — dort stehen Ladung am Mittag und
    Netzbezug in der Nacht in derselben Summe, obwohl sie sich nie begegnet
    sind.

    Zwei Aufrufer, eine Regel: ``services/speicher_wirtschaftlichkeit.py``
    (Ø-Ladepreis der Netzladung) und ``services/speicher_potential_service.py``
    (netzgeladener Anteil je Monat). Bis 2026-08-14 stand sie nur inline im
    ersten — die zweite Verwendung hätte sonst eine zweite Definition
    derselben Größe angelegt (ADR-001).
    """
    ladung = max(0.0, ladung_kwh or 0.0)
    netz = max(0.0, netzbezug_kwh or 0.0)
    return min(ladung, netz)


def gleitende_effizienz(
    monats_reihe: list[tuple[int, int, float, float]],
    fenster: int = EFFIZIENZ_FENSTER_MONATE,
) -> list[MonatsEffizienz]:
    """Gleitende Round-Trip-Effizienz über `fenster` Monate.

    Args:
        monats_reihe: chronologisch sortierte Tupel
            ``(jahr, monat, ladung_kwh, entladung_kwh)``.
        fenster: Fensterbreite in Monaten (Default `EFFIZIENZ_FENSTER_MONATE`).

    Für jeden Monat: Σentladung / Σladung über die letzten `fenster` Monate
    (inklusive dem Monat selbst); bei kürzerer Historie kumulativ ab Start.
    So mittelt sich der SoC-Übertrag aus — die Reihe zappelt nicht über
    100 %, wie es eine naive Pro-Monats-Effizienz täte.

    ⚠ **„Mittelt sich aus" ist nicht „kann nicht über 100 %"** (N-252): Sind
    die Mengen selbst falsch gepflegt (Klassiker #281 — „Ladung" enthält nur
    die PV-Ladung, die Netzladung steht als zweiter Posten daneben), dann
    liegt auch das 12-Monats-Fenster darüber. Deshalb läuft der Wert seit dem
    17.08.2026 über den Layer-SoT ``speicher_wirkungsgrad``: Er kappt und
    liefert ``None``, statt eine unmögliche Zahl in die Verlaufskurve zu
    schreiben — die sonst neben einer bereits geheilten Kachel stünde.
    """
    ergebnis: list[MonatsEffizienz] = []
    for i, (jahr, monat, _, _) in enumerate(monats_reihe):
        start = max(0, i - fenster + 1)
        fenster_rows = monats_reihe[start : i + 1]
        sum_ladung = sum(r[2] for r in fenster_rows)
        sum_entladung = sum(r[3] for r in fenster_rows)
        ergebnis.append(
            MonatsEffizienz(
                jahr=jahr,
                monat=monat,
                effizienz_prozent=speicher_wirkungsgrad(
                    sum_ladung, sum_entladung, None,
                    langes_fenster_quelle="fenster_lang",
                ).prozent,
                fenster_monate=len(fenster_rows),
            )
        )
    return ergebnis


def anlagen_soc_prozent(
    soc_je_speicher: dict,
    kapazitaet_je_speicher: dict,
) -> Optional[float]:
    """Der Ladestand der **Anlage** aus den Ladeständen ihrer Speicher (N-239).

    ``Σ Inhalt ÷ Σ Kapazität`` — also das **kapazitätsgewichtete** Mittel, nicht
    das arithmetische. Ein 15-kWh-Speicher auf 20 % und ein 5-kWh-Speicher auf
    100 % ergeben zusammen ``(3 + 5) / 20 = 40 %``; das arithmetische Mittel
    behauptete 60 % und damit anderthalb Mal so viel Energie, wie im Haus steht.

    **Warum es diese Funktion gibt.** Bis 2026-08-12 gab es sie nicht, und
    `energie_profil/_helpers.py::_get_soc_history` nahm bei mehreren Speichern
    den **ersten** gemappten Sensor und brach ab (`break  # Erstes SoC-Entity
    reicht`). `TagesEnergieProfil.soc_prozent` trug damit den Ladestand *eines*
    Geräts, während fünf Stellen im Baum „anlagenweiter Mischwert" behaupteten —
    und darauf laufen Vollzyklen, SoC-Hübe, die Potential-Heatmap und die
    Sizing-Kalibrierung.

    ⚑ **Bei genau einem Speicher ist das Ergebnis exakt dessen SoC** — die
    Umstellung ist für die überwiegende Mehrheit der Anlagen beweisbar ein
    No-op, und genau das macht sie vor einem Release vertretbar.

    Args:
        soc_je_speicher: ``{investition_id: soc_prozent}``. Geräte ohne Wert
            gehören nicht hinein — ein fehlender Ladestand ist keine 0.
        kapazitaet_je_speicher: ``{investition_id: kwh}``, **netto** (der real
            fahrbare Hub, auf den sich die Prozentskala bezieht).

    Returns:
        Ladestand in Prozent, oder ``None`` wenn kein Gerät einen Wert hat.
        **Fehlt für ein Gerät die Kapazität**, fällt die Rechnung auf das
        ungewichtete Mittel zurück: eine erfundene Gewichtung wäre schlechter
        als eine ehrlich gleichverteilte, und ein Gerät wegzulassen wäre still
        eine andere Anlage.
    """
    werte = {k: v for k, v in soc_je_speicher.items() if v is not None}
    if not werte:
        return None

    kapazitaeten = {
        k: kapazitaet_je_speicher.get(k)
        for k in werte
    }
    if any(not k for k in kapazitaeten.values()):
        return sum(werte.values()) / len(werte)

    gesamt = sum(kapazitaeten[k] for k in werte)
    if gesamt <= 0:
        return sum(werte.values()) / len(werte)
    inhalt = sum(werte[k] / 100.0 * kapazitaeten[k] for k in werte)
    return inhalt / gesamt * 100.0
