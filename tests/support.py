"""Synthetic contract data and explicit test-only provider responses."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

from generator.core import generate_mcs


def record(index=1):
    return {'id': f'eng-cf105-{index:02d}', 'client': f'Synthetic Example Bank {index}',
            'client_type': 'retail bank', 'may_be_named': False, 'domain': 'payments', 'region': 'TR',
            'challenge': 'Slow payment processing.', 'solution': 'Optimised payment processing.',
            'technologies': ['Python'], 'outcomes': [
                {'metric': f'Payment latency reduced by {44 + index}%', 'source_ref': 'synthetic.pdf#page=1'}]}


def translated(source, language):
    draft = generate_mcs(source)
    value = 44 + int(source['id'].rsplit('-', 1)[1])
    if language == 'de':
        texts = ['Zahlungsverkehr für eine Privatkundenbank', 'Eine Privatkundenbank in TR.',
                 'Langsame Zahlungsverarbeitung.', 'Optimierte Zahlungsverarbeitung.', 'Python',
                 f'Zahlungslatenz um {value} % reduziert.']
    elif language == 'tr':
        texts = ['Bir perakende bankası için ödemeler', 'TR bölgesinde bir perakende bankası.',
                 'Yavaş ödeme işlemleri.', 'Ödeme işlemleri iyileştirildi.', 'Python',
                 f'Ödeme gecikmesi %{value} azaltıldı.']
    else:
        draft['language'] = language
        return draft
    draft['titles'][0]['title'] = texts[0]
    from common.drafts import SECTION_FIELDS
    for i, (name, key) in enumerate(SECTION_FIELDS.items(), start=1):
        draft['sections'][name][0][key] = texts[i]
    for citation in draft['citations']:
        citation['claim'] = texts[-1]
    draft['language'] = language
    return draft


def closeout_pdf(source, extra_headers=()):
    from reportlab.pdfgen import canvas
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.setFont('Helvetica', 10)
    lines = [f"Engagement ID: {source['id']}", f"Client: {source['client']}",
             f"Client profile: {source['client_type']}", f"Domain: {source['domain']}",
             f"Region: {source['region']}",
             *extra_headers,
             *([f"Duration: {source['duration_months']} months"] if 'duration_months' in source else []),
             '1. The Challenge', source['challenge'],
             '2. Our Approach', source['solution'], '3. Technology', ', '.join(source['technologies']),
             '4. Outcomes', *['- ' + item['metric'] for item in source['outcomes']]]
    for i, line in enumerate(lines):
        pdf.drawString(50, 790 - i * 24, line)
    pdf.save()
    return output.getvalue()


def response(data=None, status=200, headers=None, content=b''):
    return SimpleNamespace(status_code=status, headers=headers or {}, content=content,
                           json=lambda: deepcopy(data))
