import React from 'react';
import { createRoot } from 'react-dom/client';
import { FirstLaunchOnboarding } from './components/FirstLaunchOnboarding';
import './styles.css';
createRoot(document.getElementById('root')!).render(<FirstLaunchOnboarding onComplete={() => { document.body.dataset.completed = 'true'; }} />);
