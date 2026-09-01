/**
 * Wortlaut-SoT für „worauf das individuelle Verbrauchsprofil beruht".
 *
 * Zwei Sichten nennen dieselbe Grundlage — die Legende des Live-Wetter-Widgets und
 * der Verbrauchs-Tooltip der 3-Tage-Aussicht. Beide bauten den Satz bis 2026-09-01
 * von Hand nach und nannten dabei allein die **Tageszahl**.
 *
 * Warum das zu wenig war (N-48): Das Backend gibt das individuelle Profil ab zwei
 * Tagen je Klasse frei, und ein „Tag" entsteht bereits aus einer **einzigen**
 * gemessenen Stunde. Zwei solcher Tage ergeben ein Profil, dessen übrige Slots aus
 * der BDEW-Standard-Grundlast kommen — das ist der vorgesehene Rückfall
 * (ADR-002/P4) und bleibt so. Ohne die Abdeckung daneben liest sich „2 Tage" aber
 * wie eine Aussage über die Güte des Profils.
 *
 * Deshalb nennt der Satz die Abdeckung **und ihre Folge**, statt nur eine zweite
 * Zahl danebenzustellen.
 */

/** Ein Tagesprofil hat 24 Slots — die Bezugsgröße der Abdeckung. */
const SLOTS_PRO_TAG = 24

/** Trägt `profil_typ` ein individuelles Profil (Werktag oder Wochenende)? */
export function istIndividuellesProfil(profilTyp?: string | null): boolean {
  return !!profilTyp?.startsWith('individuell')
}

/** „Werktag" bzw. „Wochenende" — die Klasse, aus der das Profil gemittelt ist. */
export function profilKlasseLabel(profilTyp?: string | null): string {
  return profilTyp === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'
}

/**
 * Die Grundlage eines individuellen Profils in einem Satzteil, z. B.
 * `"Werktag, 2 Tage, 3 von 24 Stunden gemessen — die übrigen 21 aus der Standard-Grundlast"`.
 *
 * Gibt `null` zurück, wenn gar kein individuelles Profil vorliegt; die Aufrufer
 * setzen dann ihren eigenen BDEW-Text.
 *
 * Fehlt die Abdeckung (`profilSlots` null — etwa gegen ein älteres Backend), bleibt
 * es bei der Tageszahl: eine Abdeckung zu erfinden wäre schlimmer als keine.
 */
export function verbrauchsprofilBasis(
  profilTyp?: string | null,
  profilTage?: number | null,
  profilSlots?: number | null,
): string | null {
  if (!istIndividuellesProfil(profilTyp)) return null

  const basis = [profilKlasseLabel(profilTyp), `${profilTage ?? '?'} Tage`]
  if (profilSlots == null) return basis.join(', ')

  basis.push(`${profilSlots} von ${SLOTS_PRO_TAG} Stunden gemessen`)

  // Die Folge nur nennen, wo wirklich Slots fehlen — bei voller Abdeckung gäbe es
  // keine „übrigen", und der Zusatz behauptete einen Rückfall, den es nicht gab.
  const rest = SLOTS_PRO_TAG - profilSlots
  if (rest <= 0) return basis.join(', ')
  return `${basis.join(', ')} — die übrigen ${rest} aus der Standard-Grundlast`
}
