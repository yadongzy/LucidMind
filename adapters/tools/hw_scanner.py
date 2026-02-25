"""Hardware Scanner + Local Model Recommender — 硬件扫描与本地模型智能推荐。

功能：
1. 扫描电脑硬件（CPU/RAM/GPU/显存）
2. 扫描Ollama已安装模型
3. 根据硬件配置推荐最优本地模型
4. 如果没有安装模型，建议用户安装最佳匹配的模型

设计原则（规则03）：
- 作为工具暴露给大脑，大脑可以主动调用
- 启动时自动扫描，结果注入经验库
- 不硬编码大脑行为，只提供信息和建议
"""

import asyncio
import functools
import json
import platform
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")
_pool = ThreadPoolExecutor(max_workers=2)

# 模型推荐数据库：按显存/内存需求排序
_MODEL_DB = [
    {"name": "qwen3:0.6b",  "vram_gb": 0.5, "ram_gb": 2,  "tier": "tiny",   "chinese": 0.9, "desc": "超轻量，中文优秀，适合2GB显存或纯CPU"},
    {"name": "gemma3:1b",    "vram_gb": 1.0, "ram_gb": 3,  "tier": "tiny",   "chinese": 0.5, "desc": "轻量，中文较弱，适合2GB显存"},
    {"name": "qwen3:1.7b",   "vram_gb": 1.5, "ram_gb": 4,  "tier": "small",  "chinese": 0.95, "desc": "小型，中文优秀，性价比最高"},
    {"name": "phi3:latest",  "vram_gb": 2.5, "ram_gb": 5,  "tier": "small",  "chinese": 0.4, "desc": "微软小模型，中文弱，适合4GB显存"},
    {"name": "qwen3:4b",     "vram_gb": 3.0, "ram_gb": 6,  "tier": "medium", "chinese": 0.95, "desc": "中型，中文优秀，适合4-6GB显存"},
    {"name": "qwen3:8b",     "vram_gb": 5.0, "ram_gb": 8,  "tier": "medium", "chinese": 0.98, "desc": "中大型，中文极佳，适合6-8GB显存"},
    {"name": "qwen3:14b",    "vram_gb": 9.0, "ram_gb": 16, "tier": "large",  "chinese": 0.99, "desc": "大型，适合12GB+显存"},
    {"name": "qwen3:30b",    "vram_gb": 18,  "ram_gb": 32, "tier": "xlarge", "chinese": 1.0,  "desc": "超大型，适合24GB+显存"},
]


