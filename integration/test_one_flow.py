"""The supported CLI requires explicit approval to publish."""
from integration.one_flow import run_pipeline
from tests.test_cf105_pipeline import mesh


def test_pipeline_defaults_to_review(mesh):
    clients, source, _, _ = mesh
    clients['vault'].post('/engagements', json=source,
                         headers={'Authorization': 'Bearer synthetic-test-token'})
    flow = run_pipeline(record_id=source['id'])
    assert flow.verified and not flow.approved and flow.artifact is None


def test_pipeline_explicit_approval_downloads(mesh):
    clients, source, _, _ = mesh
    clients['vault'].post('/engagements', json=source,
                         headers={'Authorization': 'Bearer synthetic-test-token'})
    flow = run_pipeline(record_id=source['id'], language='de', publish=True)
    assert flow.artifact and flow.download().startswith(b'PK')
