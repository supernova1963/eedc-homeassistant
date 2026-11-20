"""Daten-Checker — Auskunft «Zählerstände verworfen» (``zaehler_zeit_verworfen``; Sensorwechsel U3 a, Rechenweg G1, Bauplan
Nr. 150).

**Warum es das gibt.** Eine Korrektur («Bisherige Werte verwerfen», «Grund nachtragen → Korrektur», die Korrektur über ein
Stück) verwirft die Zählerstände einer Zeit. Was Home Assistant nicht füllt (ohne Verbindung, eine MQTT-Quelle, keine
Geschichte des richtigen Sensors, eine Höhe, die sich nicht prüfen lässt), bleibt für immer leer: eine **Lücke**
(``zuordnung_wechsel/zeitpunkt.ist_luecke`` — eine nicht aufgehobene Korrektur-Zeile ohne Home-Assistant-Entität, auch die
Lücken-Zeile des Korrektur-Dienstes). Die Vorschau hat das beim Eintragen gesagt; danach sagte es niemand mehr, und an
Bilanz-Feldern nannte der Befund «Stunden ohne Stundenwerte» (``erfassung_stillstand``) den Tag mit einem unwahren Satz
(«Tag und Monat zählen die Menge vollständig»).

**Was er nennt** — je Lücke eine Zeile (Auskunft, INFO, Knopf «Was gilt»), mit den Lagen aus denselben Funktionen wie Vorschau
und Leser:

* **wie eine Zählerlücke** (``zeitpunkt.ohne_hoehenwechsel`` an den gespeicherten Ständen um die Lücke — dieselbe Frage wie
  ``zeitpunkt._ohne_hoehenwechsel_je_luecke``, die die Leser fragen; das Merkmal «Höhe ungeprüft» der Lücken-Zeile zählt dort
  mit): die Menge der ganzen Zeit steht am Tag des ersten Stands danach (``stueck.tragtag_der_luecke``), die Tage darin zeigen
  keinen Wert (``stueck.tage_der_luecke``);
* **keine Differenz**: eedc bildet über die Zeit keine Differenz; die Tage darin zeigen keinen Wert, die Rand-Tage nur ihren
  Teil, die Menge fehlt. Der Grund: ein Höhenwechsel (andere oder unbekannte Quelle, Zählertausch dazwischen), «Höhe
  ungeprüft», oder — **eigener Entscheid der Bau-Sitzung U3 a** — der Kanal des Felds führt die Zeit als verworfen
  (``kanal_quelle.verworfen_ts``): seine Stundenwerte zählen dort 0 und setzen danach ohne Zuwachs an
  (``kanal/korrektur.py`` Schritt 2/3), und die Tagesansicht liest den Kanal vor der Reihe — dort steht die Menge nicht am Tag
  danach (Rechenweg «Widerlegt» Nr. 3: 6,0 statt der Menge). Ändert Lauf b (G7) den Kanal, ändert sich diese Lage mit.

Dazu die betroffenen Monate mit gespeichertem Monatswert (``verwerfen_vor_quellbeginn.abschluss_monate``) — der bleibt, wie er
ist. Eine spätere Korrektur, die die Lücke ganz überdeckt, hebt sie auf; dann verschwindet die Zeile. Keine Lücke ⇒ keine Zeile.

**Ein Befund je Ursache:** ``erfassung_stillstand`` lässt die Stellen aus, die allein eine verworfene Zeit eines Bilanz-Zählers
erklärt (``achsen_der_verworfenen_zeiten``).

Schwesterdateien: ``grund_fehlt.py`` (Wechsel ohne Grund), ``versatz.py`` (versetzter Abschnitt), ``monatswert.py``
(``monatswert_ueberholt``), ``services/daten_checker/erfassung_stillstand.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

CODE = "zaehler_zeit_verworfen"
LAGE_ZAEHLERLUECKE = "zaehlerluecke"
LAGE_KEINE_DIFFERENZ = "keine_differenz"
GRUND_HOEHE_UNGEPRUEFT = "hoehe_ungeprueft"
GRUND_KANAL = "kanal"
GRUND_HOEHENWECHSEL = "hoehenwechsel"
#: U3-K3: der Kanal setzt nach der Zeit mit der ersten Stunde des richtigen Sensors an (``kanal/korrektur.raender_…``).
GRUND_KANAL_ERSTE = "kanal_erste"

#: Wortlaute (U3 a; Vorschlag des Rechenwegs G1, festgelegt von der Bau-Sitzung — Liste im Bericht).
SATZ_MELDUNG = "{name}: Zählerstände vom {von} bis {bis} Uhr verworfen"
SATZ_VERWORFEN = ("Für diese Zeit hat eedc bei einer Korrektur die Zählerstände dieses Felds verworfen, und nichts füllt sie "
                  "wieder auf — auch nicht aus Home Assistant; das bleibt so.")
SATZ_WIE_LUECKE = ("Davor, in dieser Zeit und danach gilt dieselbe Quelle, und dazwischen ist kein Zählertausch eingetragen: "
                   "eedc rechnet über diese Zeit wie über jede Zählerlücke. Die Menge der ganzen Zeit steht am {tag} und zählt "
                   "dort in Tag, Monat und Jahr.")
SATZ_TAGE = "Die Tagesansicht zeigt {teile}."
SATZ_TAGE_OHNE = "{tage} für dieses Feld keinen Wert"
SATZ_TAGE_RAND = "{tage} nur den Teil außerhalb dieser Zeit"
SATZ_KEINE_DIFFERENZ = ("eedc bildet über diese Zeit keine Differenz zweier Zählerstände; die Menge dieser Zeit fehlt in Tag, "
                        "Monat und Jahr.")
SATZ_GRUND = {
    GRUND_HOEHENWECHSEL: ("Davor und danach gilt nicht erkennbar dieselbe Quelle, oder dazwischen ist ein Zählertausch "
                          "eingetragen."),
    GRUND_HOEHE_UNGEPRUEFT: ("Home Assistant führt den richtigen Sensor erst ab dem Ende dieser Zeit; ob seine Zählerstände "
                             "auf der Höhe der gespeicherten davor liegen, lässt sich nicht prüfen."),
    GRUND_KANAL: "Die Stundenwerte dieses Felds zählen in dieser Zeit nichts und setzen danach ohne Zuwachs neu an.",
    GRUND_KANAL_ERSTE: ("Die Stundenwerte dieses Felds zählen in dieser Zeit nichts; danach zählen sie ab der ersten Stunde des "
                        "richtigen Sensors, was Home Assistant für ihn führt."),
}
SATZ_MONATE_GESPEICHERT = "Für {monate} ist ein Monatswert gespeichert; er bleibt, wie er ist."


@dataclass(frozen=True)
class VerworfeneZeit:
    """Eine nicht aufgehobene Lücke ``[von, bis)`` eines Zählerschlüssels (``zeitpunkt.ist_luecke``)."""
    sensor_key: str
    von: datetime
    bis: datetime


async def verworfene_zeiten(db, anlage_id: int) -> list[VerworfeneZeit]:
    """Die Lücken der Anlage, je Schlüssel und Zeit einmal, aufsteigend — dieselbe Ladestelle wie die Leser
    (``zeitpunkt.lade_wechsel``, je Sitzung gemerkt; ohne Sitzung keine)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecke, lade_wechsel

    aus = {VerworfeneZeit(key, w.falsch_seit_ts, w.ab_ts)
           for key, liste in (await lade_wechsel(db, anlage_id)).items() for w in liste if ist_luecke(w)}
    return sorted(aus, key=lambda v: (v.von, v.sensor_key, v.bis))


