#!/usr/bin/env python3
"""daily_report.py — Relatorio diario de investimentos.

Gera um Markdown com:
- Cenario Macro (Selic, IPCA, CDI, Fed Funds, Tesouro)
- Variacao de preco (dia, semana, mes) por ativo
- Ativos com >3% de oscilacao
- Patrimonio total por carteira
- Noticias dos ativos (RSS)
- Noticias macro (juros, inflacao, politica)
- Insights e recomendacoes (balanceamento, alertas)

Uso:
    daily_report.py           Gera relatorio e salva em reports/
    daily_report.py --print   Mostra no terminal tambem
"""

import json
import os
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent  # scripts/ → raiz do repo
ENV_FILE = PROJECT_DIR / ".env"
SHEETS_FILE = PROJECT_DIR / "sheets.json"
SNAPSHOT_FILE = PROJECT_DIR / "snapshot.json"
REPORTS_DIR = PROJECT_DIR / "reports"

load_dotenv(ENV_FILE)
SPREADSHEET_ID = os.environ["INVEST_SPREADSHEET_ID"]


def load_snapshot() -> dict:
    with open(SNAPSHOT_FILE) as f:
        return json.load(f)


def load_ticker_map() -> dict:
    with open(SHEETS_FILE) as f:
        return json.load(f)["ticker_map"]


def load_ticker_meta() -> dict:
    """Carrega metadados por ticker: currency, geo."""
    with open(SHEETS_FILE) as f:
        return json.load(f).get("ticker_meta", {})


def get_currency(ticker: str, meta: dict) -> str:
    """Retorna BRL ou USD com base no ticker_meta."""
    return meta.get(ticker, {}).get("currency", "BRL")


def get_geo(ticker: str, meta: dict) -> str:
    """Retorna geografia com base no ticker_meta."""
    return meta.get(ticker, {}).get("geo", "Outros")


