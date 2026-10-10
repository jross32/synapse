import { useEffect, useRef, useState } from 'react';
import { MonitorPlay, Plug, ShieldCheck, Unplug } from 'lucide-react';

type OBSMessage = { op: number; d: Record<string, unknown> };
type OBSReply = { requestType: string; requestId: string; requestStatus: { result: boolean; comment?: string }; responseData?: Record<string, unknown> };

export async function obsAuthentication(password: string, salt: string, challenge: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('Secure browser cryptography is required for OBS authentication.');
  async function sha256base64(value: string): Promise<string> {
    const bytes = new TextEncoder().encode(value);
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    return btoa(String.fromCharCode(...hash));
  }
  const secret = await sha256base64(password + salt);
  return sha256base64(secret + challenge);
}

export class ObsLink {
  private ws: WebSocket | null = null;
  private pending = new Map<string, { resolve: (v: Record<string, unknown>) => void; reject: (e: Error) => void }>();
  private nextId = 0;
  private available = false;
  onClose: ((reason: string) => void) | null = null;

  connect(password: string): Promise<void> {
    return new Promise((resolve, reject) => {
      let settled = false;
      let identified = false;
      const ws = new WebSocket('ws://127.0.0.1:4455');
      this.ws = ws;
      const fail = (message: string) => {
        if (!settled) { settled = true; reject(new Error(message)); }
        ws.close();
      };
      const timer = setTimeout(() => fail('Could not connect to OBS at localhost:4455.'), 8000);
      const finish = () => {
        if (!settled) { settled = true; clearTimeout(timer); resolve(); }
      };
      ws.onmessage = async event => {
        try {
          const msg = JSON.parse(String(event.data)) as OBSMessage;
          if (msg.op === 0) {
            const d: Record<string, unknown> = { rpcVersion: 1, eventSubscriptions: 0 };
            const auth = msg.d.authentication as { challenge: string; salt: string } | undefined;
            if (auth) {
              if (!password) throw new Error('Enter your OBS WebSocket password.');
              d.authentication = await obsAuthentication(password, auth.salt, auth.challenge);
            }
            ws.send(JSON.stringify({ op: 1, d }));
          } else if (msg.op === 2) {
            identified = true; this.available = true; finish();
          } else if (msg.op === 7) {
            const reply = msg.d as unknown as OBSReply;
            const pending = this.pending.get(reply.requestId);
            if (!pending) return;
            this.pending.delete(reply.requestId);
            if (!reply.requestStatus?.result) pending.reject(new Error(reply.requestStatus?.comment || 'OBS rejected the action.'));
            else pending.resolve(reply.responseData ?? {});
          }
        } catch (e) { fail(e instanceof Error ? e.message : 'OBS protocol error.'); }
      };
      ws.onerror = () => fail('OBS WebSocket connection failed. Check Tools > obs-websocket Settings in OBS.');
      ws.onclose = () => {
        clearTimeout(timer);
        this.available = false;
        for (const item of this.pending.values()) item.reject(new Error('OBS disconnected.'));
        this.pending.clear();
        if (!identified && !settled) fail('OBS closed the connection. Check its WebSocket password.');
        this.onClose?.(identified ? 'OBS disconnected.' : 'OBS connection closed before authentication.');
      };
    });
  }

  request(requestType: string, requestData?: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (!this.ws || !this.available || this.ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Connect to OBS first.'));
    }
    const id = String(++this.nextId);
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws?.send(JSON.stringify({ op: 6, d: { requestType, requestId: id, ...(requestData ? { requestData } : {}) } }));
    });
  }
  disconnect(): void {
    this.available = false;
    this.ws?.close();
    this.ws = null;
    this.pending.forEach(p => p.reject(new Error('OBS disconnected by user.')));
    this.pending.clear();
  }
}

