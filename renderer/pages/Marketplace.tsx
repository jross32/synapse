// Marketplace hub (ADR-0017). One visual home for everything installable: tools,
// local models, MCP servers, AI workers (role + personality), and ready-made
// squads. Tools + Models reuse the existing browsers; the rest land in MW2-MW4.

import { useState } from 'react';
import { Boxes, Server, Users, UsersRound, Wrench, type LucideIcon } from 'lucide-react';

import { MarketplaceBrowser } from '../components/MarketplaceBrowser';
import { ModelBrowser } from '../components/ModelBrowser';
import { McpServerBrowser } from '../components/McpServerBrowser';
import { WorkerBrowser } from '../components/WorkerBrowser';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/ui/card';
import { cn } from '@shared/utils';

type Section = 'tools' | 'models' | 'mcp' | 'workers' | 'squads';

interface SectionDef {
  id: Section;
  label: string;
  icon: LucideIcon;
  blurb: string;
}

const SECTIONS: SectionDef[] = [
  { id: 'tools', label: 'Tools', icon: Wrench, blurb: 'One-tap launchers, editors, and dev utilities.' },
  { id: 'models', label: 'Models', icon: Boxes, blurb: 'Local LLMs for the assistant — download + manage.' },
  { id: 'mcp', label: 'MCP Servers', icon: Server, blurb: 'Connect tools + data sources your AI can use automatically.' },
  { id: 'workers', label: 'Workers', icon: Users, blurb: 'AI workers — a role plus a personality. Same role, different personality = real collaboration.' },
  { id: 'squads', label: 'Squad Presets', icon: UsersRound, blurb: 'Ready-made AI teams for common goals. Coming soon.' },
];

export function MarketplacePage(): JSX.Element {
  const [section, setSection] = useState<Section>('tools');

  return (
    <div className='flex h-full flex-col gap-4'>
      <PageHeader
        title='Marketplace'
        subtitle='Install tools, models, MCP servers, AI workers, and ready-made squads — your AI workforce, one tap away.'
      />

      <div className='flex flex-wrap gap-2'>
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const active = section === s.id;
          return (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              title={s.blurb}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'border-primary/40 bg-primary/10 text-foreground'
                  : 'border-border text-muted-foreground hover:bg-accent/60 hover:text-foreground'
              )}
            >
              <Icon className={cn('h-4 w-4', active ? 'text-primary' : 'text-current')} />
              {s.label}
            </button>
          );
        })}
      </div>

      <p className='text-sm text-muted-foreground'>{SECTIONS.find((s) => s.id === section)?.blurb}</p>

      {section === 'tools' && <MarketplaceBrowser />}
      {section === 'models' && <ModelBrowser />}
      {section === 'mcp' && <McpServerBrowser />}
      {section === 'workers' && <WorkerBrowser />}
      {section === 'squads' && (
        <ComingSoon
          icon={UsersRound}
          title='Squad Presets'
          lines={[
            'Pick a ready-made team for a goal — a UI/UX crew, an SEO sweep, a scraping pipeline, a security review.',
            'One tap drops the whole roster into the squad builder, pre-wired to the right tools + MCP servers.',
          ]}
        />
      )}
    </div>
  );
}

function ComingSoon({ icon: Icon, title, lines }: { icon: LucideIcon; title: string; lines: string[] }): JSX.Element {
  return (
    <Card className='mx-auto flex max-w-xl flex-col items-center gap-3 border-dashed p-8 text-center'>
      <Icon className='h-8 w-8 text-primary' />
      <h2 className='text-lg font-semibold'>{title}</h2>
      {lines.map((l) => (
        <p key={l} className='text-sm text-muted-foreground'>{l}</p>
      ))}
      <span className='rounded-full bg-secondary/50 px-3 py-1 text-xs text-muted-foreground'>Coming soon</span>
    </Card>
  );
}
