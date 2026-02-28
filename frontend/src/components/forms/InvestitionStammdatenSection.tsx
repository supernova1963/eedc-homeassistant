import { useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink, Info } from 'lucide-react'
import { Input } from '../ui'
import type { InvestitionTyp, Anlage } from '../../types'

interface StammdatenSectionProps {
  typ: InvestitionTyp
  paramData: Record<string, string | boolean>
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  anlage?: Anlage | null
  hasParent?: boolean
}

export default function InvestitionStammdatenSection({
  typ,
  paramData,
  onChange,
  anlage,
  hasParent
}: StammdatenSectionProps) {
  const [showAnsprechpartner, setShowAnsprechpartner] = useState(false)
  const [showWartung, setShowWartung] = useState(false)

  // Vererbung NUR für Children mit Parent (PV-Module, DC-Speicher → Wechselrichter)
  // Wechselrichter selbst ist eigenständig und erbt NICHT
  const kannVererben = hasParent
  const vererbungsQuelle = 'Wechselrichter'

  return (
    <div className="space-y-4">
      {/* Gerätedaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Gerätedaten</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Hersteller"
            name="param_stamm_hersteller"
            value={paramData.stamm_hersteller as string || ''}
            onChange={onChange}
            placeholder="z.B. Fronius, BYD, Longi"
          />
          <Input
            label="Modell"
            name="param_stamm_modell"
            value={paramData.stamm_modell as string || ''}
            onChange={onChange}
            placeholder="z.B. Symo GEN24 10.0"
          />
          <Input
            label="Seriennummer"
            name="param_stamm_seriennummer"
            value={paramData.stamm_seriennummer as string || ''}
            onChange={onChange}
            placeholder={typ === 'pv-module' ? 'z.B. SN001-SN020' : 'z.B. ABC123456'}
          />
          <Input
            label="Garantie bis"
            name="param_stamm_garantie_bis"
            type="date"
            value={paramData.stamm_garantie_bis as string || ''}
            onChange={onChange}
          />
          {/* MaStR-ID für Wechselrichter */}
          {typ === 'wechselrichter' && (
            <div>
              <Input
                label="MaStR-ID"
                name="param_stamm_mastr_id"
                value={paramData.stamm_mastr_id as string || ''}
                onChange={onChange}
                placeholder="z.B. SEE123456789"
                hint="Marktstammdatenregister-ID des Wechselrichters"
              />
              {paramData.stamm_mastr_id && (
                <a
                  href={`https://www.marktstammdatenregister.de/MaStR/Einheit/Detail/IndexOeffentlich/${paramData.stamm_mastr_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
                >
                  <ExternalLink className="w-3 h-3" />
                  Im MaStR öffnen
                </a>
              )}
            </div>
          )}
          {/* Typ-spezifische Felder */}
          {typ === 'speicher' && (
            <Input
              label="Garantie-Zyklen"
              name="param_stamm_garantie_zyklen"
              type="number"
              value={paramData.stamm_garantie_zyklen as string || ''}
              onChange={onChange}
              placeholder="z.B. 6000"
              hint="Garantierte Ladezyklen"
            />
          )}
          {typ === 'pv-module' && (
            <Input
              label="Leistungsgarantie (%)"
              name="param_stamm_garantie_leistung_prozent"
              type="number"
              min="0"
              max="100"
              value={paramData.stamm_garantie_leistung_prozent as string || ''}
              onChange={onChange}
              placeholder="z.B. 80"
              hint="Garantierte Mindestleistung nach 25 Jahren"
            />
          )}
          {typ === 'e-auto' && (
            <>
              <Input
                label="Kennzeichen"
                name="param_stamm_kennzeichen"
                value={paramData.stamm_kennzeichen as string || ''}
                onChange={onChange}
                placeholder="z.B. M-EE 1234"
              />
              <Input
                label="Fahrgestellnummer (VIN)"
                name="param_stamm_fahrgestellnummer"
                value={paramData.stamm_fahrgestellnummer as string || ''}
                onChange={onChange}
                placeholder="z.B. WVWZZZ..."
              />
              <Input
                label="Erstzulassung"
                name="param_stamm_erstzulassung"
                type="date"
                value={paramData.stamm_erstzulassung as string || ''}
                onChange={onChange}
              />
              <Input
                label="Garantie Batterie (km)"
                name="param_stamm_garantie_batterie_km"
                type="number"
                value={paramData.stamm_garantie_batterie_km as string || ''}
                onChange={onChange}
                placeholder="z.B. 160000"
              />
            </>
          )}
          {(typ === 'waermepumpe' || typ === 'e-auto') && (
            <>
              <Input
                label="Förderung Aktenzeichen"
                name="param_stamm_foerderung_aktenzeichen"
                value={paramData.stamm_foerderung_aktenzeichen as string || ''}
                onChange={onChange}
                placeholder="z.B. BAFA-2024-12345"
              />
              <Input
                label="Förderbetrag (€)"
                name="param_stamm_foerderung_betrag_euro"
                type="number"
                value={paramData.stamm_foerderung_betrag_euro as string || ''}
                onChange={onChange}
                placeholder="z.B. 5000"
              />
            </>
          )}
          {typ === 'balkonkraftwerk' && (
            <>
              <Input
                label="Anmeldung Netzbetreiber"
                name="param_stamm_anmeldung_netzbetreiber"
                type="date"
                value={paramData.stamm_anmeldung_netzbetreiber as string || ''}
                onChange={onChange}
              />
              <Input
                label="Anmeldung MaStR"
                name="param_stamm_anmeldung_marktstammdaten"
                type="date"
                value={paramData.stamm_anmeldung_marktstammdaten as string || ''}
                onChange={onChange}
              />
            </>
          )}
        </div>
        <div>
          <Input
            label="Notizen"
            name="param_stamm_notizen"
            value={paramData.stamm_notizen as string || ''}
            onChange={onChange}
            placeholder="Optionale Anmerkungen zu diesem Gerät..."
          />
        </div>
      </div>

      {/* Ansprechpartner (klappbar) */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setShowAnsprechpartner(!showAnsprechpartner)}
          className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
        >
          <div className="flex items-center gap-2">
            {showAnsprechpartner ? (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-500" />
            )}
            <span className="text-sm font-medium text-gray-900 dark:text-white">Ansprechpartner</span>
            {kannVererben && !hasAnyAnsprechpartnerValue(paramData) && (
              <span className="text-xs text-gray-500 dark:text-gray-400">(erbt von {vererbungsQuelle})</span>
            )}
          </div>
        </button>
        {showAnsprechpartner && (
          <div className="p-4 space-y-4">
            {kannVererben && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
                <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  Leere Felder übernehmen automatisch die Werte von {vererbungsQuelle}.
                  Nur bei Abweichung ausfüllen.
                </p>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="Firma"
                name="param_ansprechpartner_firma"
                value={paramData.ansprechpartner_firma as string || ''}
                onChange={onChange}
                placeholder={anlage ? `(${vererbungsQuelle})` : 'z.B. Solar Mustermann GmbH'}
              />
              <Input
                label="Name"
                name="param_ansprechpartner_name"
                value={paramData.ansprechpartner_name as string || ''}
                onChange={onChange}
                placeholder="Kontaktperson"
              />
              <Input
                label="Telefon"
                name="param_ansprechpartner_telefon"
                value={paramData.ansprechpartner_telefon as string || ''}
                onChange={onChange}
                placeholder="+49 123 456789"
              />
              <Input
                label="E-Mail"
                name="param_ansprechpartner_email"
                type="email"
                value={paramData.ansprechpartner_email as string || ''}
                onChange={onChange}
                placeholder="service@beispiel.de"
              />
              <div className="md:col-span-2">
                <Input
                  label="Ticketsystem / Support-Portal"
                  name="param_ansprechpartner_ticketsystem"
                  value={paramData.ansprechpartner_ticketsystem as string || ''}
                  onChange={onChange}
                  placeholder="https://support.beispiel.de"
                />
                {paramData.ansprechpartner_ticketsystem && (
                  <a
                    href={paramData.ansprechpartner_ticketsystem as string}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Portal öffnen
                  </a>
                )}
              </div>
              <Input
                label="Kundennummer"
                name="param_ansprechpartner_kundennummer"
                value={paramData.ansprechpartner_kundennummer as string || ''}
                onChange={onChange}
                placeholder="z.B. K-12345"
              />
              <Input
                label="Vertragsnummer"
                name="param_ansprechpartner_vertragsnummer"
                value={paramData.ansprechpartner_vertragsnummer as string || ''}
                onChange={onChange}
                placeholder="z.B. V-2024-001"
              />
              <div className="md:col-span-2">
                <Input
                  label="Notizen"
                  name="param_ansprechpartner_notizen"
                  value={paramData.ansprechpartner_notizen as string || ''}
                  onChange={onChange}
                  placeholder="Optionale Anmerkungen..."
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Wartungsvertrag (klappbar) */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setShowWartung(!showWartung)}
          className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
        >
          <div className="flex items-center gap-2">
            {showWartung ? (
              <ChevronDown className="w-4 h-4 text-gray-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-500" />
            )}
            <span className="text-sm font-medium text-gray-900 dark:text-white">Wartungsvertrag</span>
            {kannVererben && !hasAnyWartungValue(paramData) && (
              <span className="text-xs text-gray-500 dark:text-gray-400">(erbt von {vererbungsQuelle})</span>
            )}
          </div>
        </button>
        {showWartung && (
          <div className="p-4 space-y-4">
            {kannVererben && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
                <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  Leere Felder übernehmen automatisch die Werte von {vererbungsQuelle}.
                  Nur bei Abweichung ausfüllen.
                </p>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                label="Vertragsnummer"
                name="param_wartung_vertragsnummer"
                value={paramData.wartung_vertragsnummer as string || ''}
                onChange={onChange}
                placeholder="z.B. WV-2024-001"
              />
              <Input
                label="Anbieter"
                name="param_wartung_anbieter"
                value={paramData.wartung_anbieter as string || ''}
                onChange={onChange}
                placeholder="z.B. Solar Mustermann GmbH"
              />
              <Input
                label="Gültig bis"
                name="param_wartung_gueltig_bis"
                type="date"
                value={paramData.wartung_gueltig_bis as string || ''}
                onChange={onChange}
              />
              <Input
                label="Kündigungsfrist"
                name="param_wartung_kuendigungsfrist"
                value={paramData.wartung_kuendigungsfrist as string || ''}
                onChange={onChange}
                placeholder="z.B. 3 Monate zum Jahresende"
              />
              <div className="md:col-span-2">
                <Input
                  label="Leistungsumfang"
                  name="param_wartung_leistungsumfang"
                  value={paramData.wartung_leistungsumfang as string || ''}
                  onChange={onChange}
                  placeholder="z.B. Jährliche Inspektion, Reinigung, Fernüberwachung"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function hasAnyAnsprechpartnerValue(paramData: Record<string, string | boolean>): boolean {
  const fields = [
    'ansprechpartner_firma', 'ansprechpartner_name', 'ansprechpartner_telefon',
    'ansprechpartner_email', 'ansprechpartner_ticketsystem', 'ansprechpartner_kundennummer',
    'ansprechpartner_vertragsnummer', 'ansprechpartner_notizen'
  ]
  return fields.some(f => paramData[f] && String(paramData[f]).trim() !== '')
}

function hasAnyWartungValue(paramData: Record<string, string | boolean>): boolean {
  const fields = [
    'wartung_vertragsnummer', 'wartung_anbieter', 'wartung_gueltig_bis',
    'wartung_kuendigungsfrist', 'wartung_leistungsumfang'
  ]
  return fields.some(f => paramData[f] && String(paramData[f]).trim() !== '')
}
