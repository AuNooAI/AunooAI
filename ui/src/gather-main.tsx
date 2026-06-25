import React from 'react'
import ReactDOM from 'react-dom/client'
import GatherApp from './GatherApp'
import { ThemeProvider } from './components/ThemeProvider'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <GatherApp />
    </ThemeProvider>
  </React.StrictMode>,
)
