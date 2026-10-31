"""后端自检（标准库 unittest，无需 pytest）

运行：
    cd backend && python selftest.py

覆盖的是"曾经真实踩过、且容易复发"的逻辑：章节 worker 计数、续写键位与
统计、失败章节的处理、适配稿落盘、配置校验、项目库返回结构等。
外部 LLM 与网络调用一律用假实现替换，不发真实请求。
"""

import asyncio
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import core.config as core_config
import core.pipeline as pipeline_mod
import core.project_manager as pm
from core import rule_checker
from core.config import DEFAULT_CONFIG
from core.llm_client import LLMClient


# ----------------------------------------------------------------------
#  测试替身
# ----------------------------------------------------------------------
class _NullSignal:
    def connect(self, callback):
        return callback

    def emit(self, *args, **kwargs):
        pass


class FakeChapterAgent:
    """假章节生成 Agent：记录入参并立即返回一章正文。"""

    inputs: list = []

    def __init__(self, llm_client=None, agent_id: int = 0, persona=None):
        self.log_signal = _NullSignal()
        self.progress_signal = _NullSignal()
        self.status_signal = _NullSignal()
        self.finished_signal = _NullSignal()
        self.agent_id = agent_id

    def run(self, input_data):
        type(self).inputs.append(dict(input_data))
        index = input_data.get("chapter_index")
        return {
            "chapter_index": index,
            "title": f"第{index}章",
            "content": f"第{index}章正文" * 40,
            "summary": f"第{index}章摘要",
            "word_count": 200,
            "status": "draft",
        }


class FakeEvaluatorAgent:
    calls: list = []

    def __init__(self, llm_client=None):
        self.log_signal = _NullSignal()
        self.progress_signal = _NullSignal()
        self.status_signal = _NullSignal()
        self.finished_signal = _NullSignal()

    def run(self, input_data):
        type(self).calls.append(input_data.get("chapter_index"))
        return {
            "chapter_index": input_data.get("chapter_index"),
            "overall_score": 8.0,
            "pass": True,
            "needs_revision": False,
            "issues": [],
            "rule_issues": [],
            "rule_hard_count": 0,
            "highlights": [],
        }


class FakeAdapterAgent:
    calls: list = []

    def __init__(self, llm_client=None):
        self.log_signal = _NullSignal()
        self.progress_signal = _NullSignal()
        self.status_signal = _NullSignal()
        self.finished_signal = _NullSignal()

    def run(self, input_data):
        index = input_data.get("chapter_index")
        type(self).calls.append(index)
        return {
            "chapter_index": index,
            "platform": input_data.get("platform"),
            "original_title": input_data.get("title"),
            "formatted_content": f"适配后的第{index}章正文",
            "formatting_notes": ["测试"],
        }


def make_pipeline() -> pipeline_mod.NovelPipeline:
    pl = pipeline_mod.NovelPipeline()
    pl.llm = object()          # 只为通过 "llm 是否已初始化" 的检查
    pl.project_dir = None
    return pl


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def write_chapters(project_dir: Path, indices) -> None:
    for index in indices:
        pm.save_chapter(project_dir, index, {
            "chapter_index": index,
            "title": f"旧第{index}章",
            "content": f"旧第{index}章正文" * 20,
            "summary": f"旧第{index}章摘要",
            "word_count": 200,
            "status": "draft",
        })


