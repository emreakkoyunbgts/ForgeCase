import { MEDIA_TYPES, validateArtifact } from './contracts.js';

const TIMEOUTS = { reader: 35000, generator: 80000, verifier: 80000, publisher: 100000 };

export function newTrace() { return crypto.randomUUID(); }

export function describeError(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => describeError(item?.msg || item?.why || item)).join('; ');
  const message = detail?.message || detail?.why || detail?.detail || detail?.type || detail;
  return typeof message === 'string' ? message : JSON.stringify(message || 'Request failed');
}

export async function request(service, path, { method = 'GET', body, trace, key, timeout, binary = false } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout || TIMEOUTS[service] || 15000);
  const headers = { 'X-Correlation-ID': trace || newTrace() };
  if (method !== 'GET') headers['Idempotency-Key'] = key || newTrace();
  const multipart = body instanceof FormData;
  if (body && !multipart) headers['Content-Type'] = 'application/json';
  try {
    const response = await fetch(`/api/${service}${path}`, {
      method, headers, body: body ? (multipart ? body : JSON.stringify(body)) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.detail ? describeError(payload.detail) : `HTTP ${response.status}`);
      error.status = response.status;
      error.detail = payload.detail;
      error.correlationId = response.headers.get('X-Correlation-ID') || headers['X-Correlation-ID'];
      throw error;
    }
    let data;
    try { data = binary ? await response.blob() : await response.json(); }
    catch { throw new Error('The service returned an invalid response. Retry the step when it is available.'); }
    return { data, headers: response.headers };
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The service timed out. Retry the step when it is available.');
    throw error;
  } finally { clearTimeout(timer); }
}

export async function downloadArtifact(metadata, trace, provenance = false) {
  const format = Object.keys(MEDIA_TYPES).find(key => MEDIA_TYPES[key] === metadata?.media_type);
  validateArtifact(metadata, format);
  const path = provenance ? metadata.provenance_url : metadata.download_url;
  const { data } = await request('publisher', path, { trace, binary: true });
  const expectedType = provenance ? 'application/json' : metadata.media_type;
  if (data.type.split(';')[0] !== expectedType) throw new Error('Publisher returned an unexpected download type');
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = provenance ? 'provenance.json' : metadata.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
