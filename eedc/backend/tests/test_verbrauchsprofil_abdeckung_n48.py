"""Das individuelle Verbrauchsprofil weist seine gemessene Abdeckung aus (N-48).

Schwesterdateien zum selben Modul: ``test_verbrauchsprofil_slot_konvention.py``
(Slot-Zuordnung und Stundenarithmetik der drei Quellen, N-43/N-45/N-46) und
``test_live_wetter_verbrauchsprofil.py`` (der Konsument
``live_wetter._berechne_verbrauchsprofil``, der die fehlenden Slots mit der
BDEW-Standard-Grundlast füllt).

**Der Befund.** ``_build_profil_result`` gibt das individuelle Profil ab zwei
Tagen je Klasse frei — und ein „Tag" entsteht bereits aus einer **einzigen**
gemessenen Stunde, weil ``werktage_set.add(...)`` je Slot läuft. Zwei solcher
Tage ergeben ein Profil aus einem einzigen Messwert; die übrigen 23 Slots kommen
aus der Standard-Grundlast. Dem Anwender stand dabei allein ``profil_tage`` im
Tooltip — „2 Tage" liest sich wie eine Aussage über die Güte des Profils.

**Was hier NICHT geprüft wird, und das ist die Entscheidung dahinter.** Die
Schwelle bleibt bei ``tage >= 2``. Sie zu schärfen (Freigabe erst ab einer
Mindest-Abdeckung) nähme Anlagen ihr individuelles Profil weg und würfe sie auf
BDEW H0 zurück; der Rückfall auf die Standard-Grundlast je fehlendem Slot ist der
**vorgesehene** Weg (ADR-002/P4), und eine Teilabdeckung wird nicht unterdrückt —
nur der Total-Fall. Gebaut ist deshalb die **Auskunft**, nicht die Schärfung.

Geprüft wird entsprechend in beide Richtungen:

1. Die Abdeckung ist die Zahl der Stunden **mit Stichprobe** — nicht 24, nicht
   die Tageszahl. Der N-48-Fall (zwei Tage, eine Stunde) muss sie als ``1``
   ausweisen.
2. Wo eine Klasse **nicht** freigegeben ist, gibt es keine Abdeckung (``None``) —
   eine 0 wäre eine Aussage über ein Profil, das gar nicht ausgeliefert wird.
"""

from __future__ import annotations

from backend.services.live_verbrauchsprofil_service import _build_profil_result

# Ein Tagesprofil hat 24 Slots. Bewusst ausgeschrieben statt aus dem Produktivcode
# geholt: ein Pinning-Test, der seine Bezugsgröße aus derselben Stelle bezieht wie
# der geprüfte Code, prüft nur noch sich selbst.
SLOTS_PRO_TAG = 24


def _sums(werte: dict[int, list[float]]) -> dict[int, list[float]]:
    """Stunden-Eimer wie die drei Sammelpfade sie bauen: alle 24 Slots, meist leer."""
    leer: dict[int, list[float]] = {h: [] for h in range(SLOTS_PRO_TAG)}
    leer.update(werte)
    return leer


def test_abdeckung_zaehlt_stunden_mit_stichprobe_nicht_tage():
    """Der N-48-Fall: zwei Tage, aber nur EINE gemessene Stunde."""
    ergebnis = _build_profil_result(
        werktag_sums=_sums({7: [0.4, 0.5]}),
        wochenende_sums=_sums({}),
        werktage_set={"2026-08-31", "2026-09-01"},
        wochenende_set=set(),
        quelle="db",
    )

    assert ergebnis is not None
    # Die Freigabe hält — das Profil wird ausgeliefert, es wird nur beziffert.
    assert ergebnis["werktag"] is not None
    assert ergebnis["tage_werktag"] == 2
    # ... und genau hier lag die Lücke: zwei Tage, eine Stunde.
    assert ergebnis["slots_werktag"] == 1
    assert ergebnis["slots_werktag"] != ergebnis["tage_werktag"] * SLOTS_PRO_TAG


def test_abdeckung_ist_voll_wenn_jede_stunde_gemessen_wurde():
    """Gegenprobe: bei voller Messung steht dort 24, nicht weniger."""
    ergebnis = _build_profil_result(
        werktag_sums=_sums({h: [0.3] for h in range(SLOTS_PRO_TAG)}),
        wochenende_sums=_sums({}),
        werktage_set={"2026-08-31", "2026-09-01"},
        wochenende_set=set(),
        quelle="db",
    )

    assert ergebnis is not None
    assert ergebnis["slots_werktag"] == SLOTS_PRO_TAG


def test_nicht_freigegebene_klasse_hat_keine_abdeckung():
    """Ohne freigegebenes Profil gibt es nichts zu beziffern — None, nicht 0.

    Das Wochenende hat hier Messwerte, aber nur EINEN Tag: die Klasse fällt
    unter die Freigabe-Schwelle und wird gar nicht ausgeliefert. Eine 0 an dieser
    Stelle wäre eine Aussage über ein Profil, das es nicht gibt.
    """
    ergebnis = _build_profil_result(
        werktag_sums=_sums({h: [0.3] for h in range(SLOTS_PRO_TAG)}),
        wochenende_sums=_sums({12: [1.0]}),
        werktage_set={"2026-08-31", "2026-09-01"},
        wochenende_set={"2026-08-30"},
        quelle="db",
    )

    assert ergebnis is not None
    assert ergebnis["wochenende"] is None
    assert ergebnis["slots_wochenende"] is None
    # Die freigegebene Klasse daneben bleibt davon unberührt.
    assert ergebnis["slots_werktag"] == SLOTS_PRO_TAG


def test_beide_klassen_tragen_ihre_eigene_abdeckung():
    """Werktag und Wochenende werden getrennt gemessen und getrennt beziffert."""
    ergebnis = _build_profil_result(
        werktag_sums=_sums({h: [0.3] for h in range(6, 20)}),
        wochenende_sums=_sums({h: [0.5] for h in range(SLOTS_PRO_TAG)}),
        werktage_set={"2026-08-27", "2026-08-28"},
        wochenende_set={"2026-08-29", "2026-08-30"},
        quelle="ha",
    )

    assert ergebnis is not None
    assert ergebnis["slots_werktag"] == 14
    assert ergebnis["slots_wochenende"] == SLOTS_PRO_TAG
