"""N-555 Stufe 1, Regel 5: der Fahrverbrauch bleibt Fahrverbrauch — einmalige Rückbenennung.

Was war
-------
Die Startroutine ``core/database.py::_migrate_verbrauch_daten_keys_v326`` benannte seit
01.05.2026 bei **jedem** Programmstart das Feld „Verbrauch" am E-Auto
(``verbrauch_daten.verbrauch_kwh``, der **Fahrverbrauch**) in ``ladung_kwh`` um und löschte
den Verbrauch. Stand daneben schon eine Ladung von 0, wurde auch die überschrieben. Der
Fahrverbrauch tauchte danach als Heimladung auf, „Verbrauch" stand leer, kWh/100 km und der
Plug-in-Hybrid-Anteil verloren ihren Messwert. Der E-Auto-Eintrag ist aus der Startroutine
entfernt (Konzept Heimladung/Fahrverbrauch, Regel 5); diese Migration räumt die Spur.

Woran eine Umbuchung zu erkennen ist
------------------------------------
Jeder persistente Schreibweg legt eine Heimladung am E-Auto **mit** Herkunftseintrag ab
(``source_provenance["verbrauch_daten.ladung_kwh"]``: Formular, „Aus HA laden", Import,
Wiederherstellung). Die Startroutine schrieb am rohen JSON vorbei — ihr ``ladung_kwh`` hat
**keinen** Eintrag unter seinem neuen Namen. Genau das ist das Kriterium:

* E-Auto-Zeile (auch dienstlich) trägt ``ladung_kwh``, der Herkunfts-Store kennt
  ``verbrauch_daten.ladung_kwh`` nicht, und
  * ``verbrauch_kwh`` fehlt ⇒ **zurückbenennen** (``ladung_kwh`` → ``verbrauch_kwh``);
  * ``verbrauch_kwh`` ist da ⇒ ``ladung_kwh`` **entfernen** (der Verbrauch wurde seither neu
    erfasst; die Ladung ist die alte Umbuchung).
* Eine Ladung **mit** Herkunftseintrag bleibt unangetastet — auch ``legacy:unknown``.

⚠ Die Grenze: 09.05.2026
-------------------------
An diesem Tag hat eedc einmalig allen damals vorhandenen Werten ohne Herkunft den Eintrag
„Bestand, Herkunft unbekannt" gegeben (``provenance_migrate.
migrate_3d_p3_initial_provenance_legacy_unknown``, über ``_apply_once``). Weil die
Startroutine (synchron, ``run_migrations``) **vor** den Daten-Migrationen läuft, trugen die
Umbuchungen vom 01.05. bis 09.05. zu diesem Zeitpunkt schon den Namen ``ladung_kwh`` und
bekamen den Stempel — sie sehen seither aus wie echte alte Ladungen und **bleiben**. Diese
Migration erreicht nur Umbuchungen danach. Das ist die im Konzept (Abschnitt 7) benannte
Grenze, keine Lücke dieses Codes.

Idempotenz
----------
``_apply_once`` (Name ``n555_eauto_fahrverbrauch_rueckbenennung``). Zusätzlich natürlich
idempotent: nach dem Lauf trägt keine betroffene Zeile mehr ein herkunftsloses
``ladung_kwh``, und die Startroutine erzeugt keines mehr.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.investition import Investition, InvestitionMonatsdaten

logger = logging.getLogger(__name__)

#: Der Herkunftsschlüssel, den jeder persistente Schreibweg für eine E-Auto-Ladung setzt.
_HERKUNFT_LADUNG = "verbrauch_daten.ladung_kwh"


async def migrate_eauto_fahrverbrauch_rueckbenennung(session: AsyncSession) -> dict[str, int]:
    """Benennt herkunftslose E-Auto-``ladung_kwh`` zurück bzw. entfernt sie (Regel 5).

    Returns:
        ``{"zurueckbenannt": n, "entfernt": m}`` — für Proben und das Startlog.
    """
    zeilen = (await session.execute(
        select(InvestitionMonatsdaten, Investition)
        .join(Investition, Investition.id == InvestitionMonatsdaten.investition_id)
        .where(Investition.typ == "e-auto")
        .order_by(InvestitionMonatsdaten.id)
    )).all()

    zurueckbenannt = entfernt = 0
    for imd, inv in zeilen:
        daten = imd.verbrauch_daten
        if not isinstance(daten, dict) or "ladung_kwh" not in daten:
            continue
        herkunft = imd.source_provenance or {}
        if _HERKUNFT_LADUNG in herkunft:
            continue  # echte Ladung (auch legacy:unknown) — bleibt

        neu = dict(daten)
        wert = neu.pop("ladung_kwh")
        if neu.get("verbrauch_kwh") is None:
            neu["verbrauch_kwh"] = wert
            aktion = "zurückbenannt (ladung_kwh → verbrauch_kwh)"
            zurueckbenannt += 1
        else:
            aktion = "entfernt (verbrauch_kwh steht schon wieder da)"
            entfernt += 1
        imd.verbrauch_daten = neu
        flag_modified(imd, "verbrauch_daten")
        logger.info(
            "N-555 Rückbenennung: Anlage %s, Investition %s (%s), %04d-%02d: "
            "ladung_kwh=%s %s",
            inv.anlage_id, inv.id, inv.bezeichnung, imd.jahr, imd.monat, wert, aktion,
        )

    if zurueckbenannt or entfernt:
        await session.commit()
        logger.info(
            "N-555 Rückbenennung: %d Zeile(n) zurückbenannt, %d Umbuchung(en) entfernt. "
            "Umbuchungen vom 01.05. bis 09.05.2026 tragen den Stempel „Herkunft unbekannt“ "
            "und bleiben (nicht unterscheidbar).",
            zurueckbenannt, entfernt,
        )
    return {"zurueckbenannt": zurueckbenannt, "entfernt": entfernt}
