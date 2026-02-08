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

// Re-export types
export type { ApiError } from './client'
export type { HealthResponse, SettingsResponse, StatsResponse } from './system'
export type { MonatsdatenCreate, MonatsdatenUpdate, MonatsdatenMitKennzahlen } from './monatsdaten'
export type { InvestitionCreate, InvestitionUpdate, InvestitionTypInfo, ROIKomponente, ROIBerechnung, ROIDashboardResponse } from './investitionen'
export type { StrompreisCreate, StrompreisUpdate } from './strompreise'
export type { CSVTemplateInfo, DemoDataResult } from './import'
export type { PVGISPrognose, GespeichertePrognose, AktivePrognoseResponse, PVGISOptimum } from './pvgis'
export type { HASensor, HAStatus, StringMonatsdaten, StringMonatsdatenCreate, HAImportResult, HAImportPreview, HAImportPreviewMonth, MonthlyStatistic, HAMonthlyDataResponse } from './ha'