# ----------------------------------------------------------------------
#  1. 章节 worker 计数
# ----------------------------------------------------------------------
class ChapterWorkerCountTest(unittest.TestCase):
    def setUp(self):
        FakeChapterAgent.inputs = []
        self._patch = mock.patch.object(
            pipeline_mod, "ChapterGeneratorAgent", FakeChapterAgent)
        self._patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._patch.stop)

    def _generate(self, coarse_count: int, requested: int):
        pl = make_pipeline()
        pl.world_view = {"title": "t", "chapter_outline": [
            {"chapter_index": i + 1, "title": f"第{i + 1}章", "summary": f"概要{i + 1}"}
            for i in range(coarse_count)
        ]}
        pl.outline = {"chapters": [
            {"chapter_index": i + 1, "title": f"第{i + 1}章",
             "plot_detail": f"细纲{i + 1}" * 10}
            for i in range(coarse_count)
        ], "character_arcs": {}}
        pl._chapter_count = requested
        pl._chapter_length = 3000
        finalized = []
        pl._on_all_chapters_complete = lambda: finalized.append(1)
        pl._generate_chapters(3000)
        done = wait_until(lambda: pl._pending_chapter_workers == 0)
        time.sleep(0.1)
        return pl, finalized, done

    def test_outline_shorter_than_requested_does_not_hang(self):
        pl, finalized, done = self._generate(coarse_count=3, requested=5)
        self.assertTrue(done, "worker 计数没有归零，流水线会卡在章节生成阶段")
        self.assertEqual(finalized, [1])
        self.assertEqual(pl._chapter_count, 3)
        self.assertEqual(len(pl.chapters), 3)
        self.assertEqual([c["chapter_index"] for c in pl.chapters], [1, 2, 3])

    def test_outline_longer_than_requested_finalizes_once(self):
        pl, finalized, done = self._generate(coarse_count=6, requested=4)
        self.assertTrue(done)
        self.assertEqual(finalized, [1], "收尾被重复触发，会重复评估/适配")
        self.assertEqual(len(pl.chapters), 6)

    def test_progress_uses_outline_count(self):
        pl, _, _ = self._generate(coarse_count=4, requested=4)
        self.assertEqual(pl._chapter_completed_count, 4)
        self.assertEqual(pl._total_chapters, 4)

    def test_previous_chapter_summary_comes_from_outline(self):
        self._generate(coarse_count=4, requested=4)
        second = next(i for i in FakeChapterAgent.inputs
                      if i.get("chapter_index") == 2)
        # 生成时上一章还没落盘，前情提要只能来自大纲细纲
        self.assertTrue(second["previous_chapter_summary"].startswith("细纲1"))


# ----------------------------------------------------------------------
#  2. 续写：键位 / 总数 / 弧线
# ----------------------------------------------------------------------
class ContinuationTest(unittest.TestCase):
    def setUp(self):
        FakeChapterAgent.inputs = []
        self._patch = mock.patch.object(
            pipeline_mod, "ChapterGeneratorAgent", FakeChapterAgent)
        self._patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._patch.stop)
        self.project_dir = Path(self.tmp.name) / "novel"
        self.project_dir.mkdir()
        write_chapters(self.project_dir, range(1, 11))

    def _outline(self):
        return {
            "outline_meta": {
                "chapter_start": 11, "chapter_end": 15, "total_chapters": 5,
            },
            "chapters": [
                {"chapter_index": i, "title": f"新第{i}章",
                 "plot_detail": f"新细纲{i}" * 10}
                for i in range(11, 16)
            ],
            "character_arcs": {"甲": {"arc_type": "成长型",
                                  "trajectory": [{"chapter": 15, "state": "本批新状态"}]}},
        }

    def _generate(self):
        pl = make_pipeline()
        pl.project_dir = self.project_dir
        pl.world_view = {"title": "t", "chapter_outline": [
            {"chapter_index": i, "title": f"第{i}章", "summary": f"概要{i}"}
            for i in range(1, 16)
        ]}
        pl.outline = {"chapters": [], "character_arcs": {}}
        pl._chapter_length = 3000
        finalized = []
        pl._on_all_chapters_complete = lambda: finalized.append(1)
        pl._generate_continuation_chapters(self._outline())
        done = wait_until(lambda: pl._pending_chapter_workers == 0)
        time.sleep(0.1)
        return pl, finalized, done

    def test_existing_chapters_are_not_overwritten(self):
        pl, finalized, done = self._generate()
        self.assertTrue(done)
        self.assertEqual([c["chapter_index"] for c in pl.chapters],
                         list(range(1, 16)), "续写把旧章节覆盖/丢了")
        self.assertEqual(len(pl._chapter_results), 15)
        self.assertEqual(finalized, [1])

    def test_totals_cover_whole_book(self):
        pl, _, _ = self._generate()
        self.assertEqual(pl._total_chapters, 15)
        self.assertEqual(pl._chapter_count, 15)
        self.assertEqual(pl._chapter_completed_count, 15)
        self.assertEqual(pl._completed_chapters, 15)
        self.assertEqual(pl._continuation_new_indices, [11, 12, 13, 14, 15])

    def test_character_arcs_come_from_batch_outline(self):
        self._generate()
        new_inputs = [i for i in FakeChapterAgent.inputs
                      if i.get("chapter_index") == 11]
        self.assertTrue(new_inputs)
        self.assertEqual(new_inputs[0]["character_arcs"]["甲"]["arc_type"], "成长型")

    def test_continuation_starts_from_chapter_start(self):
        pl, _, _ = self._generate()
        self.assertEqual(len([c for c in pl.chapters if c["chapter_index"] >= 11]), 5)
        self.assertEqual(pl._continuation_old_count, 10)


