/**
 * Setup-Wizard Komponenten Export
 * v1.1.0 - Bereinigt (Discovery entfernt)
 */

export { default as SetupWizard } from './SetupWizard'

// Steps (für direkten Import falls benötigt)
export { default as WelcomeStep } from './steps/WelcomeStep'
export { default as AnlageStep } from './steps/AnlageStep'
export { default as HAConnectionStep } from './steps/HAConnectionStep'
export { default as StrompreiseStep } from './steps/StrompreiseStep'
export { default as InvestitionenStep } from './steps/InvestitionenStep'
export { default as SummaryStep } from './steps/SummaryStep'
export { default as CompleteStep } from './steps/CompleteStep'
