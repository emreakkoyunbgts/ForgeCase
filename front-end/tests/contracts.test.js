import test from 'node:test';
import assert from 'node:assert/strict';
import {
  FIELDS, MEDIA_TYPES, hasVerifiedDraft, validateArtifact, validateDraft,
  validateRecordList, validateReport, workflowSignature,
} from '../src/contracts.js';

const recordId = 'eng-ui-01';
const makeDraft = (language = 'en') => ({
  engagement_ids: [recordId], language, client_named: false,
  titles: [{ title: 'A grounded case study', page: recordId }],
  sections: Object.fromEntries(Object.entries(FIELDS).map(([section, field]) =>
    [section, [{ [field]: 'Supported source text', page: recordId }]])),
  citations: [{ claim: 'Reduced latency by 45%', source_ref: 'closeout.pdf#page=1', page_ref: recordId }],
});
export const artifact = {
  artifact_id: '5bd02a25-32c3-48fb-9814-9991f5371e23', filename: 'eng-ui-01.pdf',
  media_type: MEDIA_TYPES.pdf,
  download_url: '/artifacts/5bd02a25-32c3-48fb-9814-9991f5371e23/download',
  provenance_url: '/artifacts/5bd02a25-32c3-48fb-9814-9991f5371e23/provenance',
};

test('all output languages retain the same editable single-source contract', () => {
  for (const language of ['en', 'de', 'tr']) {
    const draft = makeDraft(language);
    assert.equal(validateDraft(draft, recordId, language), draft);
  }
});

test('malformed Generator payloads are rejected before entering React state', () => {
  const mutations = [
    d => { d.sections.challenge = {}; },
    d => { d.sections.challenge[0].challenge = { text: 'not prose' }; },
    d => { delete d.sections.outcomes; },
    d => { d.titles = null; },
    d => { d.titles[0].page = 'other-source'; },
    d => { d.citations = 'invalid'; },
    d => { d.citations[0].page_ref = 'other-source'; },
    d => { d.language = 'de'; },
    d => { d.engagement_ids.push('other-source'); },
    d => { d.client_named = 'false'; },
    d => { d.unknown = 'hidden prose'; },
  ];
  for (const mutate of mutations) {
    const draft = makeDraft(); mutate(draft);
    assert.throws(() => validateDraft(draft, recordId, 'en'), /invalid draft/);
  }
  for (const payload of [null, [], 'text']) assert.throws(() => validateDraft(payload, recordId, 'en'));
});

test('an empty outcome list is valid, but an entirely empty case study is rejected', () => {
  const draft = makeDraft(); draft.sections.outcomes = []; draft.citations = [];
  assert.equal(validateDraft(draft, recordId, 'en'), draft);
  for (const field of Object.keys(FIELDS)) draft.sections[field] = [];
  assert.throws(() => validateDraft(draft, recordId, 'en'), /invalid draft/);
});

test('Vault list accepts the actual nullable limit and rejects unsafe render values', () => {
  const data = { items: [{ id: recordId, client: 'Private bank', client_type: 'Bank',
    domain: 'Payments', region: 'TR', challenge: 'Latency', may_be_named: false }], total: 1, limit: null, offset: 0 };
  assert.equal(validateRecordList(data), data);
  assert.throws(() => validateRecordList({ ...data, items: [{ ...data.items[0], client_type: {} }] }));
  assert.throws(() => validateRecordList({ ...data, items: [...data.items, ...data.items] }));
  assert.throws(() => validateRecordList({ ...data, total: '1' }));
});

test('only a correctly bound PASS can enable approval', () => {
  const draft = makeDraft();
  const signature = workflowSignature(recordId, 'en', draft);
  const report = { engagement_id: recordId, verdict: 'PASS', problems: [], signature };
  assert.equal(hasVerifiedDraft(report, signature, recordId), true);
  const edited = structuredClone(draft); edited.titles[0].title = 'Edited title';
  assert.equal(hasVerifiedDraft(report, workflowSignature(recordId, 'en', edited), recordId), false);
  assert.equal(hasVerifiedDraft(report, workflowSignature(recordId, 'de', draft), recordId), false);
  assert.equal(hasVerifiedDraft(report, signature, 'other-source'), false);
  assert.equal(hasVerifiedDraft({ ...report, problems: [{ why: 'Unsupported' }] }, signature, recordId), false);
  assert.equal(hasVerifiedDraft({ ...report, verdict: 'UNKNOWN' }, signature, recordId), false);
});

