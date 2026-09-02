#!/usr/bin/env bash
# Idempotent bootstrap for the 光模块供应链图谱 (workflow-rehearsal) pipeline.
set -euo pipefail

# System packages:
#   poppler-utils     -> pdftotext, used by scan.py to extract text from corpus PDFs
#   fonts-wqy-*        -> TrueType CJK fonts for the reportlab PDF export
#                         (Noto CJK ships CFF outlines that reportlab cannot embed)
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  poppler-utils \
  fonts-wqy-zenhei \
  fonts-wqy-microhei

# Python packages:
#   pyyaml    -> render.py (tree.yaml parsing)
#   reportlab -> make_participation_pdf.py (PDF export)
#   requests  -> corpus/_fetch.py (annual-report downloader)
pip3 install --break-system-packages --upgrade \
  pyyaml \
  reportlab \
  requests

echo "install.sh: done"
