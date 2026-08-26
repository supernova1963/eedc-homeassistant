"""Warum ein **Tageswert** fehlt — die eine Stelle, an der das ausgesprochen wird (**W-18**).

## Der Anlass

dietmar1968 hat am 26.08.2026 (T89667 #210) ein Bild seiner Tagesansicht
geschickt, dazu den Satz *„Ich verstehe beim Vorhandensein folgender Sensoren
jene Anzeige nicht."* Sein Cockpit → Tag zeigte bei *Wärme erzeugt* ein „—",
und der Tooltip dahinter sagte:

    „Tageswert braucht einen Wärmemengenzähler am Gerät (Sensor zuordnen);
     sonst nur Monatswert."

**Er hatte zwei zugeordnet.** Sein erstes Bild zeigt *Heizwärme* auf
``sensor.boiler_energy_heating`` und *Warmwasser* auf ``sensor.boiler_dhw_energy``,
beide grün, beide mit Wert. eedc hat ihn aufgefordert, etwas zu tun, was er
längst getan hatte — und er hat der Auskunft geglaubt, statt der Anzeige.

⭐ **Eine falsche Ursache ist schlimmer als keine.** Ohne Hinweis sucht der
Anwender; mit einem falschen Hinweis sucht er an der falschen Stelle und meldet
danach einen Fehler, den es nicht gibt.

## Was hier gelöst ist

Der alte Text war **fest verdrahtet im Client** und konnte deshalb nur *einen*
Fall beschreiben. Tatsächlich gibt es **drei**, und der Snapshot-Pfad kann sie
auseinanderhalten — er hat die Unterscheidung bisher nur weggeworfen:

| Zustand | Was wirklich los ist |
| --- | --- |
| :data:`GRUND_NICHT_ZUGEORDNET` | Für dieses Feld ist gar kein Zähler zugeordnet |
| :data:`GRUND_KEINE_ZAEHLERSTAENDE` | Zugeordnet, aber für **diesen Tag** fehlen die Zählerstände an den Tagesrändern |
| :data:`GRUND_ZAEHLER_RUECKSPRUNG` | Zählerstände da, aber der Zähler ist im Tagesfenster zurückgesprungen |

⚠ **Der dritte Fall war bis dahin ausschließlich eine Logzeile.**
``_tageswert_aus_raendern`` erkennt den Rücksprung, gibt bewusst ``None`` zurück
(P4: keine Aussage statt einer falschen) und schreibt ein ``logger.info`` — das
kein Anwender je zu sehen bekommt. Er sah dasselbe „—" wie jemand ohne Sensor.

## Zwei Regeln, die zu diesem Modul gehören

1. **Der Grund sagt, was IST — nicht, was zu TUN ist.** Die Handlungsanweisung
   ist feldspezifisch („Wärmemengenzähler zuordnen" gilt nicht für die
   Speicher-Netzladung) und bleibt beim Aufrufer. Der Grund hier gilt für jedes
   Feld, das über eine Randdifferenz entsteht.
2. **Er steht SICHTBAR unter der Zahl, nicht im Tooltip.** Das ist keine neue
   Entscheidung, sondern eine bereits getroffene (S3, ``KomponentenSektionen.tsx``:
   *„ein Tooltip ist auf dem Telefon keine Auskunft"*) — sie war nur an einer von
   drei Kacheln umgesetzt. Die JAZ hatte ihren sichtbaren Grund, Wärme und
   Ersparnis nicht.

## Kein Spiegel im Frontend — und das ist die dritte Regel

Die Route liefert den **fertigen Satz**, nicht den Schlüssel. Eine TS-Kopie der
Textliste wäre eine zweite Wahrheit über denselben Sachverhalt; sie driftet
genau dann, wenn jemand einen Fall ergänzt und die andere Seite vergisst — die
Klasse, die in diesem Projekt schon F-56 und W-14 erzeugt hat. Der Client zeigt
an, was er bekommt.
"""

