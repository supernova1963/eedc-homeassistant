/**
 * API Module - Re-exports all API clients
 */

export { api } from './client'
export { anlagenApi } from './anlagen'
export { monatsdatenApi } from './monatsdaten'
export { investitionenApi } from './investitionen'
export { strompreiseApi } from './strompreise'
export { importApi } from './import'
export { systemApi } from './system'
export { pvgisApi } from './pvgis'
export { haApi } from './ha'
export { cockpitApi } from './cockpit'
export { wetterApi } from './wetter'
export { haImportApi } from './haImport'
export { sensorMappingApi } from './sensorMapping'
export { monatsabschlussApi } from './monatsabschluss'
export { haStatisticsApi } from './haStatistics'

// Re-export types
export type { ApiError } from './client'
export type { HealthResponse, SettingsResponse, StatsResponse } from './system'
export type { MonatsdatenCreate, MonatsdatenUpdate, MonatsdatenMitKennzahlen } from './monatsdaten'
export type { InvestitionCreate, InvestitionUpdate, InvestitionTypInfo, ROIKomponente, ROIBerechnung, ROIDashboardResponse } from './investitionen'
export type { StrompreisCreate, StrompreisUpdate } from './strompreise'
export type { CSVTemplateInfo, DemoDataResult } from './import'
export type { PVGISPrognose, GespeichertePrognose, AktivePrognoseResponse, PVGISOptimum } from './pvgis'
export type { HASensor, HAStatus, HASensorMapping } from './ha'
export type { CockpitUebersicht } from './cockpit'
export type { WetterDaten, StandortInfo } from './wetter'
export type { InvestitionMitFeldern, SensorFeld } from './haImport'
export type {
  StrategieTyp,
  FeldMapping,
  BasisMapping,
  InvestitionFelder,
  SensorMappingRequest,
  SensorMappingResponse,
  InvestitionInfo,
  HASensorInfo,
  SetupResult,
  MappingStatus,
} from './sensorMapping'
export type {
  Vorschlag,
  Warnung,
  FeldStatus,
  InvestitionStatus,
  MonatsabschlussResponse,
  MonatsabschlussInput,
  MonatsabschlussResult,
  NaechsterMonat,
  MonatHistorie,
  FeldWert,
  InvestitionWerte,
} from './monatsabschluss'
export type {
  HAStatisticsStatus,
  Monatswerte,
  VerfuegbarerMonat,
  AlleMonatswerte,
  MonatsanfangWerte,
  ImportAktion,
  MonatImportStatus,
  ImportVorschau,
  ImportRequest,
  ImportResult as HAImportResult,
} from './haStatistics'
