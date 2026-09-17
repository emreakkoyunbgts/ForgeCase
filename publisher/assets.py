"""Packaged rendering assets and visible EN/DE/TR labels."""
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ASSETS = Path(__file__).resolve().parent / 'assets'
TEMPLATE = ASSETS / 'case_study_template.docx'
FONT_FILES = {
    'DejaVuSans': 'DejaVuSans.ttf', 'DejaVuSans-Bold': 'DejaVuSans-Bold.ttf',
    'DejaVuSans-Oblique': 'DejaVuSans-Oblique.ttf',
    'DejaVuSans-BoldOblique': 'DejaVuSans-BoldOblique.ttf',
}
LABELS = {
    'en': {'challenge': 'The Challenge', 'approach': 'Our Approach', 'technology': 'Technology',
           'outcomes': 'Outcomes', 'provenance': 'Provenance', 'confidential': 'Confidential',
           'sources': 'Source records', 'references': 'Source references', 'hash': 'Content hash',
           'freshness': 'Freshness', 'reason': 'Reason', 'completed': 'Completed at', 'as_of': 'As of date',
           'FRESH': 'Fresh', 'STALE': 'Stale', 'UNKNOWN': 'Unknown',
           'DATE_MISSING': 'Completion date missing', 'DATE_INVALID': 'Invalid completion date',
           'OLDER_THAN_SIX_MONTHS': 'Older than six months', 'WITHIN_SIX_MONTHS': 'Within six months'},
    'de': {'challenge': 'Die Herausforderung', 'approach': 'Unser Ansatz', 'technology': 'Technologie',
           'outcomes': 'Ergebnisse', 'provenance': 'Herkunftsnachweis', 'confidential': 'Vertraulich',
           'sources': 'Quelldatensätze', 'references': 'Quellenverweise', 'hash': 'Inhalts-Hash',
           'freshness': 'Aktualität', 'reason': 'Grund', 'completed': 'Abgeschlossen am', 'as_of': 'Stand',
           'FRESH': 'Aktuell', 'STALE': 'Veraltet', 'UNKNOWN': 'Unbekannt',
           'DATE_MISSING': 'Abschlussdatum fehlt', 'DATE_INVALID': 'Ungültiges Abschlussdatum',
           'OLDER_THAN_SIX_MONTHS': 'Älter als sechs Monate', 'WITHIN_SIX_MONTHS': 'Innerhalb von sechs Monaten'},
    'tr': {'challenge': 'Karşılaşılan Zorluk', 'approach': 'Yaklaşımımız', 'technology': 'Teknoloji',
           'outcomes': 'Sonuçlar', 'provenance': 'Kaynak Bilgisi', 'confidential': 'Gizli',
           'sources': 'Kaynak kayıtlar', 'references': 'Kaynak referansları', 'hash': 'İçerik özeti',
           'freshness': 'Güncellik', 'reason': 'Neden', 'completed': 'Tamamlanma tarihi', 'as_of': 'Değerlendirme tarihi',
           'FRESH': 'Güncel', 'STALE': 'Eski', 'UNKNOWN': 'Bilinmiyor',
           'DATE_MISSING': 'Tamamlanma tarihi eksik', 'DATE_INVALID': 'Tamamlanma tarihi geçersiz',
           'OLDER_THAN_SIX_MONTHS': 'Altı aydan eski', 'WITHIN_SIX_MONTHS': 'Son altı ay içinde'},
}


def ensure_assets():
    for path in [TEMPLATE, ASSETS / 'fonts' / 'LICENSE_DEJAVU',
                 *(ASSETS / 'fonts' / name for name in FONT_FILES.values())]:
        if not path.is_file():
            raise RuntimeError(f'Publisher asset is missing: {path.name}')
    for name, filename in FONT_FILES.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(ASSETS / 'fonts' / filename)))
    pdfmetrics.registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold',
                                 italic='DejaVuSans-Oblique', boldItalic='DejaVuSans-BoldOblique')
