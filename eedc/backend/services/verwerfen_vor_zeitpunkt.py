"""Werkbank-Operation «Werte eines Felds vor einem Zeitpunkt verwerfen» (Fund-Päckchen H, H1; Entscheide des Masters 23.11.2026
zu NG4 a–e — Anlass: «Gefahrene km» vor dem richtigen Sensor, Befund ``ha_zaehlerstand_springt`` Fall «Summe beginnt neu», Weg 2).

**Regel — die Operation wirkt, als wäre die Quelle des Felds erst ab ``t`` zugeordnet.** Für EIN zugeordnetes Feld (Zähler- bzw.
Stand-Kanal ``basis:<feld>`` / ``inv:<id>:<feld>``) und einen frei gewählten Zeitpunkt ``t`` (volle Stunde, nicht in der Zukunft):

* **Quelle bei ``t`` teilen** (``kanal/verwerfen.teile_quelle``): die bei ``t`` geltende ``kanal_quelle`` bekommt eine zweite
  Zeile derselben Entity ab ``t``; alle Quellen vor ``t`` tragen die Marke ``verworfen_ts``. Kein neues Schema. Mehrere Quellen vor
  ``t``: alle gleich (die bestehende Form der Werkbank).
* **Eine Bedeutung der Marke:** eine verworfene Quelle kommt nicht zurück — das Nachfüllen holt unter der ersten unmarkierten
  Quelle nach ihr nichts (``nachfuellen._untergrenze``), der Konsistenzlauf übergeht markierte Abschnitte (``nachfuellen.abschnitte``),
  der Stundenlauf schreibt ab seiner letzten Zeile fort, die Nachfüll-Marke des Kanals bleibt.
* **Die Teile der Lösch-Antwort** des Sensorwechsel-Dialogs (``feld_loeschen.loesche_vor`` mit ``teilen``, derselbe Baustein):
  Kanal-Zeilen vor ``t``, Zählerstände und MQTT-Rohstände des Schlüssels vor ``t``, der Feld-Schlüssel in Stunden- und Tageszeilen
  bis zum Bestandstag von ``t`` in **allen** Monaten, die abgeleiteten Kanäle dieses Felds; die verzeichneten Wechsel wie die
  Werkbank-Form (bis zum Ende der ersten Stunde ab ``t``). Danach im Hintergrund der bestehende Lauf (``korrektur_lauf``, Art
  ``loeschen``, ohne Nachfüllen aus Home Assistant): abgeleitete Kanäle neu, betroffene Tage neu — ohne Abruf, Wetter und Preise
  wie vorher (``korrektur_lauf._ein_tag``). **Gespeicherte Monatswerte bleiben** (die Vorschau nennt die Monate).
* **Nicht freigegeben (Matrix H1, Zelle ohne eindeutige Antwort):** ein Feld, das Home Assistant führt und das der Neu-Aufbau
  eines Tages vor ``t`` direkt aus der HA-Statistik in Stunden- und Tageszeilen schreibt, weil der Tag für seine Gruppe keine
  Kanal-Deckung hat (``mengen_weiche``: der Schlüssel bliebe in der Tageszeile) — dort käme der Wert mit jedem «Tag neu
  aggregieren» zurück. Die Vorschau nennt die Tage und führt nicht aus (``ha_bestandstage``).

Schwesterdateien: ``services/feld_loeschen.py`` (Baustein), ``services/kanal/verwerfen.py`` (Kanal-Schicht),
``services/verwerfen_vor_quellbeginn.py`` (Bestand-Bausteine, die bestehende Werkbank-Form), ``services/kanal/nachfuellen.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services import verwerfen_vor_quellbeginn as vq
from backend.services.kanal import verwerfen as kv

OPERATION = "verwerfen_vor_zeitpunkt"
LABEL = "Werte eines Felds vor einem Zeitpunkt verwerfen"
QUELLE_HA, QUELLE_MQTT, QUELLE_ANDERE = "ha", "mqtt", "andere"


def uhr() -> datetime:
    """Die Uhr der Operation (Proben setzen sie)."""
    return datetime.now()


@dataclass(frozen=True)
class LageZ:
    """Alles, was Vorschau und Ausführung über EINEN Plan wissen."""

    anlage: Anlage
    key: str
    label: str
    t: int
    kanal: kv.KanalVorschau
    ziele: vq.BestandZiele
    bestand: vq.BestandZaehlung
    staende: int
    rohstaende: int
    monate: tuple[tuple[int, int], ...]
    quelle: str
    bilanz: bool
    #: Tage vor ``t``, an denen ein Neu-Aufbau das Feld aus der HA-Statistik in den Bestand schriebe (nicht freigegeben).
    ha_bestandstage: tuple[date, ...] = ()
    #: Verzeichnete Sensorwechsel, die mit verworfen werden (``feld_loeschen.zaehle_wechsel``, dieselbe Auswahl wie das Löschen).
    wechsel: int = 0

    @property
    def bis_tag(self) -> date:
        return kv.tag_der_stunde(self.t)

    @property
    def nichts_zu_tun(self) -> bool:
        return not (self.kanal.zeilen or self.staende or self.rohstaende or self.bestand.tage or self.bestand.abschluss_tage
                    or self.wechsel)


def _zeitpunkt(params: dict[str, Any]) -> int:
    if not params.get("zeitpunkt"):
        raise ValueError("Verwerfen braucht params.zeitpunkt (JJJJ-MM-TTTHH:MM, volle Stunde)")
    t = kv.zeitpunkt_aus_text(str(params["zeitpunkt"]))
    if t > int(uhr().replace(minute=0, second=0, microsecond=0).timestamp()):
        raise ValueError("Der Zeitpunkt liegt in der Zukunft — verworfen werden nur Werte, die eedc schon hat")
    return t


async def _staende(db: AsyncSession, anlage_id: int, key: str, t: int) -> tuple[int, int]:
    """Zählerstände und MQTT-Rohstände des Schlüssels vor ``t`` (gezählt, nicht gelöscht)."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    bis = datetime.fromtimestamp(t)
    zs = (await db.execute(select(func.count()).select_from(SensorSnapshot).where(and_(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt < bis)))).scalar_one()
    mk = _sensor_key_to_mqtt_key(key)
    rs = 0 if not mk else (await db.execute(select(func.count()).select_from(MqttEnergySnapshot).where(and_(
        MqttEnergySnapshot.anlage_id == anlage_id, MqttEnergySnapshot.energy_key == mk,
        MqttEnergySnapshot.timestamp < bis)))).scalar_one()
    return int(zs), int(rs)


