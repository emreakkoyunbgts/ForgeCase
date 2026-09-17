"""UI-independent HTTP workflow with content-bound verification and approval."""
from copy import deepcopy
from dataclasses import dataclass, field
import re
from urllib.parse import quote
from uuid import uuid4
from threading import Lock

from common.drafts import draft_hash, normalize_draft, validate_record_id
from common.services import ALL_SERVICES, ServiceError, call_service, response_json


@dataclass
class Workflow:
    record_id: str = ''
    language: str = 'en'
    trace: str = field(default_factory=lambda: str(uuid4()))
    draft: dict | None = None
    report: dict | None = None
    verified_hash: str | None = None
    approved_hash: str | None = None
    artifact: dict | None = None
    last_extracted: dict | None = None
    _publish_lock: object = field(default_factory=Lock, repr=False, compare=False)
    _published_key: tuple | None = field(default=None, repr=False)

    def headers(self):
        return {'X-Correlation-ID': self.trace}

    def invalidate(self):
        self.report = self.verified_hash = self.approved_hash = self.artifact = None
        self._published_key = None

    def select(self, record_id, language=None):
        if record_id:
            validate_record_id(record_id)
        language = language or self.language
        if language not in {'en', 'de', 'tr'}:
            raise ValueError('Unsupported language')
        if record_id != self.record_id or language != self.language:
            self.record_id, self.language = record_id, language
            self.draft = None
            self.trace = str(uuid4())
            self.invalidate()

    def list_records(self):
        data = response_json(call_service('GET', ALL_SERVICES['vault'] + '/engagements', headers=self.headers()))
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ServiceError('Vault returned an invalid record list', 502)
        return data['items']

    def extract(self, filename, content):
        self.select('')
        self.trace = str(uuid4())
        response = call_service('POST', ALL_SERVICES['reader'] + '/extract', timeout=35,
                                headers=self.headers(), files={'document': (filename, content, 'application/pdf')})
        self.last_extracted = response_json(response)
        if response.headers.get('X-Vault-Stored') != 'true':
            raise ServiceError('Extraction succeeded, but Vault storage was not confirmed: ' +
                               response.headers.get('X-Vault-Detail', 'unavailable'), 503)
        validate_record_id(self.last_extracted['id'])
        self.record_id = self.last_extracted['id']
        return self.last_extracted

    def generate(self):
        if not self.record_id:
            raise ValueError('Select a stored source record first')
        self.draft = None
        self.invalidate()
        data = response_json(call_service('POST', ALL_SERVICES['generator'] + '/generate', timeout=80,
            headers=self.headers(), json={'record_id': self.record_id, 'language': self.language}))
        self.draft = normalize_draft(data, self.record_id, self.language)
        return self.draft

    def edit(self, draft):
        normalized = normalize_draft(draft, self.record_id, self.language)
        if self.draft != normalized:
            self.draft = normalized
            self.invalidate()

    @property
    def signature(self):
        return draft_hash(self.draft) if self.draft is not None else None

    @property
    def verified(self):
        return bool(self.draft is not None and self.report and self.report.get('verdict') == 'PASS'
                    and self.report.get('engagement_id') == self.record_id
                    and self.report.get('problems') == [] and self.verified_hash == self.signature)

    @property
    def approved(self):
        return self.verified and self.approved_hash == self.signature

    def verify(self):
        if self.draft is None:
            raise ValueError('Generate a draft first')
        self.invalidate()
        report = response_json(call_service('POST', ALL_SERVICES['verifier'] + '/verify', timeout=80,
            headers=self.headers(), json={'record_id': self.record_id, 'draft': self.draft, 'language': self.language}))
        if (not isinstance(report, dict) or report.get('engagement_id') != self.record_id
                or report.get('verdict') not in {'PASS', 'BLOCK'} or not isinstance(report.get('problems'), list)
                or report['verdict'] == 'PASS' and report['problems']):
            raise ServiceError('Verifier returned an invalid assessment', 502)
        self.report = report
        self.verified_hash = self.signature if report['verdict'] == 'PASS' else None
        return report

    def approve(self, approved):
        if approved and not self.verified:
            raise ValueError('This exact draft must pass verification first')
        self.approved_hash = self.signature if approved else None

    def publish(self, format='docx', layout='full-case-study'):
        # This protects one UI session only. The service Idempotency-Key does
        # not provide a distributed exactly-once guarantee.
        if not self._publish_lock.acquire(blocking=False):
            raise ServiceError('Publication is already in progress', 409)
        try:
            return self._publish(format, layout)
        finally:
            self._publish_lock.release()

    def _publish(self, format, layout):
        if not self.approved:
            raise ValueError('Verify and approve this exact draft first')
        publication_key = (self.signature, format, layout)
        if self.artifact is not None and self._published_key == publication_key:
            return self.artifact
        self.artifact = None
        artifact = response_json(call_service('POST', ALL_SERVICES['publisher'] + '/publish', timeout=100,
            headers=self.headers(), json={'record_id': self.record_id, 'draft': self.draft,
                'language': self.language, 'format': format, 'layout': layout}))
        for key in ('download_url', 'provenance_url'):
            if not re.fullmatch(r'/artifacts/[0-9a-f-]+/(download|provenance)', artifact.get(key, '')):
                raise ServiceError('Publisher returned an invalid artifact', 502)
        self.artifact = artifact
        self._published_key = publication_key
        return artifact

    def download(self, provenance=False):
        if self.artifact is None:
            raise ValueError('Publish a document first')
        path = self.artifact['provenance_url' if provenance else 'download_url']
        return call_service('GET', ALL_SERVICES['publisher'] + path, headers=self.headers()).content
