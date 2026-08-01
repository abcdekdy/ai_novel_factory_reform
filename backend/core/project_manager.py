"""
项目管理 - 保存/加载/历史记录
每个项目保存为独立目录，包含config、世界观、各章节等
"""

import json
import re
import time
from pathlib import Path

# 项目根目录
PROJECTS_DIR = Path(__file__).parent.parent / "projects"


def ensure_projects_dir():
    """确保项目目录存在"""
    PROJECTS_DIR.mkdir(exist_ok=True)


def create_project(name: str) -> Path:
    """
    创建新项目目录
    返回项目目录路径
    """
    ensure_projects_dir()
    # 用时间戳保证唯一性
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = PROJECTS_DIR / f"{safe_name}_{timestamp}"
    project_dir.mkdir(exist_ok=True)
    return project_dir


def save_world_view(project_dir: Path, world_view: dict):
    """保存世界观设定"""
    path = project_dir / "world_view.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(world_view, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------
#  时间线快照辅助（G2 内部）
# ----------------------------------------------------------------------
def _char_key(name: str) -> str:
    """归一化角色名用于模糊匹配：去空白 + 小写。"""
    if not name:
        return ""
    return re.sub(r"\s+", "", name).lower()


def _canon_name(name: str, known: dict) -> str:
    """把输入名（可能带错别字/别名）映射到 known 里的标准名。"""
    key = _char_key(name)
    if not key:
        return name or ""
    # 完全匹配
    if key in known:
        return known[key]
    # 子串匹配
    for k, v in known.items():
        if key in k or k in key:
            return v
    # 没匹配到：作为新标准名加入并返回
    known[key] = name
    return name


def _extract_first_paragraphs(content: str, n: int = 2) -> str:
    """取正文前 n 段的首句作为摘要 fallback。"""
    if not content:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    first_n = paragraphs[:n]
    snippet = " / ".join(p[:80] for p in first_n)
    return snippet[:300]


def _looks_resolved(state_text: str) -> bool:
    """粗判一个状态描述是否暗示'已完结/死亡/下线'。"""
    if not state_text:
        return False
    markers = ("死亡", "陨落", "逝世", "失踪", "归隐", "飞升", "圆满",
               "消散", "身亡", "退场", "离世", "陨落于")
    return any(m in state_text for m in markers)


def save_timeline_snapshot(project_dir, snapshot: dict) -> Path:
    """把时间线快照落到 <project_dir>/timeline_snapshot.json。"""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "timeline_snapshot.json"
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return path


def load_timeline_snapshot(project_dir) -> dict:
    """加载已落盘的时间线快照。不存在则返回空。"""
    path = Path(project_dir) / "timeline_snapshot.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def load_world_view(project_dir) -> dict:
    """加载世界观设定 (project_dir 支持 str 或 Path)"""
    path = Path(project_dir) / "world_view.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_chapter(project_dir: Path, chapter_index: int, chapter_data: dict):
    """保存单个章节"""
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)

    # 保存完整数据（JSON，含评估信息等）
    meta_path = chapters_dir / f"chapter_{chapter_index:03d}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(chapter_data, f, ensure_ascii=False, indent=2)

    # 单独保存正文（方便阅读和导出）
    content = chapter_data.get("content", "")
    text_path = chapters_dir / f"chapter_{chapter_index:03d}.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        title = chapter_data.get("title", f"第{chapter_index}章")
        f.write(f"# {title}\n\n{content}")


def load_chapter(project_dir, chapter_index: int) -> dict:
    """加载单个章节元数据 (project_dir 支持 str 或 Path)"""
    meta_path = Path(project_dir) / "chapters" / f"chapter_{chapter_index:03d}_meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_all_chapters(project_dir) -> list:
    """加载所有章节 (project_dir 支持 str 或 Path)"""
    chapters_dir = Path(project_dir) / "chapters"
    if not chapters_dir.exists():
        return []

    chapters = []
    meta_files = sorted(chapters_dir.glob("chapter_*_meta.json"))
    for meta_file in meta_files:
        with open(meta_file, "r", encoding="utf-8") as f:
            chapters.append(json.load(f))
    return chapters


def load_all_chapters_map(project_dir) -> dict:
    """加载已完成章节，返回 {chapter_index: chapter_data} (project_dir 支持 str 或 Path)"""
    chapters_dir = Path(project_dir) / "chapters"
    result = {}
    if not chapters_dir.exists():
        return result
    for meta_file in sorted(chapters_dir.glob("chapter_*_meta.json")):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            idx = data.get("chapter_index") or data.get("chapter")
            if idx is not None:
                result[int(idx)] = data
        except Exception:
            continue
    return result