# ----------------------------------------------------------------------
#  3. 评估：失败章节跳过
# ----------------------------------------------------------------------
class EvaluationTest(unittest.TestCase):
    def setUp(self):
        FakeEvaluatorAgent.calls = []
        self._patch = mock.patch.object(
            pipeline_mod, "QualityEvaluatorAgent", FakeEvaluatorAgent)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_error_chapter_is_not_evaluated(self):
        pl = make_pipeline()
        pl.world_view = {"title": "t"}
        pl.outline = {"chapters": []}
        pl._chapter_length = 3000
        pl.chapters = [
            {"chapter_index": 1, "content": "正常正文" * 100, "status": "draft"},
            {"chapter_index": 2, "content": "[生成失败: boom]",
             "status": "error", "error": "boom"},
        ]
        downstream = []
        pl._run_revisions = lambda: downstream.append("revision")
        pl._adapt_chapters = lambda: downstream.append("adapt")

        pl._evaluate_chapters()

        self.assertEqual(FakeEvaluatorAgent.calls, [1])
        self.assertEqual(downstream, ["adapt"])

    def test_all_failed_reports_error(self):
        pl = make_pipeline()
        pl.world_view = {"title": "t"}
        pl.outline = {"chapters": []}
        pl._chapter_length = 3000
        pl.chapters = [
            {"chapter_index": 1, "content": "[生成失败]", "status": "error"},
            {"chapter_index": 2, "content": "[生成失败]", "status": "error"},
        ]
        pl._adapt_chapters = lambda: self.fail("全部失败时不应继续适配")
        pl._evaluate_chapters()
        self.assertEqual(pl._failed_stage, "quality_evaluation")
        self.assertFalse(pl.is_running)


# ----------------------------------------------------------------------
#  4. 适配落盘与跳过
# ----------------------------------------------------------------------
class AdaptationTest(unittest.TestCase):
    def setUp(self):
        FakeAdapterAgent.calls = []
        self._patch = mock.patch.object(
            pipeline_mod, "PlatformAdapterAgent", FakeAdapterAgent)
        self._patch.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._patch.stop)
        self.project_dir = Path(self.tmp.name) / "novel"
        self.project_dir.mkdir()

    def _pipeline(self):
        pl = make_pipeline()
        pl.project_dir = self.project_dir
        pl.world_view = {"title": "t"}
        pl._chapter_length = 3000
        pl.chapters = [
            {"chapter_index": 1, "title": "第一章", "content": "正文" * 100,
             "status": "draft"},
            {"chapter_index": 2, "title": "第二章", "content": "[生成失败]",
             "status": "error"},
        ]
        pl._finish_pipeline = lambda: None
        return pl

    def test_adaptation_is_saved_and_skipped_on_rerun(self):
        pl = self._pipeline()
        pl._adapt_chapters()
        self.assertEqual(FakeAdapterAgent.calls, [1], "失败章节不应送去做适配")
        path = pm.adaptation_path(self.project_dir, 1, "通用网文格式")
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("适配后的第1章正文", text)
        self.assertIn("通用网文格式", text)

        pl._adapt_chapters()
        self.assertEqual(FakeAdapterAgent.calls, [1], "已有适配稿时不应再次调用 LLM")

    def test_adaptation_can_be_disabled(self):
        pl = self._pipeline()
        pl.config = {**pl.config, "enable_platform_adaptation": False}
        pl._adapt_chapters()
        self.assertEqual(FakeAdapterAgent.calls, [])
        self.assertFalse(pm.adaptation_exists(self.project_dir, 1, "通用网文格式"))


# ----------------------------------------------------------------------
#  5. 完成汇总：均分口径 / 批次记录 / 状态清理
# ----------------------------------------------------------------------
class FinishPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_dir = Path(self.tmp.name) / "novel"
        self.project_dir.mkdir()

    def _pipeline(self):
        pl = make_pipeline()
        pl.project_dir = self.project_dir
        pl.world_view = {"title": "测试书"}
        pl.chapters = [
            {"chapter_index": 1, "word_count": 100, "status": "draft"},
            {"chapter_index": 2, "word_count": 200, "status": "draft"},
        ]
        pl.evaluations = {
            1: {"overall_score": 8.0},
            2: {"overall_score": 6.0},
            99: {"overall_score": 1.0},   # 上一部书残留
        }
        return pl

    def test_average_ignores_other_books(self):
        pl = self._pipeline()
        pl._finish_pipeline()
        summary = pm.load_project_summary(self.project_dir)
        self.assertEqual(summary["avg_quality_score"], 7.0)
        self.assertEqual(summary["chapter_count"], 2)
        self.assertEqual(summary["status"], "completed")

    def test_continuation_records_batch_and_keeps_generating(self):
        pl = self._pipeline()
        pl._continuation_new_indices = [3, 4]
        pl._continuation_batch = 2
        pl._continuation_guidance = "继续冒险"
        pl._finish_pipeline()
        summary = pm.load_project_summary(self.project_dir)
        self.assertEqual(summary["status"], "generating")
        self.assertEqual(len(summary["batches"]), 1)
        self.assertEqual(summary["batches"][0]["batch_number"], 2)
        self.assertEqual(summary["batches"][0]["chapter_range"], "3-4")

    def test_paused_flags_are_cleared_on_completion(self):
        pm.save_project_summary(self.project_dir, {
            "status": "paused", "paused_stage": "revision",
            "paused_at": "2026-01-01 00:00:00",
        })
        pl = self._pipeline()
        pl._finish_pipeline()
        summary = pm.load_project_summary(self.project_dir)
        self.assertNotIn("paused_stage", summary)
        self.assertNotIn("paused_at", summary)