from __future__ import annotations

from typing import Final, Optional

#: Für dieses Feld ist kein Zähler zugeordnet — der einzige Fall, den der alte
#: fest verdrahtete Text beschrieb.
GRUND_NICHT_ZUGEORDNET: Final[str] = "nicht_zugeordnet"

#: Zugeordnet, aber für diesen Tag fehlen die Zählerstände. **Der Regelfall
#: nach einer frischen Zuordnung**: Der Monatswert steht da (er kommt aus der
#: HA-Langzeitstatistik), der Tageswert nicht (er braucht Snapshots, und die
#: entstehen erst ab der Zuordnung). Genau diese Kombination — Monat gefüllt,
#: Tag leer — stand auf dietmars beiden Bildern.
GRUND_KEINE_ZAEHLERSTAENDE: Final[str] = "keine_zaehlerstaende"

#: Der Zähler ist im Tagesfenster zurückgesprungen. Bis zum 26.08.2026 nur eine
#: Logzeile (``_tageswert_aus_raendern``).
GRUND_ZAEHLER_RUECKSPRUNG: Final[str] = "zaehler_ruecksprung"

#: Der Wortlaut je Zustand. **Er beschreibt, er bewertet nicht** — ein Anwender,
#: dessen Zähler zurückspringt, hat nichts falsch gemacht
#: ([[feedback_eedc_ist_nicht_die_strom_polizei]]).
TAGESWERT_GRUND_TEXT: Final[dict[str, str]] = {
    GRUND_NICHT_ZUGEORDNET: "Kein Zähler zugeordnet",
    GRUND_KEINE_ZAEHLERSTAENDE: (
        "Zähler zugeordnet, aber für diesen Tag liegen keine Zählerstände vor. "
        "Tageswerte entstehen ab der Zuordnung; frühere Tage lassen sich in der "
        "Reparatur-Werkbank nachrechnen."
    ),
    GRUND_ZAEHLER_RUECKSPRUNG: (
        "Der Zähler ist an diesem Tag zurückgesprungen — für diesen Tag gibt es "
        "deshalb keine Aussage."
    ),
}


#: **Kurzform** derselben drei Zustände — für Stellen, an denen der Grund als
#: Beschriftung neben einer Zahl steht statt als Absatz.
#:
#: ⛔ **Sie ist eine Übersetzung, keine zweite Wahrheit.** Anlass: Die
#: Arbeitszahl sperrt sich bei fehlender Wärme mit dem kurzen Satz „kein
#: Wärmemengenzähler zugeordnet" (``waermepumpe_kennzahl.arbeitszahl``) — und
#: das ist **dieselbe Falschaussage** wie der Client-Tooltip, nur eine Ebene
#: tiefer und sichtbar. dietmar1968 sah sie unter seiner leeren JAZ-Kachel,
#: obwohl beide Wärmemengenzähler zugeordnet waren. Die Sperre bleibt richtig;
#: nur ihre Begründung war geraten.
#:
#: ⚠ Ein Test hält beide Listen deckungsgleich — eine Kurzform ohne Langform
#: (oder umgekehrt) wäre ein Zustand, den eine Fläche benennen kann und die
#: andere nicht.
TAGESWERT_GRUND_KURZ: Final[dict[str, str]] = {
    GRUND_NICHT_ZUGEORDNET: "kein Wärmemengenzähler zugeordnet",
    GRUND_KEINE_ZAEHLERSTAENDE: "für diesen Tag keine Zählerstände",
    GRUND_ZAEHLER_RUECKSPRUNG: "Zählerrücksprung an diesem Tag",
}


def tageswert_grund_kurz(grund: Optional[str]) -> Optional[str]:
    """Die Kurzform zu einem Zustand, sonst ``None``. Siehe :data:`TAGESWERT_GRUND_KURZ`."""
    if not grund:
        return None
    return TAGESWERT_GRUND_KURZ.get(grund)


