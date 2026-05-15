import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Download,
  FileVideo,
  Loader2,
  Play,
  Upload,
} from 'lucide-react';
import { getApiUrl } from './config';

const STATUS_LABELS = {
  queued: 'Queued',
  processing: 'Processing',
  completed: 'Completed',
  partial: 'Needs review',
  failed: 'Failed',
};

export default function App() {
  const [mode, setMode] = useState('url');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState(null);
  const [maxClips, setMaxClips] = useState(5);
  const [render, setRender] = useState(true);
  const [job, setJob] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const clips = job?.result?.clips || [];
  const status = job?.status || 'idle';
  const canSubmit = mode === 'url' ? url.trim().length > 0 : Boolean(file);

  useEffect(() => {
    if (!job?.job_id || ['completed', 'partial', 'failed'].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(getApiUrl(`/api/jobs/${job.job_id}`));
      if (response.ok) {
        const next = await response.json();
        setJob((current) => ({ job_id: current.job_id, ...next }));
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  const statusTone = useMemo(() => {
    if (status === 'failed') return 'text-red-300 border-red-500/40 bg-red-500/10';
    if (status === 'completed') return 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10';
    if (status === 'partial') return 'text-amber-300 border-amber-500/40 bg-amber-500/10';
    return 'text-blue-200 border-blue-500/40 bg-blue-500/10';
  }, [status]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError('');
    setJob(null);

    try {
      const body = new FormData();
      body.set('render', String(render));
      body.set('max_clips', String(maxClips));
      if (mode === 'url') body.set('url', url.trim());
      if (mode === 'file' && file) body.set('file', file);

      const response = await fetch(getApiUrl('/api/jobs'), {
        method: 'POST',
        body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to start job');
      setJob({ job_id: data.job_id, status: data.status, result: null, error: null });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start job');
    } finally {
      setSubmitting(false);
    }
  }

  function clipUrl(path) {
    if (!path || !job?.job_id) return '';
    const normalized = String(path).replaceAll('\\', '/');
    const marker = `/${job.job_id}/`;
    const markerIndex = normalized.indexOf(marker);
    if (markerIndex >= 0) return getApiUrl(`/clips/${normalized.slice(markerIndex + 1)}`);
    const outputMarker = `output/${job.job_id}/`;
    const outputIndex = normalized.indexOf(outputMarker);
    if (outputIndex >= 0) return getApiUrl(`/clips/${normalized.slice(outputIndex + 7)}`);
    if (!normalized.startsWith('/')) return getApiUrl(`/clips/${job.job_id}/${normalized}`);
    return '';
  }

  return (
    <main className="min-h-screen bg-background text-zinc-100">
      <section className="border-b border-white/10 bg-zinc-950">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-white">Clip Lab</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Turn long-form podcasts and videos into vertical clips with captions, hooks, and metadata.
            </p>
          </div>
          <a
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-300 hover:border-white/20 hover:text-white"
            href="https://github.com/"
            target="_blank"
            rel="noreferrer"
          >
            <Clipboard size={15} />
            Open source
          </a>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-[420px_1fr]">
        <form onSubmit={handleSubmit} className="h-fit rounded-lg border border-white/10 bg-surface p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Upload size={16} />
            New clip job
          </div>

          <div className="mt-5 grid grid-cols-2 gap-2 rounded-lg bg-black/30 p-1">
            <button
              type="button"
              onClick={() => setMode('url')}
              className={`rounded-md px-3 py-2 text-sm ${mode === 'url' ? 'bg-white text-black' : 'text-zinc-400 hover:text-white'}`}
            >
              URL
            </button>
            <button
              type="button"
              onClick={() => setMode('file')}
              className={`rounded-md px-3 py-2 text-sm ${mode === 'file' ? 'bg-white text-black' : 'text-zinc-400 hover:text-white'}`}
            >
              Upload
            </button>
          </div>

          {mode === 'url' ? (
            <label className="mt-5 block">
              <span className="text-xs uppercase tracking-wide text-zinc-500">Podcast or video URL</span>
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                className="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-3 text-sm outline-none focus:border-blue-400"
                placeholder="https://youtube.com/watch?v=..."
              />
            </label>
          ) : (
            <div className="mt-5">
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(event) => setFile(event.target.files?.[0] || null)}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-white/20 bg-black/30 px-4 py-8 text-sm text-zinc-300 hover:border-white/40 hover:text-white"
              >
                <FileVideo size={18} />
                {file ? file.name : 'Choose a video file'}
              </button>
            </div>
          )}

          <div className="mt-5 grid grid-cols-2 gap-3">
            <label>
              <span className="text-xs uppercase tracking-wide text-zinc-500">Max clips</span>
              <input
                type="number"
                min="1"
                max="15"
                value={maxClips}
                onChange={(event) => setMaxClips(Number(event.target.value))}
                className="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-3 text-sm outline-none focus:border-blue-400"
              />
            </label>
            <label className="flex items-end gap-3 rounded-lg border border-white/10 bg-black/30 px-3 py-3 text-sm text-zinc-300">
              <input
                type="checkbox"
                checked={render}
                onChange={(event) => setRender(event.target.checked)}
                className="h-4 w-4"
              />
              Remotion render
            </label>
          </div>

          <button
            disabled={!canSubmit || submitting}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-white px-4 py-3 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            Generate clips
          </button>

          {error && (
            <div className="mt-4 flex gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </form>

        <div className="space-y-5">
          <div className="rounded-lg border border-white/10 bg-surface p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-medium text-white">Job status</h2>
                <p className="mt-1 text-sm text-zinc-400">
                  The API writes transcript, scenes, clips, and metadata under the job output folder.
                </p>
              </div>
              <div className={`rounded-lg border px-3 py-2 text-sm ${statusTone}`}>
                {STATUS_LABELS[status] || 'Idle'}
              </div>
            </div>
            {job?.error && (
              <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                {job.error}
              </div>
            )}
            {job?.job_id && (
              <div className="mt-4 rounded-lg bg-black/30 px-3 py-2 font-mono text-xs text-zinc-400">
                {job.job_id}
              </div>
            )}
          </div>

          <div className="grid gap-4">
            {clips.map((clip, index) => {
              const primaryPath = clip.rendered_clip_path || clip.vertical_clip_path;
              const href = clipUrl(primaryPath);
              return (
                <article key={`${clip.start}-${clip.end}`} className="rounded-lg border border-white/10 bg-surface p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-blue-300">
                        <CheckCircle2 size={14} />
                        Clip {index + 1} · score {clip.viral_score}
                      </div>
                      <h3 className="mt-2 text-lg font-semibold text-white">{clip.title}</h3>
                      <p className="mt-2 text-sm text-zinc-300">{clip.viral_reason}</p>
                    </div>
                    {href && (
                      <a
                        href={href}
                        className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-zinc-200 hover:border-white/30"
                      >
                        <Download size={15} />
                        MP4
                      </a>
                    )}
                  </div>
                  <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
                    <div className="rounded-lg bg-black/30 p-3">
                      <dt className="text-xs uppercase tracking-wide text-zinc-500">Hook</dt>
                      <dd className="mt-1 text-white">{clip.hook_text}</dd>
                    </div>
                    <div className="rounded-lg bg-black/30 p-3">
                      <dt className="text-xs uppercase tracking-wide text-zinc-500">Timing</dt>
                      <dd className="mt-1 text-white">
                        {clip.start.toFixed(2)}s to {clip.end.toFixed(2)}s
                      </dd>
                    </div>
                    <div className="rounded-lg bg-black/30 p-3 md:col-span-2">
                      <dt className="text-xs uppercase tracking-wide text-zinc-500">Caption</dt>
                      <dd className="mt-1 text-white">{clip.suggested_caption}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}

            {!clips.length && (
              <div className="rounded-lg border border-white/10 bg-surface p-8 text-center text-sm text-zinc-400">
                Submit a URL or upload a video to generate candidate shorts.
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
