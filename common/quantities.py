"""Conservative EN/DE/TR quantity normalization for grounding, not fuzzy similarity."""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

UNITS = {
    'second': ('seconds', 1), 'seconds': ('seconds', 1), 'sec': ('seconds', 1),
    'sekunde': ('seconds', 1), 'sekunden': ('seconds', 1), 'saniye': ('seconds', 1),
    'minute': ('seconds', 60), 'minutes': ('seconds', 60), 'min': ('seconds', 60),
    'minuten': ('seconds', 60), 'dakika': ('seconds', 60),
    'hour': ('seconds', 3600), 'hours': ('seconds', 3600), 'hrs': ('seconds', 3600),
    'hr': ('seconds', 3600), 'stunde': ('seconds', 3600), 'stunden': ('seconds', 3600),
    'saat': ('seconds', 3600),
    'day': ('days', 1), 'days': ('days', 1), 'tag': ('days', 1), 'tage': ('days', 1),
    'tagen': ('days', 1), 'gün': ('days', 1),
    'month': ('months', 1), 'months': ('months', 1), 'monat': ('months', 1),
    'monate': ('months', 1), 'monaten': ('months', 1), 'ay': ('months', 1),
    'year': ('years', 1), 'years': ('years', 1), 'jahr': ('years', 1),
    'jahre': ('years', 1), 'jahren': ('years', 1), 'yıl': ('years', 1),
    'percent': ('percent', 1), 'per cent': ('percent', 1), 'prozent': ('percent', 1),
    '%': ('percent', 1), 'percentage points': ('percentage_points', 1),
    'percentage point': ('percentage_points', 1), 'prozentpunkte': ('percentage_points', 1),
    'prozentpunkten': ('percentage_points', 1), 'yüzde puan': ('percentage_points', 1),
    'puan': ('points', 1), 'puanlık': ('points', 1),
    'eur': ('EUR', 1), 'euro': ('EUR', 1), 'euros': ('EUR', 1),
    'usd': ('USD', 1), 'dollars': ('USD', 1), 'dollar': ('USD', 1),
    'try': ('TRY', 1), 'tl': ('TRY', 1), 'lira': ('TRY', 1),
}
UNIT_PATTERN = '|'.join(re.escape(unit) for unit in sorted(UNITS, key=len, reverse=True))
PATTERN = re.compile(
    r'(?<![\w])(?P<prefix>%|yüzde\s+|€|\$|₺)?\s*'
    r'(?P<number>[+−-]?\d+(?:[.,]\d+)*)'
    r'(?:\s*(?P<unit>' + UNIT_PATTERN + r')(?!\w))?', re.I,
)
MISSING = re.compile(r'\[MISSING[^\]]*\]', re.I)


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str
    raw: str


def decimal_value(raw, language=None):
    raw = raw.replace('−', '-')
    unsigned = raw.lstrip('+-')
    if '.' in raw and ',' in raw:
        decimal = '.' if raw.rfind('.') > raw.rfind(',') else ','
        group = ',' if decimal == '.' else '.'
        integer, fraction = raw.rsplit(decimal, 1)
        if group in integer and not re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(group) + r'\d{3})+', integer):
            raise ValueError('ambiguous quantity grouping')
        raw = integer.replace(group, '') + '.' + fraction
    elif '.' in unsigned or ',' in unsigned:
        sep = '.' if '.' in unsigned else ','
        parts = unsigned.split(sep)
        grouping = all(len(part) == 3 for part in parts[1:]) and len(parts[0]) <= 3
        if len(parts) > 2:
            if not grouping:
                raise ValueError('ambiguous quantity grouping')
            raw = raw.replace(sep, '')
        elif language is None and grouping and parts[0] != '0':
            raise ValueError('ambiguous source quantity')
        elif (language == 'en' and sep == ',') or (language in {'de', 'tr'} and sep == '.'):
            if not grouping:
                raise ValueError('invalid locale quantity grouping')
            raw = raw.replace(sep, '')
        else:
            raw = raw.replace(sep, '.')
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValueError('invalid quantity') from None


def quantities(text, language=None):
    result = []
    clean = MISSING.sub('', unicodedata.normalize('NFKC', text))
    for match in PATTERN.finditer(clean):
        number = match.group('number')
        # The hyphen in Tier-1 is a label separator, not a negative value.
        if number.startswith('-') and match.start() and clean[match.start() - 1].isalpha():
            number = number[1:]
        prefix = (match.group('prefix') or '').strip().casefold()
        unit = (match.group('unit') or '').casefold()
        if prefix in {'%', 'yüzde'}:
            # Turkish places the percentage marker before the quantity and
            # "puan" after it. Preserve the point qualifier instead of silently
            # turning "yüzde 45 puan" into a relative 45-percent change.
            if UNITS.get(unit, ('', 1))[0] in {'points', 'percentage_points'}:
                unit = 'percentage points'
            elif not unit or UNITS.get(unit, ('', 1))[0] == 'percent':
                unit = '%'
            else:
                raise ValueError('conflicting quantity units')
        elif prefix in {'€', '$', '₺'}:
            unit = {'€': 'eur', '$': 'usd', '₺': 'try'}[prefix]
        kind, multiplier = UNITS.get(unit, ('number', 1))
        result.append(Quantity(decimal_value(number, language) * multiplier, kind,
                               match.group(0).strip()))
    return result


def source_texts(value, key=''):
    if key in {'id', 'source_ref', 'page_ref', 'engagement_id', 'engagement_ids'}:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        unit = {'duration_months': ' months', 'team_size': ''}.get(key, '')
        return [str(value) + unit]
    if isinstance(value, list):
        return [text for item in value for text in source_texts(item)]
    if isinstance(value, dict):
        return [text for name, item in value.items() for text in source_texts(item, name)]
    return []


def quantity_problems(text, sources, language):
    try:
        source = {(q.value, q.unit) for item in sources for q in quantities(item)}
        draft = quantities(text, language)
    except ValueError as exc:
        return [{'type': 'unverifiable_quantity', 'why': str(exc)}]
    return [{'type': 'ungrounded_number', 'value': q.raw if q.unit == 'percent' else re.search(r'[+−-]?\d+(?:[.,]\d+)*', q.raw).group(0),
             'unit': q.unit,
             'why': 'this quantity and unit are not supported by the source evidence'}
            for q in draft if (q.value, q.unit) not in source]


def name_key(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text).casefold()
                   if char.isalnum()).replace('ı', 'i')