async def _quelle(db: AsyncSession, anlage: Anlage, key: str, quellen: list) -> str:
    """``ha``: das Feld ist heute einer HA-Entity zugeordnet (der Neu-Aufbau eines Bestandstags liest dann aus HA);
    ``mqtt``: die jüngste Quelle ist eine MQTT-Mitschrift; sonst ``andere``."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT
    from backend.services.kanal import schreiber as sch
    from backend.services.kanal.nachfuellen import STAENDE_HA_PRAEFIX

    k = await sch._kontext(db, anlage, uhr().replace(minute=0, second=0, microsecond=0))
    if k.counter_map.get(key):
        return QUELLE_HA
    letzte = quellen[-1] if quellen else None
    if (letzte is not None and letzte.familie == FAMILIE_MITSCHRIFT and letzte.statistic_id
            and not letzte.statistic_id.startswith(STAENDE_HA_PRAEFIX)):
        return QUELLE_MQTT
    return QUELLE_ANDERE


def _bleibt_im_bestand(weiche, ziele: vq.BestandZiele) -> bool:
    """Schriebe ``aggregate_day`` an diesem Tag einen Bestand-Schlüssel des Felds (Weiche ohne Wirkung auf ihn)? Die Geräte-
    Schlüssel der Weiche (Wärmepumpe, Sonstiges) zählen nicht: sie hängen am Tageswert des Kanals, und den hat ein
    verworfenes Feld nicht mehr."""
    from backend.services.kanal.bilanz_leser import ist_bilanz_schluessel

    def leer(k: str) -> bool:
        if weiche.praefixe and str(k).startswith(weiche.praefixe):
            return True
        return weiche.bilanz_ziele is not None and ist_bilanz_schluessel(k, weiche.bilanz_ziele)

    if ziele.spalte and ziele.spalte not in weiche.tep_spalten:
        return True
    return any(not leer(k) for k in ziele.tz_keys)


async def _ha_bestandstage(db: AsyncSession, anlage: Anlage, ziele: vq.BestandZiele, kanal_v: kv.KanalVorschau,
                           bestand: vq.BestandZaehlung, bis_tag: date) -> tuple[date, ...]:
    """Die Tage bis ``bis_tag``, an denen ein Neu-Aufbau das Feld aus der HA-Statistik in den Bestand schriebe
    (``mengen_weiche`` des Tages, eine Stelle mit ``aggregate_day``). Nur für Felder mit Bestand-Schlüssel."""
    from backend.services.energie_profil.mengen_weiche import mengen_weiche

    if not (ziele.spalte or ziele.tz_keys):
        return ()
    tage = set(bestand.tage) | set(bestand.abschluss_tage) | {bis_tag}
    tage |= {d for d in kanal_v.tage} | {d + timedelta(days=1) for d in kanal_v.tage}
    out = []
    for d in sorted(x for x in tage if x <= bis_tag):
        if _bleibt_im_bestand(await mengen_weiche(db, anlage, d), ziele):
            out.append(d)
    return tuple(out)


async def lage(db: AsyncSession, anlage_id: int, params: dict[str, Any]) -> LageZ:
    """Eingaben prüfen und zählen (kein Schreiben)."""
    from backend.services.feld_loeschen import gespeicherte_monate, zaehle_wechsel
    from backend.services.kanal.bilanz_quellenwahl import bilanz_benoetigte_kanaele

    key = params.get("kanal")
    if not key or not isinstance(key, str):
        raise ValueError("Verwerfen braucht params.kanal (das zugeordnete Feld, z. B. basis:einspeisung)")
    t = _zeitpunkt(params)
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")
    kanal, quellen = await kv.lade_kanal(db, anlage_id, key)
    kanal_v = await kv.vorschau(db, kanal, quellen, t)
    ziele = await vq.bestand_ziele(db, anlage, key)
    bis_tag = kv.tag_der_stunde(t)
    bestand = await vq.zaehle_bestand(db, anlage_id, ziele, bis_tag, frozenset())
    staende, roh = await _staende(db, anlage_id, key, t)
    quelle = await _quelle(db, anlage, key, quellen)
    erster = kanal_v.erste_ts if kanal_v.erste_ts is not None else (quellen[0].gueltig_ab if quellen else None)
    monate = await gespeicherte_monate(db, anlage_id, datetime.fromtimestamp(erster) if erster is not None else None,
                                       datetime.fromtimestamp(t))
    bilanz = key in await bilanz_benoetigte_kanaele(db, anlage_id, bis_tag)
    ha_tage = await _ha_bestandstage(db, anlage, ziele, kanal_v, bestand, bis_tag) if quelle == QUELLE_HA else ()
    wechsel = await zaehle_wechsel(db, anlage_id, key, bis=datetime.fromtimestamp(t + 3600),
                                   gleiche_quelle_bis=datetime.fromtimestamp(t))
    return LageZ(anlage, key, vq.feld_label(key, await vq._investitionen(db, anlage_id)), t, kanal_v, ziele, bestand,
                 staende, roh, tuple(monate), quelle, bilanz, ha_tage, wechsel)


# ── Vorschau ────────────────────────────────────────────────────────────────

SATZ_BLEIBT = ("Gespeichert bleiben: die Werte jedes anderen Felds, Wetter, Börsen- und Kraftstoffpreise, Prognosen und die "
               "gespeicherten Monatswerte.")
SATZ_BILANZ = ("Das Feld gehört zur Energiebilanz: vor dem Zeitpunkt zeigt es «—» wie ein nicht zugeordnetes Feld, die übrigen "
               "Felder des Tages bleiben. Was eedc aus ihm rechnet (etwa Eigenverbrauch, Hausverbrauch, Überschuss), ändert "
               "sich an denselben Tagen mit.")
SATZ_HA = ("Home Assistant behält seine Statistik. eedc holt die Zeit vor dem Zeitpunkt für dieses Feld nicht wieder — auch "
           "nicht mit «Aus Home Assistant neu übernehmen» oder «Tag neu aggregieren».")
SATZ_MQTT = "Die Quelle ist MQTT: die verworfenen Werte sind nicht wiederholbar — keine Quelle holt sie zurück."
#: Halt 2 (a), Entscheid Master 23.11.2026: ein HA-Feld mit Tageswert zeigt am Tag des Zeitpunkts den ganzen Tag aus der
#: HA-Statistik (der Tag verliert mit der Zeile vor ``t`` die Kanal-Deckung, der Neu-Aufbau schreibt den Tageswert aus HA).
SATZ_TAG_VON_T = ("Am {tag} zeigt dieses Feld den ganzen Tag, wie Home Assistant ihn führt — auch die Stunden vor {uhrzeit} "
                  "Uhr; die übrigen Felder dieses Tages liest eedc dann aus den gespeicherten Tageswerten, sie können sich an "
                  "diesem Tag ändern.")
SATZ_MONAT = "Für {monate} ist ein Monatswert gespeichert. Er bleibt, wie er ist."
SATZ_MONATE = "Für {monate} sind Monatswerte gespeichert. Sie bleiben, wie sie sind."
SATZ_MONATE_WEG = "Soll ein Monat zu den verbliebenen Werten passen, ändere ihn unter Einstellungen → «Daten» → «Monatsdaten» von Hand."
SATZ_NICHT_FREI = ("Für dieses Feld ist das Verwerfen hier nicht möglich: an {n} ({spanne}) schriebe jeder Neu-Aufbau des "
                   "Tages den Wert dieses Felds wieder aus der Statistik von Home Assistant. Bleibt der Wert falsch, "
                   "berichtige ihn in Home Assistant (Einstellungen → Werkzeuge → Statistik) und übernimm ihn danach mit "
                   "«Aus Home Assistant neu übernehmen».")


def _anzahl(n: int, eins: str, mehr: str) -> str:
    return f"{fmt_zahl(n)} {eins if n == 1 else mehr}"


def _was_weg(la: LageZ) -> str:
    teile = []
    if la.kanal.zeilen:
        teile.append(f"{_anzahl(la.kanal.zeilen, 'Stundenzeile', 'Stundenzeilen')} des Kanals "
                     f"({vq._spanne(list(la.kanal.tage))})")
    if la.staende:
        teile.append(_anzahl(la.staende, "Zählerstand", "Zählerstände"))
    if la.rohstaende:
        teile.append(_anzahl(la.rohstaende, "MQTT-Rohwert", "MQTT-Rohwerte"))
    tage = sorted(la.bestand.tage | la.bestand.abschluss_tage)
    if tage:
        teile.append(f"die Stunden- und Tageswerte dieses Felds an {_anzahl(len(tage), 'Tag', 'Tagen')} ({vq._spanne(tage)}), "
                     "auch in Monaten mit Monatsabschluss")
    if la.wechsel:
        teile.append(f"{_anzahl(la.wechsel, 'verzeichneter Sensorwechsel', 'verzeichnete Sensorwechsel')} dieses Felds bis "
                     "zur ersten Stunde ab dem Zeitpunkt")
    return "Gelöscht werden nur Daten dieses Felds vor dem Zeitpunkt: " + "; ".join(teile) + "."


def klartext(la: LageZ) -> list[str]:
    zeit = vq._zeit(la.t)
    if la.nichts_zu_tun:
        return [f"Nichts zu verwerfen — vor {zeit} führt eedc keine Werte von «{la.label}» ({la.key})."]
    s = [f"Verworfen werden die Werte von «{la.label}» ({la.key}) vor {zeit}. Danach verhält sich das Feld, als wäre seine "
         "Quelle erst ab diesem Zeitpunkt zugeordnet.", _was_weg(la)]
    if la.ha_bestandstage:
        return s + [_nicht_frei(la)]
    if la.bilanz:
        s.append(SATZ_BILANZ)
    s.append(_tag_von_t(la))
    s.append(SATZ_BLEIBT)
    if la.monate:
        s.append((SATZ_MONAT if len(la.monate) == 1 else SATZ_MONATE).format(monate=vq._monate_text(list(la.monate))))
        s.append(SATZ_MONATE_WEG)
    s.append(SATZ_HA if la.quelle == QUELLE_HA else SATZ_MQTT if la.quelle == QUELLE_MQTT else "")
    s.append("Danach bildet eedc die betroffenen Tage im Hintergrund neu.")
    from backend.services.feld_loeschen import SATZ_ENDGUELTIG

    s.append(SATZ_ENDGUELTIG)
    return [x for x in s if x]


def _tag_von_t(la: LageZ) -> str:
    """Der Satz «Tag von t» — nur für ein Feld aus Home Assistant mit Tageswert und einen Zeitpunkt nach Mitternacht."""
    z = datetime.fromtimestamp(la.t)
    if la.quelle != QUELLE_HA or not la.ziele.tz_keys or z.hour == 0:
        return ""
    return SATZ_TAG_VON_T.format(tag=vq._spanne([z.date()]), uhrzeit=z.strftime("%H:%M"))


def geschaetzt(la: LageZ) -> dict[str, int]:
    return {"kanalzeilen": la.kanal.zeilen, "zaehlerstaende": la.staende, "mqtt_rohwerte": la.rohstaende,
            "bestand_tage": len(la.bestand.tage | la.bestand.abschluss_tage), "monate_gespeichert": len(la.monate)}


def vorschau_daten(la: LageZ) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kanal": la.key, "label": la.label, "zeitpunkt": kv.text_aus_zeitpunkt(la.t), "quelle": la.quelle,
        "bilanz": la.bilanz, "monate": [f"{j}-{m:02d}" for j, m in la.monate],
        "ha_bestandstage": [d.isoformat() for d in la.ha_bestandstage],
    }
    if la.nichts_zu_tun:
        out["nichts_zu_tun"] = klartext(la)[0]
    return out


def _nicht_frei(la: LageZ) -> str:
    return SATZ_NICHT_FREI.format(n=_anzahl(len(la.ha_bestandstage), "Tag", "Tagen"),
                                  spanne=vq._spanne(list(la.ha_bestandstage)))


async def plan(db: AsyncSession, anlage_id: Optional[int], params: dict[str, Any]):
    """Vorschau ohne Schreiben. Eine nicht freigegebene Lage (``ha_bestandstage``) ist ein ``ValueError`` mit dem Satz."""
    if anlage_id is None:
        raise ValueError("Verwerfen braucht anlage_id")
    la = await lage(db, anlage_id, params)
    if la.ha_bestandstage and not la.nichts_zu_tun:
        raise ValueError(_nicht_frei(la))
    return geschaetzt(la), klartext(la), vorschau_daten(la)


# ── Ausführung ──────────────────────────────────────────────────────────────


async def fuehre_aus(db: AsyncSession, anlage_id: int, params: dict[str, Any]) -> dict[str, Any]:
    """Zählt frisch, löscht in EINER Sitzung (ein Commit) und startet danach den Lauf (abgeleitete Kanäle, Tage)."""
    from backend.core.database import get_session
    from backend.services import feld_loeschen
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

    la = await lage(db, anlage_id, params)
    if la.nichts_zu_tun:
        raise ValueError(f"Nichts zu tun: {klartext(la)[0]}")
    if la.ha_bestandstage:
        raise ValueError(_nicht_frei(la))
    jetzt = uhr().replace(microsecond=0)
    g = await feld_loeschen.loesche_vor(db, la.anlage, la.key, datetime.fromtimestamp(la.t), auch_abschluss=True,
                                        zum_platzhalter=False, jetzt=jetzt, teilen=True)
    lauf = await feld_loeschen.lauf_anlegen(db, anlage_id, g, mit_ha=False, jetzt=jetzt)
    summary = {"kanal": la.key, "zeitpunkt": kv.text_aus_zeitpunkt(la.t), "kanalzeilen_geloescht": g.kanalzeilen,
               "quellen_markiert": g.quellen, "quelle_geteilt": g.geteilt, "zaehlerstaende_geloescht": g.staende,
               "mqtt_rohwerte_geloescht": g.rohstaende, "wechsel_geloescht": g.wechsel,
               "abgeleitet_verworfen": g.abgeleitet_verworfen, **g.bestand, "tage_neu": len(g.tage), "lauf": lauf,
               "meldung": (f"«{la.label}» vor {vq._zeit(la.t)} verworfen: {fmt_zahl(g.kanalzeilen)} Kanalzeilen, "
                           f"{fmt_zahl(g.staende + g.rohstaende)} Zählerstände; "
                           f"{_anzahl(len(g.tage), 'Tag wird', 'Tage werden')} im Hintergrund neu gebildet.")}
    await db.commit()
    korrektur_lauf.starten(lauf, sitzungen=sitzungen_wie(db, get_session))
    return summary


# ── Auswahl (lesende Route) ─────────────────────────────────────────────────


async def auswahl(db: AsyncSession, anlage_id: int) -> list[dict[str, Any]]:
    """Alle Zähler- und Stand-Kanäle zugeordneter Felder mit ihren Quellen; vorbelegt ist der Beginn der jüngsten Quelle."""
    invs = await vq._investitionen(db, anlage_id)
    out = []
    for kanal, quellen in await kv.kanaele_mit_quellen(db, anlage_id):
        if not quellen:
            continue
        teile = kanal.key.split(":")
        inv = invs.get(int(teile[1])) if teile[0] == "inv" else None
        out.append({
            "key": kanal.key, "label": vq.feld_label(kanal.key, invs),
            "investition_id": inv.id if inv is not None else None, "typ": inv.typ if inv is not None else None,
            "quellen": [{"gueltig_ab": kv.text_aus_zeitpunkt(q.gueltig_ab), "familie": q.familie,
                         "statistic_id": q.statistic_id,
                         "verworfen_am": kv.text_aus_zeitpunkt(q.verworfen_ts) if q.verworfen_ts is not None else None}
                        for q in quellen],
            "vorbelegung": kv.text_aus_zeitpunkt(quellen[-1].gueltig_ab),
        })
    return out