export function ObsScenePanel(): JSX.Element {
  const ref = useRef<ObsLink | null>(null);
  const [connected, setConnected] = useState(false);
  const [password, setPassword] = useState('');
  const [scenes, setScenes] = useState<string[]>([]);
  const [currentScene, setCurrentScene] = useState('');
  const [streaming, setStreaming] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => () => { ref.current?.disconnect(); }, []);

  async function refresh(client: ObsLink): Promise<void> {
    const [list, status] = await Promise.all([
      client.request('GetSceneList'),
      client.request('GetStreamStatus'),
    ]);
    const rows = Array.isArray(list.scenes) ? list.scenes : [];
    setScenes(rows.map(row => (row as { sceneName?: string }).sceneName || '').filter(Boolean));
    setCurrentScene(String(list.currentProgramSceneName || ''));
    setStreaming(typeof status.outputActive === 'boolean' ? status.outputActive : null);
  }

  async function connect(): Promise<void> {
    if (busy) return;
    setBusy(true); setMessage('');
    const client = new ObsLink();
    client.onClose = reason => {
      if (ref.current === client) { setConnected(false); setMessage(reason); }
    };
    try {
      await client.connect(password);
      ref.current = client;
      setPassword(''); // Never retain credentials after handshake.
      setConnected(true);
      await refresh(client);
    } catch (e) {
      client.disconnect();
      setMessage(e instanceof Error ? e.message : 'Unable to connect to OBS.');
    } finally { setBusy(false); }
  }

  async function selectScene(sceneName: string): Promise<void> {
    const client = ref.current;
    if (!client || busy || currentScene === sceneName) return;
    setBusy(true); setMessage('');
    try {
      // Explicit user click for this particular scene is the authorization.
      await client.request('SetCurrentProgramScene', { sceneName });
      await refresh(client);
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Scene switch failed.'); }
    finally { setBusy(false); }
  }

  return (
    <section className='rounded-3xl border border-border bg-card/80 p-4 sm:p-5'>
      <div className='flex flex-wrap items-start justify-between gap-3'>
        <div>
          <h3 className='flex items-center gap-2 font-semibold'><MonitorPlay className='h-4 w-4 text-primary'/> OBS scene controller</h3>
          <p className='mt-1 max-w-xl text-xs leading-5 text-muted-foreground'>
            Connect manually to OBS Studio 28+ WebSocket on this computer (127.0.0.1:4455).
            Password stays in this window only. Scenes change only when you press a scene button.
          </p>
        </div>
        <span className={connected ? 'rounded-xl border border-emerald-500/30 px-3 py-1 text-xs text-emerald-300' : 'rounded-xl border border-border px-3 py-1 text-xs text-muted-foreground'}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
      </div>
      {!connected ? <div className='mt-4 flex flex-wrap items-end gap-3'>
        <label className='min-w-56 flex-1 text-xs text-muted-foreground'>OBS WebSocket password
          <input value={password} type='password' autoComplete='off' onChange={e => setPassword(e.target.value)}
            placeholder='Only if OBS requests one' className='mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm text-foreground'/>
        </label>
        <button type='button' disabled={busy} onClick={() => void connect()} className='rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50'>
          <Plug className='mr-1 inline h-4 w-4'/> {busy ? 'Connecting…' : 'Connect to OBS'}
        </button>
      </div> : <>
        <div className='mt-3 flex flex-wrap items-center gap-2 text-sm'>
          <span>Current: <strong>{currentScene || 'Unknown'}</strong></span>
          <span className='rounded-lg border border-border px-2 py-1 text-xs'>Streaming: {streaming === null ? 'Unknown' : streaming ? 'Active' : 'Off'}</span>
          <button type='button' className='ml-auto rounded-xl border border-border px-3 py-2 text-xs' onClick={() => {
            ref.current?.disconnect(); ref.current = null; setConnected(false); setScenes([]); setStreaming(null);
          }}><Unplug className='mr-1 inline h-3 w-3'/>Disconnect</button>
        </div>
        <div className='mt-3 flex flex-wrap gap-2'>{scenes.map(name =>
          <button type='button' key={name} disabled={busy || name === currentScene}
            aria-label={'Switch OBS scene to ' + name} onClick={() => void selectScene(name)}
            className={name === currentScene ? 'rounded-xl border border-primary bg-primary/15 px-3 py-2 text-xs text-primary' : 'rounded-xl border border-border bg-background px-3 py-2 text-xs hover:border-primary/40 disabled:opacity-50'}>
            {name}
          </button>)}
        </div>
      </>}
      <p className='mt-3 flex items-center gap-2 text-xs text-muted-foreground'><ShieldCheck className='h-4 w-4'/> This panel cannot start or end a broadcast, access your camera, or edit OBS settings. No OBS password is saved to disk.</p>
      {message && <p role='status' className='mt-2 text-xs text-amber-300'>{message}</p>}
    </section>
  );
}
