from app.editor import clean_pasted_html

html = (
    '<html><head><style>body{background:#111}</style><meta charset="utf-8"></head>'
    '<body style="background-color:#1e1e1e;color:#d4d4d4">'
    '<span style="color:#d4d4d4; background-color:#1e1e1e; font-weight:bold">x</span>'
    '</body></html>'
)
cleaned = clean_pasted_html(html)
print(cleaned)
print("bg left?", "#1e1e1e" in cleaned.lower())
