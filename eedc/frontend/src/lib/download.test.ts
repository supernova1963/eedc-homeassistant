/**
 * `istAppleMobil` (Diagnose-Paket v4, Bauplan §5 S2 Schritt 2/3): Kennungen aus der S0-Messung (15.11.2026).
 * iPhone/iPad im HA-Rahmen laden per Blob-Weg, alle übrigen per Navigation.
 */
import { describe, it, expect } from 'vitest'
import { istAppleMobil } from './download'

const IPHONE_APP =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Home Assistant/2026.10.3 '
  + '(io.robbie.HomeAssistant; build:2026.3322; iOS 27.0.1) Mobile/HomeAssistant, like Safari'
const ANDROID_APP =
  'Mozilla/5.0 (Linux; Android 14; OT5 S Build/UP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
  + 'Chrome/130.0.6723.102 Mobile Safari/537.36 Home Assistant/2026.10.1-24906 (Android 14; OT5 S)'
const IPAD_ALS_MAC =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
const DESKTOP =
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'

describe('istAppleMobil', () => {
  it('iPhone-App-Kennung aus S0 ⇒ wahr', () => {
    expect(istAppleMobil({ userAgent: IPHONE_APP, maxTouchPoints: 5 })).toBe(true)
  })

  it('iPad mit Desktop-Kennung (Macintosh mit Touch) ⇒ wahr', () => {
    expect(istAppleMobil({ userAgent: IPAD_ALS_MAC, maxTouchPoints: 5 })).toBe(true)
  })

  it('Mac ohne Touch ⇒ falsch', () => {
    expect(istAppleMobil({ userAgent: IPAD_ALS_MAC, maxTouchPoints: 0 })).toBe(false)
  })

  it('Android-App-Kennung aus S0 ⇒ falsch', () => {
    expect(istAppleMobil({ userAgent: ANDROID_APP, maxTouchPoints: 5 })).toBe(false)
  })

  it('Desktop ⇒ falsch', () => {
    expect(istAppleMobil({ userAgent: DESKTOP, maxTouchPoints: 0 })).toBe(false)
  })
})
