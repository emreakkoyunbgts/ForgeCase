"""Execute the actual Streamlit page against isolated HTTP route contracts."""
import pytest
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests.test_cf105_pipeline import mesh
APP = Path(__file__).resolve().parents[1] / 'console' / 'console.py'


def button(app, label):
    return next(item for item in app.button if item.label == label)


@pytest.mark.parametrize('language', ['en', 'de', 'tr'])
def test_console_verify_approve_download_and_edit_reset(mesh, language):
    clients, source, _, _ = mesh
    clients['vault'].post('/engagements', json=source,
                         headers={'Authorization': 'Bearer synthetic-test-token'})
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert not app.exception
    app.selectbox[0].select(source['id']).run()
    app.selectbox[1].select(language).run()
    button(app, 'Generate draft').click().run()
    assert not app.exception
    assert len(app.text_area) == 5
    button(app, 'Verify draft').click().run()
    assert not app.exception
    assert not app.checkbox[0].disabled
    app.checkbox[0].check().run()
    assert not button(app, 'Publish document').disabled
    button(app, 'Publish document').click().run()
    assert not app.exception
    assert app.session_state['document_bytes'].startswith(b'PK')
    assert json.loads(app.session_state['provenance_bytes'])['source_records'] == [source['id']]
    app.text_area[4].set_value('Invented outcome: 99% improvement').run()
    assert not app.exception
    assert not app.checkbox[0].value
    assert button(app, 'Publish document').disabled
    button(app, 'Verify draft').click().run()
    assert any('BLOCK' in str(error.value) for error in app.error)
    app.selectbox[1].select('de' if language != 'de' else 'tr').run()
    assert not app.text_area and button(app, 'Verify draft').disabled


def test_console_service_error_stops_pipeline(mesh, monkeypatch):
    import console.workflow
    from common.services import ServiceError
    def unavailable(*args, **kwargs):
        raise ServiceError('Vault unavailable', 503)
    monkeypatch.setattr(console.workflow, 'call_service', unavailable)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert any('Vault unavailable' in str(error.value) for error in app.error)
    assert button(app, 'Generate draft').disabled
