"""Phase 5+7 质量验证：测试 WikiRetriever 在 20 个典型查询下的命中情况。
支持 --skill 参数测试 Skill 桥接效果。
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine.knowledge.wiki_index import WikiIndex
from engine.knowledge.wiki_retriever import WikiRetriever

TEST_CASES = [
    ("客户发了一个微笑表情，是不是在敷衍我", "reply", []),
    ("沟通时客户说你是不是对每个客户都这样", "reply", []),
    ("客户突然不回消息了怎么办", "reply", []),
    ("怎样用提问打开话题", "reply", []),
    ("客户说不需要我们产品怎么回应", "reply", []),
    ("第一次会面不知道怎么安排", "meet", []),
    ("会面时怎么自然地引导需求", "meet", []),
    ("客户说时间不够想结束", "meet", []),
    ("会面冷场了怎么办", "meet", []),
    ("怎么在会面结束时推进下一步", "meet", []),
    ("客户最近忽冷忽热怎么回事", "ask", []),
    ("怎么判断客户对我们产品有没有兴趣", "ask", []),
    ("客户说价格太高怎么办", "ask", []),
    ("不同客户的决策链有什么区别", "ask", []),
    ("需求分析到底怎么做", "ask", []),
    ("客户聊了两个月还没成交正常吗", "analyze", []),
    ("客户回复很慢但内容很长是什么信号", "analyze", []),
    ("客户愿意开会但拒绝报价", "analyze", []),
    ("客户说预算不够但表示还可以考虑", "analyze", []),
    ("客户主动咨询但从不推进签约", "analyze", []),
]

SKILL_TEST_CASES = [
    ("spin", "客户说不需要我们的产品怎么回应", "reply", ["spin"]),
    ("spin", "会面时怎么自然地引导需求", "meet", ["spin"]),
    ("meddic", "客户说价格太高怎么办", "ask", ["meddic"]),
    ("meeting-prep", "演示时客户中途离场怎么办", "meet", ["meeting-prep"]),
    ("meeting-prep", "客户说时间不够想结束", "meet", ["meeting-prep"]),
    ("negotiation-skill", "客户最近忽冷忽热怎么回事", "ask", ["negotiation-skill"]),
    ("negotiation-skill", "客户说预算不够但还可以谈", "analyze", ["negotiation-skill"]),
    ("value-selling", "客户说竞品更便宜怎么办", "ask", ["value-selling"]),
    ("value-selling", "客户对价格敏感怎么处理", "ask", ["value-selling"]),
    ("chat-skills", "客户突然不回消息了怎么办", "reply", ["chat-skills"]),
]

def run_tests(retriever, cases, label=""):
    if label:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
    for i, (query, task_type, skills) in enumerate(cases, 1):
        results = retriever.retrieve(
            query_text=query,
            task_type=task_type,
            skills=skills,
            top_k=5,
        )
        titles = [r.title for r in results]
        print(f"  {i:2d}. [{task_type}] {query}")
        if titles:
            print(f"     → {' | '.join(titles[:3])}")
        else:
            print(f"     → (无匹配)")

def main():
    parser = argparse.ArgumentParser(description="Wiki 质量验证")
    parser.add_argument("--skill", action="store_true", help="测试 Skill 桥接")
    args = parser.parse_args()

    index = WikiIndex()
    index.build()
    retriever = WikiRetriever(index)

    run_tests(retriever, TEST_CASES, "基础查询")
    if args.skill:
        run_tests(retriever, SKILL_TEST_CASES, "Skill 桥接")

if __name__ == "__main__":
    main()
