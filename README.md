# Smartfolio

Monitoramento automatizado de carteira de investimentos com Hermes Agent.
Relatório diário com preços, indicadores macro, notícias e insights de balanceamento.

## Por que usar este projeto

- **Com um comando, você tem 6 análises.** Diga `/carteira` e receba: relatório do dia, detecção de oportunidades (ativos em queda), rebalanceamento com valores em R$, notícias de cada ativo, valuation fundamentalista (P/L, ROE, DY) e sincronização de preços na planilha.
- **Zero trabalho manual.** A planilha do Google Sheets é atualizada automaticamente. O relatório chega todo dia às 9h no WhatsApp e por email — você nem precisa pedir.
- **Custo zero.** yfinance + CoinGecko + Banco Central. Nenhuma API paga.
- **Você decide o que rodar.** A skill orquestradora pergunta uma por uma. Só executa a análise que fizer sentido naquele dia.
- **Skills modulares e reutilizáveis.** Cada análise é uma skill independente. Use separadamente ou todas de uma vez.

## Quando NÃO usar

- **Você não quer um agente de IA.** Se prefere abrir o Google Sheets manualmente, conferir cotações no StatusInvest e ler notícia por notícia no InfoMoney, este projeto adiciona complexidade desnecessária.
- **Sua carteira é 100% passiva (ETFs de índice global + renda fixa).** As análises de rebalanceamento, dividendos e valuation são mais úteis para quem tem ações e FIIs individuais.
- **Você investe menos de R$ 50 mil.** O ganho de automação pode não compensar o tempo de setup (conectar Composio, modelar planilha, etc.).
- **Você não usa Hermes Agent.** O projeto depende do ecossistema Hermes (skills, cron jobs, Composio). Sem ele, os scripts rodam standalone mas você perde a orquestração inteligente.
- **Você quer recomendação de compra ou venda.** Este projeto é para **acompanhar sua carteira com insights de mercado**, não para dizer "compre X" ou "venda Y". As análises mostram dados (P/L, peso alvo vs atual, notícias), mas a decisão é sempre sua.
- **Você quer trade ou day trade.** O foco é investimento de longo prazo: relatório diário, fundamentos, dividendos, rebalanceamento periódico. Não há gráfico de vela, RSI, estocástico ou ordem de compra/venda automática.

## Funcionalidades

- 📊 **Relatório diário** com 8 seções: oscilações, patrimônio, cenário macro (Selic, Fed, tabela de índices com ATH), tabela de ativos (variação dia/semana/mês/ano), mini-tabela temática (China, Emergentes, Ouro), destaques do mercado, notícias macro e insights
- 🔄 **Sincronização de preços** via yfinance + CoinGecko direto na planilha do Google Sheets
- 🧠 **Skills de análise**: orquestrador `/carteira`, fundamentalista (P/L, ROE, dividend yield), análise por ticker (preço-alvo, investimentos, riscos), rebalanceamento de carteira, monitor de notícias e dividendos
- 🤖 **Cron job automático**: 9h BRT com entrega via WhatsApp + email

## Créditos

As skills de análise são adaptadas de:

- [anthropics/financial-services](https://github.com/anthropics/financial-services) — templates de análise financeira
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) — scripts de valuation e ratio analysis

## Setup

### 1. Clone

```bash
git clone <seu-repo> investimentos_util
cd investimentos_util
```

### 2. Configurar

```bash
cp .env.example .env
cp sheets.example.json sheets.json
```

Edite `.env` com seus dados:

```bash
INVEST_SPREADSHEET_ID=<id-da-sua-planilha>
SHEET_WHITELIST=Minha Carteira,Outra Carteira
ALPHA_VANTAGE_KEY=  # opcional, melhora dados de ações BR
```

### 3. Ambiente Python

```bash
python3 -m venv .venv
.venv/bin/pip install yfinance python-dotenv markdown
```

### 4. Conectar Google Sheets (Composio)

```bash
composio link googlesheets --no-browser --no-wait
composio link googledrive --no-browser --no-wait
# Abra a URL de cada um no navegador e autorize
```

### 5. Preencher sheets.json

Rode para sua planilha e cole a saída no `sheets.json`:

```bash
composio execute GOOGLESHEETS_GET_SPREADSHEET_INFO -d '{"spreadsheet_id": "<seu-id>"}'
```

### 6. Primeiro snapshot

```bash
.venv/bin/python scripts/sync.py snapshot
```

## Uso

### Comandos

```bash
# Atualizar preços na planilha
.venv/bin/python scripts/sync.py update

# Verificar se a planilha mudou desde o último snapshot
.venv/bin/python scripts/sync.py check

# Gerar relatório diário completo
.venv/bin/python scripts/daily_report.py --print
```

### Skills do Hermes

As skills ficam em `skills/` e são linkadas automaticamente em `~/.hermes/skills/`:

```
"analise ABCD3"              → Fundamental Analyst
"gere relatório de balanceamento" → Portfolio Rebalancer
"tem notícia dos meus FIIs?" → Earnings Reviewer
```

### Cron job diário

O script `scripts/daily_invest_report.sh` gera o relatório `.md` + `.pdf` e envia por email (Gmail API).
Configure um cron job no Hermes:

