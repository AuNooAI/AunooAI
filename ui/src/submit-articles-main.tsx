import React from 'react'
import ReactDOM from 'react-dom/client'
import SubmitArticlesApp from './SubmitArticlesApp'
import { ThemeProvider } from './components/ThemeProvider'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <SubmitArticlesApp />
    </ThemeProvider>
  </React.StrictMode>,
)