# ----------------------------------------------------------------------
#  6. 错误处理与停止
# ----------------------------------------------------------------------
class ErrorHandlingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project_dir = Path(self.tmp.name) / "novel"
        self.project_dir.mkdir()

    def test_error_marks_project_failed(self):
        pm.save_project_summary(self.project_dir, {
            "title": "t", "status": "generating", "chapter_count": 5,
        })
        pl = make_pipeline()
        pl.project_dir = self.project_dir
        pl.current_stage = "chapter_generation"
        pl._handle_error("boom")
        summary = pm.load_project_summary(self.project_dir)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failed_stage"], "chapter_generation")
        self.assertEqual(pl._failed_stage, "chapter_generation")
        self.assertFalse(pl.is_running)

    def test_stop_clears_review_state(self):
        pl = make_pipeline()
        pl.is_running = True
        pl._world_view_reviewing = True
        pl._outline_reviewing = True
        pl._pending_world_view = {"title": "x"}
        pl.stop()
        self.assertFalse(pl.is_running)
        self.assertFalse(pl._world_view_reviewing)
        self.assertFalse(pl._outline_reviewing)
        self.assertIsNone(pl._pending_world_view)

    def test_empty_outline_is_rejected_before_agent_runs(self):
        class BoomAgent:
            def __init__(self, *args, **kwargs):
                raise AssertionError("世界观没有大纲时不应调用大纲 Agent")

        pl = make_pipeline()
        with mock.patch.object(pipeline_mod, "OutlineBuilderAgent", BoomAgent):
            pl._build_outline({"title": "t"})
        self.assertEqual(pl._failed_stage, "outline_generation")
        self.assertFalse(pl.is_running)

    def test_finalize_is_idempotent(self):
        pl = make_pipeline()
        pl._pending_chapter_workers = 0
        calls = []
        pl._on_all_chapters_complete = lambda: calls.append(1)
        pl._maybe_finalize_chapters()
        pl._maybe_finalize_chapters()
        self.assertEqual(calls, [1])

    def test_confirm_after_stop_is_rejected(self):
        pl = make_pipeline()
        pl.is_running = False
        pl._world_view_reviewing = False
        pl._outline_reviewing = False
        self.assertFalse(pl.confirm_world_view({"title": "x"}))
        self.assertFalse(pl.confirm_outline({"chapters": []}))
        self.assertFalse(pl.confirm_continuation({"chapters": []}))
        # 被拒绝时不应启动任何后台线程
        self.assertFalse(getattr(pl, "_pipeline_thread", None))


# ----------------------------------------------------------------------
#  7. 项目库 / API
# ----------------------------------------------------------------------
class ProjectsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects_root = Path(self.tmp.name)
        self._orig_projects_dir = pm.PROJECTS_DIR
        pm.PROJECTS_DIR = self.projects_root
        self.addCleanup(lambda: setattr(pm, "PROJECTS_DIR", self._orig_projects_dir))

        project = self.projects_root / "novel_20260101_000000"
        project.mkdir()
        pm.save_project_summary(project, {
            "title": "测试项目", "status": "completed",
            "chapter_count": 3, "chapters_count": 3,
            "avg_quality_score": 8.5, "completed_at": "2026-01-01 00:00:00",
        })
        self.project = project
        # 内部目录不应出现在项目列表里
        (self.projects_root / "_parse_failures").mkdir()

    def test_list_projects_flattens_summary(self):
        entries = pm.list_projects()
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["title"], "测试项目")
        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["chapter_count"], 3)
        self.assertEqual(entry["avg_quality_score"], 8.5)
        self.assertEqual(entry["name"], self.project.name)

    def test_batches_endpoint_returns_structured_list(self):
        import api.projects as projects_api
        pm.save_batch_outline(self.project, 1, {"chapters": [{"chapter_index": 4}]})
        result = asyncio.run(projects_api.get_batches(self.project.name))
        self.assertEqual(len(result["batches"]), 1)
        self.assertEqual(result["batches"][0]["batch_number"], 1)
        self.assertIn("chapters", result["batches"][0]["outline"])

    def test_export_without_chapters_is_rejected(self):
        import api.projects as projects_api
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(projects_api.export_txt(self.project.name))
        self.assertEqual(ctx.exception.status_code, 400)


