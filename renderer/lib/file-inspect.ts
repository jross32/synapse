// Client-side pre-upload inspection (ADR-0003 Phase B · v0.1.31.5).
//
// Reads the first chunk of each picked File, detects its real type via
// magic-byte sniffing (NOT the browser's File.type which is just MIME
// guess from the OS), and produces a small preview so the upload dialog
// can show an "are you sure?" surface.

const PREVIEW_BYTES = 64 * 1024;          // 64 KiB sniff window
const PREVIEW_LINES = 30;                  // capped text-preview line count
const PREVIEW_TEXT_BYTES = 4 * 1024;       // 4 KiB decode for the preview itself

export type InspectedKind =
  | 'text'
  | 'pdf'
  | 'image'
  | 'archive'
  | 'audio'
  | 'video'
  | 'executable'
  | 'office'
  | 'binary';

export interface InspectedFile {
  file: File;
  size_bytes: number;
  detected_mime: string;
  detected_kind: InspectedKind;
  /** True for anything that *runs* on the host -- PE, ELF, Mach-O, .bat, .cmd, etc. */
  is_executable: boolean;
  /** ~30-line text preview if we could decode the bytes as UTF-8. */
  text_preview: string | null;
  /** Empty file -- always 0 bytes, no preview. */
  is_empty: boolean;
  /** Set when the picker handed us a 0-byte folder entry (browsers do this). */
  looks_like_folder: boolean;
}

// Filename extensions we consider executable even when the magic bytes don't
// give us a hit (.bat scripts, .ps1, .sh, ...).
const EXECUTABLE_EXTENSIONS = new Set([
  'exe', 'msi', 'bat', 'cmd', 'com', 'scr', 'vbs', 'js', 'jse', 'wsf', 'wsh',
  'ps1', 'psm1', 'sh', 'bash', 'zsh', 'fish', 'app', 'dmg', 'pkg', 'jar',
  'dll', 'so', 'dylib',
]);

function extOf(name: string): string {
  const lower = name.toLowerCase();
  const idx = lower.lastIndexOf('.');
  return idx >= 0 ? lower.slice(idx + 1) : '';
}

function startsWith(buf: Uint8Array, sig: number[]): boolean {
  if (buf.length < sig.length) return false;
  for (let i = 0; i < sig.length; i++) if (buf[i] !== sig[i]) return false;
  return true;
}

