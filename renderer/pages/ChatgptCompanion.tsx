import {
  createElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ArrowUpRight,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  LogIn,
  Plus,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
} from 'lucide-react';

import { useDaemon } from '@shared/daemon-context';
import {
  hasElectronBridge,
  openExternal,
} from '@shared/electron-bridge';
import {
  downloadFile,
  listProjectFiles,
  uploadFiles,
} from '@shared/files-client';
import type { Project, ProjectFile } from '@shared/generated-types';
import { formatLocal } from '@shared/format-time';
import { cn } from '@shared/utils';
import {
  ChatWorkspaceShell,
  ChatWorkspaceTemplateGuide,
} from '../components/ChatWorkspaceTemplate';
import { PageHeader } from '../components/PageHeader';
import { ProjectFormDialog } from '../components/ProjectFormDialog';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Input } from '../components/ui/input';

const CHATGPT_HOME_URL = 'https://chatgpt.com/';
const CHATGPT_LOGIN_URL = 'https://chatgpt.com/auth/login';
const CHATGPT_WEBVIEW_PARTITION = 'persist:synapse-chatgpt';
const COMPANION_STATE_KEY = 'synapse.ai-coding.chatgpt-companion.v1';
const DEFAULT_ENTRY_TITLE = 'ChatGPT companion draft';
const DEFAULT_NOTES =
  'Use this for follow-ups, revision notes, or what you want Synapse to remember.';

interface CompanionDraftState {
  selectedProjectId: string;
  projectSelectionExplicit: boolean;
  title: string;
  prompt: string;
  response: string;
  notes: string;
}

interface ChatgptLinkItem {
  title: string;
  href: string;
  active: boolean;
  section: string | null;
  action?: 'url' | 'project-home';
  meta?: string | null;
}

interface ChatgptSourceItem {
  title: string;
  kind: string;
  updatedAt: string;
}

interface ChatgptMessage {
  role: 'assistant' | 'user' | 'system' | 'unknown';
  text: string;
}

interface ChatgptWorkspaceSnapshot {
  capturedAt: string;
  url: string;
  title: string;
  signedIn: boolean;
  authPrompt: string | null;
  composerPresent: boolean;
  pinned: ChatgptLinkItem[];
  projects: ChatgptLinkItem[];
  conversations: ChatgptLinkItem[];
  projectChats: ChatgptLinkItem[];
  projectSources: ChatgptSourceItem[];
  activeProjectTitle: string | null;
  activeProjectTab: string | null;
  otherLinks: ChatgptLinkItem[];
  latestMessages: ChatgptMessage[];
}

interface ChatgptComposerCommandResult {
  ok: boolean;
  filled?: boolean;
  sent?: boolean;
  error?: string;
}

interface ChatgptBridgeActionResult {
  ok: boolean;
  error?: string;
}

interface ChatgptWebviewElement extends HTMLElement {
  executeJavaScript<T>(code: string, userGesture?: boolean): Promise<T>;
  getTitle(): string;
  getURL(): string;
  goBack(): void;
  loadURL?(url: string): Promise<void> | void;
  reload(): void;
  src?: string;
}

function defaultCompanionDraftState(): CompanionDraftState {
  return {
    selectedProjectId: '',
    projectSelectionExplicit: false,
    title: DEFAULT_ENTRY_TITLE,
    prompt: '',
    response: '',
    notes: DEFAULT_NOTES,
  };
}

function readCompanionDraftState(): CompanionDraftState {
  const defaults = defaultCompanionDraftState();
  if (typeof window === 'undefined') return defaults;
  try {
    const raw = window.localStorage.getItem(COMPANION_STATE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<CompanionDraftState>;
    return {
      selectedProjectId:
        typeof parsed.selectedProjectId === 'string'
          ? parsed.selectedProjectId
          : defaults.selectedProjectId,
      projectSelectionExplicit:
        typeof parsed.projectSelectionExplicit === 'boolean'
          ? parsed.projectSelectionExplicit
          : defaults.projectSelectionExplicit,
      title: typeof parsed.title === 'string' ? parsed.title : defaults.title,
      prompt: typeof parsed.prompt === 'string' ? parsed.prompt : defaults.prompt,
      response:
        typeof parsed.response === 'string' ? parsed.response : defaults.response,
      notes: typeof parsed.notes === 'string' ? parsed.notes : defaults.notes,
    };
  } catch {
    return defaults;
  }
}

function persistCompanionDraftState(state: CompanionDraftState): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(COMPANION_STATE_KEY, JSON.stringify(state));
  } catch {
    /* local storage unavailable -- keep the workspace usable */
  }
}

