"""Independent source facts, language templates and literal evidence for CF-120.

No application code is imported. This corpus describes twelve fixed evaluation
records and one named-client case; it is not a general semantic oracle.
"""

LANGUAGES = ('en', 'de', 'tr')
RECORD_01_ID = 'eng-cf105-01'
MISSING_OUTCOME = '[MISSING: no measurable outcome was recorded for this engagement]'
DOMAINS = (
    ('payments', 'Zahlungsverkehr', 'Zahlungsdienstleister', 'ödemeler', 'ödeme hizmeti sağlayıcısı'),
    ('cloud', 'Cloud', 'Cloud-Betreiber', 'bulut', 'bulut işletmecisi'),
    ('core banking', 'Kernbankgeschäft', 'Kernbankbetreiber', 'çekirdek bankacılık', 'çekirdek bankacılık işletmecisi'),
    ('data engineering', 'Datenengineering', 'Datenengineering-Anbieter', 'veri mühendisliği', 'veri mühendisliği işletmecisi'),
    ('insurance', 'Versicherungen', 'Versicherungsanbieter', 'sigortacılık', 'sigortacılık işletmecisi'),
    ('logistics', 'Logistik', 'Logistikbetreiber', 'lojistik', 'lojistik işletmecisi'),
    ('retail', 'Einzelhandel', 'Einzelhandelsbetreiber', 'perakende', 'perakende işletmecisi'),
    ('telecommunications', 'Telekommunikation', 'Telekommunikationsbetreiber', 'telekomünikasyon', 'telekomünikasyon işletmecisi'),
    ('energy', 'Energie', 'Energiebetreiber', 'enerji', 'enerji işletmecisi'),
    ('manufacturing', 'Fertigung', 'Fertigungsbetreiber', 'üretim', 'üretim işletmecisi'),
    ('public services', 'öffentliche Dienste', 'Betreiber öffentlicher Dienste', 'kamu hizmetleri', 'kamu hizmetleri işletmecisi'),
    ('travel', 'Reisen', 'Reiseanbieter', 'seyahat', 'seyahat işletmecisi'),
)

SOURCES = {}
SPANS = {}
EVIDENCE = {}
EVALUATION_IDS = tuple(f'eng-cf105-{index:02d}' for index in range(1, 13))

for index, (domain, de_domain, de_operator, tr_domain, tr_operator) in enumerate(DOMAINS, 1):
    record_id = f'eng-cf105-{index:02d}'
    latency = 44 + index
    latency_en = f'Processing latency reduced by {latency}%.'
    cost_en = 'Operating cost reduced by 12%.'
    has_outcomes = index != 12
    SOURCES[record_id] = {
        'id': record_id, 'client': f'Synthetic Example Bank {index}',
        'client_type': f'{domain} operator', 'may_be_named': False,
        'domain': domain, 'region': 'TR',
        'challenge': f'Slow {domain} processing.',
        'solution': f'Improved {domain} processing using Python.',
        'technologies': ['Python'],
        'outcomes': [
            {'metric': latency_en, 'source_ref': f'cf105-{index}.pdf#page=1'},
            {'metric': cost_en, 'source_ref': f'cf105-{index}.pdf#page=1'},
        ] if has_outcomes else [],
        'duration_months': 11,
    }
    localized = {
        'en': (
            f'{domain} for {domain} operator', f'{domain} operator in TR.',
            f'Slow {domain} processing.', f'Improved {domain} processing using Python.',
            latency_en, cost_en,
        ),
        'de': (
            f'{de_domain} für {de_operator}', f'{de_operator} in TR.',
            f'Langsame Verarbeitung im Bereich {de_domain}.',
            f'Verbesserte Verarbeitung im Bereich {de_domain} mit Python.',
            f'Verarbeitungslatenz um {latency} Prozent reduziert.',
            'Betriebskosten um 12 Prozent gesenkt.',
        ),
        'tr': (
            f'{tr_operator} için {tr_domain}', f'TR bölgesinde {tr_operator}.',
            f'{tr_domain.capitalize()} alanında yavaş işlemler.',
            f'Python ile {tr_domain} alanında iyileştirilmiş işlemler.',
            f'İşlem gecikmesi %{latency} azaltıldı.', 'İşletme maliyeti %12 azaltıldı.',
        ),
    }
    # Preserve source #1's previously reviewed translations verbatim.
    if index == 1:
        localized['de'] = (*localized['de'][:2], 'Langsame Zahlungsverarbeitung.',
                           'Verbesserte Zahlungsverarbeitung mit Python.', *localized['de'][4:])
        localized['tr'] = (*localized['tr'][:2], 'Yavaş ödeme işlemleri.',
                           'Python ile iyileştirilmiş ödeme işlemleri.', *localized['tr'][4:])
    SPANS[record_id] = {}
    for language, (title, context, challenge, approach, metric, cost) in localized.items():
        texts = {
            '/titles/0/title': title,
            '/sections/context/0/region': context,
            '/sections/challenge/0/challenge': challenge,
            '/sections/approach/0/approach': approach,
            '/sections/technology/0/technologies': 'Python',
            '/sections/outcomes/0/outcomes': f'{metric}; {cost}' if has_outcomes else MISSING_OUTCOME,
        }
        if has_outcomes:
            texts.update({'/citations/0/claim': metric, '/citations/1/claim': cost})
        SPANS[record_id][language] = texts
    EVIDENCE[record_id] = {
        '/titles/0/title': [('/domain', domain), ('/client_type', f'{domain} operator')],
        '/sections/context/0/region': [('/client_type', f'{domain} operator'), ('/region', 'TR')],
        '/sections/challenge/0/challenge': [('/challenge', f'Slow {domain} processing.')],
        '/sections/approach/0/approach': [('/solution', f'Improved {domain} processing using Python.')],
        '/sections/technology/0/technologies': [('/technologies/0', 'Python')],
        '/sections/outcomes/0/outcomes': [('/outcomes/0/metric', latency_en),
                                         ('/outcomes/1/metric', cost_en)] if has_outcomes else [],
    }
    if has_outcomes:
        EVIDENCE[record_id].update({
            '/citations/0/claim': [('/outcomes/0/metric', latency_en)],
            '/citations/1/claim': [('/outcomes/1/metric', cost_en)],
        })

