#!/usr/bin/env bash
#
# INTEGRATION DAY — the whole pipeline, end to end.
#
# This already works, TODAY, using stubs. As each of you replaces your stub
# with real code, this same script gets better. On 3 August we run it for real.
#
#   bash scripts/run_pipeline.sh

set -e   # stop on the first error

DOC="${1:-caseforge-testdata/documents/eng-01_closeout.pdf}"
ID="eng-01"

mkdir -p records drafts out

echo "════════════════════════════════════════════════════════════"
echo "  CaseForge pipeline:  $DOC"
echo "════════════════════════════════════════════════════════════"

echo
echo "▸ 1. READER (Çağrı)      document → engagement record"
python -m reader.reader "$DOC" > "records/$ID.json"

echo "▸ 2. VAULT (Kaan)        store the record"
python -m vault.vault store "records/$ID.json"

echo "▸ 3. GENERATOR (Taha)    record → grounded case study"
python -m generator.generator "records/$ID.json" > "drafts/$ID.json"

echo "▸ 4. VERIFIER (Ömer)     THE GATE — catch anything invented"
if ! python -m verifier.verifier "drafts/$ID.json" "records/$ID.json" > "drafts/$ID.report.json"; then
    echo
    echo "  ✗ BLOCKED. The case study contains a fact that is not in the source."
    echo "    Nothing gets published. This is the system working correctly."
    exit 1
fi

echo "▸ 5. PUBLISHER (Ahmet)   case study → branded document"
python -m publisher.publisher "drafts/$ID.json" --out "out/$ID.docx"

echo
echo "── running alongside, on the same records ──"
echo "▸ 6. LIBRARIAN (Arda)    RFP → matching engagements"
python -m librarian.librarian caseforge-testdata/rfp/rfp_01_realtime_payments.txt > out/matches.json

echo "▸ 7. ANALYST (Elif)      coverage & gaps"
python -m analyst.analyst --coverage > out/coverage.json

echo
echo "════════════════════════════════════════════════════════════"
echo "  ✓ Pipeline complete. Look in out/"
echo "  ▸ 8. CONSOLE (Serhat):  streamlit run console/console.py"
echo "════════════════════════════════════════════════════════════"