#: Rangfolge, wenn ein Ausgabe-Wert von **mehreren Geräten** gespeist wird und
#: keines geliefert hat (``emob_ladung_pv_kwh`` = Wallbox + E-Auto).
#:
#: ⭐ **Der aussagekräftigste Grund gewinnt, nicht der erste.** „Nicht
#: zugeordnet" kann der Anwender selbst nachsehen — die Datenquellen-Fläche
#: zeigt es ihm. Dass ein *zugeordneter* Zähler für diesen Tag nichts hergibt,
#: sieht er nirgends; genau das war dietmars Fall. Und ein Rücksprung schlägt
#: beides: er ist der einzige Zustand, in dem eedc etwas **gemessen** hat und
#: die Aussage trotzdem verweigert.
GRUND_RANG: Final[dict[str, int]] = {
    GRUND_NICHT_ZUGEORDNET: 0,
    GRUND_KEINE_ZAEHLERSTAENDE: 1,
    GRUND_ZAEHLER_RUECKSPRUNG: 2,
}


#: Was zu TUN ist, je Ausgabe-Feld — und **nur** für
#: :data:`GRUND_NICHT_ZUGEORDNET` gültig. Regel 1 des Modulkopfs: der Grund sagt,
#: was ist; die Handlungsanweisung hängt am Feld und gehört deshalb hierher, wo
#: die Felder bekannt sind, und nicht in einen Satz, der für alle drei Zustände
#: gilt.
#:
#: ⛔ **Sie wird an keinen anderen Zustand gehängt.** Genau das war der Fehler:
#: „Sensor zuordnen" stand auch dann da, wenn der Sensor zugeordnet war.
HANDLUNG_JE_FELD: Final[dict[str, str]] = {
    "wp_heizung_kwh":
        "Wärmemengenzähler für die Heizwärme zuordnen (Einstellungen → Datenquellen).",
    "wp_warmwasser_kwh":
        "Wärmemengenzähler für das Warmwasser zuordnen (Einstellungen → Datenquellen).",
    "wp_strom_heizen_kwh":
        "Zähler für den Heiz-Strom zuordnen (Einstellungen → Datenquellen).",
    "wp_strom_warmwasser_kwh":
        "Zähler für den Warmwasser-Strom zuordnen (Einstellungen → Datenquellen).",
    "speicher_ladung_netz_kwh":
        "Zähler für die Netzladung des Speichers zuordnen (Einstellungen → Datenquellen).",
    "emob_ladung_pv_kwh":
        "PV-Ladezähler der Wallbox oder dem Fahrzeug zuordnen (Einstellungen → Datenquellen).",
    "emob_ladung_netz_kwh":
        "Netz-Ladezähler der Wallbox oder dem Fahrzeug zuordnen (Einstellungen → Datenquellen).",
}


def tageswert_grund_text(
    grund: Optional[str], ausgabe_key: Optional[str] = None,
) -> Optional[str]:
    """Der fertige Anwender-Satz — oder ``None``, wenn es keinen gibt.

    Args:
        grund: einer der drei Zustände oben.
        ausgabe_key: das Feld, um das es geht. Nur bei
            :data:`GRUND_NICHT_ZUGEORDNET` ausgewertet — dort wird die
            feldspezifische Handlungsanweisung angehängt.

    ⚠ **Ein unbekannter Zustand liefert ``None``, nicht den Schlüssel selbst.**
    Ein durchgereichter Bezeichner wie ``"zaehler_ruecksprung"`` in der
    Oberfläche wäre schlechter als gar kein Text — er sieht aus wie ein Fehler
    und ist keine Auskunft.
    """
    if not grund:
        return None
    text = TAGESWERT_GRUND_TEXT.get(grund)
    if text is None:
        return None
    if grund == GRUND_NICHT_ZUGEORDNET:
        handlung = HANDLUNG_JE_FELD.get(ausgabe_key or "")
        if handlung:
            return f"{text} — {handlung}"
    return text
