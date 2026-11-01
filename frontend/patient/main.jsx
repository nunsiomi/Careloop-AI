import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../shared/fonts.js';
import '../shared/base.css';
import './patient.css';
import { ToastProvider } from '../shared/ui.jsx';
import PatientApp from './App.jsx';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ToastProvider>
      <PatientApp />
    </ToastProvider>
  </StrictMode>
);
