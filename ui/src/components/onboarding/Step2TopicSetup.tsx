/**
 * Step 2: Topic Setup with AI Suggestions
 */

import { useState } from 'react';
import { Button } from '../ui/button';
import { TagsInput } from '../TagsInput';
import { Loader2, Sparkles } from 'lucide-react';
import { suggestTopicAttributes, type TopicSuggestion } from '../../services/api';

interface Step2TopicSetupProps {
  onNext: (data: TopicSetupData, keywords?: any) => void;
  onBack: () => void;
}

export interface TopicSetupData {
  name: string;
  description: string;
  futureSignals: string[];
  categories: string[];
  sentiments: string[];
  timeToImpact: string[];
}

const EXAMPLE_DATA = {
  signals: ['AI is hype', 'AI is evolving gradually', 'AI is accelerating', 'AI reaches plateau', 'AI breakthrough imminent'],
  categories: ['AI in Finance', 'AI Ethics', 'AI Regulation', 'Cloud Computing', 'Edge AI'],
  sentiments: ['optimistic', 'critical', 'neutral', 'mocking', 'hyperbolic', 'cautious'],
  timeToImpact: ['Immediate (0-6 months)', 'Short-term (6-18 months)', 'Mid-term (1.5-3 years)', 'Long-term (3+ years)']
};

const DEFAULT_VALUES = {
  sentiments: ['Positive', 'Negative', 'Neutral'],
  timeToImpact: ['Immediate (0-6 months)', 'Short-term (6-18 months)', 'Mid-term (18-60 months)', 'Long-term (60+ months)']
};

export function Step2TopicSetup({ onNext, onBack }: Step2TopicSetupProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [futureSignals, setFutureSignals] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [sentiments, setSentiments] = useState<string[]>(DEFAULT_VALUES.sentiments);
  const [timeToImpact, setTimeToImpact] = useState<string[]>(DEFAULT_VALUES.timeToImpact);

  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [suggestions, setSuggestions] = useState<TopicSuggestion | null>(null);
  const [suggestedKeywords, setSuggestedKeywords] = useState<any>(null);

  const handleSuggestAttributes = async () => {
    if (!name.trim()) {
      alert('Please enter a topic name first');
      return;
    }

    setLoadingSuggestions(true);

    try {
      const result = await suggestTopicAttributes({
        topic_name: name,
        topic_description: description || undefined
      });

      // Backend returns data directly, not wrapped in suggestions
      if (result) {
        // Convert snake_case to camelCase
        const suggestions: TopicSuggestion = {
          futureSignals: result.future_signals || [],
          categories: result.categories || [],
          sentiments: result.sentiments || [],
          timeToImpact: result.time_to_impact || [],
          keywords: result.keywords || []
        };

        setSuggestions(suggestions);
        setShowSuggestions(true);

        // Auto-populate with suggestions
        // Always replace description with AI-generated explanation (which is better)
        if (result.explanation) {
          setDescription(result.explanation);
        }
        if (suggestions.futureSignals?.length > 0) {
          setFutureSignals(suggestions.futureSignals);
        }
        if (suggestions.categories?.length > 0) {
          setCategories(suggestions.categories);
        }
        // Store keywords for Step 3
        if (result.keywords) {
          setSuggestedKeywords(result.keywords);
        }
        // Don't override defaults for sentiments and timeToImpact
      }
    } catch (error) {
      console.error('Error getting suggestions:', error);
      alert('Failed to get AI suggestions. Please try again.');
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleNext = () => {
    if (!name.trim()) {
      alert('Please enter a topic name');
      return;
    }

    if (futureSignals.length === 0 || categories.length === 0 || sentiments.length === 0 || timeToImpact.length === 0) {
      alert('Please fill in all required fields or use AI suggestions');
      return;
    }

    onNext({
      name,
      description,
      futureSignals,
      categories,
      sentiments,
      timeToImpact
    }, suggestedKeywords);
  };

  return (
    <div>
      <h4 className="text-xl font-bold mb-2">Step 2: Set Up Your First Topic</h4>
      <p className="text-gray-700 mb-6">Create a topic to start monitoring</p>

      <div className="bg-gray-100 rounded-lg p-4 mb-6 text-sm text-gray-800">
        <p>At the core of <strong>AuNoo AI</strong> are <strong>topics</strong>—flexible constructs that can represent markets, knowledge fields, organizations, or even specific strategic questions. For instance:</p>
        <ul className="mt-2 ml-4 list-disc space-y-1">
          <li><strong>Markets</strong>: Cloud Service Providers, EV Battery Suppliers, or Threat Intelligence Providers.</li>
          <li><strong>Knowledge Fields</strong>: Neurology, AI, or Archeology.</li>
          <li><strong>Organizations or People</strong>: AI researchers, competitors, or even a favorite sports team.</li>
          <li><strong>Scenarios</strong>: Questions like "Is AI hype?" or "How strong is the Cloud Repatriation movement?"</li>
        </ul>
      </div>

      {/* Topic Name */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Topic Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Enter a descriptive name for your topic"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-500"
        />
        <small className="text-gray-600 text-xs">Enter a descriptive name for your topic</small>
      </div>

      {/* Topic Description */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Topic Description (Optional)</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          placeholder="Provide additional details about this topic to improve attribute suggestions"
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-500"
        />
        <small className="text-gray-600 text-xs">A brief description helps the AI provide better suggestions</small>
      </div>

      {/* Suggest Button */}
      <div className="mb-6">
        <Button
          variant="outline"
          onClick={handleSuggestAttributes}
          disabled={loadingSuggestions || !name.trim()}
          className="border-pink-500 text-pink-600 hover:bg-pink-50"
        >
          {loadingSuggestions ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Generating Suggestions...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4 mr-2" />
              Suggest Details
            </>
          )}
        </Button>
      </div>

      {/* Future Signals */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Future Signals</label>
        <p className="text-gray-700 text-sm mb-2">
          Future Signals are scenarios that suggest potential directions for a topic. For instance, signals for an AI hype model could range from
          <span className="text-blue-600"> "AI is hype"</span> and
          <span className="text-blue-600"> "AI is evolving gradually"</span>, to
          <span className="text-blue-600"> "AI is accelerating"</span>.
        </p>
        <TagsInput
          value={futureSignals}
          onChange={setFutureSignals}
          suggestions={suggestions?.futureSignals || EXAMPLE_DATA.signals}
          id="futureSignalsInput"
        />
        <small className="text-gray-600 text-xs">Add signals that indicate future developments</small>
      </div>

      {/* Categories */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Categories</label>
        <p className="text-gray-700 text-sm mb-2">
          Each topic is broken down into categories, making it easier to organize and analyze data. For example, a topic on AI might include subcategories like
          <span className="text-blue-600"> AI in Finance</span> or
          <span className="text-blue-600"> Cloud Quarterly Earnings</span>.
        </p>
        <TagsInput
          value={categories}
          onChange={setCategories}
          suggestions={suggestions?.categories || EXAMPLE_DATA.categories}
          id="categoriesInput"
        />
        <small className="text-gray-600 text-xs">Add categories that describe your topic</small>
      </div>

      {/* Sentiment Options - Hidden (auto-populated with defaults) */}

      {/* Time to Impact - Hidden (auto-populated with defaults) */}

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        <Button variant="outline" onClick={onBack}>
          ← Back
        </Button>
        <Button
          onClick={handleNext}
          className="bg-pink-500 hover:bg-pink-600"
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
