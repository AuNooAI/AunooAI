import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@aunoo/ui/styles.css';
import '../shell/phoneWrap.css';
import { Explore } from './Explore';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Explore />
  </StrictMode>,
);