SOURCE_01 = SOURCES[RECORD_01_ID]
NAMED_RECORD_ID = 'eng-cf120-named'
NAMED_SOURCE = {
    'id': NAMED_RECORD_ID, 'client': 'Synthetic Named Company',
    'client_type': 'payments operator', 'may_be_named': True,
    'domain': 'payments', 'region': 'TR', 'challenge': 'Slow payments processing.',
    'solution': 'Improved payments processing using Python.', 'technologies': ['Python'],
    'outcomes': [
        {'metric': 'Processing latency reduced by 45%.', 'source_ref': 'cf120-named.pdf#page=1'},
        {'metric': 'Operating cost reduced by 12%.', 'source_ref': 'cf120-named.pdf#page=1'},
    ],
    'duration_months': 11,
}
SOURCES[NAMED_RECORD_ID] = NAMED_SOURCE
SPANS[NAMED_RECORD_ID] = {
    language: {**SPANS[RECORD_01_ID][language], '/titles/0/title': title,
               '/sections/context/0/region': context}
    for language, title, context in (
        ('en', 'payments for Synthetic Named Company', 'Synthetic Named Company in TR.'),
        ('de', 'Zahlungsverkehr für Synthetic Named Company', 'Synthetic Named Company in TR.'),
        ('tr', 'Synthetic Named Company için ödemeler', 'TR bölgesinde Synthetic Named Company.'),
    )
}
EVIDENCE[NAMED_RECORD_ID] = {
    **{span: list(pairs) for span, pairs in EVIDENCE[RECORD_01_ID].items()},
    '/titles/0/title': [('/domain', 'payments'), ('/client', 'Synthetic Named Company')],
    '/sections/context/0/region': [('/client', 'Synthetic Named Company'), ('/region', 'TR')],
}


SECTION_SPANS = (
    ('context', 'region'), ('challenge', 'challenge'), ('approach', 'approach'),
    ('technology', 'technologies'), ('outcomes', 'outcomes'),
)
# Clean publication rotation: every language meets every valid format/layout.
PUBLICATIONS = (('docx', 'full-case-study'), ('pdf', 'full-case-study'),
                ('pdf', 'one-pager'), ('pdf', 'single-slide'))


class UnknownFixture(LookupError):
    """The request asks for content outside the independently declared corpus."""


def fixture_draft(record_id, language):
    """The documented canonical single-source draft, written out from fixture text."""
    texts = SPANS[record_id][language]
    source = SOURCES[record_id]
    return {
        'engagement_ids': [record_id],
        'titles': [{'title': texts['/titles/0/title'], 'page': record_id}],
        'sections': {name: [{field: texts[f'/sections/{name}/0/{field}'], 'page': record_id}]
                     for name, field in SECTION_SPANS},
        'citations': [{'claim': texts[f'/citations/{index}/claim'], 'source_ref': outcome['source_ref'],
                       'page_ref': record_id}
                      for index, outcome in enumerate(source['outcomes'])],
        'client_named': source['may_be_named'] is True,
        'language': language,
    }


def display_values(record_id, language):
    """Publisher's final visible prose for a clean fixture draft (runbook: MCS -> display)."""
    texts = SPANS[record_id][language]
    return {'title': texts['/titles/0/title'], 'client_type': texts['/sections/context/0/region'],
            'challenge': texts['/sections/challenge/0/challenge'],
            'approach': texts['/sections/approach/0/approach'],
            'technology': texts['/sections/technology/0/technologies'],
            'outcomes': texts['/sections/outcomes/0/outcomes']}


def expected_span_text(record_id, span_id, language):
    try:
        return SPANS[record_id][language][span_id]
    except KeyError:
        raise UnknownFixture(f'no fixture text for record={record_id!r} language={language!r} span={span_id!r}') from None


def evidence_for(record_id, span_id):
    try:
        return EVIDENCE[record_id][span_id]
    except KeyError:
        raise UnknownFixture(f'no fixture evidence for record={record_id!r} span={span_id!r}') from None


def record_id_for_english_spans(spans):
    """The translation wire has no record id; identify then validate its prose."""
    by_title = {texts['en']['/titles/0/title']: record_id for record_id, texts in SPANS.items()}
    for span in spans:
        if span.get('id') == '/titles/0/title':
            try:
                return by_title[span.get('text')]
            except (KeyError, TypeError):
                raise UnknownFixture(f'no fixture source for title {span.get("text")!r}') from None
    raise UnknownFixture('translation request carried no /titles/0/title span')