test('malformed or contradictory verification decisions fail closed', () => {
  const pass = { engagement_id: recordId, verdict: 'PASS', problems: [] };
  assert.equal(validateReport(pass, recordId), pass);
  for (const patch of [{ verdict: 'UNKNOWN' }, { problems: [{}] }, { engagement_id: 'other-source' }, { problems: null }]) {
    assert.throws(() => validateReport({ ...pass, ...patch }, recordId), /invalid assessment/);
  }
  assert.throws(() => validateReport({ ...pass, verdict: 'BLOCK', problems: [null] }, recordId));
});

test('artifact links, id, type and filename must agree before display or download', () => {
  assert.equal(validateArtifact(artifact, 'pdf'), artifact);
  for (const patch of [
    { download_url: 'https://outside.example/download' },
    { download_url: artifact.provenance_url },
    { provenance_url: '/artifacts/another/provenance' },
    { artifact_id: '../local-file' }, { filename: '../private.pdf' },
    { filename: 'other.docx' }, { media_type: 'text/html' },
  ]) assert.throws(() => validateArtifact({ ...artifact, ...patch }, 'pdf'), /invalid artifact/);
});

test('analyst coverage and gap payloads are validated before reaching React state', async () => {
  const { validateCoverage, validateGaps } = await import('../src/contracts.js');
  const coverage = {
    total_engagements: 3, by_domain: { 'core banking': 2, cloud: 1 },
    by_region: { GCC: 2, DE: 1 }, by_client_type: { 'GCC bank': 2, 'German bank': 1 },
    no_outcome: ['eng-03'],
  };
  assert.equal(validateCoverage(coverage), coverage);
  assert.throws(() => validateCoverage({ ...coverage, total_engagements: -1 }), /invalid coverage/);
  assert.throws(() => validateCoverage({ ...coverage, by_domain: { cloud: 'many' } }), /invalid coverage/);
  assert.throws(() => validateCoverage({ ...coverage, no_outcome: ['../escape'] }), /invalid coverage/);

  const gaps = { total_gaps: 1, gaps: [{ domain: 'cloud', region: 'DE' }] };
  assert.equal(validateGaps(gaps), gaps);
  assert.throws(() => validateGaps({ total_gaps: 2, gaps: gaps.gaps }), /invalid gap analysis/);
  assert.throws(() => validateGaps({ total_gaps: 1, gaps: [['cloud', 'DE']] }), /invalid gap analysis/);
});

test('an editable record is rejected unless every contract field has the right shape', async () => {
  const { readETag, validateRecord } = await import('../src/contracts.js');
  const record = {
    id: 'eng-01', client: 'A bank', client_type: 'GCC bank', domain: 'core banking',
    region: 'GCC', challenge: 'Slow settlement', solution: 'Event streaming',
    may_be_named: false, technologies: ['Kafka'],
    outcomes: [{ metric: 'latency reduced', source_ref: 'closeout.pdf#page=1' }],
  };
  assert.equal(validateRecord(record), record);
  assert.throws(() => validateRecord({ ...record, may_be_named: 'false' }), /invalid engagement record/);
  assert.throws(() => validateRecord({ ...record, technologies: 'Kafka' }), /invalid engagement record/);
  assert.throws(() => validateRecord({ ...record, outcomes: [{ metric: 'only' }] }), /invalid engagement record/);

  assert.equal(readETag(new Headers({ ETag: '"abc123"' })), '"abc123"');
  assert.equal(readETag(new Headers()), null);
  assert.equal(readETag(undefined), null);
});