function timestampSlug(): string {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function sanitizeTitle(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
}

function bestSnapshotTitle(snapshot: ChatgptWorkspaceSnapshot | null): string | null {
  if (!snapshot) return null;
  const activeProjectConversation = snapshot.projectChats.find((item) => item.active);
  if (activeProjectConversation?.title) return activeProjectConversation.title;
  const activeConversation = snapshot.conversations.find((item) => item.active);
  if (activeConversation?.title) return activeConversation.title;
  const cleaned = snapshot.title.replace(/\s*\|\s*ChatGPT.*$/i, '').trim();
  return cleaned.length > 0 ? cleaned : null;
}

function hasUsableEmbeddedWebview(
  view: ChatgptWebviewElement | null
): view is ChatgptWebviewElement {
  return (
    !!view &&
    typeof view.executeJavaScript === 'function' &&
    typeof view.reload === 'function'
  );
}

function readEmbeddedWebviewUrl(view: ChatgptWebviewElement | null): string {
  if (view && typeof view.getURL === 'function') {
    try {
      const url = view.getURL();
      if (url) return url;
    } catch {
      /* fall through to src/current default */
    }
  }
  return view?.getAttribute('src') || view?.src || CHATGPT_HOME_URL;
}

function readEmbeddedWebviewTitle(view: ChatgptWebviewElement | null): string {
  if (view && typeof view.getTitle === 'function') {
    try {
      const title = view.getTitle();
      if (title) return title;
    } catch {
      /* fall through to default */
    }
  }
  return 'ChatGPT';
}

async function navigateEmbeddedWebview(
  view: ChatgptWebviewElement,
  url: string
): Promise<void> {
  if (typeof view.loadURL === 'function') {
    await Promise.resolve(view.loadURL(url));
    return;
  }
  view.setAttribute('src', url);
  try {
    view.src = url;
  } catch {
    /* some hosts expose src as a read-only upgraded property */
  }
}

async function reloadEmbeddedWebview(view: ChatgptWebviewElement): Promise<void> {
  if (typeof view.reload === 'function') {
    try {
      view.reload();
      return;
    } catch {
      /* fall through to src reload */
    }
  }
  await navigateEmbeddedWebview(view, readEmbeddedWebviewUrl(view));
}

function linkTargetSummary(item: ChatgptLinkItem): string {
  if (item.action === 'project-home') {
    return item.meta || 'Project home in ChatGPT';
  }
  return item.href || item.meta || 'Visible ChatGPT item';
}

function renderSources(sources: ChatgptSourceItem[]): string[] {
  if (sources.length === 0) {
    return ['## Current project files', '', '_No project files were visible at capture time._', ''];
  }
  return [
    '## Current project files',
    '',
    ...sources.map((item) => {
      const detail = [item.kind, item.updatedAt].filter(Boolean).join(' - ');
      return `- ${item.title}${detail ? ` (${detail})` : ''}`;
    }),
    '',
  ];
}

function buildCompanionMarkdown(args: {
  project: Project;
  title: string;
  prompt: string;
  response: string;
  notes: string;
  snapshot: ChatgptWorkspaceSnapshot | null;
}): string {
  const { project, title, prompt, response, notes, snapshot } = args;
  return [
    '# ChatGPT Companion Entry',
    '',
    `- Project: ${project.name} (\`${project.id}\`)`,
    `- Saved at: ${new Date().toISOString()}`,
    `- ChatGPT page: ${snapshot?.url ?? CHATGPT_HOME_URL}`,
    `- Browser login: managed by the Synapse desktop ChatGPT bridge`,
    `- Active ChatGPT project: ${snapshot?.activeProjectTitle ?? 'unknown'}`,
    `- Active ChatGPT tab: ${snapshot?.activeProjectTab ?? 'unknown'}`,
    `- Visible project chats: ${snapshot?.projectChats.length ?? 0}`,
    `- Visible project files: ${snapshot?.projectSources.length ?? 0}`,
    '',
    `## ${title.trim() || 'Untitled exchange'}`,
    '',
    '### Prompt',
    '',
    prompt.trim() || '_No prompt captured._',
    '',
    '### Response',
    '',
    response.trim() || '_No response captured yet._',
    '',
    '### Notes',
    '',
    notes.trim() || '_No notes._',
    '',
  ].join('\n');
}

function buildWorkspaceSnapshotMarkdown(args: {
  project: Project;
  snapshot: ChatgptWorkspaceSnapshot;
}): string {
  const { project, snapshot } = args;

  function renderLinks(label: string, items: ChatgptLinkItem[]): string[] {
    if (items.length === 0) {
      return [`## ${label}`, '', '_None visible at capture time._', ''];
    }
    return [
      `## ${label}`,
      '',
      ...items.map((item) => {
        const state = item.active ? 'active' : 'available';
        return `- ${item.title} (${state}) - ${linkTargetSummary(item)}`;
      }),
      '',
    ];
  }

  function renderMessages(messages: ChatgptMessage[]): string[] {
    if (messages.length === 0) {
      return ['## Latest visible messages', '', '_No messages were visible in the current view._', ''];
    }
    const lines: string[] = ['## Latest visible messages', ''];
    for (const message of messages) {
      lines.push(`### ${message.role}`);
      lines.push('');
      lines.push(message.text || '_Empty message._');
      lines.push('');
    }
    return lines;
  }

  return [
    '# ChatGPT Live Workspace Snapshot',
    '',
    `- Project: ${project.name} (\`${project.id}\`)`,
    `- Captured at: ${snapshot.capturedAt}`,
    `- URL: ${snapshot.url}`,
    `- Page title: ${snapshot.title}`,
    `- Signed in: ${snapshot.signedIn ? 'yes' : 'no'}`,
    `- Composer visible: ${snapshot.composerPresent ? 'yes' : 'no'}`,
    `- Active project: ${snapshot.activeProjectTitle ?? 'none'}`,
    `- Active project tab: ${snapshot.activeProjectTab ?? 'none'}`,
    '',
    ...renderLinks('Pinned', snapshot.pinned),
    ...renderLinks('Projects', snapshot.projects),
    ...renderLinks('Conversations', snapshot.conversations),
    ...renderLinks('Current project chats', snapshot.projectChats),
    ...renderSources(snapshot.projectSources),
    ...renderLinks('Other visible sidebar links', snapshot.otherLinks),
    ...renderMessages(snapshot.latestMessages),
  ].join('\n');
}

function recentCompanionFiles(files: ProjectFile[]): ProjectFile[] {
  return [...files]
    .filter((file) => file.original_name.startsWith('chatgpt-'))
    .sort((left, right) => right.uploaded_at.localeCompare(left.uploaded_at))
    .slice(0, 12);
}

async function fetchRecentCompanionFiles(projectId: string): Promise<ProjectFile[]> {
  const files = await listProjectFiles(projectId);
  return recentCompanionFiles(files);
}

function buildWorkspaceExtractionScript(): string {
  return String.raw`(() => {
    const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const isVisible = (element) => {
      if (!element || typeof element.getBoundingClientRect !== 'function') return false;
      const style = window.getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const absoluteUrl = (href) => {
      try {
        return new URL(href, window.location.href).toString();
      } catch {
        return href;
      }
    };
    const previousHeadingText = (element) => {
      let current = element.parentElement;
      while (current) {
        const children = Array.from(current.children);
        const index = children.findIndex((child) => child.contains(element));
        for (let i = index - 1; i >= 0; i -= 1) {
          const candidate = normalize(children[i].textContent || '');
          if (candidate && candidate.length <= 80) return candidate;
        }
        current = current.parentElement;
      }
      return null;
    };
    const nearestSectionLabel = (element) => {
      const labelled = element.closest('[aria-label], [aria-labelledby]');
      if (labelled instanceof HTMLElement) {
        const ariaLabel = normalize(labelled.getAttribute('aria-label') || '');
        if (ariaLabel) return ariaLabel;
        const labelledBy = labelled.getAttribute('aria-labelledby');
        if (labelledBy) {
          const target = document.getElementById(labelledBy);
          const text = normalize(target?.textContent || '');
          if (text) return text;
        }
      }
      return previousHeadingText(element);
    };
    const inferSourceKind = (title) => {
      const extension = title.includes('.') ? title.split('.').pop().toLowerCase() : '';
      if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(extension)) return 'Image';
      if (['csv', 'json', 'yaml', 'yml', 'xml'].includes(extension)) return 'Data';
      if (['md', 'txt', 'rtf', 'doc', 'docx', 'pdf'].includes(extension)) return 'Document';
      if (['py', 'ts', 'tsx', 'js', 'jsx', 'html', 'css', 'sql', 'sh'].includes(extension)) return 'Code';
      return 'File';
    };
    const linkMap = new Map();
    for (const anchor of Array.from(document.querySelectorAll('a[href]'))) {
      if (!anchor || !isVisible(anchor)) continue;
      const text = normalize(anchor.textContent || anchor.getAttribute('aria-label') || '');
      if (!text) continue;
      const href = absoluteUrl(anchor.href);
      if (!href.startsWith('http')) continue;
      if (linkMap.has(href)) continue;
      linkMap.set(href, {
        title: text,
        href,
        active: anchor.getAttribute('aria-current') === 'page',
        section: nearestSectionLabel(anchor),
        action: 'url',
        meta: null,
      });
    }
    const links = Array.from(linkMap.values());
    const projectRows = Array.from(
      document.querySelectorAll('div[role="button"][data-sidebar-item="true"][aria-controls]')
    )
      .filter((element) => isVisible(element))
      .map((element) => ({
        title: normalize(element.textContent || element.getAttribute('aria-label') || ''),
        controls: element.getAttribute('aria-controls') || '',
        expanded: element.getAttribute('aria-expanded') === 'true',
      }))
      .filter((item) => item.title)
      .slice(0, 18);
    const projectTitleFromPage = /\/project\b/i.test(window.location.pathname)
      ? normalize((document.title || '').replace(/^ChatGPT\s*-\s*/i, ''))
      : '';
    const activeProjectTitle =
      projectRows.find((item) => item.expanded)?.title || projectTitleFromPage || null;
    const activeProjectRow =
      projectRows.find((item) => item.title === activeProjectTitle) || null;
    const pinned = links
      .filter((item) => normalize(item.section || '').toLowerCase().includes('pinned'))
      .slice(0, 18);
    const projectChats = activeProjectRow && activeProjectRow.controls
      ? Array.from(
          document.getElementById(activeProjectRow.controls)?.querySelectorAll('a[href]') || []
        )
          .filter((anchor) => isVisible(anchor))
          .map((anchor) => ({
            title: normalize(anchor.textContent || anchor.getAttribute('aria-label') || ''),
            href: absoluteUrl(anchor.href),
            active: anchor.getAttribute('aria-current') === 'page',
            section: activeProjectRow.title,
            action: 'url',
            meta: 'Project chat',
          }))
          .filter((item) => item.title && item.href.startsWith('http'))
          .slice(0, 18)
      : [];
    const conversations = links
      .filter((item) => /\/c\/[a-z0-9-]+/i.test(item.href))
      .slice(0, 18);
    const fallbackProjectLinks = links
      .filter((item) => {
        const section = normalize(item.section || '').toLowerCase();
        const text = item.title.toLowerCase();
        return (
          /\/projects?\b/i.test(item.href) ||
          section.includes('project') ||
          /^project\b/.test(text)
        );
      })
      .slice(0, 18);
    const projects = projectRows.length > 0
      ? projectRows.map((item) => ({
          title: item.title,
          href: '',
          active: item.title === activeProjectTitle,
          section: 'Projects',
          action: 'project-home',
          meta: item.expanded ? 'Open project home - expanded in sidebar' : 'Open project home',
        }))
      : fallbackProjectLinks;
    const sourceSurface = document.querySelector('section[data-project-home-sources-surface="true"]');
    const activeProjectTab = sourceSurface
      ? 'sources'
      : /\/project\b/i.test(window.location.pathname)
        ? new URL(window.location.href).searchParams.get('tab') || 'project home'
        : null;
    const projectSources = sourceSurface
      ? Array.from(sourceSurface.querySelectorAll('[aria-label]'))
          .filter((element) => isVisible(element))
          .map((element) => {
            const title = normalize(element.getAttribute('aria-label') || '');
            const detailsContainer = element.parentElement?.parentElement || element.parentElement;
            const detailText = normalize(
              detailsContainer?.querySelector('.text-token-text-secondary')?.textContent || ''
            );
            if (
              !title ||
              title === 'Source actions' ||
              (!detailText && !/\.[a-z0-9]{1,8}$/i.test(title))
            ) {
              return null;
            }
            const [kind = inferSourceKind(title), updatedAt = ''] = detailText
              .split('·')
              .map((item) => normalize(item))
              .filter(Boolean);
            return {
              title,
              kind,
              updatedAt,
            };
          })
          .filter(Boolean)
          .slice(0, 30)
      : [];
    const reserved = new Set(
      [...pinned, ...conversations, ...fallbackProjectLinks, ...projectChats]
        .map((item) => item.href)
        .filter(Boolean)
    );
    const otherLinks = links.filter((item) => !reserved.has(item.href)).slice(0, 18);
    const messageCandidates = [];
    for (const element of Array.from(document.querySelectorAll('[data-message-author-role], article'))) {
      if (!isVisible(element)) continue;
      const text = normalize(element.innerText || '');
      if (!text) continue;
      const rawRole =
        normalize(element.getAttribute('data-message-author-role') || '').toLowerCase() ||
        normalize(element.getAttribute('aria-label') || '').toLowerCase();
      let role = 'unknown';
      if (rawRole.includes('assistant') || rawRole.includes('chatgpt')) role = 'assistant';
      else if (rawRole.includes('user') || rawRole.includes('you')) role = 'user';
      else if (rawRole.includes('system')) role = 'system';
      messageCandidates.push({ role, text: text.slice(0, 12000) });
    }
    const latestMessages = [];
    const seenTexts = new Set();
    for (const item of messageCandidates.reverse()) {
      if (seenTexts.has(item.text)) continue;
      seenTexts.add(item.text);
      latestMessages.unshift(item);
      if (latestMessages.length >= 6) break;
    }
    const composerPresent = Array.from(
      document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]')
    ).some((element) => isVisible(element));
    const authPrompt = Array.from(document.querySelectorAll('button, a'))
      .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || ''))
      .find((text) =>
        /log in|sign in|sign up|continue with apple|continue with google|continue with email|get started/i.test(text)
      ) || null;
    const signedIn =
      !window.location.pathname.startsWith('/auth') &&
      (
        composerPresent ||
        pinned.length > 0 ||
        conversations.length > 0 ||
        projects.length > 0 ||
        authPrompt === null
      );
    return {
      capturedAt: new Date().toISOString(),
      url: window.location.href,
      title: document.title || 'ChatGPT',
      signedIn,
      authPrompt,
      composerPresent,
      pinned,
      projects,
      conversations,
      projectChats,
      projectSources,
      activeProjectTitle,
      activeProjectTab,
      otherLinks,
      latestMessages,
    };
  })()`;
}

function buildComposerScript(prompt: string, sendNow: boolean): string {
  return `(() => {
    const promptValue = ${JSON.stringify(prompt)};
    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
    const isVisible = (element) => {
      if (!(element instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const candidates = Array.from(
      document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]')
    ).filter((element) => element instanceof HTMLElement && isVisible(element));
    const target = candidates.at(-1);
    if (!(target instanceof HTMLElement)) {
      return { ok: false, error: 'No visible ChatGPT composer was found on the current screen.' };
    }
    if (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) {
      const descriptor = Object.getOwnPropertyDescriptor(
        Object.getPrototypeOf(target),
        'value'
      );
      descriptor?.set?.call(target, promptValue);
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      target.focus();
      target.textContent = promptValue;
      target.dispatchEvent(new InputEvent('input', {
        bubbles: true,
        data: promptValue,
        inputType: 'insertText',
      }));
    }
    if (!${sendNow ? 'true' : 'false'}) {
      return { ok: true, filled: true, sent: false };
    }
    const sendButton = Array.from(document.querySelectorAll('button')).find((button) => {
      if (!(button instanceof HTMLButtonElement) || button.disabled || !isVisible(button)) return false;
      const combined = normalize(
        button.getAttribute('aria-label') || button.getAttribute('title') || button.textContent || ''
      ).toLowerCase();
      return /send|submit/i.test(combined);
    });
    if (!(sendButton instanceof HTMLButtonElement)) {
      return {
        ok: false,
        filled: true,
        sent: false,
        error: 'The prompt was filled in, but the send control could not be found automatically.',
      };
    }
    sendButton.click();
    return { ok: true, filled: true, sent: true };
  })()`;
}

function buildOpenProjectHomeScript(projectTitle: string): string {
  return `(() => {
    const targetTitle = ${JSON.stringify(projectTitle)};
    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
    const buttons = Array.from(
      document.querySelectorAll('button[aria-label="Open project home"]')
    );
    const exactMatch = buttons.find((button) => {
      const context = normalize(
        button.parentElement?.parentElement?.textContent ||
        button.parentElement?.textContent ||
        ''
      );
      return context === targetTitle;
    });
    const partialMatch = buttons.find((button) => {
      const context = normalize(
        button.parentElement?.parentElement?.textContent ||
        button.parentElement?.textContent ||
        ''
      );
      return context.startsWith(targetTitle + ' ');
    });
    const target = exactMatch || partialMatch || null;
    if (!target) {
      return {
        ok: false,
        error: 'Could not find that ChatGPT project in the current sidebar view.',
      };
    }
    target.click();
    return { ok: true };
  })()`;
}

export interface ChatgptCompanionPageProps {
  headerless?: boolean;
}

export function ChatgptCompanionPage({
  headerless = false,
}: ChatgptCompanionPageProps): JSX.Element {
  const { projects, refreshProjects, upsertProjectLocal } = useDaemon();
  const initialDraft = useMemo(() => readCompanionDraftState(), []);
  const liveBridgeAvailable = hasElectronBridge();
  const webviewRef = useRef<ChatgptWebviewElement | null>(null);
  const captureTimerRef = useRef<number | null>(null);

  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    initialDraft.selectedProjectId
  );
  const [projectSelectionExplicit, setProjectSelectionExplicit] = useState(
    initialDraft.projectSelectionExplicit
  );
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [title, setTitle] = useState(initialDraft.title);
  const [prompt, setPrompt] = useState(initialDraft.prompt);
  const [response, setResponse] = useState(initialDraft.response);
  const [notes, setNotes] = useState(initialDraft.notes);
  const [workspaceNotice, setWorkspaceNotice] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [bridgeNotice, setBridgeNotice] = useState<string | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [recentFiles, setRecentFiles] = useState<ProjectFile[]>([]);
  const [bridgeBusy, setBridgeBusy] = useState<string | null>(null);
  const [bridgeLoading, setBridgeLoading] = useState(liveBridgeAvailable);
  const [bridgeSnapshot, setBridgeSnapshot] =
    useState<ChatgptWorkspaceSnapshot | null>(null);
  const [bridgeUrl, setBridgeUrl] = useState(CHATGPT_HOME_URL);
  const [bridgeTitle, setBridgeTitle] = useState('ChatGPT');

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [projects]
  );

  const selectedProject = useMemo(
    () =>
      sortedProjects.find((project) => project.id === selectedProjectId) ?? null,
    [selectedProjectId, sortedProjects]
  );

  const visibleStatusTone = bridgeSnapshot?.signedIn
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    : 'border-amber-500/30 bg-amber-500/10 text-amber-100';

  const refreshRecent = useCallback(async (projectId: string) => {
    setLoadingFiles(true);
    try {
      const files = await fetchRecentCompanionFiles(projectId);
      setRecentFiles(files);
      setWorkspaceError(null);
    } catch (err) {
      setWorkspaceError(
        (err as Error).message || 'Could not load saved companion entries.'
      );
      throw err;
    } finally {
      setLoadingFiles(false);
    }
  }, []);

  const scheduleBridgeCapture = useCallback((delayMs = 400) => {
    if (!liveBridgeAvailable || typeof window === 'undefined') return;
    if (captureTimerRef.current !== null) {
      window.clearTimeout(captureTimerRef.current);
    }
    captureTimerRef.current = window.setTimeout(() => {
      void refreshBridgeSnapshot();
    }, delayMs);
  }, [liveBridgeAvailable]);

  const refreshBridgeSnapshot = useCallback(
    async (captureLatestReply = false): Promise<ChatgptWorkspaceSnapshot | null> => {
      const view = webviewRef.current;
      if (!liveBridgeAvailable || !hasUsableEmbeddedWebview(view)) {
        if (captureLatestReply) {
          setBridgeError(
            'The live ChatGPT bridge is only available once the desktop webview is ready.'
          );
        }
        return null;
      }
      setBridgeBusy(captureLatestReply ? 'capture-reply' : 'capture');
      try {
        const snapshot = await view.executeJavaScript<ChatgptWorkspaceSnapshot>(
          buildWorkspaceExtractionScript(),
          true
        );
        setBridgeSnapshot(snapshot);
        setBridgeUrl(snapshot.url);
        setBridgeTitle(snapshot.title || 'ChatGPT');
        setBridgeError(null);
        if ((title.trim() === '' || title === DEFAULT_ENTRY_TITLE) && bestSnapshotTitle(snapshot)) {
          setTitle(bestSnapshotTitle(snapshot) ?? DEFAULT_ENTRY_TITLE);
        }
        if (captureLatestReply) {
          const assistantReply = [...snapshot.latestMessages]
            .reverse()
            .find((message) => message.role === 'assistant');
          if (assistantReply?.text) {
            setResponse(assistantReply.text);
            setWorkspaceNotice('Captured the latest visible ChatGPT reply into the response box.');
            setWorkspaceError(null);
          } else {
            setWorkspaceError(
              'The page refreshed, but no visible assistant reply was found on the current screen.'
            );
          }
        }
        return snapshot;
      } catch (err) {
        setBridgeError((err as Error).message || 'Could not inspect the ChatGPT page.');
        return null;
      } finally {
        setBridgeBusy(null);
      }
    },
    [liveBridgeAvailable, title]
  );

  useEffect(() => {
    const selectedProjectExists =
      selectedProjectId.length > 0 &&
      sortedProjects.some((project) => project.id === selectedProjectId);

    if (selectedProjectExists && projectSelectionExplicit) {
      return;
    }
    if (sortedProjects.length === 1) {
      const onlyProjectId = sortedProjects[0]!.id;
      if (selectedProjectId !== onlyProjectId || projectSelectionExplicit) {
        setSelectedProjectId(onlyProjectId);
        setProjectSelectionExplicit(false);
      }
      return;
    }
    if (selectedProjectId !== '' || projectSelectionExplicit) {
      setSelectedProjectId('');
      setProjectSelectionExplicit(false);
    }
  }, [projectSelectionExplicit, selectedProjectId, sortedProjects]);

  useEffect(() => {
    if (!selectedProjectId) {
      setRecentFiles([]);
      return;
    }
    let cancelled = false;
    setLoadingFiles(true);
    fetchRecentCompanionFiles(selectedProjectId)
      .then((files) => {
        if (cancelled) return;
        setRecentFiles(files);
        setWorkspaceError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setWorkspaceError(
          (err as Error).message || 'Could not load saved companion entries.'
        );
      })
      .finally(() => {
        if (cancelled) return;
        setLoadingFiles(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    persistCompanionDraftState({
      selectedProjectId,
      projectSelectionExplicit,
      title,
      prompt,
      response,
      notes,
    });
  }, [
    notes,
    projectSelectionExplicit,
    prompt,
    response,
    selectedProjectId,
    title,
  ]);

  useEffect(() => {
    if (!liveBridgeAvailable) return;
    const view = webviewRef.current;
    if (!view) return;

    const onDidStartLoading = (): void => {
      setBridgeLoading(true);
    };
    const onDomReady = (): void => {
      setBridgeLoading(false);
      setBridgeError(null);
      setBridgeUrl(readEmbeddedWebviewUrl(view));
      setBridgeTitle(readEmbeddedWebviewTitle(view));
      scheduleBridgeCapture(300);
    };
    const onDidNavigate = (): void => {
      setBridgeLoading(false);
      setBridgeUrl(readEmbeddedWebviewUrl(view));
      setBridgeTitle(readEmbeddedWebviewTitle(view));
      scheduleBridgeCapture(350);
    };
    const onDidFailLoad = (event: Event): void => {
      const errorEvent = event as Event & {
        errorCode?: number;
        errorDescription?: string;
      };
      if (errorEvent.errorCode === -3) return;
      setBridgeLoading(false);
      setBridgeError(
        errorEvent.errorDescription || 'Could not load the ChatGPT bridge.'
      );
    };

    view.addEventListener('did-start-loading', onDidStartLoading as EventListener);
    view.addEventListener('dom-ready', onDomReady as EventListener);
    view.addEventListener('did-navigate', onDidNavigate as EventListener);
    view.addEventListener('did-navigate-in-page', onDidNavigate as EventListener);
    view.addEventListener('did-stop-loading', onDidNavigate as EventListener);
    view.addEventListener('did-fail-load', onDidFailLoad as EventListener);

    return () => {
      view.removeEventListener(
        'did-start-loading',
        onDidStartLoading as EventListener
      );
      view.removeEventListener('dom-ready', onDomReady as EventListener);
      view.removeEventListener('did-navigate', onDidNavigate as EventListener);
      view.removeEventListener(
        'did-navigate-in-page',
        onDidNavigate as EventListener
      );
      view.removeEventListener(
        'did-stop-loading',
        onDidNavigate as EventListener
      );
      view.removeEventListener('did-fail-load', onDidFailLoad as EventListener);
    };
  }, [liveBridgeAvailable, scheduleBridgeCapture]);

  useEffect(() => {
    return () => {
      if (captureTimerRef.current !== null && typeof window !== 'undefined') {
        window.clearTimeout(captureTimerRef.current);
      }
    };
  }, []);

  async function copyPrompt(): Promise<void> {
    try {
      await navigator.clipboard.writeText(prompt);
      setWorkspaceNotice(
        'Prompt copied. Paste it into ChatGPT or use Fill composer in the live bridge.'
      );
      setWorkspaceError(null);
    } catch (err) {
      setWorkspaceError((err as Error).message || 'Could not copy the prompt.');
    }
  }

  async function openChatgpt(url: string): Promise<void> {
    try {
      const result = await openExternal(url);
      if (!result.ok) {
        setBridgeError(result.error || 'Could not open ChatGPT.');
        return;
      }
      setBridgeNotice(
        url === CHATGPT_LOGIN_URL
          ? 'ChatGPT sign-in page opened in your browser.'
          : 'ChatGPT opened in your browser.'
      );
      setBridgeError(null);
    } catch (err) {
      setBridgeError((err as Error).message || 'Could not open ChatGPT.');
    }
  }

  async function navigateBridge(url: string): Promise<void> {
    const view = webviewRef.current;
    if (!liveBridgeAvailable || !view) {
      await openChatgpt(url);
      return;
    }
    setBridgeLoading(true);
    setBridgeNotice(null);
    setBridgeError(null);
    try {
      await navigateEmbeddedWebview(view, url);
    } catch (err) {
      setBridgeLoading(false);
      setBridgeError((err as Error).message || 'Could not open that ChatGPT page.');
    }
  }

  async function openProjectHomeInBridge(projectTitle: string): Promise<void> {
    const view = webviewRef.current;
    if (!liveBridgeAvailable || !hasUsableEmbeddedWebview(view)) {
      setBridgeError('The live ChatGPT bridge is only available once the desktop webview is ready.');
      return;
    }
    setBridgeBusy('open-project-home');
    setBridgeError(null);
    setBridgeNotice(null);
    try {
      const result = await view.executeJavaScript<ChatgptBridgeActionResult>(
        buildOpenProjectHomeScript(projectTitle),
        true
      );
      if (!result.ok) {
        setBridgeError(result.error || 'Could not open that ChatGPT project.');
        return;
      }
      setBridgeNotice(`Opened ${projectTitle} inside the ChatGPT bridge.`);
      scheduleBridgeCapture(1200);
    } catch (err) {
      setBridgeError((err as Error).message || 'Could not open that ChatGPT project.');
    } finally {
      setBridgeBusy(null);
    }
  }

  async function openIndexedItem(item: ChatgptLinkItem): Promise<void> {
    if (item.action === 'project-home') {
      await openProjectHomeInBridge(item.title);
      return;
    }
    await navigateBridge(item.href);
  }

  async function sendPromptToBridge(sendNow: boolean): Promise<void> {
    if (!prompt.trim()) {
      setWorkspaceError('Write a prompt first so Synapse has something to send.');
      return;
    }
    const view = webviewRef.current;
    if (!liveBridgeAvailable || !hasUsableEmbeddedWebview(view)) {
      setBridgeError('The live ChatGPT bridge is only available once the desktop webview is ready.');
      return;
    }
    setBridgeBusy(sendNow ? 'send-prompt' : 'fill-prompt');
    try {
      const result = await view.executeJavaScript<ChatgptComposerCommandResult>(
        buildComposerScript(prompt, sendNow),
        true
      );
      if (!result.ok) {
        setBridgeError(result.error || 'Could not place the prompt into ChatGPT.');
        if (result.filled) {
          setBridgeNotice(
            'The prompt was filled in, but you may need to press send yourself.'
          );
        }
        return;
      }
      setBridgeNotice(
        result.sent
          ? 'Prompt sent into the current ChatGPT conversation.'
          : 'Prompt placed into the current ChatGPT composer.'
      );
      setBridgeError(null);
      scheduleBridgeCapture(result.sent ? 1600 : 450);
    } catch (err) {
      setBridgeError(
        (err as Error).message || 'Could not talk to the ChatGPT composer.'
      );
    } finally {
      setBridgeBusy(null);
    }
  }

  async function saveCompanionEntry(): Promise<void> {
    if (!selectedProject) {
      setWorkspaceError('Choose a project before saving this companion exchange.');
      return;
    }
    if (!prompt.trim() && !response.trim()) {
      setWorkspaceError('Capture at least a prompt or a response before saving.');
      return;
    }
    setSaving(true);
    setWorkspaceError(null);
    try {
      const slug = sanitizeTitle(title) || 'exchange';
      const filename = `chatgpt-companion-${timestampSlug()}-${slug}.md`;
      const markdown = buildCompanionMarkdown({
        project: selectedProject,
        title,
        prompt,
        response,
        notes,
        snapshot: bridgeSnapshot,
      });
      const file = new File([markdown], filename, { type: 'text/markdown' });
      await uploadFiles(selectedProject.id, [file]);
      await refreshRecent(selectedProject.id).catch(() => undefined);
      setWorkspaceNotice(
        `Saved this ChatGPT companion exchange into ${selectedProject.name}.`
      );
    } catch (err) {
      setWorkspaceError(
        (err as Error).message || 'Could not save the companion exchange.'
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveWorkspaceSnapshot(): Promise<void> {
    if (!selectedProject) {
      setWorkspaceError('Choose a project before saving a live ChatGPT snapshot.');
      return;
    }
    setSavingSnapshot(true);
    setWorkspaceError(null);
    try {
      const snapshot = bridgeSnapshot ?? (await refreshBridgeSnapshot());
      if (!snapshot) {
        setWorkspaceError('Open a ChatGPT page first so Synapse can capture it.');
        return;
      }
      const slug = sanitizeTitle(bestSnapshotTitle(snapshot) || 'workspace');
      const filename = `chatgpt-live-workspace-${timestampSlug()}-${slug || 'workspace'}.md`;
      const markdown = buildWorkspaceSnapshotMarkdown({
        project: selectedProject,
        snapshot,
      });
      const file = new File([markdown], filename, { type: 'text/markdown' });
      await uploadFiles(selectedProject.id, [file]);
      await refreshRecent(selectedProject.id).catch(() => undefined);
      setWorkspaceNotice(
        `Saved the visible ChatGPT workspace snapshot into ${selectedProject.name}.`
      );
    } catch (err) {
      setWorkspaceError(
        (err as Error).message || 'Could not save the live ChatGPT snapshot.'
      );
    } finally {
      setSavingSnapshot(false);
    }
  }

  async function handleDownloadFile(file: ProjectFile): Promise<void> {
    try {
      await downloadFile(file.project_id, file.id, file.original_name);
      setWorkspaceError(null);
    } catch (err) {
      setWorkspaceError(
        (err as Error).message || 'Could not download that companion entry.'
      );
    }
  }

  function handleProjectChange(nextProjectId: string): void {
    setSelectedProjectId(nextProjectId);
    setProjectSelectionExplicit(nextProjectId.length > 0);
    setWorkspaceNotice(null);
    setWorkspaceError(null);
  }

  const header = headerless ? null : (
    <PageHeader
      title='ChatGPT Companion'
      subtitle='Stay inside Synapse, keep ChatGPT sign-in browser-managed, pull chats and visible project links into your project memory, and revise the results before you save them.'
    />
  );

  const latestAssistantReply = [...(bridgeSnapshot?.latestMessages ?? [])]
    .reverse()
    .find((message) => message.role === 'assistant');

  return (
    <div
      data-surface-id='chatgpt-companion.workspace'
      className='flex min-h-[72vh] flex-col gap-4'
    >
      {header}

      <ChatWorkspaceShell
        leftPane={
          <Card className='flex min-h-0 flex-col overflow-hidden'>
            <div className='border-b border-border/70 px-4 py-4'>
              <div className='flex items-center justify-between gap-3'>
                <div>
                  <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/90'>
                    Project Target
                  </p>
                  <h2 className='mt-1 text-lg font-semibold'>
                    Choose where this work belongs
                  </h2>
                </div>
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  data-action-id='chatgpt-companion.new-project'
                  onClick={() => setCreateProjectOpen(true)}
                >
                  <Plus className='h-4 w-4' />
                  New
                </Button>
              </div>
            </div>

            <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4'>
              {sortedProjects.length === 0 ? (
                <div className='rounded-xl border border-dashed border-border px-4 py-6 text-sm text-muted-foreground'>
                  No projects yet. Create one here and keep the whole ChatGPT flow
                  inside Synapse.
                </div>
              ) : (
                <label className='grid gap-2 text-sm'>
                  <span className='text-muted-foreground'>Current project</span>
                  <select
                    aria-label='Current project'
                    data-action-id='chatgpt-companion.select-project'
                    value={selectedProjectId}
                    onChange={(event) => handleProjectChange(event.target.value)}
                    style={{ colorScheme: 'dark' }}
                    className='rounded-lg border border-border bg-background px-3 py-2 text-sm'
                  >
                    {sortedProjects.length !== 1 && (
                      <option value=''>Choose a project before saving...</option>
                    )}
                    {sortedProjects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {selectedProject && (
                <div className='rounded-xl border border-border/70 bg-secondary/20 px-4 py-4 text-sm'>
                  <div className='flex items-center gap-2'>
                    <span className='font-semibold text-foreground'>
                      {selectedProject.name}
                    </span>
                    {selectedProject.pinned && <Badge variant='outline'>Pinned</Badge>}
                  </div>
                  <p className='mt-2 break-words font-mono text-xs text-muted-foreground'>
                    {selectedProject.path}
                  </p>
                  {selectedProject.description && (
                    <p className='mt-3 text-muted-foreground'>
                      {selectedProject.description}
                    </p>
                  )}
                </div>
              )}

              {!selectedProject && sortedProjects.length > 1 && (
                <div className='rounded-xl border border-dashed border-border px-4 py-4 text-sm text-muted-foreground'>
                  Pick the project first. Synapse will not guess when you have more
                  than one.
                </div>
              )}

              <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
                <div className='flex items-center gap-2'>
                  <ShieldCheck className='h-4 w-4 text-primary' />
                  <h3 className='font-semibold'>Safe browser-managed login</h3>
                </div>
                <ul className='mt-3 space-y-2 text-sm text-muted-foreground'>
                  <li>
                    ChatGPT sign-in stays in the desktop browser session, whether the
                    user continues with Apple, Google, email, or another supported
                    provider.
                  </li>
                  <li>
                    Synapse only stores the prompt, response, and workspace snapshots
                    you choose to save.
                  </li>
                  <li>
                    The embedded browser keeps its own persistent session so you are
                    not forced to log in every time.
                  </li>
                </ul>
              </div>

              <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
                <div className='flex items-center justify-between gap-3'>
                  <div>
                    <h3 className='font-semibold'>Saved exchanges</h3>
                    <p className='text-sm text-muted-foreground'>
                      Recent ChatGPT captures saved for this project.
                    </p>
                  </div>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    onClick={() =>
                      selectedProjectId && void refreshRecent(selectedProjectId)
                    }
                    disabled={loadingFiles || !selectedProjectId}
                  >
                    {loadingFiles ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <RefreshCw className='h-4 w-4' />
                    )}
                  </Button>
                </div>
                <div className='mt-3 flex max-h-72 flex-col gap-2 overflow-y-auto'>
                  {loadingFiles && (
                    <div className='flex items-center gap-2 text-sm text-muted-foreground'>
                      <Loader2 className='h-4 w-4 animate-spin' />
                      Loading recent entries...
                    </div>
                  )}
                  {!loadingFiles && recentFiles.length === 0 && (
                    <p className='text-sm text-muted-foreground'>
                      No saved ChatGPT captures yet. Save one from the right rail.
                    </p>
                  )}
                  {recentFiles.map((file) => (
                    <button
                      key={file.id}
                      type='button'
                      data-action-id='chatgpt-companion.download-entry'
                      data-entity-id={file.id}
                      className='rounded-lg border border-border/70 bg-secondary/15 px-3 py-3 text-left transition-colors hover:bg-secondary/30'
                      onClick={() => void handleDownloadFile(file)}
                    >
                      <div className='flex items-start gap-2'>
                        <FileText className='mt-0.5 h-4 w-4 text-primary' />
                        <div className='min-w-0'>
                          <p className='truncate text-sm font-medium text-foreground'>
                            {file.original_name}
                          </p>
                          <p className='text-xs text-muted-foreground'>
                            Saved {formatLocal(file.uploaded_at, 'short')}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        }
        centerPane={
          <div className='grid min-h-0 gap-4 xl:grid-rows-[minmax(0,1fr)_minmax(230px,0.62fr)]'>
            <Card
              className='flex min-h-0 flex-col overflow-hidden'
              data-surface-id='chatgpt-companion.live-bridge'
            >
            <div className='border-b border-border/70 px-5 py-4'>
              <div className='flex flex-col gap-3'>
                <div className='flex flex-wrap items-start justify-between gap-3'>
                  <div className='min-w-0'>
                    <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/90'>
                      Live Bridge
                    </p>
                    <h2 className='mt-1 text-lg font-semibold'>
                      ChatGPT inside Synapse
                    </h2>
                    <p className='mt-1 truncate text-sm text-muted-foreground'>
                      {bridgeTitle}
                    </p>
                  </div>
                  <div
                    className={cn(
                      'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium',
                      visibleStatusTone
                    )}
                  >
                    <span
                      className={cn(
                        'h-2 w-2 rounded-full',
                        bridgeSnapshot?.signedIn ? 'bg-emerald-400' : 'bg-amber-400'
                      )}
                    />
                    {bridgeSnapshot?.signedIn ? 'signed in' : 'needs attention'}
                  </div>
                </div>

                <div className='flex flex-wrap items-center gap-2'>
                  <Button
                    type='button'
                    size='sm'
                    data-action-id='chatgpt-companion.bridge-home'
                    onClick={() => void navigateBridge(CHATGPT_HOME_URL)}
                  >
                    <ArrowUpRight className='h-4 w-4' />
                    Home
                  </Button>
                  <Button
                    type='button'
                    size='sm'
                    variant='outline'
                    data-action-id='chatgpt-companion.bridge-login'
                    onClick={() =>
                      liveBridgeAvailable
                        ? void navigateBridge(CHATGPT_LOGIN_URL)
                        : void openChatgpt(CHATGPT_LOGIN_URL)
                    }
                  >
                    <LogIn className='h-4 w-4' />
                    Sign in
                  </Button>
                  <Button
                    type='button'
                    size='sm'
                    variant='outline'
                    data-action-id='chatgpt-companion.bridge-refresh'
                    onClick={() => {
                      if (liveBridgeAvailable && webviewRef.current) {
                        setBridgeLoading(true);
                        void reloadEmbeddedWebview(webviewRef.current).catch((err) => {
                          setBridgeLoading(false);
                          setBridgeError(
                            (err as Error).message ||
                              'Could not refresh the embedded ChatGPT session.'
                          );
                        });
                      } else {
                        void openChatgpt(CHATGPT_HOME_URL);
                      }
                    }}
                    disabled={bridgeLoading}
                  >
                    {bridgeLoading ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <RefreshCw className='h-4 w-4' />
                    )}
                    Refresh
                  </Button>
                  <Button
                    type='button'
                    size='sm'
                    variant='ghost'
                    data-action-id='chatgpt-companion.bridge-open-external'
                    onClick={() => void openChatgpt(bridgeUrl)}
                  >
                    <ExternalLink className='h-4 w-4' />
                    Open outside
                  </Button>
                </div>

                {(bridgeNotice || bridgeError) && (
                  <div
                    className={cn(
                      'rounded-xl border px-3 py-2 text-sm',
                      bridgeError
                        ? 'border-destructive/40 bg-destructive/10 text-destructive'
                        : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                    )}
                  >
                    {bridgeError || bridgeNotice}
                  </div>
                )}
              </div>
            </div>

            <div className='relative min-h-0 flex-1 bg-[#0b0f17]'>
              {liveBridgeAvailable
                ? createElement('webview', {
                    ref: (node: unknown) => {
                      webviewRef.current = node as ChatgptWebviewElement | null;
                    },
                    src: CHATGPT_HOME_URL,
                    partition: CHATGPT_WEBVIEW_PARTITION,
                    allowpopups: 'true',
                    className: 'h-full w-full',
                    style: { width: '100%', height: '100%' },
                  })
                : (
                    <div className='flex h-full flex-col items-center justify-center gap-4 px-6 text-center text-sm text-muted-foreground'>
                      <ShieldCheck className='h-8 w-8 text-primary' />
                      <div className='space-y-2'>
                        <p className='text-base font-medium text-foreground'>
                          Live ChatGPT bridge works in the Synapse desktop app
                        </p>
                        <p>
                          This browser preview still supports the safe companion flow,
                          but the signed-in embedded bridge needs Electron.
                        </p>
                      </div>
                      <div className='flex flex-wrap justify-center gap-2'>
                        <Button
                          type='button'
                          size='sm'
                          onClick={() => void openChatgpt(CHATGPT_HOME_URL)}
                        >
                          <ArrowUpRight className='h-4 w-4' />
                          Open ChatGPT
                        </Button>
                        <Button
                          type='button'
                          size='sm'
                          variant='outline'
                          onClick={() => void openChatgpt(CHATGPT_LOGIN_URL)}
                        >
                          <LogIn className='h-4 w-4' />
                          Open sign-in
                        </Button>
                      </div>
                    </div>
                  )}

              {liveBridgeAvailable && bridgeLoading && (
                <div className='pointer-events-none absolute inset-0 flex items-center justify-center bg-black/35'>
                  <div className='flex items-center gap-2 rounded-full border border-border bg-card/95 px-4 py-2 text-sm text-foreground shadow-lg'>
                    <Loader2 className='h-4 w-4 animate-spin text-primary' />
                    Loading ChatGPT...
                  </div>
                </div>
              )}
            </div>
            </Card>

            <Card className='flex min-h-0 flex-col overflow-hidden'>
              <div className='border-b border-border/70 px-5 py-4'>
                <div className='flex items-start justify-between gap-3'>
                  <div>
                    <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/90'>
                      Visible Index
                    </p>
                    <h2 className='mt-1 text-lg font-semibold'>
                      Projects, chats, and current context
                    </h2>
                  </div>
                  <Button
                    type='button'
                    size='sm'
                    variant='outline'
                    data-action-id='chatgpt-companion.capture-index'
                    onClick={() => void refreshBridgeSnapshot()}
                    disabled={bridgeBusy === 'capture'}
                  >
                    {bridgeBusy === 'capture' ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <RefreshCw className='h-4 w-4' />
                    )}
                    Capture
                  </Button>
                </div>
              </div>

              <div className='grid min-h-0 flex-1 gap-4 overflow-y-auto px-5 py-4 text-sm xl:grid-cols-2'>
                <div className='rounded-xl border border-border/70 bg-secondary/15 p-3 xl:col-span-2'>
                  <div className='flex flex-wrap items-center justify-between gap-3'>
                    <div>
                      <h3 className='font-semibold'>Current ChatGPT context</h3>
                      <p className='mt-1 text-muted-foreground'>
                        ChatGPT project: {bridgeSnapshot?.activeProjectTitle ?? 'none visible yet'}
                      </p>
                    </div>
                    <Badge variant='outline'>
                      Tab: {bridgeSnapshot?.activeProjectTab ?? 'general'}
                    </Badge>
                  </div>
                  {!bridgeSnapshot?.activeProjectTitle && (
                    <p className='mt-3 text-muted-foreground'>
                      Open a ChatGPT project in the live bridge to pull its chats and
                      files into this workspace view.
                    </p>
                  )}
                </div>
                <IndexedList
                  title={`Pinned (${bridgeSnapshot?.pinned.length ?? 0})`}
                  items={bridgeSnapshot?.pinned ?? []}
                  emptyLabel='No pinned links are visible yet.'
                  onOpen={(item) => void openIndexedItem(item)}
                />
                <IndexedList
                  title={`Projects (${bridgeSnapshot?.projects.length ?? 0})`}
                  items={bridgeSnapshot?.projects ?? []}
                  emptyLabel='No visible project links yet.'
                  onOpen={(item) => void openIndexedItem(item)}
                />
                <IndexedList
                  title={`Current project chats (${bridgeSnapshot?.projectChats.length ?? 0})`}
                  items={bridgeSnapshot?.projectChats ?? []}
                  emptyLabel='No project chats are visible yet.'
                  onOpen={(item) => void openIndexedItem(item)}
                />
                <IndexedList
                  title={`Chats (${bridgeSnapshot?.conversations.length ?? 0})`}
                  items={bridgeSnapshot?.conversations ?? []}
                  emptyLabel='No visible conversation links yet.'
                  onOpen={(item) => void openIndexedItem(item)}
                  className='xl:col-span-2'
                />
                <SourcesList
                  title={`Current project files (${bridgeSnapshot?.projectSources.length ?? 0})`}
                  items={bridgeSnapshot?.projectSources ?? []}
                  emptyLabel='Open a ChatGPT project and switch to its Sources tab to surface attached files here.'
                  className='xl:col-span-2'
                />
                <div className='rounded-xl border border-border/70 bg-secondary/15 p-3 xl:col-span-2'>
                  <h3 className='font-semibold'>Latest visible messages</h3>
                  <div className='mt-3 flex max-h-52 flex-col gap-2 overflow-y-auto'>
                    {(bridgeSnapshot?.latestMessages ?? []).length === 0 && (
                      <p className='text-muted-foreground'>
                        No visible conversation text has been captured yet.
                      </p>
                    )}
                    {(bridgeSnapshot?.latestMessages ?? []).map((message, index) => (
                      <div
                        key={`${message.role}-${index}`}
                        className='rounded-lg border border-border/60 bg-background/70 px-3 py-2'
                      >
                        <p className='text-[11px] font-semibold uppercase tracking-[0.18em] text-primary/85'>
                          {message.role}
                        </p>
                        <p className='mt-1 whitespace-pre-wrap text-muted-foreground'>
                          {message.text.slice(0, 320)}
                          {message.text.length > 320 ? '...' : ''}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          </div>
        }
        rightPane={
          <div className='grid min-h-0 gap-4 xl:grid-rows-[minmax(0,1fr)_minmax(240px,0.72fr)]'>
            <Card
              className='flex min-h-0 flex-col overflow-hidden'
              data-surface-id='chatgpt-companion.capture-rail'
            >
            <div className='border-b border-border/70 px-5 py-4'>
              <div className='flex items-start justify-between gap-3'>
                <div>
                  <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/90'>
                    Draft + Capture
                  </p>
                  <h2 className='mt-1 text-lg font-semibold'>
                    Prompt, revise, and save
                  </h2>
                </div>
                <div className='flex items-center gap-2'>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    data-action-id='chatgpt-companion.copy-prompt'
                    onClick={() => void copyPrompt()}
                    disabled={!prompt.trim()}
                  >
                    <Copy className='h-4 w-4' />
                    Copy
                  </Button>
                  <Button
                    type='button'
                    size='sm'
                    variant='outline'
                    data-action-id='chatgpt-companion.fill-prompt'
                    onClick={() => void sendPromptToBridge(false)}
                    disabled={bridgeBusy === 'fill-prompt' || !prompt.trim()}
                  >
                    {bridgeBusy === 'fill-prompt' ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <ArrowUpRight className='h-4 w-4' />
                    )}
                    Fill
                  </Button>
                  <Button
                    type='button'
                    size='sm'
                    data-action-id='chatgpt-companion.send-prompt'
                    onClick={() => void sendPromptToBridge(true)}
                    disabled={bridgeBusy === 'send-prompt' || !prompt.trim()}
                  >
                    {bridgeBusy === 'send-prompt' ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <Send className='h-4 w-4' />
                    )}
                    Send
                  </Button>
                </div>
              </div>
            </div>

            <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4'>
              {(workspaceNotice || workspaceError) && (
                <div
                  className={cn(
                    'rounded-xl border px-3 py-2 text-sm',
                    workspaceError
                      ? 'border-destructive/40 bg-destructive/10 text-destructive'
                      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                  )}
                >
                  {workspaceError || workspaceNotice}
                </div>
              )}

              <label className='grid gap-2 text-sm'>
                <span className='text-muted-foreground'>Entry title</span>
                <Input
                  data-action-id='chatgpt-companion.title-input'
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder='What is this exchange about?'
                />
              </label>

              <label className='grid gap-2 text-sm'>
                <span className='text-muted-foreground'>Prompt to send</span>
                <textarea
                  data-action-id='chatgpt-companion.prompt-box'
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder='Write the prompt here, then send or fill it into ChatGPT.'
                  className='min-h-[150px] resize-y rounded-xl border border-border bg-background px-4 py-3 text-sm outline-none ring-0 transition-colors focus:border-primary'
                />
              </label>

              <label className='grid gap-2 text-sm'>
                <div className='flex items-center justify-between gap-3'>
                  <span className='text-muted-foreground'>Response / revised output</span>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    data-action-id='chatgpt-companion.capture-latest-reply'
                    onClick={() => void refreshBridgeSnapshot(true)}
                    disabled={bridgeBusy === 'capture-reply'}
                  >
                    {bridgeBusy === 'capture-reply' ? (
                      <Loader2 className='h-4 w-4 animate-spin' />
                    ) : (
                      <RefreshCw className='h-4 w-4' />
                    )}
                    Capture latest
                  </Button>
                </div>
                <textarea
                  data-action-id='chatgpt-companion.response-box'
                  value={response}
                  onChange={(event) => setResponse(event.target.value)}
                  placeholder='Capture the visible reply from ChatGPT, then revise or trim it before saving.'
                  className='min-h-[170px] resize-y rounded-xl border border-border bg-background px-4 py-3 text-sm outline-none ring-0 transition-colors focus:border-primary'
                />
              </label>

              <label className='grid gap-2 text-sm'>
                <span className='text-muted-foreground'>Notes for Synapse</span>
                <textarea
                  data-action-id='chatgpt-companion.notes-box'
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder='What should Synapse remember about this exchange?'
                  className='min-h-[110px] resize-y rounded-xl border border-border bg-background px-4 py-3 text-sm outline-none ring-0 transition-colors focus:border-primary'
                />
              </label>

              <div className='flex flex-wrap items-center gap-2 pt-1'>
                <Button
                  type='button'
                  data-action-id='chatgpt-companion.save-entry'
                  onClick={() => void saveCompanionEntry()}
                  disabled={saving || !selectedProject}
                >
                  {saving ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    <Save className='h-4 w-4' />
                  )}
                  Save exchange
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  data-action-id='chatgpt-companion.save-snapshot'
                  onClick={() => void saveWorkspaceSnapshot()}
                  disabled={savingSnapshot || !selectedProject}
                >
                  {savingSnapshot ? (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  ) : (
                    <FileText className='h-4 w-4' />
                  )}
                  Save workspace snapshot
                </Button>
              </div>
            </div>
            </Card>

            <Card className='flex min-h-0 flex-col overflow-hidden'>
              <div className='border-b border-border/70 px-5 py-4'>
                <p className='text-xs font-semibold uppercase tracking-[0.2em] text-primary/90'>
                  Workflow + Template Kit
                </p>
                <h2 className='mt-1 text-lg font-semibold'>
                  Keep the flow clean and reusable
                </h2>
              </div>

              <div className='flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4 text-sm'>
                <div className='rounded-xl border border-border/70 bg-secondary/20 px-4 py-4'>
                  <div className='flex items-center gap-2'>
                    <CheckCircle2 className='h-4 w-4 text-primary' />
                    <h3 className='font-semibold'>Live bridge path</h3>
                  </div>
                  <ol className='mt-3 space-y-2 text-muted-foreground'>
                    <li>1. Pick or create a Synapse project.</li>
                    <li>2. Log into ChatGPT in the embedded browser if needed.</li>
                    <li>3. Fill or send your draft prompt into ChatGPT.</li>
                    <li>
                      4. Capture the visible reply, revise it, and save it as
                      project memory.
                    </li>
                  </ol>
                </div>

                <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
                  <h3 className='font-semibold'>What Synapse can see</h3>
                  <p className='mt-2 text-muted-foreground'>
                    Visible ChatGPT projects, chats under the expanded project,
                    visible project files on the Sources tab, page title/URL, and the
                    conversation text you choose to capture.
                  </p>
                </div>

                <div className='rounded-xl border border-border/70 bg-card px-4 py-4'>
                  <h3 className='font-semibold'>Latest visible reply</h3>
                  <p className='mt-2 whitespace-pre-wrap text-muted-foreground'>
                    {latestAssistantReply?.text.slice(0, 420) ||
                      'Capture the latest visible reply to preview it here before saving.'}
                    {latestAssistantReply && latestAssistantReply.text.length > 420
                      ? '...'
                      : ''}
                  </p>
                </div>

                <ChatWorkspaceTemplateGuide />
              </div>
            </Card>
          </div>
        }
      />

      <ProjectFormDialog
        open={createProjectOpen}
        mode='create'
        onSaved={(project) => {
          upsertProjectLocal(project);
          void refreshProjects();
          setSelectedProjectId(project.id);
          setProjectSelectionExplicit(true);
          setCreateProjectOpen(false);
          setWorkspaceNotice(
            `Created ${project.name} and selected it for this ChatGPT workspace.`
          );
          setWorkspaceError(null);
        }}
        onClose={() => setCreateProjectOpen(false)}
      />
    </div>
  );
}

function IndexedList({
  title,
  items,
  emptyLabel,
  onOpen,
  className,
}: {
  title: string;
  items: ChatgptLinkItem[];
  emptyLabel: string;
  onOpen: (item: ChatgptLinkItem) => void;
  className?: string;
}): JSX.Element {
  return (
    <div className={cn('rounded-xl border border-border/70 bg-secondary/15 p-3', className)}>
      <h3 className='font-semibold'>{title}</h3>
      <div className='mt-3 flex max-h-48 flex-col gap-2 overflow-y-auto'>
        {items.length === 0 && (
          <p className='text-muted-foreground'>{emptyLabel}</p>
        )}
        {items.map((item) => (
          <button
            key={`${item.action || 'url'}:${item.href || item.title}`}
            type='button'
            className='rounded-lg border border-border/60 bg-background/70 px-3 py-2 text-left transition-colors hover:bg-background'
            onClick={() => onOpen(item)}
          >
            <div className='flex items-start justify-between gap-3'>
              <div className='min-w-0'>
                <p className='truncate font-medium text-foreground'>{item.title}</p>
                <p className='truncate text-xs text-muted-foreground'>
                  {linkTargetSummary(item)}
                </p>
              </div>
              {item.active && <Badge variant='outline'>Active</Badge>}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function SourcesList({
  title,
  items,
  emptyLabel,
  className,
}: {
  title: string;
  items: ChatgptSourceItem[];
  emptyLabel: string;
  className?: string;
}): JSX.Element {
  return (
    <div className={cn('rounded-xl border border-border/70 bg-secondary/15 p-3', className)}>
      <h3 className='font-semibold'>{title}</h3>
      <div className='mt-3 flex max-h-48 flex-col gap-2 overflow-y-auto'>
        {items.length === 0 && (
          <p className='text-muted-foreground'>{emptyLabel}</p>
        )}
        {items.map((item) => (
          <div
            key={`${item.title}-${item.updatedAt}-${item.kind}`}
            className='rounded-lg border border-border/60 bg-background/70 px-3 py-2'
          >
            <p className='truncate font-medium text-foreground'>{item.title}</p>
            <p className='truncate text-xs text-muted-foreground'>
              {[item.kind, item.updatedAt].filter(Boolean).join(' - ') || 'Visible project file'}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
