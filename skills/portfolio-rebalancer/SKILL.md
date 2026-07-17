---
name: investimentos-portfolio-rebalancer
description: Compara alocacao atual de cada ativo na carteira com o peso alvo definido e sugere compras ou vendas para rebalanceamento. Use quando o usuario perguntar sobre balanceamento, "preciso comprar algo?", ou ao gerar relatorio periodico.
---

# Portfolio Rebalancer

Analisa alocacao atual vs alvo e sugere acoes de rebalanceamento.

## Trigger

- Usuario pergunta sobre balanceamento da carteira
- "Preciso comprar ou vender algo?"
- "Como esta minha alocacao?"
- Parte de relatorio periodico

## Fluxo

### 1. Obter dados da carteira

Do contexto (planilha, snapshot, API), obter para cada ativo:
- **Ticker** (identificador)
- **Preco atual** (ultima cotacao)
- **Quantidade** (cotas/acoes)
- **Peso alvo** (%) — quanto deveria representar da carteira
- **Valor atual** = preco × quantidade (ou valor alocado, se ja calculado)

### 2. Calcular desvios

```
patrimonio_total = soma de todos os valores atuais
peso_atual = valor_atual / patrimonio_total × 100
desvio = peso_atual - peso_alvo
```

### 3. Classificar

| Desvio | Acao |
|--------|------|
| > +2pp | VENDER (significativamente acima do alvo) |
| +1pp a +2pp | ATENCAO (tendencia de sobrepeso) |
| -1pp a +1pp | OK (dentro da banda) |
| -2pp a -1pp | ATENCAO (tendencia de subpeso) |
| < -2pp | COMPRAR (significativamente abaixo do alvo) |

### 4. Calcular valores

Para cada ativo fora da banda:
```
valor_ideal = patrimonio_total × peso_alvo / 100
ajuste = valor_ideal - valor_atual
# ajuste > 0 → comprar | ajuste < 0 → vender
```

### 5. Gerar relatorio

Agrupar por acao sugerida e ordenar por urgencia (maior desvio primeiro).
Incluir valor monetario do ajuste e, se disponivel, numero aproximado de cotas.

## Pitfalls

- PrecOs devem estar atualizados (rodar sincronizacao antes)
- Soma dos pesos alvo deve ser ~100% — se nao, ha categorias ou ativos faltando
- Ativos em moeda estrangeira precisam de conversao para mesma base
- Separar analise por carteira se houver mais de uma (ex: perfil conservador vs agressivo)
- Ajustes muito pequenos (< 1% do patrimonio) podem ser ignorados para evitar custos de corretagem
