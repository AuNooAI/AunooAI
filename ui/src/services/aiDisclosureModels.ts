// The models that actually ran on this deployment, for EU AI Act Art. 50
// disclosures. Backed by /api/ai-disclosure/models, which reads the usage
// ledger (last 30 days, most-used first) and falls back to the configured
// model list only when the ledger is missing or empty.
//
// One fetch per page load, shared by the dashboard footer and every export.
// Exports are synchronous and fire on a click long after load, so they read
// the cache; the fetch is kicked off as soon as this module is imported.

let cachedNames: string | null = null;
let inflight: Promise<string | null> | null = null;

export function getDeployedModelNames(): string | null {
  return cachedNames;
}

export function loadDeployedModelNames(): Promise<string | null> {
  if (cachedNames) return Promise.resolve(cachedNames);
  if (inflight) return inflight;
  inflight = fetch('/api/ai-disclosure/models', { credentials: 'include' })
    .then(r => (r.ok ? r.json() : null))
    .then((data: { models?: Array<{ name?: string }> } | null) => {
      const models = data?.models;
      if (Array.isArray(models) && models.length > 0) {
        cachedNames = models.map(m => m.name).filter(Boolean).join(', ');
      }
      return cachedNames;
    })
    .catch(() => null)
    .finally(() => { inflight = null; });
  return inflight;
}

// Wording for a disclosure that cannot name the exact model the artifact
// came from. Names the deployment's real models when known; the fallback
// only appears if the ledger request failed.
export function deployedModelsPhrase(): string {
  return cachedNames || 'the large language models configured for this site';
}

loadDeployedModelNames();
