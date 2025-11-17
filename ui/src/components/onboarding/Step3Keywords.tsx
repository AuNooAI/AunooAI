/**
 * Step 3: Keywords Configuration
 */

import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { TagsInput } from '../TagsInput';
import { Loader2, Sparkles } from 'lucide-react';
import { saveTopic, completeOnboarding, suggestTopicAttributes } from '../../services/api';
import type { TopicSetupData } from './Step2TopicSetup';

interface Step3KeywordsProps {
  topicData: TopicSetupData;
  suggestedKeywords?: {
    companies: string[];
    technologies: string[];
    general: string[];
    people: string[];
    exclusions: string[];
  };
  onBack: () => void;
  onComplete: () => void;
}

export function Step3Keywords({ topicData, suggestedKeywords, onBack, onComplete }: Step3KeywordsProps) {
  const [companies, setCompanies] = useState<string[]>([]);
  const [technologies, setTechnologies] = useState<string[]>([]);
  const [generalKeywords, setGeneralKeywords] = useState<string[]>([]);
  const [people, setPeople] = useState<string[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Auto-populate keywords from Step 2 suggestions
  useEffect(() => {
    if (suggestedKeywords) {
      console.log('Populating keywords from Step 2:', suggestedKeywords);

      // Only populate first 3 of each category
      if (suggestedKeywords.companies?.length > 0) {
        setCompanies(suggestedKeywords.companies.slice(0, 3));
      }
      if (suggestedKeywords.technologies?.length > 0) {
        setTechnologies(suggestedKeywords.technologies.slice(0, 3));
      }
      if (suggestedKeywords.general?.length > 0) {
        setGeneralKeywords(suggestedKeywords.general.slice(0, 3));
      }
      if (suggestedKeywords.people?.length > 0) {
        setPeople(suggestedKeywords.people.slice(0, 2));
      }
      if (suggestedKeywords.exclusions?.length > 0) {
        setExclusions(suggestedKeywords.exclusions.slice(0, 2));
      }
    }
  }, [suggestedKeywords]);

  const handleRegenerateKeywords = async () => {
    setLoadingSuggestions(true);

    try {
      const prompt = `Suggest relevant keywords for the topic "${topicData.name}". Organize them into these categories: Companies & Organizations, Technologies, General Keywords, People, and Exclusion Keywords (misinformation, unrelated terms). Provide only the most relevant and high-quality keywords for each category. Use real company and technology names where possible. Exclusion keywords should help filter out noise or unrelated results. Topic description: ${topicData.description}`;

      const result = await suggestTopicAttributes({
        topic_name: topicData.name,
        topic_description: topicData.description,
        keyword_prompt: prompt
      });

      if (result && result.keywords) {
        console.log('Regenerated keywords:', result.keywords);

        // Replace current keywords with new suggestions (first 3 of each)
        setCompanies(result.keywords.companies?.slice(0, 3) || []);
        setTechnologies(result.keywords.technologies?.slice(0, 3) || []);
        setGeneralKeywords(result.keywords.general?.slice(0, 3) || []);
        setPeople(result.keywords.people?.slice(0, 2) || []);
        setExclusions(result.keywords.exclusions?.slice(0, 2) || []);
      }
    } catch (error) {
      console.error('Error regenerating keywords:', error);
      alert('Failed to regenerate keywords. Please try again.');
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleComplete = async () => {
    // Combine all keywords into a single array
    const allKeywords = [
      ...companies.map(c => `company:${c}`),
      ...technologies.map(t => `tech:${t}`),
      ...generalKeywords,
      ...people.map(p => `person:${p}`),
      ...exclusions.map(e => e.startsWith('-') || e.startsWith('NOT ') ? e : `-${e}`)
    ];

    if (allKeywords.length === 0) {
      alert('Please add at least one keyword');
      return;
    }

    setSaving(true);

    try {
      // Save topic with all data
      const result = await saveTopic({
        name: topicData.name,
        description: topicData.description,
        futureSignals: topicData.futureSignals,
        categories: topicData.categories,
        sentiments: topicData.sentiments,
        timeToImpact: topicData.timeToImpact,
        keywords: allKeywords
      });

      if (result.status === 'success' || result.success) {
        // Complete onboarding
        await completeOnboarding();
        onComplete();
      } else {
        alert(result.message || 'Failed to save topic');
      }
    } catch (error) {
      console.error('Error completing onboarding:', error);
      alert('Failed to complete onboarding. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <h4 className="text-xl font-bold mb-2">Step 3: Set Up Keywords</h4>
      <p className="text-gray-700 mb-6">Add keywords to monitor for your topic</p>

      <div className="bg-gray-100 rounded-lg p-4 mb-6 text-sm text-gray-800">
        <p className="mb-2">
          <strong>Keywords</strong> help AuNoo find relevant articles. You can organize keywords by category:
        </p>
        <ul className="ml-4 list-disc space-y-1">
          <li><strong>Companies</strong>: Organizations to track</li>
          <li><strong>Technologies</strong>: Specific technologies or products</li>
          <li><strong>People</strong>: Key individuals or thought leaders</li>
          <li><strong>General</strong>: Other relevant terms</li>
          <li><strong>Exclusions</strong>: Terms to exclude from results (prefix with -)</li>
        </ul>
      </div>

      {/* Regenerate Keywords Button */}
      {suggestedKeywords && (
        <div className="mb-6">
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-3 text-sm text-green-800">
            <span className="font-semibold">✓</span> Keywords from Step 2 have been applied
          </div>
          <Button
            variant="outline"
            onClick={handleRegenerateKeywords}
            disabled={loadingSuggestions}
            className="border-pink-500 text-pink-600 hover:bg-pink-50"
          >
            {loadingSuggestions ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2" />
                Get Different Suggestions
              </>
            )}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Companies */}
        <div>
          <label className="block text-sm font-semibold mb-2">Companies & Organizations</label>
          <TagsInput
            value={companies}
            onChange={setCompanies}
            placeholder="Add companies"
            id="companiesInput"
          />
        </div>

        {/* Technologies */}
        <div>
          <label className="block text-sm font-semibold mb-2">Technologies</label>
          <TagsInput
            value={technologies}
            onChange={setTechnologies}
            placeholder="Add technologies"
            id="technologiesInput"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* General Keywords */}
        <div>
          <label className="block text-sm font-semibold mb-2">General Keywords</label>
          <TagsInput
            value={generalKeywords}
            onChange={setGeneralKeywords}
            placeholder="Add general keywords"
            id="generalKeywordsInput"
          />
          <small className="text-gray-600 text-xs">Keywords that don't fit into specific categories above</small>
        </div>

        {/* People */}
        <div>
          <label className="block text-sm font-semibold mb-2">People</label>
          <TagsInput
            value={people}
            onChange={setPeople}
            placeholder="Add people"
            id="peopleInput"
          />
        </div>
      </div>

      {/* Exclusions */}
      <div className="mb-6">
        <label className="block text-sm font-semibold mb-2">Exclusion Keywords</label>
        <TagsInput
          value={exclusions}
          onChange={setExclusions}
          placeholder="Add exclusions (prefix with - or NOT)"
          id="exclusionKeywordsInput"
        />
        <small className="text-gray-600 text-xs">Prefix with minus (-) or "NOT" to exclude terms from search results</small>
      </div>

      {/* Summary */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h5 className="font-semibold text-blue-900 mb-2">Topic Summary</h5>
        <div className="text-sm text-blue-800 space-y-1">
          <p><strong>Name:</strong> {topicData.name}</p>
          {topicData.description && <p><strong>Description:</strong> {topicData.description}</p>}
          <p><strong>Categories:</strong> {topicData.categories.length}</p>
          <p><strong>Future Signals:</strong> {topicData.futureSignals.length}</p>
          <p><strong>Keywords:</strong> {companies.length + technologies.length + generalKeywords.length + people.length + exclusions.length}</p>
        </div>
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        <Button variant="outline" onClick={onBack} disabled={saving}>
          ← Back
        </Button>
        <Button
          onClick={handleComplete}
          disabled={saving}
          className="bg-pink-500 hover:bg-pink-600"
        >
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Saving...
            </>
          ) : (
            'Complete Setup'
          )}
        </Button>
      </div>
    </div>
  );
}
