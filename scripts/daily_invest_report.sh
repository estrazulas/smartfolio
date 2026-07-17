#!/bin/bash
# Wrapper do daily_report.py — gera relatório .md + .pdf e envia por email
# WhatsApp: resumo curto (stdout final) | Email: relatorio completo + PDF
set -e

PROJ_DIR=~/git/smartfolio
LOG="/tmp/daily_report_$(date +%Y%m%d_%H%M%S).log"

# Carrega .env
export $(grep -v '^#' "$PROJ_DIR/.env" | xargs) 2>/dev/null || true
cd "$PROJ_DIR"

# Gera o relatório markdown
echo "=== daily_report.py ===" >> "$LOG"
.venv/bin/python daily_report.py >> "$LOG" 2>&1 || {
    echo "❌ Erro ao gerar relatório. Veja $LOG"
    cat "$LOG"
    exit 1
}

# Pega o arquivo mais recente
REPORT_MD=$(ls -t reports/daily_*.md | head -1)
DATE=$(date +%d/%m/%Y)
REPORT_PDF="${REPORT_MD%.md}.pdf"

# Gera PDF com links preservados
echo "=== PDF ===" >> "$LOG"
.venv/bin/python ~/.hermes/skills/md-to-pdf/scripts/md-to-pdf.py "$REPORT_MD" "$REPORT_PDF" >> "$LOG" 2>&1 || echo "⚠️ PDF falhou" >> "$LOG"

# Envia por email com .md + .pdf anexos
echo "=== Email ===" >> "$LOG"
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/gmail_send_attach.py \
  "${REPORT_EMAIL:-daniel.allrightt@gmail.com}" \
  "Relatório Diário de Investimentos — $DATE" \
  "$REPORT_MD" \
  "$REPORT_PDF" >> "$LOG" 2>&1 || echo "⚠️ Email falhou" >> "$LOG"

# Extrai resumo para WhatsApp (stdout = entregue ao WhatsApp)
echo "📊 Relatório $DATE"
echo ""

# Patrimonio
python3 -c "
import re
with open('$REPORT_MD') as f:
    txt = f.read()
for line in txt.split('\n'):
    if '**Dani Carteira**' in line or '**Ana Carteira**' in line or 'Total geral' in line:
        print(line.strip())
" 2>/dev/null

echo ""

# Oscilacoes
python3 -c "
import re
with open('$REPORT_MD') as f:
    txt = f.read()
in_osc = False
for line in txt.split('\n'):
    if 'Oscilações Significativas' in line:
        in_osc = True
        continue
    if in_osc and line.startswith('##'):
        break
    if in_osc and line.strip():
        print(line.strip())
" 2>/dev/null

echo ""

# Indices + Insights
python3 -c "
import re
with open('$REPORT_MD') as f:
    txt = f.read()
for line in txt.split('\n'):
    if 'Ibovespa' in line or 'IFIX' in line or 'Bitcoin USD' in line:
        print(line.strip())
in_ins = False
for line in txt.split('\n'):
    if 'Insights & Recomendações' in line:
        in_ins = True
        continue
    if in_ins and line.startswith('---'):
        break
    if in_ins and line.strip():
        print(line.strip())
" 2>/dev/null

echo ""
echo "📎 Relatório completo e PDF no email"
echo ""
echo "💬 Consulte a qualquer momento:"
echo "  • \"analise WEGE3\" — fundamentos de uma ação"
echo "  • \"gere relatório de balanceamento\" — compre/venda"
echo "  • \"tem notícia dos meus FIIs?\" — monitor de eventos"
echo "  • \"como está minha carteira?\" — resumo rápido"

# Limpa log antigo
rm -f "$LOG"