def composio(action: str, payload: dict) -> dict:
    composio_bin = os.path.expanduser("~/.composio/composio")
    cmd = [composio_bin, "execute", action, "-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    if not data.get("successful"):
        raise RuntimeError(f"composio: {data.get('error')}")
    return data


def resolve_ticker(sheet_ticker: str, ticker_map: dict) -> tuple[str, str]:
    """(source, symbol). source = yfinance | coingecko."""
    mapped = ticker_map.get(sheet_ticker, sheet_ticker)
    if mapped.startswith("COINGECKO:"):
        return "coingecko", mapped.split(":", 1)[1]
    return "yfinance", mapped


def fetch_price_history(symbol: str, source: str) -> dict:
    """Retorna {current, day_ago, week_ago, month_ago, year_ago}."""
    if source == "coingecko":
        return fetch_coingecko_history(symbol)

    try:
        t = yf.Ticker(symbol)
        # Preco atual
        current = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPreviousClose")
        if not current:
            return {}

        # Historico (ultimos 400 dias cobre 1 ano)
        hist = t.history(period="400d")
        if hist.empty:
            return {"current": current}

        def closest_price(days_back: int):
            target = hist.index[-1] - pd.Timedelta(days=days_back)
            idx = hist.index.get_indexer([target], method="nearest")[0]
            return hist["Close"].iloc[idx]

        import pandas as pd

        result = {
            "current": current,
            "day_ago": closest_price(1) if len(hist) > 1 else None,
            "week_ago": closest_price(7) if len(hist) > 5 else None,
            "month_ago": closest_price(30) if len(hist) > 21 else None,
            "year_ago": closest_price(365) if len(hist) > 252 else None,
        }

        # Sanity check: variacao anual >500% sugere split mal ajustado
        ya = result.get("year_ago")
        if ya and ya > 0 and current > 0:
            year_pct = abs((current / ya - 1) * 100)
            if year_pct > 500:
                from datetime import date, timedelta
                target = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
                end = (date.today() - timedelta(days=358)).strftime("%Y-%m-%d")
                raw = t.history(start=target, end=end, auto_adjust=False)
                if not raw.empty and len(raw) > 0:
                    raw_price = float(raw["Close"].iloc[0])
                    if raw_price > 0:
                        raw_pct = abs((current / raw_price - 1) * 100)
                        if raw_pct < 500:
                            result["year_ago"] = raw_price  # usa o valor nao-ajustado

        return result
    except Exception as e:
        print(f"  ⚠️ {symbol}: {e}")
        return {}


def fetch_coingecko_history(pair: str) -> dict:
    """BTC via CoinGecko (so preco atual + 24h)."""
    coin_map = {"BTC/BRL": "bitcoin", "BTC/USD": "bitcoin"}
    currency_map = {"BTC/BRL": "brl", "BTC/USD": "usd"}
    coin = coin_map.get(pair)
    currency = currency_map.get(pair, "usd")
    if not coin:
        return {}
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&community_data=false&developer_data=false"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        current = resp["market_data"]["current_price"].get(currency)
        change_24h = resp["market_data"]["price_change_percentage_24h_in_currency"].get(currency)
        change_7d = resp["market_data"]["price_change_percentage_7d_in_currency"].get(currency)
        change_30d = resp["market_data"]["price_change_percentage_30d_in_currency"].get(currency)

        result = {"current": current}
        if change_24h is not None:
            result["day_ago"] = current / (1 + change_24h / 100) if change_24h != -100 else None
        if change_7d is not None:
            result["week_ago"] = current / (1 + change_7d / 100) if change_7d != -100 else None
        if change_30d is not None:
            result["month_ago"] = current / (1 + change_30d / 100) if change_30d != -100 else None
        return result
    except Exception as e:
        print(f"  ⚠️ CoinGecko {pair}: {e}")
        return {}


def fetch_asset_news(tickers: list[str]) -> list[dict]:
    """Busca manchetes do mercado nos RSS (sem filtrar por ticker)."""
    news_items = []
    feeds = [
        ("InfoMoney", "https://www.infomoney.com.br/feed/"),
        ("Suno", "https://www.suno.com.br/noticias/feed/"),
    ]
    for name, feed_url in feeds:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            tree = ET.parse(resp)
            items = tree.findall(".//item")
            for item in items[:5]:  # top 5 por feed
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
                if title and len(title) > 15:
                    news_items.append({
                        "ticker": "MERCADO",
                        "title": title,
                        "link": link,
                        "source": name,
                    })
        except Exception as e:
            print(f"  ⚠️ RSS {name}: {e}")
    return news_items


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "  -   "
    # Sanity check: variacoes >500% sao erro de dados (split, evento)
    if abs(value) > 500:
        return "  ⚠️  "
    color = "🔴" if value < -3 else ("🟢" if value > 3 else "")
    return f"{color}{value:+.1f}%"


def pie_chart_url(labels: list[str], values: list[float], title: str = "",
                  width: int = 380, height: int = 260) -> str:
    """Gera URL de grafico de pizza via QuickChart.io (tamanho reduzido)."""
    import urllib.parse
    total = sum(values)
    if total <= 0:
        return ""
    pcts = [f"{v/total*100:.0f}%" for v in values]
    colors = ["#3366CC", "#DC3912", "#FF9900", "#109618", "#990099", "#0099C6", "#DD4477"]
    chart = {
        "type": "pie",
        "data": {
            "labels": [f"{l} ({p})" for l, p in zip(labels, pcts)],
            "datasets": [{"data": values, "backgroundColor": colors[:len(values)]}],
        },
        "options": {
            "title": {"display": bool(title), "text": title},
            "plugins": {"datalabels": {"display": False}},
        },
    }
    base = f"https://quickchart.io/chart?c={urllib.parse.quote(json.dumps(chart))}"
    return f"{base}&w={width}&h={height}&devicePixelRatio=1"


def chart_row(charts: list[tuple[str, str, str]]) -> str:
    """Gera HTML table row com 2 charts lado a lado.
    Cada elemento: (alt_text, url, fallback_alt).
    Se sobrar 1, ocupa a linha inteira com colspan=2."""
    if len(charts) == 1:
        alt, url, fallback = charts[0]
        return (f'<table><tr><td align="center">'
                f'<img src="{url}" alt="{fallback}" width="380"/><br/>'
                f'<b>{alt}</b>'
                f'</td></tr></table>\n\n')
    rows = ['<table><tr>']
    for alt, url, fallback in charts:
        rows.append(
            f'<td align="center">'
            f'<img src="{url}" alt="{fallback}" width="380"/><br/>'
            f'<b>{alt}</b>'
            f'</td>'
        )
    rows.append('</tr></table>\n\n')
    return ''.join(rows)


def fmt_brl(value: float) -> str:
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- Macro ---

def fetch_selic() -> dict:
    """Busca Selic e IPCA via API publica do Banco Central."""
    try:
        # Selic meta (% a.a.)
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        selic = float(resp[0]["valor"]) if resp else None

        # IPCA acumulado 12 meses
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
        resp = json.loads(urllib.request.urlopen(url, timeout=10).read())
        ipca = float(resp[0]["valor"]) if resp else None

        return {"selic": selic, "ipca_12m": ipca}
    except Exception as e:
        print(f"  ⚠️ BCB: {e}")
        return {}


def fetch_fed_funds() -> dict:
    """Busca Fed Funds Rate via yfinance (^IRX: 13-week T-bill, proxy do Fed Funds)."""
    try:
        t = yf.Ticker("^IRX")
        rate = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPreviousClose")
        if rate:
            return {"fed_funds": rate}
    except Exception as e:
        print(f"  ⚠️ Fed: {e}")
    return {}


def fetch_treasury() -> list[dict]:
    """Busca taxas do Tesouro Direto via dados abertos do Tesouro Transparente (CKAN)."""
    target_bonds = {
        "Prefixado 2032": ("Tesouro Prefixado", "01/01/2032"),
        "Prefixado 2037": ("Tesouro Prefixado com Juros Semestrais", "01/01/2037"),
        "IPCA+ 2040": ("Tesouro IPCA+", "15/08/2040"),
        "IPCA+ 2050": ("Tesouro IPCA+", "15/08/2050"),
        "Selic 2031": ("Tesouro Selic", "01/03/2031"),
    }
    found = {}

    try:
        url = "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip",
        })
        resp = urllib.request.urlopen(req, timeout=60)
        reader = resp.read().decode("latin-1", errors="ignore").splitlines()

        for line in reader:
            if not line or line.startswith("Tipo Titulo"):
                continue
            parts = line.split(";")
            if len(parts) < 6:
                continue
            tipo, venc, data_base, taxa_compra, taxa_venda = parts[0], parts[1], parts[2], parts[3], parts[4]

            for name, (target_tipo, target_venc) in target_bonds.items():
                if tipo == target_tipo and venc == target_venc:
                    if name not in found or data_base > found[name]["data_base"]:
                        found[name] = {
                            "data_base": data_base,
                            "taxa_compra": taxa_compra,
                            "taxa_venda": taxa_venda,
                        }

            if len(found) == len(target_bonds):
                break

        # Formata resultado
        result = []
        labels = {
            "Prefixado 2032": "Tesouro Prefixado 2032",
            "Prefixado 2037": "Tesouro Prefixado 2037 (Juros Sem.)",
            "IPCA+ 2040": "Tesouro IPCA+ 2040",
            "IPCA+ 2050": "Tesouro IPCA+ 2050",
            "Selic 2031": "Tesouro Selic 2031",
        }
        for name in target_bonds:
            if name in found:
                f = found[name]
                rate = f"{f['taxa_venda']}%" if name.startswith("Prefixado") else (
                    f"SELIC + {f['taxa_venda']}%" if name.startswith("Selic") else
                    f"IPCA + {f['taxa_venda']}%"
                )
                result.append({
                    "name": labels[name],
                    "rate": rate,
                    "est_rate": f"{f['taxa_venda']}%",
                    "maturity": target_bonds[name][1],
                })

        return result if result else _treasury_fallback()

    except Exception as e:
        print(f"  ⚠️ Tesouro (CKAN): {e}")
        return _treasury_fallback()