@dataclass
class Lage:
    zeit: VerworfeneZeit
    lage: str
    grund: Optional[str] = None
    tag: Optional[date] = None
    tage_ohne: list[date] = field(default_factory=list)
    tage_rand: list[date] = field(default_factory=list)
    monate: list[tuple[int, int]] = field(default_factory=list)
    monate_gespeichert: list[tuple[int, int]] = field(default_factory=list)


async def kanal_verwirft(db, anlage_id: int, key: str, v: VerworfeneZeit) -> bool:
    """Führt der Kanal des Felds diese Zeit als verworfen (eine Quellzeile mit ``verworfen_ts`` ab einer Stunde vor der Lücke
    bis zu ihrem Ende — ``kanal/korrektur.py`` setzt sie an ``w0``, frühestens eine Stunde vor «Falsch seit») **und** setzt er
    danach ohne Zuwachs an? Setzt er mit der Menge der Zeit an (U3 b, G7 (b): MQTT ohne Höhenwechsel,
    ``kanal/korrektur.ist_ueberbrueckt`` — dieselbe Regel wie der Schreiber), rechnet er wie eine Zählerlücke: nein (P-1)."""
    from backend.models.kanal import Kanal, KanalQuelle
    from backend.services.kanal.korrektur import ist_ueberbrueckt

    von, bis = int(v.von.timestamp()) - 3600, int(v.bis.timestamp())
    verwirft = (await db.execute(select(KanalQuelle.gueltig_ab).join(Kanal, Kanal.id == KanalQuelle.kanal_id).where(
        Kanal.anlage_id == anlage_id, Kanal.key == key, KanalQuelle.verworfen_ts.is_not(None),
        KanalQuelle.gueltig_ab >= von, KanalQuelle.gueltig_ab < bis).limit(1))).first() is not None
    return verwirft and not await ist_ueberbrueckt(db, anlage_id, key, von + 3600, bis)


