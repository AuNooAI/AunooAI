/**
 * Context calculation utilities (from consensus_analysis.html)
 */

export const CONTEXT_LIMITS: Record<string, number> = {
  'gpt-3.5-turbo': 16385,
  'gpt-3.5-turbo-16k': 16385,
  'gpt-4': 8192,
  'gpt-4-32k': 32768,
  'gpt-4-turbo': 128000,
  'gpt-4-turbo-preview': 128000,
  'gpt-4o': 128000,
  'gpt-4o-mini': 128000,
  'gpt-4.1': 1000000,
  'gpt-4.1-mini': 1000000,
  'gpt-4.1-nano': 1000000,
  'claude-3-opus': 200000,
  'claude-3-sonnet': 200000,
  'claude-3-haiku': 200000,
  'claude-3.5-sonnet': 200000,
  'claude-4': 200000,
  'claude-4-opus': 200000,
  'claude-4-sonnet': 200000,
  'claude-4-haiku': 200000,
  'gemini-pro': 32768,
  'gemini-1.5-pro': 2097152,
  'llama-2-70b': 4096,
  'llama-3-70b': 8192,
  'mixtral-8x7b': 32768,
  'default': 16385
};

export function estimateTokens(text: string): number {
  // Rough estimation: 1 token ≈ 4 characters for English
  return Math.ceil((text?.length || 0) / 4);
}

export function calculateOptimalSampleSize(
  model: string,
  message: string,
  mode: string = 'auto',
  customLimit?: number
): number {
  if (mode === 'custom' && customLimit) {
    return customLimit;
  }

  const contextLimit = CONTEXT_LIMITS[model] || CONTEXT_LIMITS.default;
  const isMegaContext = contextLimit >= 1000000;

  let baseSampleSize: number;

  switch (mode) {
    case 'focused':
      baseSampleSize = isMegaContext ? 50 : 25;
      break;
    case 'balanced':
      baseSampleSize = isMegaContext ? 100 : 50;
      break;
    case 'comprehensive':
      baseSampleSize = isMegaContext ? 200 : 100;
      break;
    case 'auto':
    default:
      // Auto-size based on context window and message complexity
      const messageComplexity = (message?.length || 0) > 200 ? 1.2 : 1.0;
      let baseSize = isMegaContext ? 150 : 75;

      // For trend convergence analysis, we need more articles
      if (message && (message.includes('trend') || message.includes('convergence'))) {
        baseSize = isMegaContext ? 300 : 150;
      }

      baseSampleSize = Math.round(baseSize * messageComplexity);
      break;
  }

  // Ensure reasonable limits
  const maxLimit = isMegaContext ? 1000 : 400;
  const minLimit = 10;

  return Math.max(minLimit, Math.min(baseSampleSize, maxLimit));
}

export interface ContextInfo {
  sampleSize: number;
  totalTokens: number;
  contextUsage: number;
  contextLimit: number;
  modelIndicator: string;
  displayText: string;
  colorClass: string;
}

export function calculateContextInfo(
  model: string,
  sampleSizeMode: string = 'auto',
  customLimit?: number
): ContextInfo {
  const message = 'trend convergence analysis'; // Default message for estimation
  const sampleSize = calculateOptimalSampleSize(model, message, sampleSizeMode, customLimit);
  const contextLimit = CONTEXT_LIMITS[model] || CONTEXT_LIMITS.default;

  // Estimate token usage
  const systemTokens = 500; // System prompt
  const messageTokens = estimateTokens(message);
  const tokensPerArticle = 180; // Optimized article representation
  const articleTokens = sampleSize * tokensPerArticle;
  const totalTokens = systemTokens + messageTokens + articleTokens;

  const contextUsage = (totalTokens / contextLimit) * 100;

  // Model indicator
  const modelIndicator = contextLimit >= 1000000 ? ' 🚀1M' :
                        contextLimit >= 200000 ? ' ⚡200K' :
                        contextLimit >= 100000 ? ' 💫100K' : '';

  const displayText = `Context: ${sampleSize} articles, ~${totalTokens.toLocaleString()} tokens (${contextUsage.toFixed(1)}%)${modelIndicator}`;

  // Color coding
  let colorClass = 'text-blue-700'; // Default blue
  if (contextUsage > 90) {
    colorClass = 'text-red-600 font-bold';
  } else if (contextUsage > 70) {
    colorClass = 'text-orange-600 font-semibold';
  } else if (contextUsage > 50) {
    colorClass = 'text-green-600 font-medium';
  }

  return {
    sampleSize,
    totalTokens,
    contextUsage,
    contextLimit,
    modelIndicator,
    displayText,
    colorClass
  };
}
