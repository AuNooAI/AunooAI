/**
 * Step 1: API Keys Configuration
 */

import { useState } from 'react';
import { Eye, EyeOff, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { validateApiKey } from '../../services/api';

interface Step1ApiKeysProps {
  onNext: () => void;
}

interface ApiKeyState {
  provider: string;
  key: string;
  validated: boolean;
  testing: boolean;
  error: string | null;
}

const PROVIDER_INFO = {
  openai: {
    name: 'OpenAI',
    link: 'https://platform.openai.com/api-keys',
    help: 'Supports GPT-4, GPT-4o, and more'
  },
  anthropic: {
    name: 'Anthropic',
    link: 'https://console.anthropic.com/settings/keys',
    help: 'Supports Claude 3.5, Claude 4, and more'
  },
  gemini: {
    name: 'Google Gemini',
    link: 'https://aistudio.google.com/app/apikey',
    help: 'Supports Gemini Pro, Gemini 2.0 Flash, and more'
  },
  newsapi: {
    name: 'NewsAPI',
    link: 'https://newsapi.org/register'
  },
  thenewsapi: {
    name: 'TheNewsAPI',
    link: 'https://www.thenewsapi.com/register'
  },
  newsdata: {
    name: 'NewsData.io',
    link: 'https://newsdata.io/register'
  }
};

export function Step1ApiKeys({ onNext }: Step1ApiKeysProps) {
  const [llm, setLlm] = useState<ApiKeyState>({
    provider: '',
    key: '',
    validated: false,
    testing: false,
    error: null
  });

  const [news, setNews] = useState<ApiKeyState>({
    provider: '',
    key: '',
    validated: false,
    testing: false,
    error: null
  });

  const [firecrawl, setFirecrawl] = useState<ApiKeyState>({
    provider: 'firecrawl',
    key: '',
    validated: false,
    testing: false,
    error: null
  });

  const [showLlmKey, setShowLlmKey] = useState(false);
  const [showNewsKey, setShowNewsKey] = useState(false);
  const [showFirecrawlKey, setShowFirecrawlKey] = useState(false);

  const testKey = async (type: 'llm' | 'news' | 'firecrawl') => {
    const state = type === 'llm' ? llm : type === 'news' ? news : firecrawl;
    const setState = type === 'llm' ? setLlm : type === 'news' ? setNews : setFirecrawl;

    if (!state.key) {
      setState({ ...state, error: 'Please enter an API key' });
      return;
    }

    if (type !== 'firecrawl' && !state.provider) {
      setState({ ...state, error: 'Please select a provider' });
      return;
    }

    setState({ ...state, testing: true, error: null });

    try {
      const result = await validateApiKey({
        provider: state.provider,
        api_key: state.key
      });

      // Backend returns {status: "valid", configured: true}
      if (result.configured || result.status === 'valid') {
        setState({ ...state, validated: true, testing: false, error: null });
      } else {
        setState({ ...state, validated: false, testing: false, error: 'Validation failed' });
      }
    } catch (error) {
      setState({ ...state, validated: false, testing: false, error: error instanceof Error ? error.message : 'Failed to test key' });
    }
  };

  const canProceed = llm.validated && news.validated && firecrawl.validated;

  return (
    <div>
      <h4 className="text-xl font-bold mb-2">Step 1: Configure API Keys</h4>
      <p className="text-gray-700 mb-6">Set up your API keys for AI and news services</p>

      {/* LLM Provider */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">AI Provider</label>
        <Select
          value={llm.provider}
          onValueChange={(value) => setLlm({ ...llm, provider: value, validated: false, error: null })}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select an AI provider" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="openai">OpenAI (GPT-4, GPT-4o, etc.)</SelectItem>
            <SelectItem value="anthropic">Anthropic (Claude)</SelectItem>
            <SelectItem value="gemini">Google Gemini</SelectItem>
          </SelectContent>
        </Select>
        <small className="text-gray-600 text-xs">Choose your AI provider - one key works for all models from that provider.</small>
      </div>

      {llm.provider && (
        <div className="mb-6">
          <label className="block text-sm font-semibold mb-2">
            {PROVIDER_INFO[llm.provider as keyof typeof PROVIDER_INFO]?.name} API Key
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showLlmKey ? 'text' : 'password'}
                value={llm.key}
                onChange={(e) => setLlm({ ...llm, key: e.target.value, validated: false, error: null })}
                placeholder="Enter API key"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-500"
              />
              <button
                type="button"
                onClick={() => setShowLlmKey(!showLlmKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-800"
              >
                {showLlmKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <Button
              variant="outline"
              onClick={() => testKey('llm')}
              disabled={llm.testing}
            >
              {llm.testing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Test'}
            </Button>
          </div>
          {llm.validated && (
            <div className="mt-2 flex items-center gap-1 text-green-600 text-sm">
              <CheckCircle className="w-4 h-4" />
              <span>Key configured ✓</span>
            </div>
          )}
          {llm.error && (
            <div className="mt-2 flex items-center gap-1 text-red-600 text-sm">
              <XCircle className="w-4 h-4" />
              <span>{llm.error}</span>
            </div>
          )}
          <small className="text-gray-600 text-xs">
            {PROVIDER_INFO[llm.provider as keyof typeof PROVIDER_INFO]?.help}.{' '}
            <a
              href={PROVIDER_INFO[llm.provider as keyof typeof PROVIDER_INFO]?.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-pink-600 hover:text-pink-700"
            >
              Get API key ↗
            </a>
          </small>
        </div>
      )}

      {/* News Provider */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">News Provider</label>
        <Select
          value={news.provider}
          onValueChange={(value) => setNews({ ...news, provider: value, validated: false, error: null })}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select a news provider" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newsapi">NewsAPI</SelectItem>
            <SelectItem value="thenewsapi">TheNewsAPI</SelectItem>
            <SelectItem value="newsdata">NewsData.io</SelectItem>
          </SelectContent>
        </Select>
        <small className="text-gray-600 text-xs">Choose your news data provider.</small>
      </div>

      {news.provider && (
        <div className="mb-6">
          <label className="block text-sm font-semibold mb-2">
            {PROVIDER_INFO[news.provider as keyof typeof PROVIDER_INFO]?.name} API Key
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showNewsKey ? 'text' : 'password'}
                value={news.key}
                onChange={(e) => setNews({ ...news, key: e.target.value, validated: false, error: null })}
                placeholder="Enter API key"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-500"
              />
              <button
                type="button"
                onClick={() => setShowNewsKey(!showNewsKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-800"
              >
                {showNewsKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <Button
              variant="outline"
              onClick={() => testKey('news')}
              disabled={news.testing}
            >
              {news.testing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Test'}
            </Button>
          </div>
          {news.validated && (
            <div className="mt-2 flex items-center gap-1 text-green-600 text-sm">
              <CheckCircle className="w-4 h-4" />
              <span>Key configured ✓</span>
            </div>
          )}
          {news.error && (
            <div className="mt-2 flex items-center gap-1 text-red-600 text-sm">
              <XCircle className="w-4 h-4" />
              <span>{news.error}</span>
            </div>
          )}
          <small className="text-gray-600 text-xs">
            Required for fetching news articles.{' '}
            <a
              href={PROVIDER_INFO[news.provider as keyof typeof PROVIDER_INFO]?.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-pink-600 hover:text-pink-700"
            >
              Register here ↗
            </a>
          </small>
        </div>
      )}

      {/* Firecrawl */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Firecrawl Key</label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type={showFirecrawlKey ? 'text' : 'password'}
              value={firecrawl.key}
              onChange={(e) => setFirecrawl({ ...firecrawl, key: e.target.value, validated: false, error: null })}
              placeholder="Enter API key"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
            <button
              type="button"
              onClick={() => setShowFirecrawlKey(!showFirecrawlKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-800"
            >
              {showFirecrawlKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <Button
            variant="outline"
            onClick={() => testKey('firecrawl')}
            disabled={firecrawl.testing}
          >
            {firecrawl.testing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Test'}
          </Button>
        </div>
        {firecrawl.validated && (
          <div className="mt-2 flex items-center gap-1 text-green-600 text-sm">
            <CheckCircle className="w-4 h-4" />
            <span>Key configured ✓</span>
          </div>
        )}
        {firecrawl.error && (
          <div className="mt-2 flex items-center gap-1 text-red-600 text-sm">
            <XCircle className="w-4 h-4" />
            <span>{firecrawl.error}</span>
          </div>
        )}
        <small className="text-gray-600 text-xs">
          Required for web scraping and data collection.{' '}
          <a
            href="https://www.firecrawl.dev/pricing"
            target="_blank"
            rel="noopener noreferrer"
            className="text-pink-600 hover:text-pink-700"
          >
            Free plan ↗
          </a>
        </small>
      </div>

      {/* Next Button */}
      <div className="flex justify-end mt-8">
        <Button
          onClick={onNext}
          disabled={!canProceed}
          className="bg-pink-500 hover:bg-pink-600"
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