def _treasury_fallback() -> list[dict]:
    """Fallback estatico quando CKAN falha."""
    return [
        {"name": "Tesouro Prefixado 2032", "rate": "14,53%", "est_rate": "14,53%", "maturity": "01/01/2032"},
        {"name": "Tesouro Prefixado 2037 (Juros Sem.)", "rate": "14,61%", "est_rate": "14,61%", "maturity": "01/01/2037"},
        {"name": "Tesouro IPCA+ 2040", "rate": "IPCA + 7,69%", "est_rate": "7,69%", "maturity": "15/08/2040"},
        {"name": "Tesouro IPCA+ 2050", "rate": "IPCA + 7,41%", "est_rate": "7,41%", "maturity": "15/08/2050"},
        {"name": "Tesouro Selic 2031", "rate": "SELIC + 0,08%", "est_rate": "0,08%", "maturity": "01/03/2031"},
    ]


def fetch_indices() -> dict:
    """Busca Ibovespa, IFIX, BTC/USD, USD/BRL e EUR/BRL com variacao dia/semana/mes/ano."""
    import math
    result = {}
    indices = {
        "IBOV": "^BVSP", "IFIX": "IFIX.SA", "BTC": "BTC-USD",
        "USD": "USDBRL=X", "EUR": "EURBRL=X",
    }
    # XFIX11.SA e um ETF que replica o IFIX — usado como proxy para historico
    ifix_proxy_ticker = "XFIX11.SA"

    for name, ticker in indices.items():
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price = info.get("lastPrice")

            def valid(v):
                return v is not None and not (isinstance(v, float) and math.isnan(v))

            if not price or not valid(price):
                continue

            entry = {"price": price}
            # Para IFIX, usa XFIX11.SA como proxy (ETF que replica o indice)
            hist_ticker = ifix_proxy_ticker if name == "IFIX" else ticker
            hist = yf.Ticker(hist_ticker).history(period="400d")
            if hist.empty or len(hist) < 2:
                result[name] = entry  # sem historico, so preco
                continue

            current_close = float(hist["Close"].iloc[-1])
            for label, days in [("day", 1), ("week", 7), ("month", 21), ("year", 252)]:
                idx = max(0, len(hist) - 1 - days)
                prev = float(hist["Close"].iloc[idx])
                if prev > 0:
                    entry[f"{label}_pct"] = (current_close / prev - 1) * 100
                else:
                    entry[f"{label}_pct"] = None

            # ATH (all-time high) via history
            ath = float(hist["Close"].max())
            if ath > 0:
                if name == "IFIX":
                    # Converte ATH do proxy (XFIX11) para escala do IFIX
                    ifix_ratio = price / current_close if current_close > 0 else 1
                    ath = ath * ifix_ratio
                entry["ath"] = ath
                entry["ath_pct"] = (price / ath - 1) * 100

            result[name] = entry
        except Exception as e:
            print(f"  ⚠️ Indice {name}: {e}")
    return result


