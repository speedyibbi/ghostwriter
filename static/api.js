/** Shared fetch helper with optional API key (localStorage). */
const API_KEY_STORAGE = 'ghostwriter_api_key';

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || '';
}

function setApiKey(key) {
  if (key) localStorage.setItem(API_KEY_STORAGE, key.trim());
  else localStorage.removeItem(API_KEY_STORAGE);
}

async function api(method, path, body, retried = false) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  const key = getApiKey();
  if (key) opts.headers['X-API-Key'] = key;
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));

  if (res.status === 401 && !retried && String(data.detail || '').includes('API key')) {
    const entered = prompt('This server requires an API key. Enter your Ghostwriter API key:');
    if (entered) {
      setApiKey(entered);
      return api(method, path, body, true);
    }
  }

  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

async function ensureApiKeyConfigured() {
  const cfg = await fetch('/config').then(r => r.json()).catch(() => ({}));
  if (cfg.api_key_required && !getApiKey()) {
    const entered = prompt('API key required. Enter your Ghostwriter API key:');
    if (entered) setApiKey(entered);
  }
}
