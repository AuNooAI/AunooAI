import React from 'react'
import ReactDOM from 'react-dom/client'
import { OperationsHQ } from './pages/OperationsHQ'
import { ThemeProvider } from './components/ThemeProvider'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <OperationsHQ />
    </ThemeProvider>
  </React.StrictMode>,
)