def load_outline(project_dir) -> dict:
    """加载详细大纲 (outline.json) — project_dir 支持 str 或 Path"""
    path = Path(project_dir) / "outline.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_project_summary(project_dir) -> dict:
    """加载项目摘要 — project_dir 支持 str 或 Path"""
    path = Path(project_dir) / "summary.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_project_summary(project_dir, summary: dict):
    """保存项目摘要（含灵感、状态、统计等） — project_dir 支持 str 或 Path"""
    project_dir = Path(project_dir)
    path = project_dir / "summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def fix_project_status(project_dir) -> str:
    """根据实际进度修正项目状态。返回修正后的状态。

    场景：用户在所有章节完成后点击"暂停"，导致 summary.json 中 status=paused
    但实际项目已完成。此函数检测这类不一致并修正。
    """
    project_dir = Path(project_dir)
    summary = load_project_summary(project_dir)

    chapters = load_all_chapters(project_dir)
    total_chapters = len(chapters)
    expected = summary.get("chapters_count") or summary.get("chapter_count", 0)

    # 已有章节 >= 预期章节，且预期 > 0 → 项目实际已完成
    if expected > 0 and total_chapters >= expected and summary.get("status") == "paused":
        summary["status"] = "completed"
        summary.pop("paused_stage", None)
        summary["completed_at"] = summary.get(
            "completed_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        save_project_summary(project_dir, summary)
        return "completed"

    return summary.get("status", "generating")


def export_to_txt(project_dir, output_path: str) -> bool:
    """导出完整小说为单个txt文件 (project_dir 支持 str 或 Path)"""
    world_view = load_world_view(project_dir)
    chapters = load_all_chapters(project_dir)

    if not chapters:
        return False

    with open(output_path, "w", encoding="utf-8") as f:
        # 标题
        title = world_view.get("title", "未命名小说")
        f.write(f"《{title}》\n")
        f.write("=" * 60 + "\n\n")

        # 世界观简介
        if world_view.get("summary"):
            f.write("【世界观简介】\n")
            f.write(world_view["summary"] + "\n\n")

        # 各章节
        for ch in chapters:
            ch_title = ch.get("title", "")
            ch_content = ch.get("content", "")
            f.write(f"\n{'=' * 60}\n")
            f.write(f"  {ch_title}\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(ch_content + "\n")

    return True


def export_to_markdown(project_dir, output_path: str) -> bool:
    """导出完整小说为Markdown文件 (project_dir 支持 str 或 Path)"""
    world_view = load_world_view(project_dir)
    chapters = load_all_chapters(project_dir)

    if not chapters:
        return False

    with open(output_path, "w", encoding="utf-8") as f:
        title = world_view.get("title", "未命名小说")
        f.write(f"# 《{title}》\n\n")

        if world_view.get("summary"):
            f.write("## 世界观简介\n\n")
            f.write(world_view["summary"] + "\n\n")

        if world_view.get("characters"):
            f.write("## 主要角色\n\n")
            for char in world_view.get("characters", []):
                f.write(f"- **{char.get('name', '')}**：{char.get('desc', '')}\n")
            f.write("\n")

        f.write("---\n\n")
        for ch in chapters:
            ch_title = ch.get("title", "")
            ch_content = ch.get("content", "")
            f.write(f"## {ch_title}\n\n")
            f.write(ch_content + "\n\n")
            f.write("---\n\n")

    return True


def list_projects() -> list:
    """列出所有项目。加载时自动修正过时的 paused 状态。"""
    ensure_projects_dir()
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir(), reverse=True):
        if d.is_dir():
            summary_file = d / "summary.json"
            summary = {}
            if summary_file.exists():
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                # 自动修正：所有章节已生成但状态为 paused → 改为 completed
                actual_chapters = len(load_all_chapters(d))
                expected = summary.get("chapters_count") or summary.get("chapter_count", 0)
                if (expected > 0 and actual_chapters >= expected
                        and summary.get("status") == "paused"):
                    summary["status"] = "completed"
                    summary.pop("paused_stage", None)
                    save_project_summary(d, summary)
            # 如果 summary 为空，尝试从目录内容推断基本信息
            if not summary:
                chapters = load_all_chapters(d)
                wv = load_world_view(d)
                summary = {
                    "title": wv.get("title", ""),
                    "chapter_count": len(chapters),
                    "status": "generating",
                }
            projects.append({
                "name": d.name,
                "path": str(d),
                "summary": summary
            })
    return projects


# ----------------------------------------------------------------------
#  续写 / 批次支持
# ----------------------------------------------------------------------
def save_batch_outline(project_dir, batch_number: int, outline: dict):
    """保存某个批次的续写大纲为 outline_batch_N.json（不覆盖旧批次）。"""
    path = Path(project_dir) / f"outline_batch_{batch_number}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(outline, f, ensure_ascii=False, indent=2)


def load_batch_outline(project_dir, batch_number: int) -> dict:
    """加载某个批次的续写大纲。"""
    path = Path(project_dir) / f"outline_batch_{batch_number}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_latest_batch_outline(project_dir) -> dict:
    """加载最新批次的续写大纲（按文件修改时间）。返回 outline_dict 而非 (batch_number, outline_dict)。"""
    batches = list_batch_outlines(project_dir)
    return batches[-1][1] if batches else {}


def list_batch_outlines(project_dir) -> list:
    """列出所有批次大纲，按批次号排序。返回 [(batch_number, outline_dict)]。"""
    project_dir = Path(project_dir)
    result = []
    for f in sorted(project_dir.glob("outline_batch_*.json")):
        try:
            batch_number = int(f.stem.replace("outline_batch_", ""))
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            result.append((batch_number, data))
        except Exception:
            continue
    return result


def get_next_batch_number(project_dir) -> int:
    """返回下一个批次号（已有批次最大值 + 1；无批次则返回 1）。"""
    batches = list_batch_outlines(project_dir)
    if not batches:
        return 1
    return max(b[0] for b in batches) + 1


def update_project_batches(project_dir, batch_info: dict):
    """往 summary.json 的 batches[] 里追加一条批次记录。"""
    summary = load_project_summary(project_dir)
    batches = summary.get("batches", [])
    if not isinstance(batches, list):
        batches = []
    batches.append(batch_info)
    summary["batches"] = batches
    # 同步更新总章数与总字数
    summary["chapters_count"] = summary.get("chapters_count", 0) + batch_info.get("chapter_count", 0)
    save_project_summary(project_dir, summary)


def load_legacy_package(project_dir, recent_n: int = 3) -> dict:
    """
    一次性拼接完整遗产包，供续写大纲 Agent 使用。

    返回: {
        "world_view": dict,                 # 世界观本体（原样）
        "existing_chapters_count": int,      # 已完成章节数
        "recent_chapters": list,            # 最近 N 章的 {chapter_index, title, summary, cliffhanger}
        "character_current_states": dict,   # {角色名: 当前状态描述}
        "unresolved_foreshadowing": list,   # 未回收伏笔 [{chapter_index, foreshadowing}]
        "existing_rules": list,             # 已有 consistency_rules
        "existing_arcs": dict,              # 已有 character_arcs
        "previous_batches": list,           # 历史批次元信息 [{batch_number, guidance, chapter_range}]
    }
    """
    world_view = load_world_view(project_dir)
    all_chapters = load_all_chapters(project_dir)
    summary = load_project_summary(project_dir)

    # 按章节号排序
    all_chapters.sort(key=lambda c: c.get("chapter_index", c.get("chapter", 0)))

    # 最近 N 章的 summary + cliffhanger
    recent = []
    for ch in all_chapters[-recent_n:]:
        recent.append({
            "chapter_index": ch.get("chapter_index"),
            "title": ch.get("title", ""),
            "summary": ch.get("summary", ch.get("plot_detail", "")),
            "cliffhanger": ch.get("cliffhanger", ""),
        })

    # 角色当前状态：从最新批次大纲（或原始 outline.json）的 character_arcs 里取最后一次 state
    character_current_states = {}
    existing_arcs = {}
    existing_rules = []

    latest_outline = load_latest_batch_outline(project_dir)
    if not latest_outline:
        latest_outline = load_outline(project_dir)

    if latest_outline:
        existing_arcs = latest_outline.get("character_arcs", {})
        existing_rules = latest_outline.get("consistency_rules", [])
        for name, arc in existing_arcs.items():
            traj = arc.get("trajectory", [])
            if traj:
                # 取最后一个轨迹点作为当前状态
                character_current_states[name] = traj[-1].get("state", "")
            else:
                character_current_states[name] = ""

    # 未回收伏笔：从所有批次大纲 + 原始 outline 里收集 foreshadowing
    # 简化处理：把所有章节的 foreshadowing 都视为"待回收"，由 LLM 决定哪些已回收
    unresolved_foreshadowing = []
    all_outlines = [load_outline(project_dir)] + [b[1] for b in list_batch_outlines(project_dir)]
    seen_chapters = set()
    for ol in all_outlines:
        if not ol:
            continue
        for ch in ol.get("chapters", []):
            idx = ch.get("chapter_index")
            if idx in seen_chapters:
                continue
            seen_chapters.add(idx)
            for fs in ch.get("foreshadowing", []):
                unresolved_foreshadowing.append({
                    "from_chapter": idx,
                    "foreshadowing": fs,
                })

    # 历史批次元信息
    previous_batches = []
    raw_batches = summary.get("batches", [])
    if isinstance(raw_batches, list):
        for b in raw_batches:
            previous_batches.append({
                "batch_number": b.get("batch_number"),
                "guidance": b.get("guidance", ""),
                "chapter_range": b.get("chapter_range", ""),
                "created_at": b.get("created_at", ""),
            })

    # 时间线快照（续写时减少"读完整本前文"的必要）
    timeline_snapshot = build_timeline_snapshot(project_dir)

    return {
        "world_view": world_view,
        "existing_chapters_count": len(all_chapters),
        "recent_chapters": recent,
        "character_current_states": character_current_states,
        "unresolved_foreshadowing": unresolved_foreshadowing,
        "existing_rules": existing_rules,
        "existing_arcs": existing_arcs,
        "previous_batches": previous_batches,
        # ---- G2: 时间线快照 ----
        "timeline_snapshot": timeline_snapshot,
    }


# ----------------------------------------------------------------------
#  时间线快照（G2）
# ----------------------------------------------------------------------
def build_timeline_snapshot(project_dir) -> dict:
    """
    拼接结构化的"当前状态快照"，供续写时减少对长前文的依赖。

    返回:
    {
      "generated_at": str,
      "total_chapters": int,
      "timeline": [{"chapter", "title", "key_events", "characters_involved", "plot_summary"}],
      "character_states": {name: {"status", "first_appearance", "last_appearance",
                                   "latest_state", "appearance_chapters": [...]}},
      "unresolved_threads": [{"type", "from_chapter", "detail"}],
    }

    此函数尽可能容忍缺失字段；任何异常都返回最小可用结构而非 raise。
    """
    project_dir = Path(project_dir)
    from typing import List, Dict, Any
    empty = {
        "generated_at": "", "total_chapters": 0,
        "timeline": [], "character_states": {}, "unresolved_threads": [],
    }
    try:
        world_view = load_world_view(project_dir)
        all_chapters = load_all_chapters(project_dir)
        all_chapters.sort(
            key=lambda c: c.get("chapter_index", c.get("chapter", 0)))
        generated_at = time.strftime("%Y-%m-%d %H:%M:%S")

        # ---- 主线时间线 ----
        timeline: List[Dict[str, Any]] = []
        character_states: Dict[str, Dict[str, Any]] = {}
        unresolved_threads: List[Dict[str, Any]] = []

        # 初始角色来自 world_view
        char_keys: Dict[str, str] = {}   # 小写/别名 -> 标准名
        for ch_view in (world_view.get("characters") or []):
            name = (ch_view.get("name") or "").strip()
            if not name:
                continue
            key = _char_key(name)
            char_keys[key] = name
            character_states[name] = {
                "status": "Alive",
                "first_appearance": None,
                "last_appearance": None,
                "latest_state": ch_view.get("desc", ""),
                "appearance_chapters": [],
            }

        # 通过每章详情建立角色出场记录 + 关键事件
        all_chapter_meta: List[Dict[str, Any]] = []
        chapters_dir = project_dir / "chapters"
        if chapters_dir.exists():
            meta_files = sorted(chapters_dir.glob("chapter_*_meta.json"))
        else:
            meta_files = []
        for meta_file in meta_files:
            try:
                with open(meta_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                all_chapter_meta.append(data)
            except Exception:
                continue
        all_chapter_meta.sort(
            key=lambda c: c.get("chapter_index", c.get("chapter", 0)))

        # 从 meta 的 summary 字段里抽取正文摘要（meta 保存时带去重）
        for meta in all_chapter_meta:
            idx = meta.get("chapter_index", meta.get("chapter"))
            title = meta.get("title", "")
            summary = (meta.get("summary")
                       or meta.get("plot_detail")
                       or _extract_first_paragraphs(
                               meta.get("content", ""), 2))
            events = meta.get("key_events") or []
            chars_present = meta.get("characters_present") or []
            cliffhanger = meta.get("cliffhanger") or ""

            # 从内容里抽取简易事件 tag（若无显式 key_events）
            timeline_events = list(events) if events else []
            # 角色出场
            involved: List[str] = []
            seen: set = set()
            for cp in (chars_present or []):
                cname = (cp or "").strip()
                if not cname:
                    continue
                canon = _canon_name(cname, char_keys)
                if canon and canon not in seen:
                    seen.add(canon)
                    involved.append(canon)

            timeline.append({
                "chapter": idx,
                "title": title,
                "key_events": timeline_events,
                "characters_involved": involved,
                "cliffhanger": cliffhanger,
                "plot_summary": (summary or "")[:200],
            })

            # 更新角色状态：最近出场 + 状态标签
            for canon_name in involved:
                if canon_name not in character_states:
                    character_states[canon_name] = {
                        "status": "Alive",
                        "first_appearance": idx,
                        "last_appearance": idx,
                        "latest_state": "",
                        "appearance_chapters": [],
                    }
                st = character_states[canon_name]
                st["last_appearance"] = idx
                if st["first_appearance"] is None:
                    st["first_appearance"] = idx
                if isinstance(idx, int):
                    st["appearance_chapters"].append(idx)

        # ---- 角色状态解析：从 character_arcs 取最新状态 ----
        latest_outline = load_latest_batch_outline(project_dir) or {}
        if not latest_outline:
            latest_outline = load_outline(project_dir) or {}
        arcs = latest_outline.get("character_arcs") or {}
        for name, arc in arcs.items():
            canon = _canon_name(name, char_keys) or name
            traj = arc.get("trajectory") or []
            if canon not in character_states:
                character_states[canon] = {
                    "status": "Alive",
                    "first_appearance": None,
                    "last_appearance": None,
                    "latest_state": "",
                    "appearance_chapters": [],
                }
            if traj:
                character_states[canon]["latest_state"] = traj[-1].get("state", "")

        # ---- 未完结伏笔 ----
        all_outlines: List[dict] = []
        base_ol = load_outline(project_dir)
        if base_ol:
            all_outlines.append(base_ol)
        for _, bol in list_batch_outlines(project_dir):
            all_outlines.append(bol)

        seen_fs: set = set()
        for ol in all_outlines:
            if not ol or not isinstance(ol, dict):
                continue
            for ch in (ol.get("chapters") or []):
                idx = ch.get("chapter_index")
                for fs in (ch.get("foreshadowing") or []):
                    fs_text = (fs or "").strip()
                    if not fs_text:
                        continue
                    fsid = f"{idx}:{fs_text}"
                    if fsid in seen_fs:
                        continue
                    seen_fs.add(fsid)
                    unresolved_threads.append({
                        "type": "foreshadowing",
                        "from_chapter": idx,
                        "detail": fs_text,
                    })

        # 闭合的人物弧标记为 resolved；未闭合的加入 unresolved
        for name, arc in arcs.items():
            canon = _canon_name(name, char_keys) or name
            arc_type = arc.get("arc_type", "")
            traj = arc.get("trajectory") or []
            # 如果 traj 最后一个 state 明显是终态就不加入 unresolved
            if traj:
                last = traj[-1].get("state", "")
                if not _looks_resolved(last):
                    unresolved_threads.append({
                        "type": "character_arc",
                        "from_chapter": traj[-1].get("chapter"),
                        "detail": f"角色「{canon}」（{arc_type}）轨迹最后状态：{last}",
                    })

        # 序列化 appearance_chapters 时去重
        for st in character_states.values():
            if st.get("appearance_chapters"):
                st["appearance_chapters"] = sorted(
                    set(st["appearance_chapters"]))

        return {
            "generated_at": generated_at,
            "total_chapters": len(all_chapters),
            "timeline": timeline,
            "character_states": character_states,
            "unresolved_threads": unresolved_threads,
        }

    except Exception as e:
        # 绝不因 snapshot 失败影响主流程
        empty["_error"] = str(e)
        return empty
