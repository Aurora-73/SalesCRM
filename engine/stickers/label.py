"""贴纸标注工具 — 生成 HTML 标注页面 + 导入标注结果。

用法：
    python -m engine.stickers.label generate [--limit 100]  # 生成 HTML 标注页面
    python -m engine.stickers.label import                  # 从 JSON 导入标注结果
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import load_config
from engine.importers.db_init import get_db
from .core import ensure_stickers_table, label_sticker


def generate_html(limit: int = 100, min_freq: int = 1) -> Path:
    config = load_config()
    conn = get_db(config.db_path)
    ensure_stickers_table(conn)

    rows = conn.execute("""
        SELECT s.md5, s.frequency, s.label, s.emotion, s.user_verified,
               (SELECT raw_content FROM messages WHERE type = 47 AND raw_content LIKE '%' || s.md5 || '%' LIMIT 1) as sample_raw
        FROM stickers s
        WHERE s.user_verified = 0 AND s.frequency >= ?
        ORDER BY s.frequency DESC
        LIMIT ?
    """, (min_freq, limit)).fetchall()

    cdn_pattern = re.compile(r'cdnurl\s*=\s*"([^"]+)"')

    stickers = []
    for r in rows:
        cdn_url = ""
        width = 0
        height = 0
        product_id = ""
        if r["sample_raw"]:
            raw = r["sample_raw"]
            m = cdn_pattern.search(raw)
            if m and m.group(1):
                cdn_url = m.group(1).replace("&amp;", "&")
            wm = re.search(r'width\s*=\s*"?(\d+)"?', raw)
            hm = re.search(r'height\s*=\s*"?(\d+)"?', raw)
            pm = re.search(r'productid\s*=\s*"([^"]*)"', raw)
            if wm:
                width = int(wm.group(1))
            if hm:
                height = int(hm.group(1))
            if pm:
                product_id = pm.group(1)

        wcd_url = f"http://127.0.0.1:10392/api/chat/media/emoji?md5={r['md5']}" if r["md5"] else ""

        stickers.append({
            "md5": r["md5"],
            "frequency": r["frequency"],
            "cdn_url": cdn_url,
            "wcd_url": wcd_url,
            "width": width,
            "height": height,
            "product_id": product_id,
            "label": r["label"] or "",
            "emotion": r["emotion"] or "",
        })

    conn.close()

    output_path = ROOT / "data" / "cache" / "sticker_labels.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = _build_html(stickers)
    output_path.write_text(html, encoding="utf-8")
    print(f"已生成标注页面: {output_path}")
    print(f"包含 {len(stickers)} 个未标注贴纸 (最低频率 {min_freq})")
    return output_path


def _build_html(stickers: list[dict]) -> str:
    stickers_json = json.dumps(stickers, ensure_ascii=False, indent=2)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>贴纸标注工具</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
  h1 {{ text-align: center; margin-bottom: 10px; font-size: 1.5em; }}
  .stats {{ text-align: center; margin-bottom: 20px; color: #888; }}
  .toolbar {{ text-align: center; margin-bottom: 20px; }}
  .toolbar button {{ padding: 8px 20px; margin: 0 5px; border: none; border-radius: 6px;
    cursor: pointer; font-size: 14px; }}
  .btn-export {{ background: #4CAF50; color: white; }}
  .btn-skip {{ background: #666; color: white; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
  .card {{ background: #16213e; border-radius: 10px; padding: 12px; text-align: center;
    border: 2px solid transparent; transition: border-color 0.2s; }}
  .card.labeled {{ border-color: #4CAF50; }}
  .card img {{ max-width: 120px; max-height: 120px; margin: 8px 0; image-rendering: auto; }}
  .card .freq {{ color: #ff6b6b; font-weight: bold; font-size: 1.1em; }}
  .card .md5 {{ color: #666; font-size: 0.75em; font-family: monospace; }}
  .card .no-img {{ display: none; padding: 15px; color: #888; font-size: 12px; }}
  .card select, .card input {{ width: 100%; margin: 4px 0; padding: 4px; border-radius: 4px;
    border: 1px solid #333; background: #0f3460; color: #eee; font-size: 13px; }}
  .card select:focus, .card input:focus {{ outline: none; border-color: #4CAF50; }}
  .count {{ color: #4CAF50; font-weight: bold; }}
</style>
</head>
<body>
<h1>贴纸标注工具</h1>
<div class="stats">
  共 <span id="total">0</span> 个贴纸，已标注 <span class="count" id="labeled">0</span> 个
</div>
<div class="toolbar">
  <button class="btn-export" onclick="exportJSON()">导出 JSON</button>
  <button class="btn-skip" onclick="skipAll()">跳过未标注</button>
</div>
<div class="grid" id="grid"></div>

<script>
const stickers = {stickers_json};
const grid = document.getElementById('grid');
const totalEl = document.getElementById('total');
const labeledEl = document.getElementById('labeled');
let labeledCount = 0;

totalEl.textContent = stickers.length;

function buildImgHtml(s) {{
  let result = '';
  if (s.cdn_url || s.wcd_url) {{
    result += '<img src="' + (s.cdn_url || s.wcd_url) + '" alt="sticker" loading="lazy"'
           + ' onerror="var c=this.parentElement; this.style.display=\\'none\\'; '
           + 'var ni=c.querySelector(\\'.no-img\\'); if(ni)ni.style.display=\\'block\\'; '
           + 'var nxt=c.querySelector(\\'.fallback-img\\'); '
           + 'if(nxt)' + (s.wcd_url ? 'nxt.src=\\'' + s.wcd_url + '\\'; nxt.style.display=\\'block\\';' : 'nxt.style.display=\\'none\\';')
           + '">';
    if (s.cdn_url && s.wcd_url) {{
      result += '<img class="fallback-img" src="' + s.wcd_url + '" alt="sticker(wcd)" loading="lazy"'
             + ' style="display:none; max-width:120px; max-height:120px; margin:8px 0;"'
             + ' onerror="this.style.display=\\'none\\';var ni=this.parentElement.querySelector(\\'.no-img\\');if(ni)ni.style.display=\\'block\\';">';
    }}
  }}
  result += '<div class="no-img">图片未缓存<br>' + (s.width ? s.width + 'x' + s.height : '') + (s.product_id ? '<br>贴纸包' : '') + '<br><span style="color:#666;font-size:10px">通过频率和尺寸标注</span></div>';
  return result;
}}

stickers.forEach((s, i) => {{
  const card = document.createElement('div');
  card.className = 'card';
  card.id = 'card-' + i;

  card.innerHTML = `
    <div class="freq">#${{i+1}} · ${{s.frequency}}次</div>
    ${{buildImgHtml(s)}}
    <div class="md5">${{s.md5 ? s.md5.substring(0,12)+'...' : ''}}</div>
    <select onchange="updateEmotion(${{i}}, this.value)">
      <option value="">-- 情绪 --</option>
      <option value="positive">positive (积极/友好/认可)</option>
      <option value="negative">negative (消极/敷衍/抗拒)</option>
      <option value="neutral">neutral (中性，不表达态度)</option>
      <option value="ambiguous">ambiguous (模糊/不确定)</option>
    </select>
    <input type="text" placeholder="描述 (如: 开心大笑)" onchange="updateLabel(${{i}}, this.value)"
      value="${{s.label}}">
  `;
  grid.appendChild(card);
}});

function updateEmotion(i, val) {{
  stickers[i].emotion = val;
  checkLabeled(i);
}}

function updateLabel(i, val) {{
  stickers[i].label = val;
  checkLabeled(i);
}}

function checkLabeled(i) {{
  const card = document.getElementById('card-' + i);
  if (stickers[i].emotion || stickers[i].label) {{
    card.classList.add('labeled');
  }} else {{
    card.classList.remove('labeled');
  }}
  labeledCount = stickers.filter(s => s.emotion || s.label).length;
  labeledEl.textContent = labeledCount;
}}

function exportJSON() {{
  const labeled = stickers.filter(s => s.emotion || s.label);
  if (labeled.length === 0) {{
    alert('没有标注任何贴纸');
    return;
  }}
  const blob = new Blob([JSON.stringify(labeled, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sticker_labels.json';
  a.click();
  alert('已导出 ' + labeled.length + ' 个标注。\\n请将 sticker_labels.json 放到 data/cache/ 目录，\\n然后运行: python -m engine.stickers.label import');
}}

function skipAll() {{
  const unlabeled = stickers.filter(s => !s.emotion && !s.label);
  if (unlabeled.length > 0 && confirm('跳过 ' + unlabeled.length + ' 个未标注贴纸？')) {{
    unlabeled.forEach(s => s.emotion = 'neutral');
    stickers.forEach((s, i) => checkLabeled(i));
  }}
}}
</script>
</body>
</html>"""


def import_labels() -> None:
    json_path = ROOT / "data" / "cache" / "sticker_labels.json"
    if not json_path.is_file():
        print(f"未找到 {json_path}")
        return

    with open(json_path, encoding="utf-8") as f:
        labels = json.load(f)

    config = load_config()
    conn = get_db(config.db_path)
    ensure_stickers_table(conn)

    success = 0
    for item in labels:
        md5 = item.get("md5", "")
        if not md5:
            continue
        if label_sticker(conn, md5,
                         label=item.get("label", ""),
                         emotion=item.get("emotion", "")):
            success += 1

    conn.close()
    print(f"导入完成: {success}/{len(labels)} 个贴纸已标注")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m engine.stickers.label generate [--limit 100] [--min-freq 1]")
        print("  python -m engine.stickers.label import")
        sys.exit(1)

    action = sys.argv[1]
    if action == "generate":
        limit = 100
        min_freq = 1
        for i, arg in enumerate(sys.argv[2:], 2):
            if arg == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
            elif arg == "--min-freq" and i + 1 < len(sys.argv):
                min_freq = int(sys.argv[i + 1])
        generate_html(limit=limit, min_freq=min_freq)
    elif action == "import":
        import_labels()
    else:
        print(f"未知操作: {action}")
