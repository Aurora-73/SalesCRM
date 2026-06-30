"""Skill 注册表 — 解析 skill 文件目录，提供搜索索引。

供 agent_brief 的 _search_skills 使用，通过 trigger 匹配找到相关 skill。
"""

from __future__ import annotations

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillMeta:
    """单个 Skill 的元数据。"""
    name: str                    # 目录名，如 "spin"
    display_name: str            # 中文名，从 frontmatter 或标题提取
    description: str             # description 或首段摘要
    path: Path                   # SKILL.md 绝对路径
    triggers: list[str]          # 触发关键词
    has_references: bool         # 是否有 references/ 目录
    reference_files: list[str]   # references/ 下的文件名列表
    char_count: int              # SKILL.md 字符数
    # --- 元数据增强 ---
    scope: list[str]             # 可用场景：analyze/reply/meet/ask，空 = 全部
    priority: str                # primary / auxiliary
    contraindications: list[str] # 不适用场景关键词
    skill_type: str              # framework / stage / chat / other


# 从 description 中提取中文关键词的正则
_CJK_WORD_RE = re.compile(r"[一-鿿]{2,6}")
# YAML frontmatter 边界
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# 首行 Markdown 标题
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


class SkillRegistry:
    """Skill 注册表，负责扫描、索引、搜索。"""

    def __init__(self, skills_dir: Path):
        self._skills_dir = skills_dir
        self._skills: dict[str, SkillMeta] = {}

    def scan(self) -> None:
        """扫描 skills/ 目录，解析每个子目录的 SKILL.md。"""
        if not self._skills_dir.is_dir():
            return

        for child in sorted(self._skills_dir.iterdir()):
            if not child.is_dir():
                continue
            # 跳过以 _ 开头的索引文件目录
            if child.name.startswith("_"):
                continue

            # 优先顶层 SKILL.md，其次 skill/SKILL.md（兼容 qingsheng 等嵌套结构）
            skill_md = child / "SKILL.md"
            dir_name = child.name
            if not skill_md.is_file():
                skill_md = child / "skill" / "SKILL.md"
            if not skill_md.is_file():
                # 兼容嵌套结构
                for sub in sorted(child.iterdir()):
                    if sub.is_dir() and not sub.name.startswith(("_", ".")):
                        candidate = sub / "SKILL.md"
                        if candidate.is_file():
                            skill_md = candidate
                            dir_name = sub.name
                            break
            if not skill_md.is_file():
                continue

            meta = self._parse_skill(dir_name, skill_md)
            if meta:
                self._skills[meta.name] = meta

            # 扫描 sub-skills/ 目录
            for sub_skills_dir in child.glob("sub-skills"):
                if not sub_skills_dir.is_dir():
                    continue
                for sub in sorted(sub_skills_dir.iterdir()):
                    if not sub.is_dir() or sub.name.startswith(("_", ".")):
                        continue
                    sub_md = sub / "SKILL.md"
                    if sub_md.is_file():
                        sub_meta = self._parse_skill(sub.name, sub_md)
                        if sub_meta and sub_meta.name not in self._skills:
                            self._skills[sub_meta.name] = sub_meta

    def get(self, name: str) -> SkillMeta | None:
        return self._skills.get(name)

    def search_by_triggers(self, text: str) -> list[tuple[str, float]]:
        """根据文本内容匹配相关 Skill。返回 [(name, relevance), ...] 按相关度降序。"""
        results: list[tuple[str, float]] = []
        text_lower = text.lower()

        for name, meta in self._skills.items():
            score = 0.0
            # 1. 触发词子串匹配（高权重）
            for trigger in meta.triggers:
                if trigger.lower() in text_lower:
                    score += 3.0
            # 2. 短关键词匹配（从 triggers + description 提取 2-4 字词）
            short_kws = self._extract_short_keywords(meta)
            for kw in short_kws:
                if kw in text:
                    score += 1.5
            # 3. display_name 子串匹配
            if meta.display_name.lower() in text_lower:
                score += 2.0

            if score > 0:
                results.append((name, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ------------------------------------------------------------------
    # 内部解析
    # ------------------------------------------------------------------

    def _parse_skill(self, dir_name: str, skill_md: Path) -> SkillMeta | None:
        """解析单个 SKILL.md 文件。"""
        try:
            text = skill_md.read_text(encoding="utf-8")
        except Exception:
            return None

        name = dir_name
        display_name = dir_name
        description = ""
        triggers: list[str] = []
        # 元数据增强字段
        scope: list[str] = []
        priority = "primary"
        contraindications: list[str] = []

        # 尝试解析 YAML frontmatter
        fm_match = _FRONTMATTER_RE.match(text)
        if fm_match:
            try:
                fm = yaml.safe_load(fm_match.group(1))
                if isinstance(fm, dict):
                    name = fm.get("name", dir_name)
                    display_name = name
                    description = fm.get("description", "")
                    triggers = self._extract_triggers_from_description(description)
                    # 从 frontmatter tags 字段提取触发词
                    tags = fm.get("tags", [])
                    if isinstance(tags, list):
                        for tag in tags:
                            if isinstance(tag, str) and len(tag) >= 2:
                                triggers.append(tag)
                    # 元数据增强字段（可选，向后兼容）
                    raw_scope = fm.get("scope", [])
                    if isinstance(raw_scope, list):
                        scope = [s for s in raw_scope if isinstance(s, str)]
                    raw_priority = fm.get("priority", "")
                    if raw_priority in ("primary", "auxiliary"):
                        priority = raw_priority
                    raw_contra = fm.get("contraindications", [])
                    if isinstance(raw_contra, list):
                        contraindications = [str(c) for c in raw_contra]
            except Exception:
                pass

        # 如果没有 frontmatter，从标题提取
        if not description:
            title_match = _TITLE_RE.search(text)
            if title_match:
                display_name = title_match.group(1).strip()
                after_title = text[title_match.end():]
                para_match = re.search(r"\n\n(.+?)(?:\n\n|\Z)", after_title, re.DOTALL)
                if para_match:
                    description = para_match.group(1).strip()[:200]

        # 从 display_name 提取中文关键词作为触发词
        name_words = _CJK_WORD_RE.findall(display_name)
        for w in name_words:
            if len(w) >= 2 and w not in triggers:
                triggers.append(w)

        # 从首段 description 提取更多关键词
        if description:
            desc_words = _CJK_WORD_RE.findall(description[:200])
            # 取较长的关键词（4+ 字），避免太泛的短词
            for w in desc_words:
                if len(w) >= 4 and w not in triggers:
                    triggers.append(w)

        # 检查 references 目录
        ref_dir = skill_md.parent / "references"
        ref_files: list[str] = []
        has_refs = ref_dir.is_dir()
        if has_refs:
            ref_files = [f.name for f in ref_dir.iterdir() if f.is_file()]

        # 推断 skill_type
        skill_type = _infer_skill_type(dir_name)

        return SkillMeta(
            name=name,
            display_name=display_name,
            description=description[:500],
            path=skill_md,
            triggers=triggers,
            has_references=has_refs,
            reference_files=ref_files,
            char_count=len(text),
            scope=scope,
            priority=priority,
            contraindications=contraindications,
            skill_type=skill_type,
        )

    @staticmethod
    def _extract_triggers_from_description(desc: str) -> list[str]:
        """从 description 中提取触发关键词。

        匹配规则：
        1. 「」包裹的短语
        2. / 分隔的中文关键词（如 "微信/聊天/不回我"）
        3. 显式触发词后面的词
        """
        triggers: list[str] = []

        # 「」包裹的短语
        for m in re.finditer(r"「([^」]+)」", desc):
            triggers.append(m.group(1))

        # 中文关键词用 / 分隔（在显式触发词说明中）
        for m in re.finditer(r"(?:触发词|triggers?|显式触发词|fires on)[：:s]*\s*(.+?)(?:\.|$)", desc, re.IGNORECASE):
            segment = m.group(1)
            for part in re.split(r"[/、,，]", segment):
                part = part.strip().strip("「」\"'()（）")
                if part and len(part) >= 2:
                    triggers.append(part)

        # 从括号内的关键词提取（如 "(微信/聊天/不回我/见面)" 或 "（微信/聊天/不回我/见面）"）
        for m in re.finditer(r"[（(]([^）)]+)[）)]", desc):
            inner = m.group(1)
            if "/" in inner:
                for part in inner.split("/"):
                    part = part.strip()
                    if part and len(part) >= 2:
                        triggers.append(part)

        # 去重保序，只保留包含中文的触发词
        seen: set[str] = set()
        unique: list[str] = []
        for t in triggers:
            # 过滤掉纯英文或过长的触发词
            if len(t) > 20:
                continue
            if not re.search(r"[一-鿿]", t):
                continue
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique

    @staticmethod
    def _extract_short_keywords(meta: SkillMeta) -> set[str]:
        """从 Skill 元数据提取 2-4 字短关键词，用于子串搜索。

        来源：triggers 中的短词、display_name 的中文片段、description 的分词。
        """
        kws: set[str] = set()

        # 1. triggers 中长度 <= 4 的直接用
        for t in meta.triggers:
            if 2 <= len(t) <= 4 and re.search(r"[一-鿿]", t):
                kws.add(t)

        # 2. display_name 中提取 2-3 字片段
        cjk_in_name = re.findall(r"[一-鿿]+", meta.display_name)
        for seg in cjk_in_name:
            for size in (2, 3):
                for i in range(len(seg) - size + 1):
                    kws.add(seg[i:i + size])

        # 3. description 前 200 字，按标点分词后提取 2-3 字片段
        desc = meta.description[:200]
        segments = re.split(r"[，。、；：！？\s,;.!?\n]+", desc)
        for seg in segments:
            cjk_parts = re.findall(r"[一-鿿]+", seg)
            for part in cjk_parts:
                for size in (2, 3):
                    for i in range(len(part) - size + 1):
                        sub = part[i:i + size]
                        # 过滤太泛的停用词
                        if sub not in ("我们", "他们", "这个", "那个", "什么", "怎么",
                                       "可以", "需要", "应该", "如果", "因为", "但是",
                                       "一个", "没有", "知道", "已经", "就是", "不是"):
                            kws.add(sub)

        return kws


def _infer_skill_type(dir_name: str) -> str:
    """从目录名推断 Skill 类型。

    返回值：
        framework  — 核心框架（spin, meddic, challenger-sale 等）
        stage      — 阶段技能（stage-1-lead, stage-2-contact 等）
        chat       — 聊天技能（chat-skills, chat-analyzer）
        meeting    — 会面技能（meeting-prep, demo-skill）
        negotiation — 谈判技能（negotiation-skill, pricing-skill）
        other      — 其余
    """
    name = dir_name.lower()
    # 核心框架优先匹配
    _FRAMEWORKS = {
        "spin", "meddic", "challenger-sale", "value-selling",
        "negotiation-framework", "objection-handling",
    }
    if name in _FRAMEWORKS:
        return "framework"
    if name.startswith("stage-1") or name.startswith("stage-2") or name.startswith("stage-3"):
        return "stage"
    if name.startswith("stage-4") or "meeting" in name or "demo" in name:
        return "meeting"
    if name.startswith("stage-5") or "negotiation" in name or "pricing" in name:
        return "negotiation"
    if "chat" in name:
        return "chat"
    return "other"
