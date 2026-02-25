"""Introspect Tool — 让大脑能看见自己。

Papert 原则：孩子必须能调试自己的程序。
大脑必须能检查自己的代码、日志、经验、健康状态。

这是大脑的"镜子"——不修改 brain.py（规则 06），作为 ToolPort 适配器注册。
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("introspect")

_ROOT = Path(__file__).parent.parent.parent
_LOGS_DIR = _ROOT / "logs"
_DATA_DIR = _ROOT / "data"
_IDENTITY_DIR = _ROOT / "identity"


class IntrospectAdapter(ToolPort):
    """自省工具 — 让大脑能检查自己的源码、日志、经验、健康。"""

    _learning_adapter = None  # 由 brain_init 注入共享实例

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "introspect",
                    "description": "自省工具：检查自己的源码、日志、经验库、测试结果、灵魂文件。用于自我诊断和学习。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "enum": ["source", "logs", "lessons", "test", "soul", "health_report", "record_lesson"],
                                "description": (
                                    "检查目标: "
                                    "source=读自己的源码文件, "
                                    "logs=读最近的模块日志, "
                                    "lessons=分析经验库, "
                                    "test=运行pytest自测, "
                                    "soul=读灵魂文件, "
                                    "health_report=生成完整健康报告, "
                                    "record_lesson=主动记录一条经验(需要module=触发条件,lines参数无用,用module写触发,用第二个参数写教训内容)"
                                ),
                            },
                            "module": {
                                "type": "string",
                                "description": "模块名(source: brain/brain_resilience/brain_learning/metacognition/self_eval; logs: brain/llm/tools/stream/learning/api/daemon; record_lesson: 触发条件/经验标题)",
                            },
                            "lesson_content": {
                                "type": "string",
                                "description": "经验内容(仅record_lesson时使用): 你学到了什么",
                            },
                            "lines": {
                                "type": "integer",
                                "description": "读取行数(日志默认50行, 源码默认全部)",
                            },
                        },
                        "required": ["target"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        target = params.get("target", "")
        module = params.get("module", "")
        lines = params.get("lines", 0)

        try:
            if target == "source":
                return await self._read_source(module)
            elif target == "logs":
                return await self._read_logs(module, lines or 50)
            elif target == "lessons":
                return await self._analyze_lessons()
            elif target == "test":
                return await self._run_tests()
            elif target == "soul":
                return await self._read_soul()
            elif target == "health_report":
                return await self._health_report()
            elif target == "record_lesson":
                return await self._record_lesson(module, params.get("lesson_content", ""))
            else:
                return {"success": False, "error": f"未知目标: {target}"}
        except Exception as e:
            logger.error(f"自省失败: target={target}, error={e}")
            return {"success": False, "error": str(e)}

    async def _read_source(self, module: str) -> dict[str, Any]:
        """读自己的源码。"""
        allowed = {
            "brain": _ROOT / "brain.py",
            "brain_resilience": _ROOT / "brain_resilience.py",
            "brain_learning": _ROOT / "brain_learning.py",
            "metacognition": _ROOT / "metacognition.py",
            "self_eval": _ROOT / "self_eval.py",
            "brain_daemon": _ROOT / "brain_daemon.py",
            "planner": _ROOT / "planner.py",
            "soul_engine": _IDENTITY_DIR / "soul_engine.py",
        }
        if not module:
            # 列出可检查的模块
            info = []
            for name, path in allowed.items():
                if path.exists():
                    line_count = len(path.read_text(encoding="utf-8").splitlines())
                    info.append(f"  {name}: {path.name} ({line_count}行)")
            result = "可检查的源码模块:\n" + "\n".join(info)
            result += "\n\n用 module 参数指定要读的模块，如 introspect(target='source', module='brain')"
            logger.info("自省: 列出可检查模块")
            return {"success": True, "result": result}

        path = allowed.get(module)
        if not path or not path.exists():
            return {"success": False, "error": f"未知模块: {module}，可选: {list(allowed.keys())}"}

        content = path.read_text(encoding="utf-8")
        lines_list = content.splitlines()
        # 生成带行号的源码（方便定位）
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines_list))
        logger.info(f"自省: 读取源码 {module} ({len(lines_list)}行)")
        return {"success": True, "result": f"=== {path.name} ({len(lines_list)}行) ===\n{numbered}"}

    async def _read_logs(self, module: str, lines: int) -> dict[str, Any]:
        """读最近的日志。"""
        if not module:
            module = "brain"
        log_file = _LOGS_DIR / f"{module}.log"
        if not log_file.exists():
            available = [f.stem for f in _LOGS_DIR.glob("*.log")]
            return {"success": False, "error": f"日志不存在: {module}.log，可用: {available}"}

        content = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        result = f"=== {module}.log (最近{len(recent)}行 / 共{len(all_lines)}行) ===\n"
        result += "\n".join(recent)

        # 简单统计
        errors = sum(1 for l in recent if "ERROR" in l)
        warnings = sum(1 for l in recent if "WARNING" in l)
        result += f"\n\n--- 统计: {errors} 错误, {warnings} 警告 ---"

        logger.info(f"自省: 读取日志 {module}.log (最近{len(recent)}行, {errors}错误, {warnings}警告)")
        return {"success": True, "result": result}

    async def _analyze_lessons(self) -> dict[str, Any]:
        """分析经验库。"""
        lessons_file = _DATA_DIR / "lessons.json"
        if not lessons_file.exists():
            return {"success": False, "error": "经验库不存在"}

        lessons = json.loads(lessons_file.read_text(encoding="utf-8"))
        total = len(lessons)

        # 分析
        triggers = [l.get("trigger", "") for l in lessons]
        unique_triggers = len(set(triggers))
        duplicates = total - unique_triggers

        # 按类型分类
        categories = {}
        for l in lessons:
            t = l.get("trigger", "")
            if "工具失败" in t:
                cat = "工具失败经验"
            elif "反思" in t:
                cat = "反思经验"
            elif "用户教学" in t or "用户纠正" in t:
                cat = "用户教学"
            elif "灵魂进化" in t:
                cat = "灵魂进化"
            else:
                cat = "其他"
            categories[cat] = categories.get(cat, 0) + 1

        # 找矛盾经验（同一触发不同教训）
        trigger_lessons = {}
        contradictions = []
        for l in lessons:
            t = l.get("trigger", "")[:50]
            lesson_text = l.get("lesson", "")[:50]
            if t in trigger_lessons and trigger_lessons[t] != lesson_text:
                contradictions.append(f"  触发: {t}\n  教训A: {trigger_lessons[t]}\n  教训B: {lesson_text}")
            trigger_lessons[t] = lesson_text

        result = f"=== 经验库分析 ===\n"
        result += f"总数: {total} 条\n"
        result += f"唯一触发: {unique_triggers} 条\n"
        result += f"重复: {duplicates} 条\n\n"
        result += "分类统计:\n"
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            result += f"  {cat}: {count} 条\n"

        if contradictions:
            result += f"\n⚠️ 发现 {len(contradictions)} 对矛盾经验:\n"
            for c in contradictions[:3]:
                result += f"{c}\n"

        # 最近5条经验
        result += "\n最近5条经验:\n"
        for l in lessons[-5:]:
            result += f"  触发: {l.get('trigger', '')[:60]}\n  教训: {l.get('lesson', '')[:80]}\n\n"

        logger.info(f"自省: 分析经验库 ({total}条, {duplicates}重复, {len(contradictions)}矛盾)")
        return {"success": True, "result": result}

    async def _run_tests(self) -> dict[str, Any]:
        """运行 pytest 自测。"""
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "tests/test_brain.py", "-v", "--tb=short"],
                capture_output=True, text=True, timeout=60, cwd=str(_ROOT),
            )
            output = proc.stdout + proc.stderr
            # 提取关键信息
            passed = output.count(" PASSED")
            failed = output.count(" FAILED")
            errors = output.count(" ERROR")

            summary = f"=== 自测结果 ===\n"
            summary += f"通过: {passed}, 失败: {failed}, 错误: {errors}\n"
            summary += f"退出码: {proc.returncode}\n\n"
            summary += output[-2000:]  # 最后2000字符

            status = "健康" if proc.returncode == 0 else "异常"
            logger.info(f"自省: 自测完成 — {status} (通过{passed} 失败{failed} 错误{errors})")
            return {"success": proc.returncode == 0, "result": summary}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "自测超时(60秒)"}

    async def _read_soul(self) -> dict[str, Any]:
        """读灵魂文件。"""
        soul_path = _IDENTITY_DIR / "SOUL.md"
        if not soul_path.exists():
            return {"success": False, "error": "SOUL.md 不存在"}

        content = soul_path.read_text(encoding="utf-8")
        lines = len(content.splitlines())

        # 检查进化日志
        evo_path = _IDENTITY_DIR / "soul_evolution.json"
        evo_info = ""
        if evo_path.exists():
            try:
                evos = json.loads(evo_path.read_text(encoding="utf-8"))
                evo_info = f"\n\n=== 灵魂进化历史 ({len(evos)}次) ===\n"
                for e in evos[-5:]:
                    evo_info += f"  {e.get('time', '?')}: {e.get('rule', '')[:60]} (触发: {e.get('trigger', '')[:40]})\n"
            except Exception:
                pass

        result = f"=== SOUL.md ({lines}行, 上限200行) ===\n{content}{evo_info}"
        logger.info(f"自省: 读取灵魂 ({lines}行)")
        return {"success": True, "result": result}

    async def _health_report(self) -> dict[str, Any]:
        """生成完整健康报告。"""
        report = ["=== LucidMind 健康报告 ===\n"]

        # 1. 源码行数检查
        report.append("📏 源码行数:")
        limits = {"brain.py": 600, "brain_resilience.py": 300, "brain_learning.py": 300,
                  "brain_daemon.py": 300, "metacognition.py": 300}
        for name, limit in limits.items():
            path = _ROOT / name
            if path.exists():
                lines = len(path.read_text(encoding="utf-8").splitlines())
                status = "✅" if lines <= limit else "❌"
                report.append(f"  {status} {name}: {lines}/{limit}行")

        # 2. 日志健康
        report.append("\n📋 日志健康:")
        for log_file in sorted(_LOGS_DIR.glob("*.log")):
            size_kb = log_file.stat().st_size / 1024
            content = log_file.read_text(encoding="utf-8", errors="replace")
            errors = content.count("ERROR")
            report.append(f"  {log_file.stem}: {size_kb:.0f}KB, {errors}个ERROR")

        # 3. 经验库
        lessons_file = _DATA_DIR / "lessons.json"
        if lessons_file.exists():
            lessons = json.loads(lessons_file.read_text(encoding="utf-8"))
            report.append(f"\n📚 经验库: {len(lessons)}条")
        else:
            report.append("\n📚 经验库: 不存在")

        # 4. SOUL.md
        soul_path = _IDENTITY_DIR / "SOUL.md"
        if soul_path.exists():
            soul_lines = len(soul_path.read_text(encoding="utf-8").splitlines())
            status = "✅" if soul_lines <= 200 else "❌"
            report.append(f"\n🧬 灵魂: {status} {soul_lines}/200行")

        # 5. 测试
        report.append("\n🧪 建议: 运行 introspect(target='test') 进行自测")

        result = "\n".join(report)
        logger.info("自省: 生成健康报告")
        return {"success": True, "result": result}

    async def _record_lesson(self, trigger: str, lesson_content: str) -> dict[str, Any]:
        """主动记录一条经验到经验库（带质量门控）。"""
        if not trigger:
            return {"success": False, "error": "需要提供 module 参数作为触发条件/经验标题"}
        if not lesson_content:
            return {"success": False, "error": "需要提供 lesson_content 参数作为经验内容"}
        # 质量门控：拒绝模糊/通用/启动自检产生的垃圾
        _reject_keywords = ["启动自检", "变得更聪明", "执行任务", "从每次交互中学习",
                            "减少错误", "理解用户", "记住偏好", "重复提问"]
        combined = (trigger + lesson_content).lower()
        for kw in _reject_keywords:
            if kw in combined:
                logger.info(f"自省: 拒绝低质量经验(含'{kw}'): {trigger[:40]}")
                return {"success": True, "result": f"经验已评估，不需要记录（通用知识，非特定教训）"}
        try:
            adapter = IntrospectAdapter._learning_adapter
            if not adapter:
                from adapters.learning.json_lessons import JSONLessonsAdapter
                adapter = JSONLessonsAdapter(data_dir=str(_DATA_DIR))
            await adapter.learn({
                "trigger": trigger,
                "lesson": lesson_content,
                "source": "self_record",
                "source_session": "introspect",
            })
            total = len(adapter._lessons)
            logger.info(f"自省: 主动记录经验 trigger='{trigger[:50]}', 总数={total}")
            return {"success": True, "result": f"经验已记录！触发: {trigger}\n内容: {lesson_content}\n经验库总数: {total}条"}
        except Exception as e:
            return {"success": False, "error": f"记录经验失败: {e}"}
