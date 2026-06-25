import React from 'react'
import ReactDOM from 'react-dom/client'
import { NewsFeedPage } from './pages/NewsFeedPage'
import { ThemeProvider } from './components/ThemeProvider'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <NewsFeedPage />
    </ThemeProvider>
  </React.StrictMode>,
)
