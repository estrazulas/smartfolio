---
name: md-to-pdf
description: "Convert markdown to PDF preserving hyperlinks. Uses Python markdown library + Google Chrome headless. Solution for editors (MerMark, etc.) that strip links when printing to PDF."
---

# md-to-pdf — Markdown to PDF com Links Preservados

Converte arquivos .md para PDF mantendo todos os hyperlinks clicaveis. Resolve o problema de editores como MerMark que perdem links no dialogo "Imprimir PDF".

## Quando usar

- Usuario gerou PDF de um .md e os links nao funcionam
- Precisa de PDF com hyperlinks clicaveis (YouTube timestamps, URLs de referencia, etc.)
- MerMark ou outro editor de markdown perdeu links no export

## Requisitos

- Google Chrome instalado (`google-chrome` no PATH)
- Python `markdown` library: `pip install markdown`

## Uso

```bash
python3 scripts/md-to-pdf.py [input.md] [output.pdf]
```

**Defaults:**
- input.md: `plano-nivelamento-ia-dev.md` (diretorio atual)
- output.pdf: `plano-nivelamento-com-links.pdf`

### Exemplos

```bash
# Usando defaults
python3 ~/.hermes/skills/md-to-pdf/scripts/md-to-pdf.py

# Especificando arquivos
python3 ~/.hermes/skills/md-to-pdf/scripts/md-to-pdf.py ~/Desktop/conteudoestudos/meu-arquivo.md meu-output.pdf
```

## Como funciona

1. Converte .md para HTML usando a lib `markdown` com extensoes (tables, fenced_code, codehilite)
2. Aplica CSS para formatacao limpa (headers, tabelas, codigo)
3. Renderiza o HTML via Google Chrome headless com `--print-to-pdf`
4. Chrome mantem os hyperlinks como links ativos no PDF
5. Remove o HTML temporario

## Pitfalls

- Requer `pip install markdown` (instalar com `--break-system-packages` se estiver em Debian/Ubuntu sem venv)
- Chrome precisa estar acessivel como `google-chrome` (verificar com `which google-chrome`)
- Arquivos grandes (+100 paginas) podem precisar aumentar o timeout de 30s no script
- O HTML temporario e deletado automaticamente apos gerar o PDF
