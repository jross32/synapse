// Help popup for the "Import ChatGPT export" button (v0.1.36).
//
// Single source of truth for what the import feature is, why it
// exists, how to use it effectively, and what NOT to expect. Lives
// in its own file so the user-facing copy can be edited independently
// of the Apps page wiring.

import { Modal } from './ui/modal';

export interface ChatgptImportHelpProps {
  open: boolean;
  onClose: () => void;
}

export function ChatgptImportHelp({
  open,
  onClose,
}: ChatgptImportHelpProps): JSX.Element | null {
  if (!open) return null;
  return (
    <Modal
      open
      onClose={onClose}
      labelledBy='chatgpt-import-help-title'
      className='max-w-2xl'
    >
      <h2
        id='chatgpt-import-help-title'
        className='text-lg font-semibold'
      >
        Import ChatGPT export — how it works
      </h2>

      <section className='flex flex-col gap-2 text-sm'>
        <h3 className='text-sm font-semibold uppercase tracking-wide text-muted-foreground'>
          What it is
        </h3>
        <p>
          Synapse can ingest the official ChatGPT data export. Every
          conversation in the zip turns into a Markdown file under a
          dedicated project (<code className='font-mono'>imported-chatgpt</code>),
          so a Claude / Codex / Copilot session inside Synapse can read
          your prior chats as project files.
        </p>
      </section>

      <section className='flex flex-col gap-2 text-sm'>
        <h3 className='text-sm font-semibold uppercase tracking-wide text-muted-foreground'>
          How to get the export
        </h3>
        <ol className='ml-5 list-decimal space-y-1'>
          <li>
            In ChatGPT, click your profile picture →{' '}
            <strong>Settings</strong>.
          </li>
          <li>
            Open <strong>Data Controls</strong> → <strong>Export Data</strong> →{' '}
            <strong>Confirm export</strong>.
          </li>
          <li>
            OpenAI emails you a download link within a few minutes. The
            link expires in 24 hours.
          </li>
          <li>
            Download the <code className='font-mono'>.zip</code>. That's
            the file Synapse wants.
          </li>
        </ol>
      </section>

      <section className='flex flex-col gap-2 text-sm'>
        <h3 className='text-sm font-semibold uppercase tracking-wide text-muted-foreground'>
          How to use it effectively
        </h3>
        <ul className='ml-5 list-disc space-y-1'>
          <li>
            Click <strong>Import ChatGPT export</strong>, pick the zip.
            Re-importing the same zip is safe — duplicates are
            sha256-deduped and shown in a summary banner.
          </li>
          <li>
            Open the auto-created <code className='font-mono'>imported-chatgpt</code>{' '}
            project, hit <strong>Files</strong>, click any conversation
            to preview it in-app.
          </li>
          <li>
            Spawn a Claude session against that project (Apps tile →
            "Open in workbench"). The session sees the conversations as
            files under <code className='font-mono'>$SYNAPSE_FILES</code>.
            Ask it: <em>"summarise the most recent conversation about X"</em>{' '}
            and it can.
          </li>
          <li>
            Forked retries collapse to the branch ChatGPT was showing
            when you exported, not the abandoned attempts.
          </li>
        </ul>
      </section>

      <section className='flex flex-col gap-2 text-sm'>
        <h3 className='text-sm font-semibold uppercase tracking-wide text-muted-foreground'>
          What it is NOT
        </h3>
        <ul className='ml-5 list-disc space-y-1'>
          <li>
            <strong>Not a live link.</strong> One-shot ingest of the zip
            you just downloaded. Future ChatGPT messages don't sync in.
          </li>
          <li>
            <strong>Not browser scraping.</strong> Synapse never logs
            into your ChatGPT account or hits OpenAI APIs. The zip is
            the boundary; Contract #15 (no third-party network).
          </li>
          <li>
            <strong>Not an OpenAI feature.</strong> ChatGPT lives at
            OpenAI; Synapse is local. You're moving a copy of YOUR data
            from one place to another.
          </li>
        </ul>
      </section>

      <section className='flex flex-col gap-2 text-sm'>
        <h3 className='text-sm font-semibold uppercase tracking-wide text-muted-foreground'>
          Why it's here
        </h3>
        <p>
          The "second brain" use case: you've already had a long ChatGPT
          conversation on a topic, and you want a different CLI (Claude
          Code / Codex / Copilot) to read it before continuing. Import
          once, every future session in that project can reference it.
        </p>
      </section>
    </Modal>
  );
}
