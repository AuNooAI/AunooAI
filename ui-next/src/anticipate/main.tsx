import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@aunoo/ui/styles.css';
import '../shell/phoneWrap.css';
import './lineItemsWrap.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
