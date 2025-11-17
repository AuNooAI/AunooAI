/**
 * TagsInput Component - Reusable tags/chips input with suggestions
 */

import { useState, KeyboardEvent } from 'react';
import { X } from 'lucide-react';

interface TagsInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  id?: string;
}

export function TagsInput({
  value,
  onChange,
  placeholder = 'Type and press Enter to add',
  suggestions = [],
  id
}: TagsInputProps) {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      if (!value.includes(inputValue.trim())) {
        onChange([...value, inputValue.trim()]);
      }
      setInputValue('');
    } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
      // Remove last tag when backspace is pressed on empty input
      onChange(value.slice(0, -1));
    }
  };

  const removeTag = (tagToRemove: string) => {
    onChange(value.filter(tag => tag !== tagToRemove));
  };

  const addSuggestion = (suggestion: string) => {
    if (!value.includes(suggestion)) {
      onChange([...value, suggestion]);
    }
  };

  return (
    <div>
      {/* Tags Container */}
      <div className="border border-pink-200 rounded-lg p-3 min-h-[100px] flex flex-wrap gap-2 items-start bg-white">
        {value.map((tag, index) => (
          <span
            key={index}
            className="inline-flex items-center bg-pink-100 text-pink-700 px-3 py-1 rounded-full text-sm border border-pink-200 shadow-sm"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="ml-2 opacity-60 hover:opacity-100 transition-opacity"
              aria-label={`Remove ${tag}`}
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          id={id}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={value.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[150px] border-none outline-none p-1 text-sm"
        />
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {suggestions.map((suggestion, index) => (
            <button
              key={index}
              type="button"
              onClick={() => addSuggestion(suggestion)}
              disabled={value.includes(suggestion)}
              className="px-3 py-1 text-sm bg-pink-50 text-pink-600 border border-pink-200 rounded-full hover:bg-pink-500 hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-pink-50 disabled:hover:text-pink-600 relative group"
            >
              {suggestion}
              {!value.includes(suggestion) && (
                <span className="absolute -top-6 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                  Click to add
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
