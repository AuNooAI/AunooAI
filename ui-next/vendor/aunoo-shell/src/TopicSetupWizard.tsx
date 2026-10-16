import { useEffect, useRef, useState } from 'react';
import {
  Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, Grid, Icon, LineItems,
  Select, Skeleton, Stack, Stepper, TagInput, Text, TextArea, TextField, TextLink,
} from '@aunoo/ui';
import {
  AI_PROVIDERS, ALTERNATE_KEYWORDS, DEFAULT_CATEGORIES, DEFAULT_SIGNALS, FIRECRAWL_URL, KEY_STATUS, NEWS_PROVIDERS,
  SENTIMENTS, TIME_TO_IMPACT, suggestFor, type KeyId, type KeywordSets,
} from './mock';
import type { Notify } from './hooks';

const STEPS = [
  { id: 'keys', label: 'API Keys' },
  { id: 'topic', label: 'Topic Setup' },
  { id: 'keywords', label: 'Keywords' },
];
const FAKE_MS = 700;

export interface NewTopic {
  name: string;
  description: string;
  futureSignals: string[];
  categories: string[];
  sentiments: string[];
  timeToImpact: string[];
  /** Payload form: `company:x`, `tech:x`, general as-is, `person:x`, `-exclusion`. */
  keywords: string[];
}

export interface TopicSetupWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (topic: NewTopic) => void;
  notify: Notify;
}

type KeyState = { value: string; status: 'idle' | 'testing' | 'ok' | 'error'; error?: string };
const EMPTY_KEY: KeyState = { value: '', status: 'idle' };
const EMPTY_KEYWORDS: KeywordSets = { companies: [], technologies: [], general: [], people: [], exclusions: [] };

const configured = (provider: string) => Boolean((KEY_STATUS as Record<string, boolean>)[provider]);
const firstConfigured = (options: { value: string }[]) => options.find((o) => configured(o.value))?.value ?? '';
const allKeysConfigured = () =>
  AI_PROVIDERS.some((p) => configured(p.value)) && NEWS_PROVIDERS.some((p) => configured(p.value)) && configured('firecrawl');

const exclusion = (k: string) => (k.startsWith('-') || k.startsWith('NOT ') ? k : `-${k}`);

/**
 * AI-guided Topic Setup (TOPIC_SETUP_SPEC): API keys → topic → keywords. Mounted once by the
 * shell; the top-bar "Set up topic", the sidebar item and `?onboarding=true` all open it.
 */
