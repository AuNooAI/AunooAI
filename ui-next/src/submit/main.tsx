import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@aunoo/ui/styles.css';
import '../shell/phoneWrap.css';
import { SubmitArticles } from './SubmitArticles';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SubmitArticles />
  </StrictMode>,
);
