import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import '../shared/fonts.js';
import '../shared/base.css';
import './clinician.css';
import { ToastProvider } from '../shared/ui.jsx';
import ClinicianApp from './App.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <HashRouter>
      <ToastProvider>
        <ClinicianApp />
      </ToastProvider>
    </HashRouter>
  </StrictMode>
);
