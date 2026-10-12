import React from 'react';
export function SyncNeuralMark(): JSX.Element {
  return <svg className="syn-sync-neural-mark" viewBox="0 0 130 130" role="img" aria-label="Glowing Synapse neural emblem">
    <defs>
      <linearGradient id="syn-neural-cool" x1="0" y1="1" x2="1" y2="0"><stop stopColor="#18ceff"/><stop offset=".58" stopColor="#358fff"/><stop offset="1" stopColor="#a15eff"/></linearGradient>
      <filter id="syn-neural-glow" x="-65%" y="-65%" width="230%" height="230%"><feGaussianBlur stdDeviation="5"/></filter>
    </defs>
    <g fill="none" stroke="url(#syn-neural-cool)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.8" filter="url(#syn-neural-glow)" opacity=".74">
      <path d="M65 109V26C49 13 34 24 33 37c-16 2-21 18-13 28-6 15 2 28 14 29 4 17 18 20 31 15Zm0-83c12-12 32-8 34 9 16 4 19 19 12 30 8 18-3 30-15 31-5 13-17 19-31 13"/>
    </g>
    <g fill="none" stroke="url(#syn-neural-cool)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.8">
      <path d="M65 109V26C49 13 34 24 33 37c-16 2-21 18-13 28-6 15 2 28 14 29 4 17 18 20 31 15Zm0-83c12-12 32-8 34 9 16 4 19 19 12 30 8 18-3 30-15 31-5 13-17 19-31 13"/>
      <path d="M33 37c8-1 16 6 15 15m-28 13c12-4 22 1 25 13m-11 16c-5-13-3-21 10-24m5-42c-4 12-2 21 8 27m8 12c-15-9-24-1-23 9m23 24c-11-3-15-11-11-23m11-47v77m34-72c-10 1-16 9-13 19m25 11c-12-5-22-3-28 9m23 22c2-13-3-19-15-25m-16-36c10 10 12 22 1 32m-11 15c15-7 23 0 21 12m-21 10c13-3 18-10 15-23"/>
      <path d="M49 53c6 6 8 14 6 22m26-25c-4 8-4 18-1 25m-27 16c-7 6-8 12-5 16m36-16c7 6 8 12 4 16" opacity=".72"/>
    </g>
    <g fill="#8ddfff"><circle cx="49" cy="54" r="2.1"/><circle cx="81" cy="76" r="2.1"/><circle cx="45" cy="78" r="1.8"/><circle cx="89" cy="52" r="1.8"/></g>
  </svg>;
}
