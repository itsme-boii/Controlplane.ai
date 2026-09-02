import markdown
from pathlib import Path

css = """
<style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1, h2, h3 { color: #111; margin-top: 1.5em; }
    h1 { border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
    pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; border: 1px solid #e1e4e8; }
    code { background: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; font-size: 85%; }
    pre code { background: transparent; padding: 0; }
    blockquote { border-left: 4px solid #dfe2e5; margin: 0; padding-left: 16px; color: #6a737d; }
    table { border-collapse: collapse; width: 100%; margin-top: 1em; margin-bottom: 1em; }
    th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
    th { background-color: #f6f8fa; font-weight: 600; }
    a { color: #0366d6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    hr { height: 0.25em; padding: 0; margin: 24px 0; background-color: #e1e4e8; border: 0; }
</style>
"""

def md_to_html(md_path, html_path):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    html = markdown.markdown(text, extensions=['fenced_code', 'tables'])
    title = md_path.stem.replace('_', ' ').title()
    full_html = f"<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n<title>{title}</title>\n{css}</head>\n<body>\n{html}\n</body>\n</html>"
    
    html_path.parent.mkdir(exist_ok=True, parents=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated {html_path}")

def main():
    md_files = [
        Path("README.md"),
        Path("docs/render_deployment.md"),
        Path("docs/architecture.md"),
        Path("docs/presentation_script.md"),
        Path("docs/business_proposal.md")
    ]

    for md_file in md_files:
        if md_file.exists():
            html_file = Path("docs/html") / md_file.with_suffix('.html').name
            md_to_html(md_file, html_file)

if __name__ == "__main__":
    main()
