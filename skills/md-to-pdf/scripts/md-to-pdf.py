#!/usr/bin/env python3
"""
Convert markdown to PDF preserving hyperlinks.
Uses Python markdown + Google Chrome headless.

Usage:
    python3 <script> [input.md] [output.pdf]

Defaults:
    input.md  = plano-nivelamento-ia-dev.md (in current dir)
    output.pdf = plano-nivelamento-com-links.pdf
"""
import markdown
import subprocess
import sys
import os

def md_to_pdf(md_path, pdf_path):
    # Read markdown
    with open(md_path, 'r') as f:
        md_content = f.read()

    # Convert to HTML with tables extension
    html_body = markdown.markdown(
        md_content,
        extensions=['extra', 'tables', 'fenced_code', 'codehilite', 'sane_lists']
    )

    # Extract title from first h1
    title = "Documento"
    for line in md_content.split('\n'):
        if line.startswith('# '):
            title = line.lstrip('# ').strip()
            break

    # Full HTML document
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
    @page {{ margin: 2cm; }}
    body {{
        font-family: 'DejaVu Sans', 'Segoe UI', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #1a1a1a;
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }}
    h1 {{ font-size: 18pt; margin-top: 0; color: #111; }}
    h2 {{ font-size: 14pt; margin-top: 24pt; color: #222; border-bottom: 1px solid #ccc; padding-bottom: 4pt; }}
    h3 {{ font-size: 12pt; margin-top: 18pt; color: #333; }}
    a {{ color: #1565C0; text-decoration: underline; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12pt 0; font-size: 10pt; }}
    th, td {{ border: 1px solid #999; padding: 6pt 8pt; text-align: left; }}
    th {{ background-color: #f0f0f0; font-weight: bold; }}
    tr:nth-child(even) {{ background-color: #fafafa; }}
    code {{ background-color: #f5f5f5; padding: 2pt 4pt; border-radius: 3pt; font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; }}
    pre {{ background-color: #f5f5f5; padding: 10pt; border-radius: 4pt; overflow-x: auto; }}
    pre code {{ background: none; padding: 0; }}
    hr {{ border: none; border-top: 1px solid #ddd; margin: 20pt 0; }}
    blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 12pt; color: #555; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # Write HTML file
    html_path = md_path + '.html'
    with open(html_path, 'w') as f:
        f.write(html)

    print(f"HTML gerado: {html_path}")

    # Convert to PDF using Chrome headless
    result = subprocess.run([
        'google-chrome',
        '--headless',
        '--disable-gpu',
        '--no-margins',
        f'--print-to-pdf={os.path.abspath(pdf_path)}',
        f'file://{os.path.abspath(html_path)}'
    ], capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        print(f"ERRO Chrome: {result.stderr}")
        sys.exit(1)

    print(f"PDF gerado: {pdf_path}")
    print(f"Tamanho: {os.path.getsize(pdf_path)} bytes")

    # Clean up temp HTML
    os.remove(html_path)
    print(f"Temp HTML removido: {html_path}")


if __name__ == '__main__':
    md_path = sys.argv[1] if len(sys.argv) > 1 else 'plano-nivelamento-ia-dev.md'
    pdf_path = sys.argv[2] if len(sys.argv) > 2 else 'plano-nivelamento-com-links.pdf'
    md_to_pdf(md_path, pdf_path)