class HWScannerAdapter(ToolPort):
    """硬件扫描与本地模型推荐工具。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "hw_scan":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        action = params.get("action", "full_scan")
        try:
            loop = asyncio.get_event_loop()
            if action == "hardware":
                result = await loop.run_in_executor(_pool, scan_hardware)
            elif action == "models":
                result = await loop.run_in_executor(_pool, scan_ollama_models)
            elif action == "recommend":
                result = await loop.run_in_executor(_pool, recommend_model)
            elif action == "install":
                model_name = params.get("model", "")
                if not model_name:
                    return {"success": False, "result": None, "error": "install需要model参数，如 model='qwen3:1.7b'"}
                result = await loop.run_in_executor(_pool, functools.partial(install_model, model_name))
                return {"success": True, "result": result}
            else:  # full_scan
                result = await loop.run_in_executor(_pool, full_scan)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)[:300]}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "hw_scan",
            "description": "硬件扫描与本地模型管理。扫描CPU/RAM/GPU，检测Ollama模型，推荐最优模型，下载安装模型。",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string",
                           "enum": ["full_scan", "hardware", "models", "recommend", "install"],
                           "description": "full_scan=扫描+推荐, hardware=硬件, models=模型列表, recommend=推荐, install=下载安装模型"},
                "model": {"type": "string",
                          "description": "install时指定模型名，如 qwen3:1.7b"}
            }, "required": ["action"]}
        }}]


def _cmd(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def scan_hardware() -> dict:
    """扫描硬件配置：CPU、内存、GPU、显存。跨平台支持。"""
    hw = {"os": platform.system(), "arch": platform.machine(), "python": platform.python_version()}
    is_win = platform.system() == "Windows"

    # CPU
    if is_win:
        cpu_name = _cmd('wmic cpu get Name /format:list').replace("Name=", "").strip()
        cores = _cmd('wmic cpu get NumberOfCores /format:list').replace("NumberOfCores=", "").strip()
    else:
        cpu_name = _cmd("cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2").strip()
        cores = _cmd("nproc")
    hw["cpu"] = cpu_name or platform.processor()
    hw["cpu_cores"] = int(cores) if cores.isdigit() else 0
    # CPU频率检测（用于纯CPU推理性能评估）
    cpu_str = hw["cpu"].lower()
    hw["cpu_low_power"] = any(tag in cpu_str for tag in ["u cpu", "1.6ghz", "1.8ghz", "1.0ghz", "1.2ghz", "celeron", "pentium", "atom"])

    # RAM
    if is_win:
        raw = _cmd('wmic memorychip get Capacity /format:list')
        caps = [int(x.replace("Capacity=", "")) for x in raw.strip().split("\n") if x.strip().startswith("Capacity=")]
        hw["ram_gb"] = round(sum(caps) / (1024**3), 1) if caps else 0
    else:
        mem_kb = _cmd("grep MemTotal /proc/meminfo | awk '{print $2}'")
        hw["ram_gb"] = round(int(mem_kb) / (1024**2), 1) if mem_kb.isdigit() else 0

    # GPU (NVIDIA)
    gpu_info = _cmd("nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits")
    if gpu_info:
        parts = [p.strip() for p in gpu_info.split(",")]
        hw["gpu"] = parts[0] if len(parts) > 0 else "Unknown"
        hw["gpu_vram_mb"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        hw["gpu_vram_free_mb"] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        hw["gpu_vram_gb"] = round(hw["gpu_vram_mb"] / 1024, 1)
    else:
        hw["gpu"] = "None (CPU only)"
        hw["gpu_vram_mb"] = 0
        hw["gpu_vram_gb"] = 0

    # 可用内存
    if is_win:
        free = _cmd('wmic OS get FreePhysicalMemory /format:list').replace("FreePhysicalMemory=", "").strip()
        hw["ram_free_gb"] = round(int(free) / (1024**2), 1) if free.isdigit() else 0
    else:
        avail = _cmd("grep MemAvailable /proc/meminfo | awk '{print $2}'")
        hw["ram_free_gb"] = round(int(avail) / (1024**2), 1) if avail.isdigit() else 0

    logger.info(f"硬件扫描: CPU={hw['cpu'][:30]}, RAM={hw['ram_gb']}GB, GPU={hw.get('gpu','?')}, VRAM={hw['gpu_vram_gb']}GB")
    return hw


def scan_ollama_models() -> dict:
    """扫描Ollama已安装的模型列表。"""
    result = {"ollama_running": False, "models": []}
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        data = json.loads(resp.read())
        result["ollama_running"] = True
        for m in data.get("models", []):
            size_gb = round(m.get("size", 0) / (1024**3), 1)
            result["models"].append({
                "name": m["name"],
                "size_gb": size_gb,
                "family": m.get("details", {}).get("family", "unknown"),
                "params": m.get("details", {}).get("parameter_size", "unknown"),
            })
        logger.info(f"Ollama模型: {[m['name'] for m in result['models']]}")
    except Exception as e:
        logger.info(f"Ollama未运行或无法连接: {e}")
    return result


def recommend_model() -> dict:
    """根据硬件配置推荐最优本地模型。"""
    hw = scan_hardware()
    ollama = scan_ollama_models()

    vram_gb = hw.get("gpu_vram_gb", 0)
    ram_gb = hw.get("ram_gb", 0)
    # GPU推理需要≥4GB显存才有意义（2GB扣除Ollama开销后不够）
    gpu_usable = vram_gb >= 4
    cpu_low_power = hw.get("cpu_low_power", False)
    if gpu_usable:
        effective_limit = vram_gb * 0.8
    elif cpu_low_power:
        # 低压 CPU（笔记本 U 系列）：纯CPU推理只能跑小模型（实测8b崩溃）
        effective_limit = min(ram_gb * 0.3, 3.0)  # 封顶 3GB，只能跑≤1.7b
    else:
        effective_limit = ram_gb * 0.4

    # 从大到小找第一个能跑的模型（优先中文能力强的qwen系列）
    candidates = []
    for model in reversed(_MODEL_DB):
        needed = model["vram_gb"] if gpu_usable else model["ram_gb"] * 0.6
        if needed <= effective_limit:
            candidates.append(model)
    # 按中文能力排序，同分取参数量最大的
    if candidates:
        candidates.sort(key=lambda m: (m["chinese"], m["vram_gb"]), reverse=True)
        recommended = candidates[0]
    else:
        recommended = _MODEL_DB[0]  # 兜底：最小模型

    # 检查推荐模型是否已安装
    installed_names = [m["name"] for m in ollama.get("models", [])]
    is_installed = recommended["name"] in installed_names

    # 在已安装模型中找最优的（优先中文能力强的）
    best_installed = None
    installed_candidates = []
    if installed_names:
        for model in _MODEL_DB:
            if model["name"] in installed_names:
                needed = model["vram_gb"] if gpu_usable else model["ram_gb"] * 0.6
                if needed <= effective_limit:
                    installed_candidates.append(model)
        # 模糊匹配（如 mollysama/rwkv-6-world:1.6b）
        if not installed_candidates:
            for iname in installed_names:
                base = iname.split(":")[0].split("/")[-1]
                for model in _MODEL_DB:
                    if base in model["name"] or model["name"].split(":")[0] in base:
                        needed = model["vram_gb"] if gpu_usable else model["ram_gb"] * 0.6
                        if needed <= effective_limit:
                            installed_candidates.append({"name": iname, **{k: v for k, v in model.items() if k != "name"}})
                            break
        if installed_candidates:
            installed_candidates.sort(key=lambda m: (m["chinese"], m["vram_gb"]), reverse=True)
            best_installed = installed_candidates[0]

    advice = []
    if vram_gb < 2:
        advice.append(f"GPU显存仅{vram_gb}GB，将使用纯CPU推理（较慢）")
        advice.append(f"建议使用≤1.7b参数的小模型以保证响应速度")
    elif vram_gb < 4:
        advice.append(f"GPU显存{vram_gb}GB，适合运行≤4b参数的模型")
    elif vram_gb < 8:
        advice.append(f"GPU显存{vram_gb}GB，可运行8b参数模型")
    else:
        advice.append(f"GPU显存{vram_gb}GB，可运行大型模型")

    if not ollama.get("ollama_running"):
        advice.append("Ollama未运行！请先启动Ollama: ollama serve")
    elif not installed_names:
        advice.append(f"未安装任何模型！建议安装: ollama pull {recommended['name']}")
    elif not is_installed and best_installed:
        advice.append(f"已安装模型中最优: {best_installed['name']}")
        if recommended["name"] != best_installed["name"]:
            advice.append(f"更优选择(未安装): ollama pull {recommended['name']}")

    result = {
        "hardware_summary": f"CPU={hw['cpu'][:40]}, RAM={ram_gb}GB, GPU={hw.get('gpu','None')}, VRAM={vram_gb}GB",
        "recommended_model": recommended["name"],
        "recommended_desc": recommended["desc"],
        "recommended_installed": is_installed,
        "best_installed_model": best_installed["name"] if best_installed else None,
        "installed_models": installed_names,
        "effective_limit_gb": round(effective_limit, 1),
        "inference_mode": "GPU" if vram_gb >= 2 else "CPU (slow)",
        "advice": advice,
    }
    logger.info(f"模型推荐: {recommended['name']} (installed={is_installed}), best_installed={best_installed}")
    return result


def full_scan() -> str:
    """完整扫描：硬件+模型+推荐，返回人类可读的报告。"""
    rec = recommend_model()
    lines = [
        "=== 硬件扫描与模型推荐报告 ===",
        f"硬件: {rec['hardware_summary']}",
        f"推理模式: {rec['inference_mode']}",
        f"有效算力上限: {rec['effective_limit_gb']}GB",
        "",
        f"推荐模型: {rec['recommended_model']} ({rec['recommended_desc']})",
        f"已安装: {'是' if rec['recommended_installed'] else '否'}",
    ]
    if rec["best_installed_model"]:
        lines.append(f"已安装最优: {rec['best_installed_model']}")
    lines.append(f"已安装模型: {', '.join(rec['installed_models']) if rec['installed_models'] else '无'}")
    lines.append("")
    lines.append("建议:")
    for a in rec["advice"]:
        lines.append(f"  - {a}")
    return "\n".join(lines)


def install_model(model_name: str) -> str:
    """下载安装Ollama模型。大脑可通过hw_scan(action='install', model='xxx')调用。"""
    # 安全检查：只允许安装已知安全的模型前缀
    safe_prefixes = ["qwen", "gemma", "phi", "llama", "mistral", "deepseek", "yi", "glm", "rwkv"]
    base = model_name.split(":")[0].split("/")[-1].lower()
    if not any(base.startswith(p) for p in safe_prefixes):
        return f"安全限制：不允许安装未知模型 {model_name}。允许的前缀: {safe_prefixes}"

    # 检查是否已安装
    existing = scan_ollama_models()
    if model_name in [m["name"] for m in existing.get("models", [])]:
        return f"模型 {model_name} 已安装，无需重复下载。"

    # 检查Ollama是否运行
    if not existing.get("ollama_running"):
        return "Ollama未运行，请先启动: ollama serve"

    # 执行下载（可能需要几分钟）
    logger.info(f"开始下载模型: {model_name}")
    try:
        r = subprocess.run(
            f"ollama pull {model_name}",
            shell=True, capture_output=True, text=True, timeout=600  # 10分钟超时
        )
        if r.returncode == 0:
            logger.info(f"模型下载完成: {model_name}")
            return f"模型 {model_name} 下载安装成功！可以使用了。"
        else:
            err = r.stderr.strip()[:200]
            logger.warning(f"模型下载失败: {model_name} — {err}")
            return f"模型 {model_name} 下载失败: {err}"
    except subprocess.TimeoutExpired:
        return f"模型 {model_name} 下载超时（>10分钟），可能网络较慢，请手动执行: ollama pull {model_name}"
    except Exception as e:
        return f"下载异常: {e}"


def get_optimal_model_name() -> str:
    """快速接口：返回当前硬件最优的已安装模型名称。供启动时自动配置用。"""
    try:
        rec = recommend_model()
        if rec["best_installed_model"]:
            return rec["best_installed_model"]
        if rec["recommended_installed"]:
            return rec["recommended_model"]
        # 没有最优的，返回已安装中最小的
        if rec["installed_models"]:
            return rec["installed_models"][0]
    except Exception as e:
        logger.warning(f"获取最优模型失败: {e}")
    return "qwen3:0.6b"  # 兜底