export function TopicSetupWizard({ open, onOpenChange, onComplete, notify }: TopicSetupWizardProps) {
  const [loading, setLoading] = useState(true);
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
  const [signalOptions, setSignalOptions] = useState(DEFAULT_SIGNALS);
  const [categoryOptions, setCategoryOptions] = useState(DEFAULT_CATEGORIES);
  const [explanation, setExplanation] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [keywords, setKeywords] = useState<KeywordSets>(EMPTY_KEYWORDS);
  const [applied, setApplied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<{ name?: string; tags?: string; keywords?: string }>({});
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const timers = useRef<number[]>([]);
  const later = (fn: () => void, ms = FAKE_MS) => timers.current.push(window.setTimeout(fn, ms));

  const reset = () => {
    setStep(0);
    setAiProvider(firstConfigured(AI_PROVIDERS));
    setNewsProvider(firstConfigured(NEWS_PROVIDERS));
    setKeys({ ai: EMPTY_KEY, news: EMPTY_KEY, firecrawl: EMPTY_KEY });
    setName('');
    setDescription('');
    setSignals([]);
    setCategories([]);
    setSentiments(SENTIMENTS);
    setTimeToImpact(TIME_TO_IMPACT);
    setSignalOptions(DEFAULT_SIGNALS);
    setCategoryOptions(DEFAULT_CATEGORIES);
    setExplanation('');
    setKeywords(EMPTY_KEYWORDS);
    setApplied(false);
    setErrors({});
  };

  // Loading gate (§2): check key status, then skip Step 1 when everything is configured
  useEffect(() => {
    if (!open) return;
    reset();
    setLoading(true);
    later(() => {
      setLoading(false);
      if (allKeysConfigured()) setStep(1);
    });
    return () => {
      timers.current.forEach(window.clearTimeout);
      timers.current = [];
    };
  }, [open]);

  const keyReady = (id: KeyId, provider?: string) => (provider !== undefined && configured(provider)) || keys[id].status === 'ok';
  const step1Done = keyReady('ai', aiProvider) && keyReady('news', newsProvider) && (configured('firecrawl') || keys.firecrawl.status === 'ok');
  const keywordTotal = Object.values(keywords).reduce((n, list) => n + list.length, 0);
  const dirty = Boolean(name || description || signals.length || categories.length || keywordTotal || Object.values(keys).some((k) => k.value));

  const setKey = (id: KeyId, next: Partial<KeyState>) => setKeys((k) => ({ ...k, [id]: { ...k[id], ...next } }));
  const testKey = (id: KeyId, needsProvider: boolean) => {
    if (needsProvider) return setKey(id, { status: 'error', error: 'Please select a provider' });
    if (!keys[id].value.trim()) return setKey(id, { status: 'error', error: 'Please enter an API key' });
    setKey(id, { status: 'testing', error: undefined });
    // Demo rule: keys shorter than 8 characters fail validation
    later(() => setKey(id, keys[id].value.trim().length >= 8 ? { status: 'ok' } : { status: 'error', error: 'Validation failed' }));
  };

  const suggest = () => {
    if (!name.trim()) return setErrors({ name: 'Please enter a topic name first' });
    setSuggesting(true);
    later(() => {
      const s = suggestFor(name.trim());
      setSuggesting(false);
      setExplanation(s.explanation);
      setSignalOptions(s.future_signals);
      setCategoryOptions(s.categories);
      setSignals((cur) => [...new Set([...cur, ...s.future_signals])]);
      setCategories((cur) => [...new Set([...cur, ...s.categories])]);
      setKeywords(s.keywords);
      setApplied(true);
      setErrors({});
    }, 1000);
  };

  const next = () => {
    if (step === 1) {
      if (!name.trim()) return setErrors({ name: 'Please enter a topic name' });
      if (!signals.length || !categories.length) return setErrors({ tags: 'Please fill in all required fields or use AI suggestions' });
      setErrors({});
    }
    setStep((s) => s + 1);
  };

  const complete = () => {
    if (keywordTotal === 0) return setErrors({ keywords: 'Please add at least one keyword' });
    setSaving(true);
    later(() => {
      setSaving(false);
      onComplete({
        name: name.trim(),
        description: description.trim(),
        futureSignals: signals,
        categories,
        sentiments,
        timeToImpact,
        keywords: [
          ...keywords.companies.map((k) => `company:${k}`),
          ...keywords.technologies.map((k) => `tech:${k}`),
          ...keywords.general,
          ...keywords.people.map((k) => `person:${k}`),
          ...keywords.exclusions.map(exclusion),
        ],
      });
      onOpenChange(false);
    });
  };

  const close = (nextOpen: boolean) => {
    if (nextOpen) return onOpenChange(true);
    // Bug 6: closing with unsaved input asks first
    if (dirty && !saving) setConfirmDiscard(true);
    else onOpenChange(false);
  };

  const setKw = (key: keyof KeywordSets) => (tags: string[]) => setKeywords((k) => ({ ...k, [key]: tags }));
  const ai = AI_PROVIDERS.find((p) => p.value === aiProvider);
  const news = NEWS_PROVIDERS.find((p) => p.value === newsProvider);

  const keyField = (id: KeyId, label: string, providerValue: string | undefined, hint: React.ReactNode) => {
    // Bug 3: a configured provider shows its configured state, also after Back from Step 2
    if (providerValue !== undefined ? configured(providerValue) : configured('firecrawl')) {
      return <Banner tone="success" icon="CheckCircle" title={`${label}: key configured`} />;
    }
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
        hint={k.status === 'ok' ? 'Key configured ✓' : hint}
        action={
          <Button size="lg" variant="secondary" busy={k.status === 'testing'} onClick={() => testKey(id, providerValue === '')}>
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
        <Button size="lg" iconStart={<Icon name="Check" size="sm" />} busy={saving} onClick={complete}>{saving ? 'Saving…' : 'Complete Setup'}</Button>
      )}
    </>
  );

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={close}
        title={loading ? 'Loading Onboarding' : 'Welcome to AuNoo AI'}
        description={loading ? 'Checking your API key configuration...' : 'Set up your AuNoo AI account and create your first topic'}
        footer={footer}
      >
        {loading ? (
          <Stack gap="md">
            <Text>Checking configuration...</Text>
            <Skeleton lines={3} />
          </Stack>
        ) : (
          <Stack gap="lg">
            <Stepper steps={STEPS} current={step} label="Topic setup progress" />

            {step === 0 && (
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text variant="label" as="div">Step 1: Configure API Keys</Text>
                  <Text>Set up your API keys for AI and news services</Text>
                </Stack>
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
                  : <Text>Choose your AI provider - one key works for all models from that provider.</Text>}
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
                {keyField('firecrawl', 'Firecrawl Key', undefined, <>Required for web scraping and data collection. · <TextLink href={FIRECRAWL_URL} external>Free plan</TextLink></>)}
              </Stack>
            )}

            {step === 1 && (
              <Stack gap="lg">
                <Stack gap="sm">
                  <Text variant="label" as="div">Step 2: Set Up Your First Topic</Text>
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
                  <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={!name.trim()} busy={suggesting} onClick={suggest}>
                    {suggesting ? 'Generating Suggestions...' : 'Suggest Details'}
                  </Button>
                </Stack>
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
                {/* Open question 1: sentiments and time-to-impact are hidden live; exposed here as Advanced */}
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
                      <Button
                        variant="secondary"
                        size="sm"
                        iconStart={<Icon name="Sparkle" size="sm" />}
                        busy={regenerating}
                        onClick={() => {
                          setRegenerating(true);
                          later(() => {
                            setRegenerating(false);
                            setKeywords(ALTERNATE_KEYWORDS);
                            notify('New keyword suggestions applied', 'Sparkle');
                          });
                        }}
                      >
                        {regenerating ? 'Generating...' : 'Get Different Suggestions'}
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
            <Button
              variant="danger"
              size="lg"
              onClick={() => {
                setConfirmDiscard(false);
                onOpenChange(false);
              }}
            >
              Discard
            </Button>
          </>
        }
      >
        <Text variant="description">The keys, topic and keywords you’ve entered will be lost.</Text>
      </Dialog>
    </>
  );
}
