import { useEffect, useState } from 'react';
import {
  Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, Grid, Icon, LineItems,
  Select, Skeleton, Stack, Stepper, TagInput, Text, TextArea, TextField, TextLink, type SelectOption,
} from '@aunoo/ui';
import type { Notify } from '@aunoo/shell';
import { getAvailableModels } from '@monolith/api';
import { api, ApiError, errorText } from './api';

/*
 * AI-guided Topic Setup: API keys → topic → keywords. The design's TopicSetupWizard
 * (vendor/aunoo-shell) on the real /api/onboarding routes. Mounted once by AppShell; "Set up
 * topic", the sidebar item and `?onboarding=true` open it.
 */

const STEPS = [
  { id: 'keys', label: 'API Keys' },
  { id: 'topic', label: 'Topic Setup' },
  { id: 'keywords', label: 'Keywords' },
];

type KeyId = 'ai' | 'news' | 'firecrawl';
// The providers /api/onboarding/validate-api-key accepts
const AI_PROVIDERS: (SelectOption & { help: string; keyUrl: string })[] = [
  { value: 'openai', label: 'OpenAI', help: 'One key works for every OpenAI model', keyUrl: 'https://platform.openai.com/api-keys' },
  { value: 'anthropic', label: 'Anthropic (Claude)', help: 'One key works for every Claude model', keyUrl: 'https://console.anthropic.com/settings/keys' },
  { value: 'gemini', label: 'Google Gemini', help: 'One key works for every Gemini model', keyUrl: 'https://aistudio.google.com/app/apikey' },
];
const NEWS_PROVIDERS: (SelectOption & { registerUrl: string })[] = [
  { value: 'newsapi', label: 'NewsAPI', registerUrl: 'https://newsapi.org/register' },
  { value: 'thenewsapi', label: 'TheNewsAPI', registerUrl: 'https://www.thenewsapi.com/register' },
  { value: 'newsdata', label: 'NewsData.io', registerUrl: 'https://newsdata.io/register' },
];
const FIRECRAWL_URL = 'https://www.firecrawl.dev/pricing';
// The server's defaults for a new topic (save-topic falls back to the same lists)
const SENTIMENTS = ['Positive', 'Negative', 'Neutral'];
const TIME_TO_IMPACT = ['Immediate (0-6 months)', 'Short-term (6-18 months)', 'Mid-term (18-60 months)', 'Long-term (60+ months)'];

interface KeywordSets { companies: string[]; technologies: string[]; general: string[]; people: string[]; exclusions: string[] }
interface Suggestion { explanation?: string; categories?: string[]; future_signals?: string[]; keywords?: Partial<KeywordSets> }
type KeyStatus = Record<string, boolean>;
type KeyState = { value: string; status: 'idle' | 'testing' | 'ok' | 'error'; error?: string };

const EMPTY_KEY: KeyState = { value: '', status: 'idle' };
const EMPTY_KEYWORDS: KeywordSets = { companies: [], technologies: [], general: [], people: [], exclusions: [] };
const asKeywords = (k: Partial<KeywordSets> | undefined): KeywordSets => ({
  companies: k?.companies ?? [], technologies: k?.technologies ?? [], general: k?.general ?? [], people: k?.people ?? [], exclusions: k?.exclusions ?? [],
});
const exclusion = (k: string) => (k.startsWith('-') || k.startsWith('NOT ') ? k : `-${k}`);

export interface TopicSetupWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  notify: Notify;
  /** After the topic is saved */
  onComplete?: (name: string) => void;
}