MACRO_RSS = [
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
    ("Investing.com", "https://br.investing.com/rss/news.rss"),
]

MACRO_KEYWORDS = [
    "SELIC", "JUROS", "COPOM", "IPCA", "INFLAÇÃO", "INFLAcaO",
    "TESOURO DIRETO", "TESOURO", "TÍTULOS PÚBLICOS", "TITULOS",
    "FED", "FOMC", "BANCO CENTRAL", "BACEN",
    "RENDA FIXA", "CDI", "PIB", "CÂMBIO", "CAMBIAL", "DÓLAR",
    "FISCAL", "DÍVIDA", "TAXA", "TREASURY", "BOND",
    "TARIFA", "TARIFAÇO", "EUA", "IBOVESPA", "BOLSA",
]


def fetch_macro_news() -> list[dict]:
    """Busca noticias macro nos RSS e filtra por keywords."""
    macro_items = []
    for name, feed_url in MACRO_RSS:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            tree = ET.parse(resp)
            items = tree.findall(".//item")
            for item in items[:10]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
                link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
                if not title:
                    continue
                title_upper = title.upper()
                if any(kw in title_upper for kw in MACRO_KEYWORDS):
                    macro_items.append({"title": title, "link": link, "source": name})
        except Exception as e:
            print(f"  ⚠️ RSS macro {name}: {e}")
    return macro_items[:8]  # max 8


def generate_insights(all_assets: dict, portfolios: dict, macro: dict, macro_us: dict, indices: dict) -> list[str]:
    """Gera insights baseados nos dados do dia."""
    insights = []

    # --- Alertas de variacao >5% ---
    snapshot = load_snapshot()
    for sheet_name, snap_data in snapshot["sheets"].items():
        assets = all_assets.get(sheet_name, {})
        if not assets:
            continue
        for ticker in snap_data["tickers"]:
            prices = assets.get(ticker, {})
            if not prices.get("current"):
                continue
            day_pct = ((prices["current"] / prices["day_ago"] - 1) * 100) if prices.get("day_ago") else None
            if day_pct and abs(day_pct) > 5:
                direction = "subiu" if day_pct > 0 else "caiu"
                insights.append(f"⚠️ **{ticker}** {direction} {abs(day_pct):.1f}% hoje ({sheet_name})")

    # --- Renda Fixa vs Bolsa ---
    selic = macro.get("selic")
    ipca = macro.get("ipca_12m")
    if selic:
        real = (1 + selic / 100) / (1 + ipca / 100) - 1 if ipca else selic * 0.7
        insights.append(f"🏦 **Selic {selic:.1f}%** — Renda Fixa paga ~{selic*0.7:.1f}% liq IR. Juro real de ~{real*100:.1f}% a.a.")

    # --- Mercado (Ibovespa / IFIX) ---
    if "IBOV" in indices:
        ibov = indices["IBOV"]
        direction = "subiu" if ibov["day_pct"] > 0 else "caiu"
        if abs(ibov["day_pct"]) > 1:
            insights.append(f"📊 **Ibovespa {direction} {abs(ibov['day_pct']):.1f}%** — {'bolsa reagindo a noticias' if abs(ibov['day_pct']) > 2 else 'movimento moderado'}")
    if "IFIX" in indices:
        ifix = indices["IFIX"]
        if "day_pct" in ifix and ifix["day_pct"] is not None:
            direction = "subiu" if ifix["day_pct"] > 0 else "caiu"
            insights.append(f"🏢 **IFIX {direction} {abs(ifix['day_pct']):.1f}%** — {'FIIs em movimento' if abs(ifix['day_pct']) > 0.5 else 'FIIs estaveis'}")

    # --- BTC ---
    if "BTC" in indices:
        btc = indices["BTC"]
        direction = "subiu" if btc["day_pct"] > 0 else "caiu"
        if abs(btc["day_pct"]) > 2:
            insights.append(f"₿ **Bitcoin {direction} {abs(btc['day_pct']):.1f}%** — volatilidade elevada, atencao")

    # --- Fed / US ---
    if macro_us.get("fed_funds"):
        insights.append(f"🇺🇸 **Fed Funds {macro_us['fed_funds']:.2f}%** — {'juros altos favorecem renda fixa em dolar' if macro_us['fed_funds'] > 3 else 'juros em queda favorecem bolsa americana'}")

    # --- Sentimento geral ---
    sentiment_parts = []
    if selic and ipca and selic > ipca + 5:
        sentiment_parts.append("juro real elevado favorece renda fixa BR")
    if "IBOV" in indices and indices["IBOV"]["day_pct"] < -1:
        sentiment_parts.append("bolsa em queda pode ser oportunidade de compra")
    elif "IBOV" in indices and indices["IBOV"]["day_pct"] > 1:
        sentiment_parts.append("bolsa em alta, cautela com novos aportes")
    if "IFIX" in indices and "day_pct" in indices["IFIX"] and indices["IFIX"]["day_pct"] is not None and indices["IFIX"]["day_pct"] < -0.5:
        sentiment_parts.append("FIIs descontados, bons yields")
    if sentiment_parts:
        insights.append(f"🧭 **Sentimento**: {', '.join(sentiment_parts)}")

    if not insights:
        insights.append("✅ Nenhum alerta relevante hoje.")

    return insights


