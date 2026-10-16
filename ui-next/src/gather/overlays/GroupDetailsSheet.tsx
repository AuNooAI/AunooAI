import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, Icon, IconButton, Meter, SettingRow, Sheet,
  Skeleton, Stack, Text, TextField, TextLink,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { getRecentArticlesForGroup } from '@monolith/gatherApi';
import { errorText } from '../../shell';
import { toArticle, type Article, type Keyword, type KeywordGroup } from '../model';
import { fmt, plural, type Notify } from '../lib';
import { KeywordSuggestionsDialog } from './KeywordSuggestionsDialog';

interface Props {
  group: KeywordGroup | null;
  onClose: () => void;
  onAddKeyword: (groupId: string, text: string) => void;
  onEditKeyword: (keywordId: string, text: string) => void;
  onRemoveKeyword: (keywordId: string) => void;
  onDeleteGroup: (groupId: string) => void;
  /** Run Check for this group (POST check-now with group_id). */
  onRunCheck: (groupId: string) => Promise<unknown>;
  checking: boolean;
  /** Open Test LLM Enrichment with this article preloaded. */
  onTestArticle: (uri: string, groupId: string) => void;
  /** Reload groups after a suggestion changed the keywords. */
  onKeywordsChanged: () => void;
  askConfirm: (confirm: Confirm) => void;
  notify: Notify;
}

const RECENT_LIMIT = 20;
/** Suggestions need some matched articles to compare (the old panel's rule). */
const MIN_MATCHES_FOR_SUGGESTIONS = 3;

const sentimentTone = (s?: string) => {
  const v = (s ?? '').toLowerCase();
  return v.includes('positive') ? 'success' : v.includes('negative') ? 'error' : v.includes('mixed') ? 'warning' : 'neutral';
};

/** The old panel's checks: many unscored recent articles, mostly irrelevant matches, a collection error. */
function healthWarnings(group: KeywordGroup, articles: Article[]) {
  const out: { tone: 'warning' | 'error'; title: string; text: string }[] = [];
  const recent = articles.slice(0, 10);
  if (recent.filter((a) => a.score === null).length >= 5) {
    out.push({ tone: 'warning', title: 'Most recent articles are unscored', text: 'Relevance scoring may be failing for this group. Try Test LLM Enrichment on one of them.' });
  }
  const scored = group.relevant + group.irrelevant;
  if (scored > 100 && group.irrelevant / scored > 0.8) {
    out.push({ tone: 'warning', title: 'Over 80% of matches are irrelevant', text: 'These keywords may be too broad. Use AI suggestions on the weakest keywords.' });
  }
  if (group.lastError) out.push({ tone: 'error', title: 'Last check failed', text: group.lastError });
  return out;
}

function ArticleRow({ a, groupId, onTestArticle }: { a: Article; groupId: string; onTestArticle: Props['onTestArticle'] }) {
  const r = a.raw;
  const facts = [
    r.topic_alignment_score != null && `Topic alignment ${Math.round(r.topic_alignment_score * 100)}%`,
    r.time_to_impact,
    r.driver_type,
    r.category,
  ].filter(Boolean) as string[];
  const explained = r.overall_match_explanation || r.summary || r.sentiment_explanation || r.time_to_impact_explanation || r.driver_type_explanation;
  return (
    <SettingRow
      title={<TextLink href={a.uri} external>{a.title}</TextLink>}
      description={[a.source, a.date].filter(Boolean).join(' · ')}
      actions={
        <>
          {a.score === null ? (
            <Chip size="sm" tone="muted">Unscored</Chip>
          ) : (
            <Chip size="sm" tone={a.relevant ? 'success' : 'neutral'}>{a.score}%</Chip>
          )}
          {a.sentiment && <Chip size="sm" tone={sentimentTone(a.sentiment)}>{a.sentiment}</Chip>}
          {(a.score === null || !a.sentiment) && (
            <IconButton icon={<Icon name="Flask" size="sm" />} label={`Test LLM enrichment on ${a.title}`} onClick={() => onTestArticle(a.uri, groupId)} />
          )}
        </>
      }
    >
      {(facts.length > 0 || explained) && (
        <Stack gap="sm">
          {facts.length > 0 && (
            <Stack direction="row" gap="sm">
              {facts.map((f) => <Chip key={f} size="sm" tone="neutral">{f}</Chip>)}
            </Stack>
          )}
          {explained && (
            <Collapsible>
              <CollapsibleTrigger variant="ghost" size="sm">AI analysis</CollapsibleTrigger>
              <CollapsibleContent>
                <Stack gap="sm">
                  {r.overall_match_explanation && <Text><strong>Match:</strong> {r.overall_match_explanation}</Text>}
                  {r.summary && <Text><strong>Summary:</strong> {r.summary}</Text>}
                  {r.sentiment_explanation && <Text><strong>Sentiment:</strong> {r.sentiment_explanation}</Text>}
                  {r.time_to_impact_explanation && <Text><strong>Time to impact:</strong> {r.time_to_impact_explanation}</Text>}
                  {r.driver_type_explanation && <Text><strong>Driver type:</strong> {r.driver_type_explanation}</Text>}
                </Stack>
              </CollapsibleContent>
            </Collapsible>
          )}
        </Stack>
      )}
    </SettingRow>
  );
}

