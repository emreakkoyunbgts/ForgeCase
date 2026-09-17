"""Read published bytes the way a recipient would; magic bytes alone prove nothing."""
from io import BytesIO
import re
from xml.etree import ElementTree
from zipfile import ZipFile

import pdfplumber

MEDIA_TYPES = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}


def squash(text):
    return ' '.join(text.split())


def document_text(content, fmt):
    """Return (visible text, page count or None) of a downloaded DOCX/PDF."""
    if fmt == 'docx':
        # Paragraph-only APIs miss tables, nested tables and header/footer
        # stories. Read every text-bearing Word part, preserving adjacent runs
        # so splitting a private name across runs cannot hide a disclosure.
        namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        parts = []
        with ZipFile(BytesIO(content)) as archive:
            assert 'word/document.xml' in archive.namelist(), 'DOCX has no main document part'
            names = [name for name in archive.namelist() if re.fullmatch(
                r'word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml', name)]
            for name in sorted(names):
                root = ElementTree.fromstring(archive.read(name))
                for paragraph in root.iter(namespace + 'p'):
                    words = []
                    for node in paragraph.iter():
                        if node.tag == namespace + 't':
                            words.append(node.text or '')
                        elif node.tag in {namespace + 'tab', namespace + 'br', namespace + 'cr'}:
                            words.append(' ')
                    parts.append(''.join(words))
        return '\n'.join(parts), None
    if fmt != 'pdf':
        raise ValueError('Unsupported document format: ' + str(fmt))
    with pdfplumber.open(BytesIO(content)) as pdf:
        return '\n'.join(page.extract_text() or '' for page in pdf.pages), len(pdf.pages)


def assert_document(content, fmt, layout, expected, forbidden=()):
    """Assert expected Unicode prose and absence of private text in all document stories."""
    assert content.startswith(b'PK' if fmt == 'docx' else b'%PDF')
    text, pages = document_text(content, fmt)
    if fmt == 'pdf' and layout != 'full-case-study':
        assert pages == 1
    normalized = squash(text)
    for prose in expected.values():
        assert squash(prose) in normalized, (prose, text)
    for private_text in forbidden:
        assert squash(private_text) not in normalized, 'Document disclosed private text: ' + private_text
    assert '{{' not in text and '}}' not in text, 'Unresolved document placeholder'
    assert '\ufffd' not in text, 'Document contains a Unicode replacement character'
    return text