function detect(buf: Uint8Array, name: string):
  { mime: string; kind: InspectedKind; is_executable: boolean }
{
  const ext = extOf(name);
  // --- Executable signatures first (they're the safety-critical ones) ---
  if (startsWith(buf, [0x4d, 0x5a])) {
    // 'MZ' -- Windows PE (.exe, .dll, .scr, ...)
    return { mime: 'application/vnd.microsoft.portable-executable', kind: 'executable', is_executable: true };
  }
  if (startsWith(buf, [0x7f, 0x45, 0x4c, 0x46])) {
    // '\x7fELF' -- Linux/Unix ELF binaries
    return { mime: 'application/x-elf', kind: 'executable', is_executable: true };
  }
  // Mach-O fat or single (both byte orders)
  if (
    startsWith(buf, [0xca, 0xfe, 0xba, 0xbe]) ||
    startsWith(buf, [0xcf, 0xfa, 0xed, 0xfe]) ||
    startsWith(buf, [0xfe, 0xed, 0xfa, 0xcf])
  ) {
    return { mime: 'application/x-mach-binary', kind: 'executable', is_executable: true };
  }
  if (EXECUTABLE_EXTENSIONS.has(ext)) {
    return { mime: 'application/octet-stream', kind: 'executable', is_executable: true };
  }

  // --- Common document / asset signatures ---
  if (startsWith(buf, [0x25, 0x50, 0x44, 0x46])) {
    return { mime: 'application/pdf', kind: 'pdf', is_executable: false };
  }
  if (startsWith(buf, [0x89, 0x50, 0x4e, 0x47])) {
    return { mime: 'image/png', kind: 'image', is_executable: false };
  }
  if (startsWith(buf, [0xff, 0xd8, 0xff])) {
    return { mime: 'image/jpeg', kind: 'image', is_executable: false };
  }
  if (startsWith(buf, [0x47, 0x49, 0x46, 0x38])) {
    return { mime: 'image/gif', kind: 'image', is_executable: false };
  }
  if (startsWith(buf, [0x52, 0x49, 0x46, 0x46]) && startsWith(buf.slice(8), [0x57, 0x41, 0x56, 0x45])) {
    return { mime: 'audio/wav', kind: 'audio', is_executable: false };
  }
  if (startsWith(buf, [0x49, 0x44, 0x33]) || (buf[0] === 0xff && (buf[1] & 0xe0) === 0xe0)) {
    return { mime: 'audio/mpeg', kind: 'audio', is_executable: false };
  }
  if (startsWith(buf, [0x50, 0x4b, 0x03, 0x04])) {
    // 'PK\x03\x04' -- ZIP. Office formats are zips with specific contents.
    if (ext === 'docx' || ext === 'xlsx' || ext === 'pptx') {
      return { mime: `application/vnd.openxmlformats-officedocument.${ext}`, kind: 'office', is_executable: false };
    }
    if (ext === 'jar') {
      return { mime: 'application/java-archive', kind: 'executable', is_executable: true };
    }
    return { mime: 'application/zip', kind: 'archive', is_executable: false };
  }
  if (startsWith(buf, [0x1f, 0x8b])) {
    return { mime: 'application/gzip', kind: 'archive', is_executable: false };
  }
  // mp4 / quicktime check (`ftyp` at offset 4)
  if (buf.length >= 8 && buf[4] === 0x66 && buf[5] === 0x74 && buf[6] === 0x79 && buf[7] === 0x70) {
    return { mime: 'video/mp4', kind: 'video', is_executable: false };
  }

  // --- Text? Try UTF-8 decode and see if it has nulls/control bytes. ---
  const sniff = buf.slice(0, Math.min(buf.length, 8192));
  let nullish = 0;
  for (const b of sniff) {
    if (b === 0) { nullish++; }
    else if (b < 7 || (b > 13 && b < 32 && b !== 27)) { nullish++; }
  }
  if (nullish === 0) {
    // Probably text. Refine the mime by extension.
    const map: Record<string, string> = {
      md: 'text/markdown', json: 'application/json', csv: 'text/csv',
      html: 'text/html', xml: 'application/xml', yml: 'application/yaml',
      yaml: 'application/yaml', ts: 'text/typescript', tsx: 'text/typescript',
      js: 'text/javascript', jsx: 'text/javascript', py: 'text/x-python',
      log: 'text/plain', txt: 'text/plain',
    };
    return { mime: map[ext] ?? 'text/plain', kind: 'text', is_executable: false };
  }
  return { mime: 'application/octet-stream', kind: 'binary', is_executable: false };
}

function decodeText(buf: Uint8Array): string | null {
  try {
    const slice = buf.slice(0, Math.min(buf.length, PREVIEW_TEXT_BYTES));
    const txt = new TextDecoder('utf-8', { fatal: false }).decode(slice);
    // If the result is dominated by `�` (replacement char), it wasn't text.
    let replacements = 0;
    for (const ch of txt) if (ch === '�') replacements++;
    if (replacements > Math.max(2, txt.length / 16)) return null;
    return txt.split(/\r?\n/).slice(0, PREVIEW_LINES).join('\n');
  } catch {
    return null;
  }
}

export async function inspectFile(file: File): Promise<InspectedFile> {
  // Browsers hand 0-byte File entries with empty type when a folder is dragged.
  const looksLikeFolder = file.size === 0 && file.type === '' && !/\.[A-Za-z0-9]+$/.test(file.name);
  if (looksLikeFolder) {
    return {
      file,
      size_bytes: 0,
      detected_mime: 'inode/directory',
      detected_kind: 'binary',
      is_executable: false,
      text_preview: null,
      is_empty: true,
      looks_like_folder: true,
    };
  }
  if (file.size === 0) {
    return {
      file,
      size_bytes: 0,
      detected_mime: file.type || 'application/octet-stream',
      detected_kind: 'text',
      is_executable: false,
      text_preview: '',
      is_empty: true,
      looks_like_folder: false,
    };
  }
  const head = await file.slice(0, PREVIEW_BYTES).arrayBuffer();
  const buf = new Uint8Array(head);
  const { mime, kind, is_executable } = detect(buf, file.name);
  const text_preview = kind === 'text' ? decodeText(buf) : null;
  return {
    file,
    size_bytes: file.size,
    detected_mime: mime,
    detected_kind: kind,
    is_executable,
    text_preview,
    is_empty: false,
    looks_like_folder: false,
  };
}

export async function inspectAll(files: File[]): Promise<InspectedFile[]> {
  return await Promise.all(files.map(inspectFile));
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
