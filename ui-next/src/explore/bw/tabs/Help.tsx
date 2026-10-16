import { useEffect, useState } from 'react';
import { Banner, Panel, Skeleton } from '@aunoo/ui';
import { api, errorText } from '../../../shell';
import { Markdown } from '../../../shell/Markdown';
import type { BwContext } from '../context';

/** Brand Watcher documentation: docs/brand_watcher_help.md via GET /api/docs/brand-watcher-help, as the old Help tab. */
export function Help(_: BwContext) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<{ content?: string }>('/api/docs/brand-watcher-help').then((r) => setText(r.content ?? ''), (e: unknown) => setError(errorText(e)));
  }, []);
  return (
    <Panel title="How Brand Watcher works">
      {error ? <Banner tone="error" title="The help page didn’t load" description={error} /> : text == null ? <Skeleton variant="text" lines={10} /> : <Markdown text={text} />}
    </Panel>
  );
}
