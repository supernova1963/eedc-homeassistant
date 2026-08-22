import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AppWithSetup from './components/AppWithSetup'
import './index.css'
import { ThemeProvider } from './context/ThemeContext'
import { SperreProvider } from './context/SperreContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <SperreProvider>
        <AppWithSetup>
          <App />
        </AppWithSetup>
      </SperreProvider>
    </ThemeProvider>
  </React.StrictMode>,
)