def main():
    print_stdout = "--print" in sys.argv

    # 1. Garantir precos atualizados
    print("📊 sync.py update...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "scripts" / "sync.py"), "update"],
        capture_output=True, text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"⚠️ sync.py falhou (exit {result.returncode}): {result.stderr[:200]}")
    else:
        print("✅ sync.py OK")

    # 2. Carregar dados
    snapshot = load_snapshot()
    ticker_map = load_ticker_map()
    ticker_meta = load_ticker_meta()
    today = datetime.now(timezone.utc)

    # 3. Buscar historico de precos
    print("📈 Buscando historico de precos...")
    all_assets = {}  # {sheet_name: {ticker: {current, day_ago, ...}}}
    all_tickers_set = set()

    for sheet_name, snap_data in snapshot["sheets"].items():
        all_assets[sheet_name] = {}
        for ticker in snap_data["tickers"]:
            source, symbol = resolve_ticker(ticker, ticker_map)
            prices = fetch_price_history(symbol, source)
            if prices:
                all_assets[sheet_name][ticker] = prices
            all_tickers_set.add(ticker)

    # 4. Buscar patrimonio e alocacao por ativo
    print("💰 Lendo patrimonio e alocacao...")
    portfolios = {}
    allocations = {}  # {sheet_name: [(ticker, value, category), ...]}
    for sheet_name in snapshot["sheets"]:
        cfg = None
        ss = load_ticker_map()
        with open(SHEETS_FILE) as f:
            sheets_cfg = json.load(f)["spreadsheets"][SPREADSHEET_ID]["sheets"]
            cfg = sheets_cfg.get(sheet_name)

        if not cfg:
            continue

        # Le coluna G (alocado) + total
        max_col = "H"  # colunas A-H bastam
        last_row = max(
            p["row"] for p in snapshot["sheets"][sheet_name]["positions"].values()
        ) + 2

        data = composio("GOOGLESHEETS_BATCH_GET", {
            "spreadsheet_id": SPREADSHEET_ID,
            "ranges": [f"{sheet_name}!A1:{max_col}{last_row}"],
        })
        rows = data["data"]["valueRanges"][0].get("values", [])

        # Procura "Total Btg" ou "Total Inter" nas primeiras linhas
        total = 0
        for row in rows[:5]:
            for i, cell in enumerate(row):
                if isinstance(cell, str) and ("Total Btg" in cell or "Total Inter" in cell or "Total" in cell):
                    for c in row:
                        if isinstance(c, str) and "R$" in c:
                            try:
                                val = c.replace("R$", "").replace(".", "").replace(",", ".")
                                total = max(total, float(val))  # pega o maior
                            except ValueError:
                                pass
                            break

        portfolios[sheet_name] = total

        # Extrai alocacao por ativo (coluna G = alocado)
        sheet_allocs = []
        cat = None
        for row in rows:
            if not row:
                continue
            ticker = row[0].strip() if len(row) > 0 and row[0] else ""
            # Detecta categoria (linhas como "Ações BR", "FIIs", "Equity")
            if ticker in ("Ações BR", "FIIs", "Equity", "RF", "Proteções"):
                cat = ticker
                continue
            if ticker in ("Ações", "Caixa", "Pre", "Inflacao"):
                continue  # subcategorias, mantem a categoria pai
            # Pega valor alocado da coluna G
            if ticker and len(row) > 6:
                g_val = row[6].strip() if row[6] else ""
                if g_val:
                    try:
                        val = float(g_val.replace("R$", "").replace("$", "").replace(".", "").replace(",", ".").strip())
                        if val > 0:
                            current_cat = cat or "Outros"
                            sheet_allocs.append((ticker, val, current_cat))
                    except ValueError:
                        pass
        allocations[sheet_name] = sheet_allocs

    # 5. Buscar noticias
    print("📰 Buscando noticias...")
    all_tickers = list(all_tickers_set)
    news = fetch_asset_news(all_tickers)

    # 5b. Buscar noticias macro
    print("🌎 Buscando noticias macro...")
    macro_news = fetch_macro_news()

    # 5c. Buscar dados macro
    print("🏦 Buscando indicadores macro...")
    macro_data = fetch_selic()
    fed_data = fetch_fed_funds()
    indices = fetch_indices()

    # 5d. Gerar insights
    print("💡 Gerando insights...")
    insights = generate_insights(all_assets, portfolios, macro_data, fed_data, indices)

    # 6. Gerar relatorio
    report = []
    date_str = today.strftime("%d/%m/%Y")
    file_date = today.strftime("%Y-%m-%d")

    report.append(f"# 📊 Relatório Diário — {date_str}\n")

    # --- Variacoes >3% ---
    report.append("## 📈 Oscilações Significativas (>3%)\n")
    alertas = []
    seen_alerts = set()
    for sheet_name, assets in all_assets.items():
        for ticker, prices in assets.items():
            if not prices.get("current") or not prices.get("day_ago"):
                continue
            pct = (prices["current"] / prices["day_ago"] - 1) * 100
            key = (ticker, abs(pct))
            if abs(pct) > 3 and key not in seen_alerts:
                seen_alerts.add(key)
                emoji = "🟢" if pct > 0 else "🔴"
                currency_sign = "US$" if get_currency(ticker, ticker_meta) == "USD" else "R$"
                price_fmt = f"{currency_sign} {prices['current']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                alertas.append(f"  {emoji} **{ticker}**: {pct:+.1f}% ({price_fmt})")

    if alertas:
        report.extend(alertas)
    else:
        report.append("  Nenhum ativo com oscilação >3% no dia.\n")
    report.append("")

    # --- Patrimonio ---
    report.append("## 💰 Patrimônio\n")
    total_geral = sum(portfolios.values())
    for name, val in sorted(portfolios.items()):
        report.append(f"  **{name}**: {fmt_brl(val)}")
    report.append(f"\n  **Total geral**: {fmt_brl(total_geral)}\n")

    # --- Cenário Macro ---
    report.append("## 🏦 Cenário Macro\n")
    if macro_data.get("selic"):
        report.append(f"  **Selic**: {macro_data['selic']:.1f}% a.a.")
        report.append(f"  **CDI**: ~{macro_data['selic'] - 0.1:.1f}% a.a. (≈ Selic - 0.1pp)")
        report.append(f"  **CDB 100% CDI (liq IR)**: ~{macro_data['selic'] * 0.7:.1f}% a.a. (aliquota 30%)")
        report.append(f"  **Poupança**: ~{macro_data['selic'] * 0.7 * 0.6:.1f}% a.a. (70% da Selic)")
    if macro_data.get("ipca_12m"):
        report.append(f"  **IPCA 12m**: {macro_data['ipca_12m']:.2f}%")
        if macro_data.get("selic"):
            real = (1 + macro_data['selic'] / 100) / (1 + macro_data['ipca_12m'] / 100) - 1
            report.append(f"  **Juro Real**: ~{real * 100:.1f}% a.a.")
    if fed_data.get("fed_funds"):
        report.append(f"\n  🇺🇸 **Fed Funds**: {fed_data['fed_funds']:.2f}% a.a.")
        report.append(f"  **Treasury 10Y**: referencia para renda fixa em USD")

    # --- Tesouro Nacional ---
    treasury = fetch_treasury()
    if treasury:
        report.append("")
        report.append("## 🇧🇷 Tesouro Nacional\n")
        for bond in treasury:
            report.append(f"  **{bond['name']}**: {bond['rate']} | Rent. est.: {bond['est_rate']} | Venc: {bond['maturity']}")
    else:
        report.append(f"\n  🇧🇷 **Tesouro Nacional**: dados indisponiveis")

    if indices:
        report.append("")
        report.append("| Índice | Preço | Dia | Semana | Mês | Ano | ATH |")
        report.append("|--------|-------|-----|--------|-----|-----|-----|")
        labels = {"IBOV": "Ibovespa", "IFIX": "IFIX", "BTC": "Bitcoin USD", "USD": "Dólar", "EUR": "Euro"}
        for name in ["IBOV", "IFIX", "BTC", "USD", "EUR"]:
            if name not in indices:
                continue
            d = indices[name]
            is_brl = name not in ("BTC",)
            is_currency = name in ("USD", "EUR")
            if is_currency:
                price_fmt = f"R$ {d['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            else:
                price_fmt = f"R$ {d['price']:,.0f}" if is_brl else f"$ {d['price']:,.0f}"
                price_fmt = price_fmt.replace(",", "X").replace(".", ",").replace("X", ".")

            def pct_str(key):
                v = d.get(f"{key}_pct")
                if v is None:
                    return "N/D"
                color = "🔴" if v < -1 else ("🟢" if v > 1 else "")
                return f"{color}{v:+.1f}%"

            ath_str = pct_str("ath") if "ath_pct" in d else "N/D"
            report.append(
                f"| {labels[name]} | {price_fmt} | {pct_str('day')} | {pct_str('week')} | {pct_str('month')} | {pct_str('year')} | {ath_str} |"
            )
    report.append("")

    # --- Graficos de Pizza (Alocacao) ---
    if allocations:
        # Wrapper para manter título + gráficos juntos no PDF
        report.append('<div style="page-break-inside: avoid;">')
        report.append("## 🍕 Alocação\n")
        chart_pairs = []  # [(label, url, fallback_alt), ...]

        # 1. Por classe de ativo (uma pizza por carteira)
        for sheet_name in sorted(allocations.keys()):
            sheet_allocs = allocations[sheet_name]
            if not sheet_allocs:
                continue
            by_cat = {}
            for ticker, val, cat in sheet_allocs:
                by_cat[cat] = by_cat.get(cat, 0) + val
            if by_cat:
                url = pie_chart_url(list(by_cat.keys()), list(by_cat.values()),
                                    f"Renda Variável — {sheet_name}")
                if url:
                    chart_pairs.append((sheet_name, url, sheet_name))

        # 2. Por moeda (BRL × USD)
        usd_total = 0
        brl_total = 0
        for sheet_name, sheet_allocs in allocations.items():
            for ticker, val, cat in sheet_allocs:
                if get_currency(ticker, ticker_meta) == "USD":
                    usd_total += val
                else:
                    brl_total += val
        if usd_total > 0 or brl_total > 0:
            url = pie_chart_url(["BRL", "USD"], [brl_total, usd_total],
                                "Renda Variável — Exposição por Moeda")
            if url:
                chart_pairs.append(("Moeda", url, "Moeda"))

        # 3. Geografico (usa ticker_meta["geo"])
        geo_map = {}     # {geo: valor_total}
        geo_tickers = {} # {geo: [tickers_sem_prefixo]}
        for sheet_name, sheet_allocs in allocations.items():
            for ticker, val, cat in sheet_allocs:
                geo = get_geo(ticker, ticker_meta)
                geo_map[geo] = geo_map.get(geo, 0) + val
                # Extrai nome curto do ticker (sem prefixo NASDAQ:/NYSEARCA:/CURRENCY:)
                short = ticker.split(":")[-1] if ":" in ticker else ticker
                geo_tickers.setdefault(geo, [])
                if short not in geo_tickers[geo]:
                    geo_tickers[geo].append(short)
        geo_order = [g for g in ["Brasil", "EUA", "China", "Emergentes", "Cripto", "Global"] if g in geo_map]
        other_geos = sorted(set(geo_map.keys()) - set(geo_order), key=lambda g: -geo_map[g])
        # Label dinâmico: "Global (IAU, SLV, DBA)" sem hardcode
        geo_labels = []
        for g in geo_order + other_geos:
            tickers_str = ", ".join(geo_tickers[g])
            geo_labels.append(f"{g} ({tickers_str})" if tickers_str else g)
        geo_values = [geo_map[g] for g in (geo_order + other_geos)]
        if geo_labels:
            url = pie_chart_url(geo_labels, geo_values,
                                "Renda Variável — Alocação Geográfica")
            if url:
                chart_pairs.append(("Geografia", url, "Geografia"))

        # 4. Cripto e Proteções
        cripto_val = prot_val = 0
        for sheet_name, sheet_allocs in allocations.items():
            for ticker, val, cat in sheet_allocs:
                geo = get_geo(ticker, ticker_meta)
                if geo == "Cripto":
                    cripto_val += val
                elif geo == "Global":
                    prot_val += val
        if cripto_val > 0 or prot_val > 0:
            c_labels, c_values = [], []
            if cripto_val > 0:
                c_labels.append("Bitcoin"); c_values.append(cripto_val)
            if prot_val > 0:
                # Nome dinâmico com tickers que são Global
                prot_tickers = geo_tickers.get("Global", [])
                prot_label = f"Proteções ({', '.join(prot_tickers)})" if prot_tickers else "Proteções"
                c_labels.append(prot_label); c_values.append(prot_val)
            if c_labels:
                url = pie_chart_url(c_labels, c_values,
                                    "Renda Variável — Cripto & Proteções")
                if url:
                    chart_pairs.append(("Cripto & Proteções", url, "CriptoProtecoes"))

        # Renderiza 2 por linha
        for i in range(0, len(chart_pairs), 2):
            row = chart_pairs[i:i+2]
            report.append(chart_row(row))

        report.append("</div>\n")

    # --- Tabela completa ---
    report.append('<div style="page-break-before: always;"></div>')
    report.append("## 📋 Todos os Ativos\n")
    report.append("| Ticker | Preço | Dia | Semana | Mês | Ano |")
    report.append("|--------|-------|-----|--------|-----|-----|")

    for sheet_name in sorted(snapshot["sheets"].keys()):
        assets = all_assets.get(sheet_name, {})
        if not assets:
            continue
        report.append(f"| **{sheet_name}** | | | | | |")
        for ticker, prices in assets.items():
            if not prices.get("current"):
                continue

            current = prices["current"]
            currency = get_currency(ticker, ticker_meta)

            if currency == "USD":
                price_str = f"$ {current:,.2f}"
            else:
                # BRL: formata com R$
                if ticker == "CURRENCY:BTCBRL":
                    price_str = f"{fmt_brl(current)}"
                else:
                    price_str = f"R$ {current:,.2f}".replace(".", ",")

            day_pct = ((current / prices["day_ago"] - 1) * 100) if prices.get("day_ago") else None
            week_pct = ((current / prices["week_ago"] - 1) * 100) if prices.get("week_ago") else None
            month_pct = ((current / prices["month_ago"] - 1) * 100) if prices.get("month_ago") else None
            year_pct = ((current / prices["year_ago"] - 1) * 100) if prices.get("year_ago") else None

            report.append(
                f"| {ticker} | {price_str} | {fmt_pct(day_pct)} | {fmt_pct(week_pct)} | {fmt_pct(month_pct)} | {fmt_pct(year_pct)} |"
            )

    report.append("")

    # --- Mini-tabela temática (usa ticker_meta["geo"]) ---
    report.append("## 🌍 Temáticos: China, Emergentes, Proteção\n")
    report.append("| Índice | Preço | Dia | Semana | Mês | Ano | ATH |")
    report.append("|--------|-------|-----|--------|-----|-----|-----|")
    # Agrupa tickers por geo relevante, usa ticker_meta
    geo_labels = {"China": "China", "Emergentes": "Emergentes", "Global": "Proteção"}
    seen = set()
    for sheet_name in sorted(all_assets.keys()):
        for ticker, prices in all_assets[sheet_name].items():
            if ticker in seen or not prices.get("current"):
                continue
            geo = get_geo(ticker, ticker_meta)
            label = geo_labels.get(geo)
            if not label:
                continue
            seen.add(ticker)
            cur = prices["current"]
            currency_sign = "US$" if get_currency(ticker, ticker_meta) == "USD" else "R$"
            day = ((cur / prices["day_ago"] - 1) * 100) if prices.get("day_ago") else None
            week = ((cur / prices["week_ago"] - 1) * 100) if prices.get("week_ago") else None
            month = ((cur / prices["month_ago"] - 1) * 100) if prices.get("month_ago") else None
            year = ((cur / prices["year_ago"] - 1) * 100) if prices.get("year_ago") else None
            price_str = f"{currency_sign} {cur:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            report.append(
                f"| {label} ({ticker}) | {price_str} | {fmt_pct(day)} | {fmt_pct(week)} | {fmt_pct(month)} | {fmt_pct(year)} |   |"
            )
    report.append("")

    # --- Noticias ---
    report.append("## 📰 Destaques do Mercado\n")
    if news:
        for n in news:
            report.append(f"  - [{n['title']}]({n['link']}) — _{n['source']}_")
        report.append("")
    else:
        report.append("  Nenhuma notícia encontrada.\n")

    # --- Noticias Macro ---
    report.append("\n## 🌎 Cenário Macro — Notícias\n")
    if macro_news:
        for n in macro_news:
            report.append(f"  - [{n['title']}]({n['link']}) — _{n['source']}_")
        report.append("")
    else:
        report.append("  Nenhuma notícia macro relevante.\n")

    # --- Insights ---
    report.append("## 💡 Insights & Recomendações\n")
    for insight in insights:
        report.append(f"  {insight}")
    report.append("")

    report.append(f"\n---\n*Relatório gerado em {date_str}*")

    # 7. Salvar
    REPORTS_DIR.mkdir(exist_ok=True)
    filename = REPORTS_DIR / f"daily_{file_date}.md"
    content = "\n".join(report)
    with open(filename, "w") as f:
        f.write(content)
    print(f"\n✅ Relatório salvo: {filename}")

    if print_stdout:
        print("\n" + content)


if __name__ == "__main__":
    main()
