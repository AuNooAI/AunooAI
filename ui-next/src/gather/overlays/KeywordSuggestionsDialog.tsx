import { useEffect, useState } from 'react';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, Eyebrow, Icon, SettingRow,
  Skeleton, Stack, Text, TextLink,
} from '@aunoo/ui';
import {
  applyKeywordSuggestion, getKeywordSuggestions, type ApplySuggestionRequest, type KeywordSuggestion, type KeywordSuggestionResult,
} from '@monolith/gatherApi';
import { errorText } from '../../shell';
import type { Keyword } from '../model';
import type { Notify } from '../lib';

interface Props {
  /** The keyword to analyse; null = closed. */
  target: { keyword: Keyword; groupId: string } | null;
  onClose: () => void;
  /** After a suggestion is applied: reload keywords and articles. */
  onApplied: () => void;
  notify: Notify;
}

type State = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; result: KeywordSuggestionResult };

/** Results are kept per keyword for the visit, as the old panel did, so reopening doesn't re-run the LLM. */
const cache = new Map<string, KeywordSuggestionResult>();

const SECTIONS: { type: ApplySuggestionRequest['suggestion_type']; key: 'replacements' | 'additions' | 'exclusions'; title: string; action: string }[] = [
  { type: 'replace', key: 'replacements', title: 'Replace with', action: 'Apply' },
  { type: 'add', key: 'additions', title: 'Add alongside', action: 'Add' },
  { type: 'exclude', key: 'exclusions', title: 'Exclude terms', action: 'Add' },
];

/** AI suggestions for one keyword (GET suggest-improvements), with Apply / Add buttons (POST apply-suggestion). */
export function KeywordSuggestionsDialog({ target, onClose, onApplied, notify }: Props) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [applying, setApplying] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    const key = target.keyword.id;
    const cached = cache.get(key);
    if (cached) {
      setState({ kind: 'ready', result: cached });
      return;
    }
    let alive = true;
    setState({ kind: 'loading' });
    getKeywordSuggestions(Number(key), Number(target.groupId)).then(
      (result) => {
        if (!alive) return;
        if (!result.error) cache.set(key, result);
        setState(result.error ? { kind: 'error', message: result.error } : { kind: 'ready', result });
      },
      (e) => alive && setState({ kind: 'error', message: errorText(e) }),
    );
    return () => {
      alive = false;
    };
  }, [target?.keyword.id, target?.groupId]);

  const apply = async (type: ApplySuggestionRequest['suggestion_type'], s: KeywordSuggestion) => {
    if (!target) return;
    const id = `${type}:${s.keyword}`;
    setApplying(id);
    try {
      const r = await applyKeywordSuggestion(Number(target.keyword.id), Number(target.groupId), {
        suggestion_type: type,
        suggested_keyword: s.keyword,
        reason: s.reason,
      });
      if (!r.success) throw new Error(r.error || r.message || 'Not applied');
      cache.delete(target.keyword.id);
      notify(r.message || `“${s.keyword}” applied`, 'Sparkle');
      onApplied();
      onClose();
    } catch (e) {
      notify(`Couldn’t apply “${s.keyword}”: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setApplying(null);
    }
  };

  const body = () => {
    if (state.kind === 'loading') {
      return (
        <Stack gap="sm">
          <Text variant="description">Analyzing keyword performance…</Text>
          <Skeleton variant="block" />
        </Stack>
      );
    }
    if (state.kind === 'error') return <Banner tone="error" icon="WarningCircle" title="No suggestions" description={state.message} />;
    const r = state.result;
    if (r.status === 'insufficient_data') return <Banner tone="info" icon="Info" title="Not enough data yet" description={r.message} />;
    if (r.status === 'good') return <Banner tone="success" icon="CheckCircle" title="Keyword performing well" description={r.message} />;
    const samples = r.sample_low_relevance_articles ?? [];
    return (
      <Stack gap="lg">
        <Stack direction="row" gap="sm">
          <Chip size="sm" tone="info">Confidence {Math.round((r.confidence ?? 0) * 100)}%</Chip>
        </Stack>
        {r.analysis && <Text>{r.analysis}</Text>}
        {SECTIONS.map(({ type, key, title, action }) => {
          const list = r.suggestions?.[key] ?? [];
          if (list.length === 0) return null;
          return (
            <Stack key={key} gap="sm">
              <Eyebrow as="h3">{title}</Eyebrow>
              <Stack as="ul" gap="sm" label={title}>
                {list.map((s) => (
                  <li key={s.keyword}>
                    <SettingRow
                      title={s.keyword}
                      description={s.reason}
                      actions={
                        <Button
                          size="sm"
                          variant="secondary"
                          busy={applying === `${type}:${s.keyword}`}
                          disabled={applying !== null}
                          onClick={() => apply(type, s)}
                        >
                          {action}
                        </Button>
                      }
                    />
                  </li>
                ))}
              </Stack>
            </Stack>
          );
        })}
        {(samples.length > 0 || r.sample_low_relevance_titles?.length > 0) && (
          <Collapsible>
            <CollapsibleTrigger variant="ghost" size="sm">Sample low-relevance articles</CollapsibleTrigger>
            <CollapsibleContent>
              <Stack as="ul" gap="sm" label="Sample low-relevance articles">
                {samples.length > 0
                  ? samples.map((a) => (
                      <li key={a.url}>
                        <TextLink href={a.url} external>{a.title}</TextLink> <Text as="span" variant="hint">{Math.round(a.relevance_score * 100)}%</Text>
                      </li>
                    ))
                  : r.sample_low_relevance_titles.map((t) => <li key={t}><Text>{t}</Text></li>)}
              </Stack>
            </CollapsibleContent>
          </Collapsible>
        )}
      </Stack>
    );
  };

  return (
    <Dialog
      open={target !== null}
      onOpenChange={(o) => !o && onClose()}
      title={<><Icon name="Sparkle" size="sm" /> AI Suggestions for “{target?.keyword.text}”</>}
      size="lg"
      footer={
        <DialogClose>
          <Button variant="secondary" size="lg">Close</Button>
        </DialogClose>
      }
    >
      {body()}
    </Dialog>
  );
}