/** Group Details: keywords with their performance and AI suggestions, health warnings, recent articles, Run Check, delete. */
export function GroupDetailsSheet({
  group, onClose, onAddKeyword, onEditKeyword, onRemoveKeyword, onDeleteGroup, onRunCheck, checking, onTestArticle, onKeywordsChanged,
  askConfirm, notify,
}: Props) {
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [articles, setArticles] = useState<Article[] | null>(null);
  const [articlesError, setArticlesError] = useState<string | null>(null);
  const [suggest, setSuggest] = useState<Keyword | null>(null);

  const loadArticles = useCallback((id: string) => {
    setArticles(null);
    setArticlesError(null);
    getRecentArticlesForGroup(Number(id), RECENT_LIMIT).then(
      (list) => setArticles(list.map(toArticle)),
      (e) => setArticlesError(errorText(e)),
    );
  }, []);

  useEffect(() => {
    setDraft('');
    setEditing(null);
    if (group) loadArticles(group.id);
  }, [group?.id, loadArticles]);

  const add = () => {
    if (!group || !draft.trim()) return;
    onAddKeyword(group.id, draft.trim());
    setDraft('');
  };
  const saveEdit = () => {
    if (!editing || !editing.text.trim()) return;
    onEditKeyword(editing.id, editing.text.trim());
    setEditing(null);
  };

  const warnings = group && articles ? healthWarnings(group, articles) : [];

  return (
    <>
      <Sheet
        open={group !== null}
        onOpenChange={(open) => !open && onClose()}
        title={group?.name ?? ''}
        description={group ? `${plural(group.keywords.length, 'keyword')} • ${plural(group.total, 'article')}` : undefined}
        meta={group && <Chip size="sm" tone="accent">{group.topic}</Chip>}
        size="lg"
        footer={
          group && (
            <>
              <Button
                iconStart={<Icon name="ArrowClockwise" size="sm" />}
                busy={checking}
                onClick={async () => {
                  try {
                    await onRunCheck(group.id);
                    notify(`Check started for “${group.name}”`, 'ArrowsClockwise');
                  } catch (e) {
                    notify(`Check failed: ${errorText(e)}`, 'WarningCircle');
                  }
                }}
              >
                {checking ? 'Running…' : 'Run Check'}
              </Button>
              <Button
                variant="secondary"
                iconStart={<Icon name="Trash" size="sm" />}
                onClick={() =>
                  askConfirm({
                    title: 'Delete keyword group?',
                    message: `“${group.name}” and its ${plural(group.keywords.length, 'keyword')} will stop collecting. Articles already collected are kept.`,
                    action: 'Delete group',
                    onConfirm: () => {
                      onDeleteGroup(group.id);
                      onClose();
                    },
                  })
                }
              >
                Delete Group
              </Button>
            </>
          )
        }
      >
        {group && (
          <Stack gap="lg">
            {warnings.map((w) => (
              <Banner key={w.title} tone={w.tone} icon="Warning" title={w.title} description={w.text} />
            ))}

            <Stack gap="sm">
              <Eyebrow as="h3">Keywords &amp; performance</Eyebrow>
              <Stack as="ul" gap="sm" label="Keywords">
                {group.keywords.map((k) => (
                  <li key={k.id}>
                    {editing?.id === k.id ? (
                      <TextField
                        label={`Edit ${k.text}`}
                        hideLabel
                        value={editing.text}
                        onChange={(text) => setEditing({ id: k.id, text })}
                        onSubmit={saveEdit}
                        action={
                          <>
                            <Button size="lg" disabled={!editing.text.trim()} onClick={saveEdit}>Save</Button>
                            <Button size="lg" variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
                          </>
                        }
                      />
                    ) : (
                      <SettingRow
                        title={k.text}
                        description={k.matches > 0 ? `${fmt(k.matches)} matches • ${k.avg}% avg` : 'No articles matched yet'}
                        actions={
                          <>
                            <IconButton
                              icon={<Icon name="Sparkle" size="sm" />}
                              label={
                                k.matches >= MIN_MATCHES_FOR_SUGGESTIONS
                                  ? `AI suggestions for ${k.text}${k.avg < 50 ? ' (needs attention)' : ''}`
                                  : `AI suggestions for ${k.text}: needs at least ${MIN_MATCHES_FOR_SUGGESTIONS} matched articles`
                              }
                              disabled={k.matches < MIN_MATCHES_FOR_SUGGESTIONS}
                              onClick={() => setSuggest(k)}
                            />
                            <IconButton icon={<Icon name="PencilSimple" size="sm" />} label={`Edit ${k.text}`} onClick={() => setEditing({ id: k.id, text: k.text })} />
                            <IconButton
                              icon={<Icon name="X" size="sm" />}
                              label={`Remove ${k.text}`}
                              tone="danger"
                              onClick={() =>
                                askConfirm({
                                  title: 'Remove keyword?',
                                  message: `“${k.text}” will no longer be collected for ${group.name}.`,
                                  action: 'Remove keyword',
                                  onConfirm: () => onRemoveKeyword(k.id),
                                })
                              }
                            />
                          </>
                        }
                      >
                        {k.matches > 0 && (
                          <Meter
                            label={`${k.text}: share of matches with high relevance`}
                            value={k.highPct}
                            valueText={`${k.highPct}% high · ${k.lowPct}% low`}
                            tone={k.avg >= 50 ? 'success' : k.avg >= 30 ? 'warning' : 'neutral'}
                          />
                        )}
                      </SettingRow>
                    )}
                  </li>
                ))}
              </Stack>
              <TextField
                label="Add new keyword"
                hideLabel
                placeholder="Add new keyword..."
                value={draft}
                onChange={setDraft}
                onSubmit={add}
                action={<Button size="lg" iconStart={<Icon name="Plus" size="sm" />} disabled={!draft.trim()} onClick={add}>Add</Button>}
              />
            </Stack>

            <Stack gap="sm">
              <Eyebrow as="h3">Recent articles</Eyebrow>
              {articlesError ? (
                <Banner tone="error" icon="WarningCircle" title="Couldn’t load recent articles" description={articlesError} />
              ) : articles === null ? (
                <Skeleton variant="block" />
              ) : articles.length === 0 ? (
                <Text variant="description">No articles collected for this group yet.</Text>
              ) : (
                <Stack as="ul" gap="sm" label="Recent articles">
                  {articles.map((a) => (
                    <li key={a.id}>
                      <ArticleRow a={a} groupId={group.id} onTestArticle={onTestArticle} />
                    </li>
                  ))}
                </Stack>
              )}
            </Stack>
          </Stack>
        )}
      </Sheet>
      <KeywordSuggestionsDialog
        target={suggest && group ? { keyword: suggest, groupId: group.id } : null}
        onClose={() => setSuggest(null)}
        onApplied={() => {
          onKeywordsChanged();
          if (group) loadArticles(group.id);
        }}
        notify={notify}
      />
    </>
  );
}
