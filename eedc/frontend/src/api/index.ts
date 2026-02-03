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

// Re-export types
export type { ApiError } from './client'
export type { HealthResponse, SettingsResponse, StatsResponse } from './system'
export type { MonatsdatenCreate, MonatsdatenUpdate, MonatsdatenMitKennzahlen } from './monatsdaten'
export type { InvestitionCreate, InvestitionUpdate, InvestitionTypInfo, ROIBerechnung, ROIDashboardResponse } from './investitionen'
export type { StrompreisCreate, StrompreisUpdate } from './strompreise'
export type { CSVTemplateInfo } from './import'
