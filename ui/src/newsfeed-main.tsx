import React from 'react'
import ReactDOM from 'react-dom/client'
import { NewsFeedPage } from './pages/NewsFeedPage'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <NewsFeedPage />
  </React.StrictMode>,
)
