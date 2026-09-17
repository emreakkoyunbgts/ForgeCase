export const FIELDS = {
  context: 'region', challenge: 'challenge', approach: 'approach',
  technology: 'technologies', outcomes: 'outcomes',
};
export const MEDIA_TYPES = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const unsafeFilename = value => /[\\/]/.test(value) || [...value].some(char => char.charCodeAt(0) < 32);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const onlyKeys = (value, keys) => Object.keys(value).every(key => keys.includes(key));

export function validRecordId(value) {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= 200 &&
    !['.', '..'].includes(value) && !unsafeFilename(value);
}

export function validateRecordList(data) {
  if (!object(data) || !Array.isArray(data.items) ||
    !['total', 'offset'].every(key => Number.isInteger(data[key]) && data[key] >= 0) ||
    !(data.limit === null || (Number.isInteger(data.limit) && data.limit > 0)) ||
    !data.items.every(item => object(item) && validRecordId(item.id) &&
      ['client', 'client_type', 'domain', 'region', 'challenge'].every(key => typeof item[key] === 'string') &&
      typeof item.may_be_named === 'boolean') ||
    new Set(data.items.map(item => item.id)).size !== data.items.length) {
    throw new Error('Vault returned an invalid record list');
  }
  return data;
}

export function validateDraft(data, recordId, language) {
  const entries = (items, field) => Array.isArray(items) && items.every(item =>
    object(item) && onlyKeys(item, [field, 'page']) &&
    typeof item[field] === 'string' && item.page === recordId);
  if (!object(data) || !validRecordId(recordId) || !['en', 'de', 'tr'].includes(language) ||
    !onlyKeys(data, ['engagement_ids', 'titles', 'sections', 'citations', 'client_named', 'language']) ||
    data.language !== language || !Array.isArray(data.engagement_ids) ||
    data.engagement_ids.length !== 1 || data.engagement_ids[0] !== recordId ||
    typeof data.client_named !== 'boolean' || !entries(data.titles, 'title') ||
    !object(data.sections) || !onlyKeys(data.sections, Object.keys(FIELDS)) ||
    !Object.entries(FIELDS).every(([section, field]) => entries(data.sections[section], field)) ||
    !Object.entries(FIELDS).some(([section, field]) => data.sections[section].some(item => item[field].trim())) ||
    !Array.isArray(data.citations) || !data.citations.every(item => object(item) &&
      onlyKeys(item, ['claim', 'source_ref', 'page_ref']) && typeof item.claim === 'string' &&
      typeof item.source_ref === 'string' && item.page_ref === recordId) || JSON.stringify(data).length > 24000) {
    throw new Error('Generator returned an invalid draft or a different source or language');
  }
  return data;
}

export function validateReport(data, recordId) {
  if (!object(data) || data.engagement_id !== recordId || !['PASS', 'BLOCK'].includes(data.verdict) ||
    !Array.isArray(data.problems) || !data.problems.every(object) ||
    (data.verdict === 'PASS' && data.problems.length)) {
    throw new Error('Verifier returned an invalid assessment');
  }
  return data;
}

export function validateArtifact(data, format) {
  if (!object(data) || !UUID.test(data.artifact_id) || !Object.hasOwn(MEDIA_TYPES, format) ||
    typeof data.filename !== 'string' || !data.filename.trim() || data.filename.length > 255 ||
    unsafeFilename(data.filename) ||
    !data.filename.endsWith('.' + format) || data.media_type !== MEDIA_TYPES[format] ||
    data.download_url !== `/artifacts/${data.artifact_id}/download` ||
    data.provenance_url !== `/artifacts/${data.artifact_id}/provenance`) {
    throw new Error('Publisher returned invalid artifact metadata');
  }
  return data;
}

// Mirrors VALID_REGIONS in common/contract.py; the vault rejects anything else.
export const REGIONS = ['UK', 'DE', 'NL', 'TR', 'GCC'];

export function readETag(headers) {
  const value = headers?.get?.('ETag');
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function validateRecord(data) {
  if (!object(data) || !validRecordId(data.id) ||
    !['client', 'client_type', 'domain', 'region', 'challenge', 'solution'].every(key => typeof data[key] === 'string') ||
    typeof data.may_be_named !== 'boolean' ||
    !Array.isArray(data.technologies) || !data.technologies.every(item => typeof item === 'string') ||
    !Array.isArray(data.outcomes) || !data.outcomes.every(item => object(item) &&
      typeof item.metric === 'string' && typeof item.source_ref === 'string')) {
    throw new Error('Vault returned an invalid engagement record');
  }
  return data;
}

export function validateCoverage(data) {
  const counts = value => object(value) &&
    Object.values(value).every(count => Number.isInteger(count) && count >= 0);
  if (!object(data) || !Number.isInteger(data.total_engagements) || data.total_engagements < 0 ||
    !['by_domain', 'by_region', 'by_client_type'].every(key => counts(data[key])) ||
    !Array.isArray(data.no_outcome) || !data.no_outcome.every(validRecordId)) {
    throw new Error('Analyst returned an invalid coverage profile');
  }
  return data;
}

export function validateGaps(data) {
  if (!object(data) || !Number.isInteger(data.total_gaps) || data.total_gaps < 0 ||
    !Array.isArray(data.gaps) || data.gaps.length !== data.total_gaps ||
    !data.gaps.every(item => object(item) && onlyKeys(item, ['domain', 'region']) &&
      typeof item.domain === 'string' && typeof item.region === 'string')) {
    throw new Error('Analyst returned an invalid gap analysis');
  }
  return data;
}

export function workflowSignature(recordId, language, draft) {
  return JSON.stringify({ recordId, language, draft });
}

export function hasVerifiedDraft(report, signature, recordId) {
  return Boolean(report?.signature === signature && report.verdict === 'PASS' &&
    report.engagement_id === recordId && Array.isArray(report.problems) && report.problems.length === 0);
}
