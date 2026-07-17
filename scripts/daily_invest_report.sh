#!/bin/bash
# Wrapper do daily_report.py — gera relatório .md + .pdf e envia por email
# WhatsApp: resumo curto (stdout final) | Email: relatorio completo + PDF
set -e

PROJ_DIR=~/git/smartfolio
LOG="/tmp/daily_report_$(date +%Y%m%d_%H%M%S).log"

# Carrega .env (com aspas para valores com espaço)
set -a
source "$PROJ_DIR/.env" 2>/dev/null || true
set +a
cd "$PROJ_DIR"

# Gera o relatório markdown
echo "=== daily_report.py ===" >> "$LOG"
.venv/bin/python scripts/daily_report.py >> "$LOG" 2>&1 || {
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
  "${REPORT_EMAIL:-}" \
  "Relatório Diário de Investimentos — $DATE" \
  "$REPORT_MD" \
  "$REPORT_PDF" >> "$LOG" 2>&1 || echo "⚠️ Email falhou" >> "$LOG"

# Extrai resumo para WhatsApp (stdout = entregue ao WhatsApp)
# SEM patrimonio por seguranca — apenas top 5 altas e quedas por carteira
echo "📊 Relatório $DATE"
echo ""

# Top 5 altas e quedas por carteira (apenas percentuais, sem R$)
python3 -c "
import re

with open('$REPORT_MD') as f:
    txt = f.read()

lines = txt.split('\n')
current_portfolio = None
assets = []

for line in lines:
    # Detect portfolio
    if line.startswith('| **') and 'Carteira' in line:
        current_portfolio = line.replace('|','').replace('**','').strip()
        continue
    # Stop at next section
    if line.startswith('##') and current_portfolio:
        break
    # Parse asset rows: | Ticker | Price | Day | Week | Month | Year |
    if current_portfolio and line.startswith('|') and not line.startswith('|---') and not line.startswith('| Ticker'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 4:
            ticker = parts[1]
            day_pct = parts[3].replace('🔴','').replace('🟢','').replace('🟡','').strip()
            if ticker and day_pct and '%' in day_pct:
                try:
                    pct_val = float(day_pct.replace('%','').replace('+',''))
                    assets.append((current_portfolio, ticker, pct_val, day_pct))
                except:
                    pass

# Group by portfolio
from collections import defaultdict
by_portfolio = defaultdict(list)
for pf, ticker, val, pct in assets:
    by_portfolio[pf].append((ticker, val, pct))

for pf_name in sorted(by_portfolio.keys()):
    items = by_portfolio[pf_name]
    losers = sorted([i for i in items if i[1] < 0], key=lambda x: x[1])[:5]
    gainers = sorted([i for i in items if i[1] > 0], key=lambda x: x[1], reverse=True)[:5]

    if losers or gainers:
        print(f'🏷️ {pf_name}')
        if losers:
            print('  🔴 Quedas:')
            for t, v, p in losers:
                print(f'    {t}: {p}')
        if gainers:
            print('  🟢 Altas:')
            for t, v, p in gainers:
                print(f'    {t}: {p}')
        print()

# If no data at all
if not by_portfolio:
    print('Sem dados de variação disponíveis.')
    print()
" 2>/dev/null

echo ""

# Indices (com variacao diaria) + Insights
python3 -c "
import re

with open('$REPORT_MD') as f:
    txt = f.read()

# Parse indices table for day variation
print('📈 Índices:')
idx_section = False
for line in txt.split('\n'):
    if '| Ibovespa |' in line and 'Dia' in line:
        idx_section = True
        continue
    if idx_section and line.startswith('|---'):
        continue
    if idx_section and line.startswith('|') and not line.startswith('| Índice'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 4:
            name = parts[1].replace('Índice','').strip()
            day = parts[3].replace('🔴','').replace('🟢','').replace('🟡','').strip()
            if name and day and '%' in day:
                emoji = '🔴' if '-' in day else '🟢'
                print(f'  {emoji} {name}: {day}')
    if idx_section and (line.startswith('##') or 'Temáticos' in line):
        idx_section = False

# Macro
print()
print('🏦 Macro:')
for line in txt.split('\n'):
    line = line.strip()
    if '**Selic**' in line or '**Juro Real**' in line:
        val = line.split(':',1)[-1].strip().replace('**','')
        print(f'  • Selic: {val}' if 'Selic' in line else f'  • Juro Real: {val}')
    if '**Fed Funds**' in line:
        val = line.split(':',1)[-1].strip().replace('**','')
        print(f'  • Fed Funds: {val}')

# Sentimento
print()
for line in txt.split('\n'):
    if 'Sentimento' in line:
        val = line.split('**',1)[-1].replace('**','').strip().lstrip(':').strip()
        print(f'🧭 {val}')
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