'use client';

import { useEffect, useState } from 'react';
import type { Fetched } from './api';

/** One foreground request on entry, then at most once per minute; no background keepalive. */
export function useLiveData<T>(key: string, initial: Fetched<T>) {
  const [result, setResult] = useState({ key, state: initial });
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let stopped = false;
    let controller: AbortController | null = null;
    let lastAttempt = 0;
    setResult({ key, state: initial });
    const refresh = async () => {
      if (document.visibilityState === 'hidden' || controller || Date.now() - lastAttempt < 60_000) return;
      lastAttempt = Date.now();
      controller = new AbortController();
      const active = controller;
      const timeout = window.setTimeout(() => active.abort(), 55_000);
      setLoading(true);
      try {
        const response = await fetch(`/api/live?${key}`, { cache: 'no-store', signal: active.signal });
        if (!response.ok) throw new Error('Live request failed');
        const next = await response.json() as Fetched<T>;
        if (!next || typeof next !== 'object' || typeof next.degraded !== 'boolean' || !('data' in next)) {
          throw new Error('Invalid live response');
        }
        if (!stopped) setResult({ key, state: next });
      } catch {
        if (!stopped) setResult((previous) => ({ key, state: { ...previous.state, degraded: true } }));
      } finally {
        window.clearTimeout(timeout);
        controller = null;
        if (!stopped) setLoading(false);
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 60_000);
    const onVisible = () => void refresh();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      stopped = true;
      controller?.abort();
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [key, initial, attempt]);
  return { state: result.key === key ? result.state : initial, loading, refresh: () => setAttempt((value) => value + 1) };
}
