"""
章节硬性规则校验器
============================
对章节正文做**程序化**校验，与 QualityEvaluatorAgent 的 LLM 主观打分互补。

校验项（全部为确定性算法，无 LLM 调用）：

1. **字数校验**       ：实际字数偏离目标字数超过阈值则 fail。
2. **禁用句式校验**   ：正文出现"第X章""第X节""本章说"等绝对禁止的句式。
3. **章尾钩子校验**   ：章尾是否具备有效悬念/情绪钩子（问号、叹号、省略号、
                          悬念引导词），否则读留存率会下滑。
4. **关键事件覆盖**   ：比较大纲里的关键事件关键词是否落到正文；用 LLM 归一化后的
                          "语义覆盖信号"作为辅助，程序侧基于命名实体（人名/地名/关键
                          短语）做兜底字符串匹配。
5. **出场人物校验**   ：`characters_present` 中列出的人物名是否真正在章内出现——
                          未出现则可能是人物忽然消失（一致性隐患）。

返回标准化 ``rule_issues`` 列表 + 统计 ``stats``。RevisionAgent 在修订时会
看到其中的 issues，作者的审阅也能据此定位问题。

设计要点
---------
- ``hard_issues``   ：必须修复的问题（会强制 ``pass=false``）
- ``soft_issues``   ：建议修复的问题（不直接卡流程，但会喂给修订 agent）
- 无任何第三方依赖 / 网络 / LLM 调用。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


# ----------------------------------------------------------------------
#  公共入口
# ----------------------------------------------------------------------

def check_chapter(content: str, context: dict) -> dict:
    """
    对单章进行全部硬性规则校验。

    参数
    ----------
    content : str
        纯正文（不含标题行）。
    context : dict
        {
          "chapter_index": int,
          "target_length": int,              # 目标字数
          "key_events": list[str],           # outline 中的关键事件
          "foreshadowing": list[str],        # outline 中的伏笔
          "cliffhanger": str,                # 章尾悬念设计
          "characters_present": list[str],   # 本应出场的角色名
          "characters_all": list[str],       # 全部角色名（来自 world_view）
          "consistency_rules": list[str],    # 全局一致性规则文本
          "world_rules": str,                # 世界规则摘要
        }
        字段均做容错处理，缺失不会崩。

    返回
    -------
    dict
        {
          "rule_pass": bool,
          "hard_issues": [rule_issue, ...],
          "soft_issues": [rule_issue, ...],
          "stats": {...}
        }
    """
    if not isinstance(content, str):
        content = str(content) if content else ""
    content = content.strip()

    hard: list[dict] = []
    soft: list[dict] = []

    # 单次统计
    stats: dict[str, Any] = {}

    # 1. 字数
    wc = _check_word_count(content, _as_int(context.get("target_length"), 3000))
    stats["word_count"] = wc
    hard.extend(wc.get("hard_issues", []))
    soft.extend(wc.get("soft_issues", []))

    # 2. 禁用句式（含中英混杂段落）
    fp = _check_forbidden_patterns(content)
    stats["forbidden"] = fp
    hard.extend(fp.get("hard_issues", []))
    soft.extend(fp.get("soft_issues", []))

    # 3. 章尾钩子
    ck = _check_cliffhanger(content, context.get("cliffhanger"))
    stats["cliffhanger"] = ck
    hard.extend(ck.get("hard_issues", []))
    soft.extend(ck.get("soft_issues", []))

    # 4. 关键事件覆盖
    ke = _check_key_events(content, context.get("key_events", []),
                           context.get("characters_all", []))
    stats["key_events"] = ke
    hard.extend(ke.get("hard_issues", []))
    soft.extend(ke.get("soft_issues", []))

    # 5. 出场人物校验
    cp = _check_characters(content, context.get("characters_present", []))
    stats["characters"] = cp
    hard.extend(cp.get("hard_issues", []))
    soft.extend(cp.get("soft_issues", []))

    rule_pass = not any(issue.get("severity") == "hard" for issue in hard)

    return {
        "rule_pass": rule_pass,
        "has_hard_issue": bool(hard),
        "has_soft_issue": bool(soft),
        "hard_issues": hard,
        "soft_issues": soft,
        "all_issues": hard + soft,
        "stats": stats,
    }


# ----------------------------------------------------------------------
#  1. 字数
# ----------------------------------------------------------------------

_HARD_RATIO = 0.30   # 偏离目标超 30% 直接 fail
_SOFT_RATIO = 0.15   # 偏离 15%~30% 标记为 soft

def _check_word_count(content: str, target: int) -> dict:
    actual = len(content)
    ratio = abs(actual - target) / target if target > 0 else 0.0
    hard, soft = [], []

    if ratio >= _HARD_RATIO:
        hard.append(_issue(
            type="word_count",
            severity="hard",
            description=(
                f"字数严重偏离目标：实际 {actual} 字 / 目标 {target} 字（偏离 {ratio:.0%}）。"
            ),
            location="全章",
            suggestion=(
                f"请调整正文长度，向 {target} 字靠拢（建议误差 ±15%）。"
            ),
        ))
    elif ratio >= _SOFT_RATIO:
        soft.append(_issue(
            type="word_count",
            severity="soft",
            description=(
                f"字数略偏离目标：实际 {actual} 字 / 目标 {target} 字（偏离 {ratio:.0%}）。"
            ),
            location="全章",
            suggestion=(
                f"可适当增减篇幅，理想区间 {int(target * 0.85)}–{int(target * 1.15)} 字。"
            ),
        ))

    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "actual": actual,
        "target": target,
        "ratio": round(ratio, 3),
        "pass": ratio < _HARD_RATIO,
    }


# ----------------------------------------------------------------------
#  2. 禁用句式（程序确定性）
# ----------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    # 标题式标记混入正文
    (re.compile(r"第\s*[零〇一二三四五六七八九十百千万\d]+\s*章"),          "正文混入章标题标记"),
    (re.compile(r"第\s*[零〇一二三四五六七八九十百千万\d]+\s*节"),          "正文混入节标题标记"),
    (re.compile(r"第\s*[零〇一二三四五六七八九十百千万\d]+\s*回"),          "正文混入回目标记"),
    (re.compile(r"第\s*[零〇一二三四五六七八九十百千万\d]+\s*卷"),          "正文混入卷标记"),
    # 元说明
    (re.compile(r"本章说"),                                                "正文混入'本章说'元说明"),
    (re.compile(r"本章字数[：:约]?约?\d+"),                                  "正文混入字数统计"),
    (re.compile(r"（本章未完[^）]*）"),                                     "正文混入未完续待标记"),
]
_FORBIDDEN_LITERAL = ["本章说", "未完待续", "（未完）"]


def _check_forbidden_patterns(content: str) -> dict:
    hard, soft = [], []
    found = []

    for pat, reason in _FORBIDDEN_PATTERNS:
        matches = pat.findall(content)
        if matches:
            sample = matches[0]
            if isinstance(sample, tuple):
                sample = "".join(sample)
            hard.append(_issue(
                type="forbidden_phrase",
                severity="hard",
                description=f"检测到禁用句式：{reason}（匹配「{truncate(sample, 20)}」）。",
                location=f"正文（首次出现位置约 {content.find(sample)} 字附近）",
                suggestion="删除此类标题式记录 / 元说明，正文只保留故事内容。",
            ))
            found.append(sample)

    # 英文段落检测：一段内拉丁字符占比明显异常（模型偶发夹杂）
    eng_paras = _find_english_paragraphs(content)
    for para_sample, ratio in eng_paras:
        soft.append(_issue(
            type="forbidden_phrase",
            severity="soft",
            description=(
                f"检测到疑似英文段落（拉丁字符占比约 {ratio:.0%}）：「{truncate(para_sample, 40)}」。"
            ),
            location="正文段落",
            suggestion="请将该段落翻译为中文，避免中英混杂。",
        ))
        found.append(para_sample)

    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "found": found,
        "pass": not hard,
    }


_LATIN_RUN_RE = re.compile(r"[A-Za-z][A-Za-z\s,.'\"\\-]{4,}")

def _find_english_paragraphs(content: str, min_latin_ratio: float = 0.45) -> list[tuple[str, float]]:
    """返回拉丁字符比例 >= 阈值 的段落。"""
    hits: list[tuple[str, float]] = []
    paragraphs = re.split(r"\n\s*\n|\n|。(?=[一-龥『「\"'])", content)
    for para in paragraphs:
        para = para.strip()
        if len(para) < 10:
            continue
        latin_chars = sum(1 for ch in para if _is_latin(ch))
        ratio = latin_chars / len(para)
        if ratio >= min_latin_ratio and latin_chars >= 8:
            hits.append((para, ratio))
    return hits[:3]


def _is_latin(ch: str) -> bool:
    return "a" <= ch.lower() <= "z"


# ----------------------------------------------------------------------
#  3. 章尾钩子
# ----------------------------------------------------------------------

# 常见"钩子起始"词——出现在章尾 120 字以内可认定存在悬念引导
_HOOK_OPENERS = (
    "突然", "就在这时", "就在这时，", "下一秒，", "没想到",
    "却不知", "谁也没想到", "话音未落", "然而就在这时",
    "正在此时", "猛然", "蓦地", "便在此时", "岂料",
    "谁知道", "谁能想到", "可谁也没", "谁都没有",
)
_HOOK_END_PUNCT = ("？", "！", "……", "...")


def _check_cliffhanger(content: str, cliffhanger_design: str | None) -> dict:
    hard, soft = [], []
    if not content:
        return {"hard_issues": hard, "soft_issues": soft, "pass": True,
                "last_200_chars": "", "hook_detected": False}

    last = content[-200:]
    last_trimmed = last.rstrip()
    last_char = last_trimmed[-1] if last_trimmed else ""

    ends_with_hook_punct = last_char in _HOOK_END_PUNCT
    has_opener = any(op in last for op in _HOOK_OPENERS)

    hook_detected = ends_with_hook_punct or has_opener
    reason_parts: list[str] = []
    if ends_with_hook_punct:
        reason_parts.append(f"句尾为「{last_char}」")
    if has_opener:
        found = next(op for op in _HOOK_OPENERS if op in last)
        reason_parts.append(f"句尾出现悬念引导词「{found}」")

    if not hook_detected:
        # 纯叙述硬结尾 → 标记为 soft（多数铺垫章允许，不强卡）
        soft.append(_issue(
            type="cliffhanger",
            severity="soft",
            description=(
                f"章尾未检测到悬念钩子：截尾「{truncate(last_trimmed, 60)}」"
                f"以普通叙述结尾，留存率可能受损。"
            ),
            location="章尾（末 200 字）",
            suggestion=(
                "在章末加入悬念引导词 / 疑问 / 情绪爆点，"
                "或使用省略号、感叹号、反问句制造未完感。"
            ),
        ))
    elif not ends_with_hook_punct and has_opener:
        # 有引导词但落在段落中间、整段仍以句号收尾 → 提醒
        soft.append(_issue(
            type="cliffhanger",
            severity="soft",
            description=(
                f"章尾存在悬念引导词（{truncate(last_trimmed, 60)}），但整体仍以句号结尾，"
                f"钩子力道可能不足。"
            ),
            location="章尾",
            suggestion="让引导词落在段落收尾，或与问/叹号配合使用。",
        ))

    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "last_200_chars": last,
        "hook_detected": hook_detected,
        "pass": True,   # 钩子不会强卡；强卡留给 key_events / forbidden
    }


# ----------------------------------------------------------------------
#  4. 关键事件覆盖
# ----------------------------------------------------------------------

# 去除中文停用词后保留"内容词"骨架
_STOPWORDS = set(
    "的了吗呢啊哦嗯在是就不也这那有和与但被把让给要到从对向为将就又都而"
    "但其很最更太非常已经正在时候之后之前里中上下内外出进入出现于之"
)


def _check_key_events(content: str, key_events: list[str],
                      all_characters: list[str]) -> dict:
    hard, soft = [], []
    if not key_events:
        return {"hard_issues": hard, "soft_issues": soft,
                "total": 0, "covered": 0, "missing": [], "pass": True}

    covered, missing = [], []
    for evt in key_events:
        evt = (evt or "").strip()
        if not evt:
            continue
        if _event_covered(evt, content, all_characters):
            covered.append(evt)
        else:
            missing.append(evt)

    for m in missing:
        soft.append(_issue(
            type="key_event_missing",
            severity="soft",
            description=f"疑似遗漏关键事件：「{truncate(m, 40)}」。",
            location="全章",
            suggestion=(
                "补写该事件至少一处具体呈现（可以是一句对话、一个动作或一处描写），"
                "不要仅用概括性叙述带过。"
            ),
        ))

    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "total": len(key_events),
        "covered": len(covered),
        "missing": missing,
        "covered_items": covered,
        "pass": not missing,
    }


def _event_covered(evt: str, content: str, all_characters: list[str]) -> bool:
    """判定关键事件是否在正文里有语义锚点出现。

    策略（低成本、无模型）：
      1) 提取事件里的命名实体（人物名），只要该人名/别名出现在章内即视为锚定；
      2) 否则提取事件里 >=2 字的"内容词"（去掉停用词后的连续汉字段），
         只要其中一节命中正文即视为锚定。
    """
    # 1) 人名命中
    for name in all_characters:
        if name and len(name) >= 2 and name in evt and name in content:
            return True

    # 2) 内容词命中：拆成 2-gram / 短语
    segments = re.findall(r"[一-龥]{2,}", evt)
    content_len = len(content)
    # 先尝试完整片段
    for seg in segments:
        if len(seg) >= 3 and seg in content:
            return True
    # 再尝试去停用词后的"内容词"
    for seg in segments:
        stripped = _strip_stopwords(seg)
        if len(stripped) >= 2 and stripped in content:
            return True
    return False


def _strip_stopwords(s: str) -> str:
    return "".join(ch for ch in s if ch not in _STOPWORDS)


# ----------------------------------------------------------------------
#  5. 出场人物校验
# ----------------------------------------------------------------------

def _check_characters(content: str, chars_present: list[str]) -> dict:
    hard, soft = [], []
    if not chars_present:
        return {"hard_issues": hard, "soft_issues": soft,
                "expected": [], "missing": [], "pass": True}

    missing = []
    for name in chars_present:
        name = (name or "").strip()
        if not name or len(name) < 2:
            continue
        if name not in content:
            missing.append(name)

    for m in missing:
        soft.append(_issue(
            type="character_missing",
            severity="soft",
            description=f"标注为「出场」的角色「{truncate(m, 20)}」未在正文中出现。",
            location="全章",
            suggestion=(
                "请确认该角色是否应在本次章节登场；若确实出场，"
                "修改其出场段落的人名（不要用昵称/代称替代）。"
            ),
        ))

    return {
        "hard_issues": hard,
        "soft_issues": soft,
        "expected": chars_present,
        "missing": missing,
        "pass": not missing,
    }


# ----------------------------------------------------------------------
#  工具函数
# ----------------------------------------------------------------------

def _issue(type: str, severity: str, description: str,
           location: str, suggestion: str) -> dict:
    """构造一个标准化的 rule_issue。"""
    return {
        "type": type,
        "severity": severity,            # "hard" | "soft"
        "source": "rule_checker",        # 与 LLM 评估 issues 区分
        "description": description,
        "location": location,
        "suggestion": suggestion,
    }


def truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default