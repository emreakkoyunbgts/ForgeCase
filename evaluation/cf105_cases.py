"""Labelled synthetic acceptance data; no customer data or runtime fallback."""
from copy import deepcopy
from tests.support import record

DOMAINS = ['payments', 'cloud', 'core banking', 'data engineering', 'insurance',
           'logistics', 'retail', 'telecommunications', 'energy', 'manufacturing',
           'public services', 'travel']


def sources():
    for i, domain in enumerate(DOMAINS, 1):
        source = record(i)
        source.update(domain=domain, client_type=f'{domain} operator', duration_months=11,
                      challenge=f'Slow {domain} processing.',
                      solution=f'Improved {domain} processing using Python.')
        source['outcomes'] = [] if i == 12 else [
            {'metric': f'Processing latency reduced by {44+i}%.', 'source_ref': f'cf105-{i}.pdf#page=1'},
            {'metric': 'Operating cost reduced by 12%.', 'source_ref': f'cf105-{i}.pdf#page=1'},
        ]
        yield source


NEGATIVES = {
    'en': {'metric_swap':'Operating cost reduced by 45%.', 'wrong_duration':'The project lasted 12 months.',
           'negation':'Processing latency did not decrease.', 'date':'The project was completed in 2039.',
           'unsupported':'Customer satisfaction improved substantially.',
           'percentage_points':'Processing latency reduced by 45 percentage points.'},
    'de': {'metric_swap':'Die Betriebskosten wurden um 45 Prozent gesenkt.',
           'wrong_duration':'Das Projekt dauerte 12 Monate.', 'negation':'Die Verarbeitungslatenz ist nicht gesunken.',
           'date':'Das Projekt wurde 2039 abgeschlossen.', 'unsupported':'Die Kundenzufriedenheit hat sich erheblich verbessert.',
           'percentage_points':'Die Verarbeitungslatenz wurde um 45 Prozentpunkte gesenkt.'},
    'tr': {'metric_swap':'İşletme maliyeti yüzde 45 azaltıldı.', 'wrong_duration':'Proje 12 ay sürdü.',
           'negation':'İşlem gecikmesi azalmadı.', 'date':'Proje 2039 yılında tamamlandı.',
           'unsupported':'Müşteri memnuniyeti önemli ölçüde arttı.',
           'percentage_points':'İşlem gecikmesi 45 yüzde puan azaltıldı.'},
}


def poisoned(draft, source, language):
    for label, text in {**NEGATIVES[language], 'name_disclosure': source['client']}.items():
        changed = deepcopy(draft)
        changed['sections']['outcomes'][0]['outcomes'] = text
        yield label, changed
