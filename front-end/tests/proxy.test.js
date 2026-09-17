import test from 'node:test';
import assert from 'node:assert/strict';
import makeConfig from '../vite.config.js';

test('local proxy injects fallback token only if incoming authorization is absent', () => {
  const previous = process.env.CASEFORGE_TOKEN;
  process.env.CASEFORGE_TOKEN = 'synthetic-test-token';
  try {
    const config = makeConfig({ mode: 'test' });
    assert.equal(config.server.host, '127.0.0.1');
    assert.equal(config.preview.proxy, config.server.proxy);
    const [pattern, proxy] = Object.entries(config.server.proxy).find(([key]) => key.includes('vault'));
    assert.equal(new RegExp(pattern).test('/api/vault/engagements'), true);
    assert.equal(new RegExp(pattern).test('/api/vault-extra/engagements'), false);
    assert.equal(proxy.rewrite('/api/vault/engagements'), '/engagements');
    let callback;
    proxy.configure({ on: (event, fn) => { assert.equal(event, 'proxyReq'); callback = fn; } });
    const headers = [];
    callback({ setHeader: (...args) => headers.push(args) }, { headers: {} });
    callback({ setHeader: (...args) => headers.push(args) }, { headers: { authorization: 'Bearer incoming-user-token' } });
    assert.deepEqual(headers, [['Authorization', 'Bearer synthetic-test-token']]);
  } finally {
    if (previous === undefined) delete process.env.CASEFORGE_TOKEN; else process.env.CASEFORGE_TOKEN = previous;
  }
});
