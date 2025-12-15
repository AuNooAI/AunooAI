/**
 * PAM Dashboard Entry Point
 * Power, Attention & Money Analysis
 * v2.0 - Agent-based architecture with external data providers
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import PAMApp from './PAMApp'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PAMApp />
  </React.StrictMode>,
)
