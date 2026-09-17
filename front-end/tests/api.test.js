import test from 'node:test';
import assert from 'node:assert/strict';
import { describeError, downloadArtifact, request } from '../src/api.js';

const artifact = {
  artifact_id: '5bd02a25-32c3-48fb-9814-9991f5371e23', filename: 'eng-ui-01.pdf', media_type: 'application/pdf',
  download_url: '/artifacts/5bd02a25-32c3-48fb-9814-9991f5371e23/download',
  provenance_url: '/artifacts/5bd02a25-32c3-48fb-9814-9991f5371e23/provenance',
};

test('HTTP requests retain one correlation ID and POST idempotency key without browser secrets', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, ...options }); return Response.json({ ok: true });
  });
  await request('vault', '/engagements', { trace: 'flow-01' });
  await request('generator', '/generate', { method: 'POST', body: { record_id: 'eng-01', language: 'tr' }, trace: 'flow-01', key: 'write-01' });
  assert.deepEqual(calls.map(call => call.headers['X-Correlation-ID']), ['flow-01', 'flow-01']);
  assert.equal(calls[1].headers['Idempotency-Key'], 'write-01');
  assert.equal(calls[1].headers.Authorization, undefined);
  assert.equal(calls[1].url, '/api/generator/generate');
  assert.deepEqual(JSON.parse(calls[1].body), { record_id: 'eng-01', language: 'tr' });
});

test('upload leaves the multipart boundary to the browser and preserves storage headers', async t => {
  const form = new FormData(); form.append('document', new Blob(['PDF']), 'closeout.pdf');
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    assert.equal(options.body, form);
    assert.equal(options.headers['Content-Type'], undefined);
    assert.ok(options.headers['Idempotency-Key']);
    return Response.json({ id: 'eng-01' }, { headers: { 'X-Vault-Stored': 'false', 'X-Vault-Detail': 'Write outcome uncertain' } });
  });
  const result = await request('reader', '/extract', { method: 'POST', body: form, trace: 'upload-01' });
  assert.equal(result.headers.get('X-Vault-Stored'), 'false');
  assert.equal(result.data.id, 'eng-01');
});

test('dependency failures preserve detail, status and trace and never retry a write', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json(
    { detail: { message: 'Model unavailable' } }, { status: 503, headers: { 'X-Correlation-ID': 'same-trace' } },
  ));
  await assert.rejects(request('publisher', '/publish', { method: 'POST', body: {}, trace: 'same-trace' }),
    error => error.status === 503 && error.message === 'Model unavailable' && error.correlationId === 'same-trace');
  assert.equal(fetch.mock.callCount(), 1);
});

test('timeout aborts once and malformed successful JSON yields an explicit service error', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  }));
  await assert.rejects(request('generator', '/generate', { method: 'POST', body: {}, timeout: 5 }), /timed out/);
  assert.equal(fetch.mock.callCount(), 1);
  fetch.mock.mockImplementation(async () => new Response('not JSON', { status: 200 }));
  await assert.rejects(request('vault', '/engagements'), /invalid response/);
});

test('download retrieves real HTTP bytes and chooses artifact and provenance filenames', async t => {
  const saved = [], requested = [], blobs = [];
  t.mock.method(globalThis, 'fetch', async url => {
    requested.push(url);
    return new Response(url.endsWith('/provenance') ? '{"verified":true}' : '%PDF-test-bytes', {
      headers: { 'Content-Type': url.endsWith('/provenance') ? 'application/json' : 'application/pdf' },
    });
  });
  const oldDocument = globalThis.document;
  globalThis.document = { body: { appendChild() {} }, createElement: () => ({ click() { saved.push(this.download); }, remove() {} }) };
  t.after(() => { if (oldDocument === undefined) delete globalThis.document; else globalThis.document = oldDocument; });
  t.mock.method(URL, 'createObjectURL', blob => { blobs.push(blob); return 'blob:test-download'; });
  t.mock.method(URL, 'revokeObjectURL', () => {});
  await downloadArtifact(artifact, 'download-trace');
  await downloadArtifact(artifact, 'download-trace', true);
  assert.deepEqual(saved, ['eng-ui-01.pdf', 'provenance.json']);
  assert.deepEqual(await Promise.all(blobs.map(blob => blob.text())), ['%PDF-test-bytes', '{"verified":true}']);
  assert.deepEqual(requested, ['/api/publisher' + artifact.download_url, '/api/publisher' + artifact.provenance_url]);
});

test('invalid download links and wrong response types cannot create a download', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('<html>Error</html>', { headers: { 'Content-Type': 'text/html' } }));
  await assert.rejects(downloadArtifact({ ...artifact, download_url: 'file:///private.pdf' }, 'trace'), /invalid artifact/);
  assert.equal(fetch.mock.callCount(), 0);
  await assert.rejects(downloadArtifact(artifact, 'trace'), /unexpected download type/);
});

test('nested service errors always become renderable text', () => {
  assert.equal(describeError([{ why: { metric: 'unsupported' } }, null]), '{"metric":"unsupported"}; "Request failed"');
  assert.equal(describeError({ why: { message: 'nested value' } }), '{"message":"nested value"}');
});