```
schedule: 0 12 * * *     # 9h BRT
script: daily_invest_report.sh
no_agent: true
deliver: whatsapp          # resumo curto
email: via gmail_send_attach.py no próprio script
```

---

## Modelo de Planilha

Sua planilha deve seguir esta estrutura de colunas (a partir da linha 5):

| A (Ticker) | B (Peso Alvo) | C (Preço Atual) | D (Qtd) | E (Peso) | F (Valor Alvo) | G (Alocado) | H (Diferença) |
|------------|---------------|-----------------|---------|----------|----------------|-------------|---------------|
| ABCD3      | 15%           |                 | 100     | 15       |                |             |               |
| FIII11     | 20%           |                 | 50      | 20       |                |             |               |
| MCHI       | 10%           |                 | 30      | 10       |                |             |               |

**Regras:**
- **Linhas 1-3**: totais da carteira (Total BR, Total US, Total Geral)
- **Linha 4**: cabeçalho da seção ("Ações BR", "FIIs", "Equity", etc.)
- **Linhas 5+**: ativos com ticker na coluna A
- **Coluna C**: use `=PROCV(A5;AtivosPrecos!A:C;2;FALSO)` para puxar o preço automaticamente
- **Tickers BR**: ações (ex: ABCD3, XYZB4), FIIs (ex: FIII11, FOOO11)
- **Tickers US**: prefixo `NASDAQ:` ou `NYSEARCA:` (ex: `NASDAQ:MCHI`, `NYSEARCA:SPHQ`)
- **BTC**: `CURRENCY:BTCBRL` (BRL) ou `BTCUSD` (USD)
- **Linhas de categoria**: "Ações BR", "RF", "Caixa", "FIIs", "Equity", "Proteções" — são ignoradas pelo scanner

### Ticker mapping

No `sheets.json`, mapeie como cada ticker da planilha é buscado:

```json
{
  "ticker_map": {
    "ABCD3": "ABCD3.SA",
    "FIII11": "FIII11.SA",
    "NASDAQ:MCHI": "MCHI",
    "NYSEARCA:SPHQ": "SPHQ",
    "CURRENCY:BTCBRL": "COINGECKO:BTC/BRL",
    "BTCUSD": "COINGECKO:BTC/USD"
  }
}
```

### AtivosPrecos (aba gerada automaticamente)

O `sync.py update` escreve nesta aba:

| Ticker | Preço | Moeda |
|--------|-------|-------|
| ABCD3 | 43.49 | BRL |
| FIII11 | 102.70 | BRL |
| NASDAQ:MCHI | 54.14 | USD |
| BTCUSD | 63714 | USD |

Use `=PROCV(A5;AtivosPrecos!A:C;2;FALSO)` na sua aba de carteira para puxar o preço.

Crie uma planilha no Google Sheets com 2 abas: `Minha Carteira` e `Outra Carteira` (ou os nomes que preferir).

**Aba "Minha Carteira":**

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| | | | | Total Geral | | | |
| | | | | Total BR | R$ 0,00 | | |
| | | | | Total US | R$ 0,00 | | |
| Ações BR | | | QTD | Peso | Alvo | Alocado | Diff |
| ABCD3 | 50% | | 100 | 50 | R$ 0,00 | R$ 0,00 | |
| FIIs | 30% | | | 30 | R$ 0,00 | R$ 0,00 | |
| FIII11 | 100% | | 50 | 30 | R$ 0,00 | R$ 0,00 | |
| Equity | 20% | | | 20 | R$ 0,00 | R$ 0,00 | |
| NASDAQ:MCHI | 100% | | 30 | 20 | R$ 0,00 | R$ 0,00 | |

## Estrutura do Projeto

```
├── .env.example          → template de variáveis
├── sheets.example.json   → template de mapeamento
├── CLAUDE.md             → instruções para agentes
├── sync.py               → snapshot | check | update (preços)
├── daily_report.py       → relatório diário completo
├── skills/               → skills do Hermes
│   ├── fundamental-analyst/
│   ├── portfolio-rebalancer/
│   └── earnings-reviewer/
├── scripts/
│   └── daily_invest_report.sh  → wrapper do cron job
└── reports/              → saída dos relatórios (gitignored)
```

## Fontes de Dados

| Fonte | Uso | Custo |
|-------|-----|-------|
| yfinance | Preços, histórico, fundamentos, índices, Fed Funds (^IRX) | Grátis |
| yfinance (proxy) | IFIX via XFIX11.SA (ETF que replica o índice) | Grátis |
| CoinGecko | Bitcoin BRL/USD | Grátis |
| Banco Central | Selic, IPCA | Grátis |
| InfoMoney RSS | Manchetes do mercado | Grátis |
| Suno RSS | Notícias de FIIs | Grátis |

## Limitações

- yfinance pode ter atraso de ~15min em cotações
- Dados fundamentalistas de ações BR no yfinance são limitados (P/L, ROE podem vir vazios)
- `GOOGLESHEETS_BATCH_UPDATE` escreve a partir de A1 — usar aba separada (AtivosPrecos)