export function TopicSetupWizard({ open, onOpenChange, notify, onComplete }: TopicSetupWizardProps) {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<KeyStatus>({});
  // The site runs models through a provider that needs no key here (e.g. Bedrock)
  const [modelsAvailable, setModelsAvailable] = useState(false);
  const [step, setStep] = useState(0);
  const [aiProvider, setAiProvider] = useState('');
  const [newsProvider, setNewsProvider] = useState('');
  const [keys, setKeys] = useState<Record<KeyId, KeyState>>({ ai: EMPTY_KEY, news: EMPTY_KEY, firecrawl: EMPTY_KEY });
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [signals, setSignals] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [sentiments, setSentiments] = useState(SENTIMENTS);
  const [timeToImpact, setTimeToImpact] = useState(TIME_TO_IMPACT);
  const [signalOptions, setSignalOptions] = useState<string[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [explanation, setExplanation] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [keywords, setKeywords] = useState<KeywordSets>(EMPTY_KEYWORDS);
  const [applied, setApplied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<{ name?: string; tags?: string; keywords?: string; save?: string }>({});
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);

  const configured = (provider: string) => Boolean(status[provider]);
  const aiConfigured = modelsAvailable || AI_PROVIDERS.some((p) => configured(p.value));

  const reset = () => {
    setStep(0);
    setAiProvider('');
    setNewsProvider('');
    setKeys({ ai: EMPTY_KEY, news: EMPTY_KEY, firecrawl: EMPTY_KEY });
    setName('');
    setDescription('');
    setSignals([]);
    setCategories([]);
    setSentiments(SENTIMENTS);
    setTimeToImpact(TIME_TO_IMPACT);
    setSignalOptions([]);
    setCategoryOptions([]);
    setExplanation('');
    setSuggestError(null);
    setKeywords(EMPTY_KEYWORDS);
    setApplied(false);
    setErrors({});
  };

  // Check which keys are set, then skip Step 1 when everything is configured
  useEffect(() => {
    if (!open) return;
    let alive = true;
    reset();
    setLoading(true);
    void Promise.all([
      api<KeyStatus>('/api/onboarding/check-keys').catch(() => ({}) as KeyStatus),
      getAvailableModels().catch(() => []),
    ]).then(([s, models]) => {
      if (!alive) return;
      setStatus(s);
      const hasModels = models.length > 0;
      setModelsAvailable(hasModels);
      const news = NEWS_PROVIDERS.find((p) => s[p.value])?.value ?? '';
      setAiProvider(AI_PROVIDERS.find((p) => s[p.value])?.value ?? '');
      setNewsProvider(news);
      setLoading(false);
      const ai = hasModels || AI_PROVIDERS.some((p) => s[p.value]);
      if (ai && news && s.firecrawl) setStep(1);
    });
    return () => {
      alive = false;
    };
  }, [open]);

  const keyReady = (id: KeyId, provider: string) => configured(provider) || keys[id].status === 'ok';
  const step1Done = (aiConfigured || keyReady('ai', aiProvider)) && Boolean(newsProvider) && keyReady('news', newsProvider) && keyReady('firecrawl', 'firecrawl');
  const keywordTotal = Object.values(keywords).reduce((n, list) => n + list.length, 0);
  const dirty = Boolean(name || description || signals.length || categories.length || keywordTotal || Object.values(keys).some((k) => k.value));

  const setKey = (id: KeyId, next: Partial<KeyState>) => setKeys((k) => ({ ...k, [id]: { ...k[id], ...next } }));
  // Tests the key with the provider and, when it works, stores it in the site's .env
  const testKey = async (id: KeyId, provider: string) => {
    if (!provider) return setKey(id, { status: 'error', error: 'Please select a provider' });
    const value = keys[id].value.trim();
    if (!value) return setKey(id, { status: 'error', error: 'Please enter an API key' });
    setKey(id, { status: 'testing', error: undefined });
    try {
      await api('/api/onboarding/validate-api-key', { method: 'POST', json: { provider, api_key: value } });
      setKey(id, { status: 'ok', value: '' });
      setStatus((s) => ({ ...s, [provider]: true }));
    } catch (e) {
      setKey(id, { status: 'error', error: errorText(e) || 'Validation failed' });
    }
  };

  const fetchSuggestions = () =>
    api<Suggestion>('/api/onboarding/suggest-topic-attributes', { method: 'POST', json: { topic_name: name.trim(), topic_description: description.trim() } });

  const suggest = async () => {
    if (!name.trim()) return setErrors({ name: 'Please enter a topic name first' });
    setSuggesting(true);
    setSuggestError(null);
    try {
      const s = await fetchSuggestions();
      setExplanation(s.explanation ?? '');
      setSignalOptions(s.future_signals ?? []);
      setCategoryOptions(s.categories ?? []);
      setSignals((cur) => [...new Set([...cur, ...(s.future_signals ?? [])])]);
      setCategories((cur) => [...new Set([...cur, ...(s.categories ?? [])])]);
      setKeywords(asKeywords(s.keywords));
      setApplied(true);
      setErrors({});
    } catch (e) {
      setSuggestError(errorText(e));
    } finally {
      setSuggesting(false);
    }
  };

  // The old page's "different suggestions" also re-ran the full suggestion (a custom prompt skipped the keyword rules)
  const regenerate = async () => {
    setRegenerating(true);
    try {
      const s = await fetchSuggestions();
      setKeywords(asKeywords(s.keywords));
      notify('New keyword suggestions applied', 'Sparkle');
    } catch (e) {
      notify(`No new suggestions: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setRegenerating(false);
    }
  };

  const next = () => {
    if (step === 1) {
      if (!name.trim()) return setErrors({ name: 'Please enter a topic name' });
      if (!signals.length || !categories.length) return setErrors({ tags: 'Please fill in all required fields or use AI suggestions' });
      setErrors({});
    }
    setStep((s) => s + 1);
  };

  const complete = async (overwrite = false) => {
    if (keywordTotal === 0) return setErrors({ keywords: 'Please add at least one keyword' });
    setSaving(true);
    setErrors({});
    const topic = name.trim();
    try {
      await api('/api/onboarding/save-topic', {
        method: 'POST',
        json: {
          name: topic,
          description: description.trim(),
          future_signals: signals,
          categories,
          // The names save-topic reads (the old page sent `sentiments`/`timeToImpact`, which it ignored)
          sentiment: sentiments,
          time_to_impact: timeToImpact,
          keywords: [
            ...keywords.companies.map((k) => `company:${k}`),
            ...keywords.technologies.map((k) => `tech:${k}`),
            ...keywords.general,
            ...keywords.people.map((k) => `person:${k}`),
            ...keywords.exclusions.map(exclusion),
          ],
          ...(overwrite ? { requires_confirmation: true, confirmed: true } : {}),
        },
      });
      // Marks onboarding done and stores the news provider (the old page never sent it)
      await api('/api/onboarding/complete', { method: 'POST', json: { news_provider: newsProvider || undefined } }).catch(() => undefined);
      notify(`Topic “${topic}” created. Collection starts in a few minutes.`, 'CheckCircle');
      onOpenChange(false);
      onComplete?.(topic);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setConfirmOverwrite(true);
      else setErrors({ save: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  const close = (nextOpen: boolean) => {
    if (nextOpen) return onOpenChange(true);
    if (dirty && !saving) setConfirmDiscard(true);
    else onOpenChange(false);
  };

  const setKw = (key: keyof KeywordSets) => (tags: string[]) => setKeywords((k) => ({ ...k, [key]: tags }));
  const ai = AI_PROVIDERS.find((p) => p.value === aiProvider);
  const news = NEWS_PROVIDERS.find((p) => p.value === newsProvider);

  const keyField = (id: KeyId, label: string, provider: string, hint: React.ReactNode) => {
    if (configured(provider)) return <Banner tone="success" icon="CheckCircle" title={`${label}: key configured`} />;
    const k = keys[id];
    return (
      <TextField
        label={label}
        type="password"
        secretName="API key"
        placeholder="Enter API key"
        value={k.value}
        onChange={(v) => setKey(id, { value: v, status: 'idle', error: undefined })}
        error={k.status === 'error' ? k.error : undefined}
        hint={hint}
        action={
          <Button size="lg" variant="secondary" busy={k.status === 'testing'} onClick={() => void testKey(id, provider)}>
            {k.status === 'testing' ? 'Testing…' : 'Test'}
          </Button>
        }
      />
    );
  };

  const footer = loading ? null : step === 0 ? (
    <Button size="lg" iconEnd={<Icon name="CaretRight" size="sm" />} disabled={!step1Done} onClick={() => setStep(1)}>Next</Button>
  ) : (
    <>
      <Button variant="secondary" size="lg" iconStart={<Icon name="CaretLeft" size="sm" />} disabled={saving} onClick={() => setStep((s) => s - 1)}>
        Back
      </Button>
      {step === 1 ? (
        <Button size="lg" iconEnd={<Icon name="CaretRight" size="sm" />} onClick={next}>Next</Button>
      ) : (
        <Button size="lg" iconStart={<Icon name="Check" size="sm" />} busy={saving} onClick={() => void complete()}>{saving ? 'Saving…' : 'Complete Setup'}</Button>
      )}
    </>
  );

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={close}
        title={loading ? 'Loading topic setup' : 'Set up a topic'}
        description={loading ? 'Checking your API key configuration…' : 'Create a topic to start collecting and analysing articles'}
        footer={footer}
      >
        {loading ? (
          <Stack gap="md">
            <Text>Checking configuration…</Text>
            <Skeleton lines={3} />
          </Stack>
        ) : (
          <Stack gap="lg">
            <Stepper steps={STEPS} current={step} label="Topic setup progress" />

            {step === 0 && (
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text variant="label" as="div">Step 1: Configure API Keys</Text>
                  <Text>Set up your API keys for AI and news services. A key that works is saved to this site’s settings.</Text>
                </Stack>
                {aiConfigured && !AI_PROVIDERS.some((p) => configured(p.value)) ? (
                  <Banner tone="success" icon="CheckCircle" title="AI models: configured" description="This site’s AI models are already set up." />
                ) : (
                  <>
                    <Select
                      label="AI Provider"
                      fullWidth
                      placeholder="Select an AI provider"
                      options={AI_PROVIDERS}
                      value={aiProvider}
                      onValueChange={(v) => { setAiProvider(v); setKey('ai', EMPTY_KEY); }}
                    />
                    {aiProvider
                      ? keyField('ai', `${ai?.label.split(' (')[0]} API key`, aiProvider, <>{ai?.help} · <TextLink href={ai!.keyUrl} external>Get API key</TextLink></>)
                      : <Text>Choose your AI provider. One key works for all models from that provider.</Text>}
                  </>
                )}
                <Select
                  label="News Provider"
                  fullWidth
                  placeholder="Select a news provider"
                  options={NEWS_PROVIDERS}
                  value={newsProvider}
                  onValueChange={(v) => { setNewsProvider(v); setKey('news', EMPTY_KEY); }}
                />
                {newsProvider
                  ? keyField('news', `${news?.label} API key`, newsProvider, <>Required for fetching news articles. · <TextLink href={news!.registerUrl} external>Register here</TextLink></>)
                  : <Text>Choose your news data provider.</Text>}
                {keyField('firecrawl', 'Firecrawl key', 'firecrawl', <>Required for web scraping and data collection. · <TextLink href={FIRECRAWL_URL} external>Free plan</TextLink></>)}
              </Stack>
            )}

            {step === 1 && (
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text variant="label" as="div">Step 2: Set Up Your Topic</Text>
                  <Text>Create a topic to start monitoring</Text>
                </Stack>
                <Banner
                  tone="info"
                  icon="Info"
                  title="Topics are at the core of AuNoo AI"
                  description="Flexible constructs that can represent markets, knowledge fields, organizations, or even specific strategic questions. For instance:"
                />
                <LineItems
                  label="Kinds of topic"
                  items={[
                    { id: 'markets', label: 'Markets', amount: 'Cloud Service Providers, EV Battery Suppliers' },
                    { id: 'fields', label: 'Knowledge Fields', amount: 'Neurology, AI, Archeology' },
                    { id: 'orgs', label: 'Organizations or People', amount: 'AI researchers, competitors' },
                    { id: 'scenarios', label: 'Scenarios', amount: '“Is AI hype?”' },
                  ]}
                />
                <TextField
                  label="Topic Name"
                  placeholder="Enter a descriptive name for your topic"
                  value={name}
                  error={errors.name}
                  hint={errors.name ? undefined : 'Enter a descriptive name for your topic'}
                  onChange={(v) => { setName(v); setErrors({}); }}
                />
                <TextArea
                  label="Topic Description (Optional)"
                  rows={3}
                  placeholder="Provide additional details about this topic to improve attribute suggestions"
                  hint="A brief description helps the AI provide better suggestions"
                  value={description}
                  onChange={setDescription}
                />
                <Stack direction="row" gap="sm">
                  <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={!name.trim()} busy={suggesting} onClick={() => void suggest()}>
                    {suggesting ? 'Generating Suggestions…' : 'Suggest Details'}
                  </Button>
                </Stack>
                {suggestError && <Banner tone="error" icon="WarningCircle" title="No suggestions" description={suggestError} />}
                {explanation && <Banner tone="promo" icon="Sparkle" title="AI suggestions applied" description={explanation} />}
                <TagInput
                  label="Future Signals"
                  tags={signals}
                  onChange={(t) => { setSignals(t); setErrors({}); }}
                  suggestions={signalOptions}
                  placeholder="Type and press Enter to add"
                  hint="Scenarios that suggest potential directions for a topic — e.g. from “AI is hype” to “AI is accelerating”."
                />
                <TagInput
                  label="Categories"
                  tags={categories}
                  onChange={(t) => { setCategories(t); setErrors({}); }}
                  suggestions={categoryOptions}
                  placeholder="Type and press Enter to add"
                  hint="Categories that break the topic down, e.g. AI in Finance or Cloud Quarterly Earnings."
                />
                {errors.tags && <Text tone="error">{errors.tags}</Text>}
                <Collapsible>
                  <Stack gap="md">
                    <Stack direction="row">
                      <CollapsibleTrigger variant="ghost" size="sm">Advanced</CollapsibleTrigger>
                    </Stack>
                    <CollapsibleContent>
                      <Stack gap="md">
                        <TagInput label="Sentiments" tags={sentiments} onChange={setSentiments} />
                        <TagInput label="Time to Impact" tags={timeToImpact} onChange={setTimeToImpact} />
                      </Stack>
                    </CollapsibleContent>
                  </Stack>
                </Collapsible>
              </Stack>
            )}

            {step === 2 && (
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text variant="label" as="div">Step 3: Set Up Keywords</Text>
                  <Text>Add keywords to monitor for your topic</Text>
                </Stack>
                <LineItems
                  label="Keyword categories"
                  items={[
                    { id: 'companies', label: 'Companies', amount: 'Organizations to track' },
                    { id: 'tech', label: 'Technologies', amount: 'Specific technologies or products' },
                    { id: 'people', label: 'People', amount: 'Key individuals or thought leaders' },
                    { id: 'general', label: 'General', amount: 'Other relevant terms' },
                    { id: 'exclusions', label: 'Exclusions', amount: 'Terms to exclude (prefix with -)' },
                  ]}
                />
                {applied && (
                  <Banner
                    tone="success"
                    icon="CheckCircle"
                    title="Keywords from Step 2 have been applied"
                    action={
                      <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} busy={regenerating} onClick={() => void regenerate()}>
                        {regenerating ? 'Generating…' : 'Get Different Suggestions'}
                      </Button>
                    }
                  />
                )}
                <Grid columns={2} stackAt="small" gap="md">
                  <TagInput label="Companies & Organizations" tags={keywords.companies} onChange={setKw('companies')} placeholder="Add companies" />
                  <TagInput label="Technologies" tags={keywords.technologies} onChange={setKw('technologies')} placeholder="Add technologies" />
                  <TagInput
                    label="General Keywords"
                    tags={keywords.general}
                    onChange={setKw('general')}
                    placeholder="Add general keywords"
                    hint="Keywords that don't fit into specific categories above"
                  />
                  <TagInput label="People" tags={keywords.people} onChange={setKw('people')} placeholder="Add people" />
                </Grid>
                <TagInput
                  label="Exclusion Keywords"
                  tags={keywords.exclusions}
                  onChange={(t) => setKw('exclusions')(t.map(exclusion))}
                  placeholder="Add exclusions (prefix with - or NOT)"
                  hint="Prefix with minus (-) or “NOT” to exclude terms from search results"
                />
                {errors.keywords && <Text tone="error">{errors.keywords}</Text>}
                {errors.save && <Banner tone="error" icon="WarningCircle" title="Topic not saved" description={errors.save} />}
                <LineItems
                  label="Topic summary"
                  items={[
                    { id: 'name', label: 'Name', amount: name },
                    ...(description.trim() ? [{ id: 'desc', label: 'Description', amount: description.trim() }] : []),
                    { id: 'cats', label: 'Categories', amount: String(categories.length) },
                    { id: 'signals', label: 'Future Signals', amount: String(signals.length) },
                  ]}
                  total={{ label: 'Keywords', amount: String(keywordTotal) }}
                />
              </Stack>
            )}
          </Stack>
        )}
      </Dialog>

      <Dialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title="Discard setup?"
        footer={
          <>
            <DialogClose>
              <Button variant="secondary" size="lg">Keep editing</Button>
            </DialogClose>
            <Button variant="danger" size="lg" onClick={() => { setConfirmDiscard(false); onOpenChange(false); }}>Discard</Button>
          </>
        }
      >
        <Text variant="description">The topic and keywords you’ve entered will be lost. Keys that tested OK are already saved.</Text>
      </Dialog>

      <Dialog
        open={confirmOverwrite}
        onOpenChange={setConfirmOverwrite}
        title="Topic already exists"
        footer={
          <>
            <DialogClose>
              <Button variant="secondary" size="lg">Cancel</Button>
            </DialogClose>
            <Button variant="danger" size="lg" busy={saving} onClick={() => { setConfirmOverwrite(false); void complete(true); }}>Overwrite</Button>
          </>
        }
      >
        <Text variant="description">{`A topic called “${name.trim()}” already exists. Saving replaces its settings and keywords.`}</Text>
      </Dialog>
    </>
  );
}
