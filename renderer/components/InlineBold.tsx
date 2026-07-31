// Minimal inline-markdown rendering shared by the AI-activity surfaces (ADR-0028).
//
// Notification/activity bodies are markdown-ish (`**Status:** green`). Synapse has no
// markdown renderer, and raw `**` markers read as noise -- so honour just the one
// construct the projector emits (inline bold) and leave everything else verbatim.

export function renderInlineBold(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i} className='font-semibold text-foreground'>
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    )
  );
}
