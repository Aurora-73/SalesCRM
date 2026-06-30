"""导出7个人的聊天记录到文件，供深度分析"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config import load_config
from engine.importers.db_init import get_db
from engine.facts import ensure_people_archives_migrated
from engine.identity import resolve_contact
from engine.agent.chat import agent_chat

config = load_config()
conn = get_db(config.db_path)
ensure_people_archives_migrated(conn, config.my_wxid)

targets = [
    "客户A",
    "客户B",
    "客户C",
    "客户D",
    "客户E",
    "客户F",
    "客户G",
]

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "outputs", "chat_analysis")
os.makedirs(out_dir, exist_ok=True)

for name in targets:
    result = resolve_contact(conn, name)
    person = result.person
    if not person:
        print(f"[SKIP] 找不到: {name}, candidates={result.candidates}")
        continue
    print(f"[START] {name} -> person_id={person.id}, display={person.display_name}, accounts={len(person.accounts)}")

    md = agent_chat(conn, config, person, recent=9999)

    safe_name = person.display_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    out_path = os.path.join(out_dir, f"{safe_name}_chat.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    msg_count = md.count("**[")  # count message blocks
    print(f"[DONE] {name}: ~{msg_count} messages, {len(md)} chars -> {out_path}")

print("\n全部导出完成")
