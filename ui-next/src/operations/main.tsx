import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@aunoo/ui/styles.css';
import '../shell/phoneWrap.css';
import { OperationsHQ } from './OperationsHQ';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <OperationsHQ />
  </StrictMode>,
);
