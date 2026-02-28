import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AppWithSetup from './components/AppWithSetup'
import './index.css'
import { ThemeProvider } from './context/ThemeContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <AppWithSetup>
        <App />
      </AppWithSetup>
    </ThemeProvider>
  </React.StrictMode>,
)
