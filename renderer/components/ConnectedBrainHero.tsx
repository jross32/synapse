import { ArrowUpRight, Bot, Boxes, Download, Monitor, Sparkles } from 'lucide-react';
import type { NavigationIntent } from '@shared/nav';
import './connected-brain-hero.css';

type ConnectedBrainHeroProps = {
  projectCount: number;
  activeCount: number;
  onNavigate: (intent: NavigationIntent) => void;
};

const nodes: ReadonlyArray<readonly [number, number, number]> = [
  [96, 116, 4], [121, 79, 5], [161, 66, 4], [199, 91, 5],
  [237, 64, 4], [271, 96, 5], [297, 131, 4], [262, 160, 5],
  [300, 199, 4], [250, 224, 5], [217, 261, 4], [168, 238, 5],
  [132, 261, 4], [108, 207, 5], [75, 180, 4], [148, 144, 5],
  [195, 174, 7], [229, 133, 5], [180, 209, 4], [136, 188, 4],
];

const strands = [
  'M96 116 Q125 90 161 66 Q197 68 237 64 Q269 71 297 131',
  'M75 180 Q103 140 121 79 Q156 113 199 91 Q257 100 271 96',
  'M96 116 Q154 112 148 144 Q168 167 195 174 Q233 168 262 160',
  'M108 207 Q138 178 148 144 Q176 119 229 133 Q263 172 300 199',
  'M132 261 Q146 209 136 188 Q170 197 195 174 Q214 218 217 261',
  'M168 238 Q189 206 180 209 Q227 227 250 224 Q289 218 300 199',
  'M121 79 Q142 139 136 188 Q116 226 132 261',
  'M237 64 Q219 113 229 133 Q239 183 250 224',
  'M199 91 Q202 126 195 174 Q188 220 217 261',
  'M161 66 Q152 105 148 144 Q133 167 108 207',
  'M271 96 Q244 133 262 160 Q272 181 300 199',
];

export function ConnectedBrainHero({ projectCount, activeCount, onNavigate }: ConnectedBrainHeroProps): JSX.Element {
  return (
    <section className='synapse-brain-hero' aria-labelledby='synapse-brain-title'>
      <div className='synapse-brain-hero__content'>
        <div className='synapse-brain-hero__eyebrow'><Sparkles size={13} aria-hidden='true' /> YOUR CONNECTED WORKSPACE</div>
        <h1 id='synapse-brain-title' className='synapse-brain-hero__title'>Your Connected <span>Brain</span></h1>
        <p className='synapse-brain-hero__summary'>
          Your AI assistants, tools, projects, and machines in one place.
          Pick up where you left off, from any connected device.
        </p>
        <div className='synapse-brain-hero__actions'>
          <button type='button' className='synapse-brain-hero__primary' onClick={() => onNavigate({ page: 'apps', section: 'projects' })}>
            Explore projects <ArrowUpRight size={16} aria-hidden='true' />
          </button>
          <button type='button' className='synapse-brain-hero__secondary' onClick={() => onNavigate({ page: 'updates' })}>
            <Download size={16} aria-hidden='true' /> Downloads &amp; updates
          </button>
        </div>
        <div className='synapse-brain-hero__quicklinks' aria-label='Synapse areas'>
          <button type='button' onClick={() => onNavigate({ page: 'ai-coding', section: 'sessions' })}><Bot size={16} aria-hidden='true' /> AI assistants</button>
          <button type='button' onClick={() => onNavigate({ page: 'tools' })}><Boxes size={16} aria-hidden='true' /> Connected tools</button>
          <button type='button' onClick={() => onNavigate({ page: 'settings' })}><Monitor size={16} aria-hidden='true' /> My machines</button>
        </div>
      </div>
      <div className='synapse-brain-hero__art' aria-hidden='true'>
        <div className='synapse-brain-hero__art-halo' />
        <svg className='synapse-brain-hero__neural-svg' viewBox='0 0 380 335' fill='none' role='presentation'>
          <defs>
            <linearGradient id='synapse-neural-line' x1='70' y1='70' x2='300' y2='265' gradientUnits='userSpaceOnUse'>
              <stop stopColor='var(--synapse-accent-glow)' />
              <stop offset='.52' stopColor='var(--synapse-accent)' />
              <stop offset='1' stopColor='var(--synapse-hero-pink)' />
            </linearGradient>
            <radialGradient id='synapse-neural-core'><stop stopColor='var(--synapse-accent-glow)' stopOpacity='.38' /><stop offset='1' stopColor='var(--synapse-accent)' stopOpacity='0' /></radialGradient>
          </defs>
          <circle cx='190' cy='164' r='149' fill='url(#synapse-neural-core)' />
          <path d='M136 261 C68 243 57 202 69 162 C53 118 82 76 122 70 C136 34 181 39 198 59 C242 30 276 55 283 89 C318 99 325 134 310 161 C332 199 295 241 252 246 C224 272 188 282 168 249' stroke='url(#synapse-neural-line)' strokeWidth='3' strokeLinecap='round' opacity='.92' />
          <path d='M191 60 Q176 103 195 144 Q211 172 190 214 Q183 239 217 261' stroke='url(#synapse-neural-line)' strokeWidth='2' opacity='.88' />
          <path d='M77 166 Q145 112 197 138 Q249 120 313 163 M86 204 Q155 181 198 201 Q260 179 296 210' stroke='url(#synapse-neural-line)' strokeWidth='1.3' opacity='.48' />
          {strands.map((d) => <path key={d} d={d} stroke='url(#synapse-neural-line)' strokeWidth='1.65' strokeLinecap='round' opacity='.66' />)}
          {nodes.map(([x,y,r],i) => (
            <g key={i}>
              <circle cx={x} cy={y} r={r+5} fill='var(--synapse-accent-glow)' opacity='.12' />
              <circle cx={x} cy={y} r={r} fill={i % 3 === 0 ? 'var(--synapse-hero-pink)' : 'var(--synapse-accent-glow)'} stroke='var(--synapse-bg-nucleus)' strokeWidth='1' />
            </g>
          ))}
          <path d='M76 180 C34 178 30 122 2 112 M298 132 C334 112 354 65 378 77 M251 224 C297 261 321 278 373 273 M133 261 C106 284 86 301 22 304' stroke='url(#synapse-neural-line)' strokeWidth='2' strokeLinecap='round' opacity='.48' />
        </svg>
        <div className='synapse-brain-hero__art-caption'>ONE WORKSPACE. ALL YOUR AI.</div>
        <div className='synapse-brain-hero__metric'><strong>{activeCount}</strong> running <span aria-hidden='true'>/</span> <strong>{projectCount}</strong> projects</div>
      </div>
    </section>
  );
}
