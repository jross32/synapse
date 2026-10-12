import { ArrowUpRight, Bot, Boxes, Download, Monitor, Sparkles } from 'lucide-react';
import type { NavigationIntent } from '@shared/nav';
import './connected-brain-hero.css';
import { Brain3D } from './Brain3D';

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
      <div className='synapse-brain-hero__art'>
        <Brain3D activeCount={activeCount} onNavigate={onNavigate} />
      </div>
    </section>
  );
}
