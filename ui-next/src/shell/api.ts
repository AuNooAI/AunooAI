/** JSON fetch for the monolith API: same-origin session cookie, FastAPI `detail` turned into the error message. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...rest,
    headers: { Accept: 'application/json', ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.hash)}`);
    throw new ApiError('Signed out', 401);
  }
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown; error?: unknown; message?: unknown } | undefined) ?? {};
    const msg = detail.detail ?? detail.error ?? detail.message;
    throw new ApiError(typeof msg === 'string' ? msg : `${res.status} ${res.statusText}`, res.status);
  }
  return data as T;
}

/** Error text for a toast. */
export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
