import React from 'react';
import { createRoot } from 'react-dom/client';
import { DeviceSyncOnboarding } from './components/DeviceSyncOnboarding';

createRoot(document.getElementById('root')!).render(<DeviceSyncOnboarding signedIn accountId="qa-account" currentHostId="qa-desktop" />);
