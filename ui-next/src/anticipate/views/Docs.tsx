import { useEffect, useState } from 'react';
import { Banner, Panel, Skeleton } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { Markdown } from '../../shell/Markdown';
import type { ViewProps } from './types';

/** One of the docs GET /api/docs/{name} serves (changelog, roadmap, how-it-works-…). */
export function DocPanel({ name, title }: { name: string; title?: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setText(null);
    setError(null);
    api<{ content: string }>(`/api/docs/${name}`).then(
      (r) => alive && setText(r.content ?? ''),
      (e) => alive && setError(errorText(e)),
    );
    return () => {
      alive = false;
    };
  }, [name]);
  if (error) return <Banner tone="error" icon="WarningCircle" title="Couldn’t load this document" description={error} />;
  if (text === null) return <Skeleton lines={8} />;
  return title ? <Panel title={title}><Markdown text={text} /></Panel> : <Markdown text={text} />;
}

export const Changelog = (_: ViewProps) => <DocPanel name="changelog" title="Changelog" />;
export const Roadmap = (_: ViewProps) => <DocPanel name="roadmap" title="Roadmap" />;