def _monate(von: datetime, bis: datetime) -> list[tuple[int, int]]:
    letzte = bis - timedelta(seconds=1)
    out, j, m = [], von.year, von.month
    while (j, m) <= (letzte.year, letzte.month):
        out.append((j, m))
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    return out


def _grund(wechsel, v: VerworfeneZeit) -> str:
    from backend.models.zuordnung_wechsel import ANSATZ_HOEHE_UNGEPRUEFT
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecken_zeile

    if any(w.aufgehoben_durch is None and ist_luecken_zeile(w) and w.ansatz == ANSATZ_HOEHE_UNGEPRUEFT
           and (w.falsch_seit_ts, w.ab_ts) == (v.von, v.bis) for w in wechsel or ()):
        return GRUND_HOEHE_UNGEPRUEFT
    return GRUND_HOEHENWECHSEL


async def lage_der_zeit(db, anlage, v: VerworfeneZeit) -> Lage:
    """Was für diese Zeit gilt — dieselben Funktionen wie Vorschau (``korrektur.lage``) und Leser."""
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.zuordnung_wechsel.stueck import tage_der_luecke, tragtag_der_luecke
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel, ohne_hoehenwechsel, staende_um

    from backend.services.kanal.korrektur import raender_der_verworfenen_zeit
    from backend.services.zuordnung_wechsel.stueck import reihe_raender, tage_im_kanal

    wechsel = (await lade_wechsel(db, anlage.id)).get(v.sensor_key)
    vor, nach = await staende_um(db, anlage.id, v.sensor_key, v.von, v.bis)
    kanal = await kanal_verwirft(db, anlage.id, v.sensor_key, v)
    # U3-K3: trägt der Kanal davor Werte, liest die Tagesansicht ihn — die Tage nach seinen Rändern.
    raender = await raender_der_verworfenen_zeit(db, anlage.id, v.sensor_key, int(v.von.timestamp()),
                                                 int(v.bis.timestamp())) if kanal else None
    ohne, rand = (await tage_im_kanal(db, anlage, v.sensor_key, datetime.fromtimestamp(raender[0]),
                                      datetime.fromtimestamp(raender[1]),
                                      reihe=await reihe_raender(db, anlage.id, v.sensor_key, v.von, v.bis))
                  if raender is not None else await tage_der_luecke(db, anlage, v.sensor_key, v.von, v.bis))
    monate = _monate(v.von, v.bis)
    gespeichert = await vq.abschluss_monate(db, anlage.id)
    la = Lage(v, LAGE_KEINE_DIFFERENZ, tage_ohne=ohne, tage_rand=rand, monate=monate,
              monate_gespeichert=[m for m in monate if m in gespeichert])
    if not kanal and ohne_hoehenwechsel(wechsel, vor, nach, (v.von, v.bis)):
        la.lage, la.tag = LAGE_ZAEHLERLUECKE, await tragtag_der_luecke(db, anlage, v.sensor_key, v.bis)
        la.tage_ohne = [d for d in ohne if d != la.tag]
        la.tage_rand = [d for d in rand if d != la.tag]
    else:
        la.grund = (GRUND_KANAL_ERSTE if raender is not None and raender[2] else GRUND_KANAL) if kanal else _grund(wechsel, v)
    return la


