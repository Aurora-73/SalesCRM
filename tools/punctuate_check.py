import os

_root = os.path.join(os.path.dirname(__file__), "..")
doc_dir = os.path.join(_root, "docs", "other-book", "doc")
files = sorted(os.listdir(doc_dir))
md_files = [f for f in files if f.endswith('.md')]

with open(os.path.join(_root, "punctuation_status.txt"), 'w', encoding='utf-8') as out:
    for f in md_files:
        filepath = os.path.join(doc_dir, f)
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()

        has_comma = '，' in content
        has_period = '。' in content

        if has_comma and has_period:
            comma_count = content.count('，') + content.count('。') + content.count('？') + content.count('！')
            text_length = len(content)
            density = comma_count / text_length
            status = 'DONE' if density > 0.01 else 'NEEDS PUNCTUATION'
        else:
            status = 'NEEDS PUNCTUATION'

        out.write(f"{status}: {f}\n")