# ----------------------------------------------------------------------
#  8. 配置校验
# ----------------------------------------------------------------------
class ConfigApiTest(unittest.TestCase):
    def setUp(self):
        import api.config as config_api
        self.config_api = config_api
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._patch = mock.patch.object(
            core_config, "CONFIG_FILE", Path(self.tmp.name) / "config.json")
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_rejects_non_numeric_concurrency(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.config_api.update_config({"concurrency": "abc"}))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_out_of_range_values(self):
        from fastapi import HTTPException
        for payload in ({"concurrency": 0}, {"max_revision_rounds": -1},
                        {"quality_threshold": 11}):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.config_api.update_config(payload))
            self.assertEqual(ctx.exception.status_code, 422)

    def test_accepts_valid_values(self):
        asyncio.run(self.config_api.update_config({
            "concurrency": 5,
            "quality_threshold": 7.5,
            "enable_platform_adaptation": False,
        }))
        config = core_config.load_config()
        self.assertEqual(config["concurrency"], 5)
        self.assertEqual(config["quality_threshold"], 7.5)
        self.assertFalse(config["enable_platform_adaptation"])

    def test_dead_config_keys_are_gone(self):
        for key in ("temperature", "max_tokens", "enable_outline_agent",
                    "web_monitor_port", "theme"):
            self.assertNotIn(key, DEFAULT_CONFIG)


# ----------------------------------------------------------------------
#  9. LLM 客户端与规则校验
# ----------------------------------------------------------------------
class LlmClientTest(unittest.TestCase):
    def setUp(self):
        self._orig = LLMClient._create_message
        self.calls = 0

        def fake_create(self, *args, **kwargs):
            type(self).calls += 1
            return "连接成功"

        LLMClient.calls = 0
        LLMClient._create_message = fake_create
        self.addCleanup(lambda: setattr(LLMClient, "_create_message", self._orig))

    def test_connection_test_makes_single_call(self):
        client = LLMClient(api_key="k", base_url="https://example.com", model="m")
        result = client.test_connection()
        self.assertTrue(result["ok"])
        self.assertEqual(LLMClient.calls, 1, "连接测试不应因短响应重复调用")

    def test_short_response_retry_can_be_disabled(self):
        client = LLMClient(api_key="k", base_url="https://example.com", model="m")
        client.chat("s", "u", min_length=0)
        self.assertEqual(LLMClient.calls, 1)
        LLMClient.calls = 0
        client.chat("s", "u")  # 默认 min_length=50 → 短响应重试
        self.assertEqual(LLMClient.calls, 3)


class RuleCheckerTest(unittest.TestCase):
    def test_word_count_ignores_whitespace(self):
        content = "字" * 100 + "\n" * 500
        self.assertEqual(rule_checker.count_words(content), 100)
        result = rule_checker.check_chapter(content, {"target_length": 100})
        self.assertEqual(result["stats"]["word_count"]["actual"], 100)
        self.assertEqual(result["hard_issues"], [])

    def test_short_chapter_is_hard_issue(self):
        result = rule_checker.check_chapter("字" * 50, {"target_length": 100})
        self.assertTrue(any(i["type"] == "word_count" and i["severity"] == "hard"
                            for i in result["hard_issues"]))


# ----------------------------------------------------------------------
#  10. 状态快照（前端重连回填用）
# ----------------------------------------------------------------------
class StatusSnapshotTest(unittest.TestCase):
    def test_get_status_exposes_review_state(self):
        pl = make_pipeline()
        pl._world_view_reviewing = True
        pl._pending_world_view = {"title": "待审阅"}
        pl.world_view = {"title": "待审阅"}
        status = pl.get_status()
        self.assertTrue(status["reviewing"]["world"])
        self.assertEqual(status["pending"]["world"]["title"], "待审阅")
        self.assertIn("failed_stage", status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