def _datum(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _uhr(t: datetime) -> str:
    return t.strftime("%d.%m.%Y %H:%M")


def _tage_satz(la: Lage) -> Optional[str]:
    from backend.services.zuordnung_wechsel.korrektur import _tage_bereich

    teile = []
    if la.tage_ohne:
        teile.append(SATZ_TAGE_OHNE.format(tage=_tage_bereich(la.tage_ohne)))
    if la.tage_rand:
        teile.append(SATZ_TAGE_RAND.format(tage=" und ".join(f"am {_datum(d)}" for d in la.tage_rand)))
    return SATZ_TAGE.format(teile=" und ".join(teile)) if teile else None


def texte(name: str, la: Lage) -> tuple[str, str]:
    """Meldung und Details in Anwender-Sprache (kein Menüweg — «Was gilt» öffnet den Lösungsweg)."""
    from backend.services.verwerfen_vor_quellbeginn import _monate_text

    meldung = SATZ_MELDUNG.format(name=name, von=_uhr(la.zeit.von), bis=_uhr(la.zeit.bis))
    teile = [SATZ_VERWORFEN]
    if la.lage == LAGE_ZAEHLERLUECKE:
        teile.append(SATZ_WIE_LUECKE.format(tag=_datum(la.tag) if la.tag else _uhr(la.zeit.bis)))
    else:
        teile += [SATZ_GRUND[la.grund], SATZ_KEINE_DIFFERENZ]
    if (tage := _tage_satz(la)) is not None:
        teile.append(tage)
    if la.monate_gespeichert:
        teile.append(SATZ_MONATE_GESPEICHERT.format(monate=_monate_text(la.monate_gespeichert)))
    return meldung, " ".join(teile)


class ZaehlerZeitVerworfenChecks:
    """Auskunft je verworfener, nicht wieder gefüllter Zeit eines Zählerfelds."""

    async def _check_zaehler_zeit_verworfen(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.models.investition import Investition
        from backend.services.daten_checker.datenquelle.grund_fehlt import feld_name

        zeiten = await verworfene_zeiten(self.db, anlage.id)
        if not zeiten:
            return []
        invs = {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
        return [_befund(feld_name(invs, v.sensor_key), await lage_der_zeit(self.db, anlage, v)) for v in zeiten]


def _befund(name: str, la: Lage) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1; W-6: eine Auskunft ist INFO)."""
    meldung, details = texte(name, la)
    v = la.zeit
    teile = v.sensor_key.split(":")
    return CheckErgebnis(
        kategorie=CheckKategorie.ZAEHLER_ZEIT_VERWORFEN.value,
        schwere=CheckSeverity.INFO,
        meldung=meldung,
        details=details,
        investition_id=int(teile[1]) if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit() else None,
        code="zaehler_zeit_verworfen",
        werte={"schluessel": v.sensor_key, "von": v.von.isoformat(timespec="minutes"),
               "bis": v.bis.isoformat(timespec="minutes"), "lage": la.lage, "grund": la.grund,
               "tag": la.tag.isoformat() if la.tag else None, "tage_ohne_wert": [d.isoformat() for d in la.tage_ohne],
               "tage_teilwert": [d.isoformat() for d in la.tage_rand],
               "monate": [f"{j}-{m:02d}" for j, m in la.monate],
               "monate_gespeichert": [f"{j}-{m:02d}" for j, m in la.monate_gespeichert]},
    )


# ── Abgrenzung zu ``erfassung_stillstand`` (ein Befund je Ursache) ───────────────────────────────────────────────────────


async def achsen_der_verworfenen_zeiten(db, anlage) -> list[tuple[str, datetime, datetime]]:
    """Je Lücke eines Bilanz-Zählers ``(Achse, von, bis)`` — die Achse des Zählers in der Tagesbilanz (dieselbe Abbildung
    Feld → Kategorie → Achse wie ``daten_checker._ist_bilanz_kanal``). Leer ohne Lücke (dann keine weitere Abfrage)."""
    from backend.core.berechnungen.spannen import achse_der_kategorie
    from backend.services.snapshot.keys import _categorize_counter

    zeiten = await verworfene_zeiten(db, anlage.id)
    if not zeiten:
        return []
    invs = {str(i.id): i for i in getattr(anlage, "investitionen", None) or ()}
    aus = []
    for v in zeiten:
        teile = v.sensor_key.split(":")
        if len(teile) == 2 and teile[0] == "basis":
            kategorie = _categorize_counter(teile[1], None, None)
        elif len(teile) == 3 and teile[0] == "inv" and teile[1] in invs:
            kategorie = _categorize_counter(teile[2], invs[teile[1]].typ, invs[teile[1]].parameter)
        else:
            continue
        if (achse := achse_der_kategorie(kategorie)) is not None:
            aus.append((achse, v.von, v.bis))
    return aus


def stelle_erklaert(von: datetime, bis: datetime, achsen_mit_nachtrag: set[str],
                    verworfen: list[tuple[str, datetime, datetime]]) -> bool:
    """Erklärt eine verworfene Zeit diese Stelle ``[von, bis)`` des Befunds ``erfassung_stillstand`` ganz? Ja, wenn jede
    Achse, deren Menge die Stelle nachträgt, zu einem Zähler gehört, dessen Lücke die Stelle umfasst — mit einer Stunde Rand
    an beiden Enden (der Kanal setzt eine Stunde vor «Falsch seit» an; die Nachtragsstunde ist die erste nach der Lücke)."""
    if not achsen_mit_nachtrag:
        return False
    stunde = timedelta(hours=1)
    return all(any(a == achse and v_von - stunde <= von and bis <= v_bis + stunde for a, v_von, v_bis in verworfen)
               for achse in achsen_mit_nachtrag)


__all__ = ["CODE", "LAGE_KEINE_DIFFERENZ", "LAGE_ZAEHLERLUECKE", "VerworfeneZeit", "ZaehlerZeitVerworfenChecks",
           "achsen_der_verworfenen_zeiten", "kanal_verwirft", "lage_der_zeit", "stelle_erklaert", "texte", "verworfene_zeiten"]
