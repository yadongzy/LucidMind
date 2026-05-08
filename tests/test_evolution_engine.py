"""Tests for Evolution Engine Phase 4: SelfHeal + GitHooks + Metrics."""
import tempfile
from pathlib import Path



# ─── SelfHealEngine ───

def test_self_heal_import():
    from checkup.self_heal import SelfHealEngine, HealResult
    assert SelfHealEngine is not None
    assert HealResult is not None


def test_heal_result_to_dict():
    from checkup.self_heal import HealResult
    r = HealResult(trigger="test", original_score=70, final_score=80)
    d = r.to_dict()
    assert d["trigger"] == "test"
    assert d["delta"] == 10
    assert d["improved"] is True


def test_heal_result_not_improved():
    from checkup.self_heal import HealResult
    r = HealResult(trigger="test", original_score=80, final_score=80)
    assert r.improved is False
    assert r.to_dict()["delta"] == 0


def test_quick_check():
    from checkup.self_heal import SelfHealEngine
    engine = SelfHealEngine(".")
    check = engine.quick_check()
    assert "score" in check
    assert "healthy" in check
    assert "issues_count" in check
    assert isinstance(check["score"], int)


# ─── GitHooks ───

def test_git_hooks_import():
    from checkup.git_hooks import install_hooks, uninstall_hooks
    assert callable(install_hooks)
    assert callable(uninstall_hooks)


def test_install_uninstall_hooks():
    """Test hook install/uninstall in a temp git repo."""
    with tempfile.TemporaryDirectory() as tmp:
        hooks_dir = Path(tmp) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)

        from checkup.git_hooks import install_hooks, uninstall_hooks

        result = install_hooks(Path(tmp))
        assert result["success"] is True
        assert "pre-commit" in result["hooks"]
        assert (hooks_dir / "pre-commit").exists()
        assert (hooks_dir / "post-merge").exists()

        # Verify content
        content = (hooks_dir / "pre-commit").read_text()
        assert "LucidMind" in content

        # Uninstall
        result2 = uninstall_hooks(Path(tmp))
        assert result2["success"] is True
        assert "pre-commit" in result2["removed"]
        assert not (hooks_dir / "pre-commit").exists()


def test_install_hooks_no_git():
    with tempfile.TemporaryDirectory() as tmp:
        from checkup.git_hooks import install_hooks
        result = install_hooks(Path(tmp))
        assert result["success"] is False


# ─── EvolutionMetrics ───

def test_metrics_import():
    from checkup.evolution_metrics import EvolutionMetrics
    assert EvolutionMetrics is not None


def test_metrics_summary():
    from checkup.evolution_metrics import EvolutionMetrics
    m = EvolutionMetrics()
    summary = m.compute_summary(30)
    d = summary.to_dict()
    assert "total_heals" in d
    assert "success_rate" in d
    assert "weekly_frequency" in d
    assert "health_trend" in d
    assert isinstance(d["success_rate"], float)


def test_metrics_targets():
    from checkup.evolution_metrics import EvolutionMetrics
    m = EvolutionMetrics()
    targets = m.get_targets()
    assert "targets" in targets
    assert "success_rate" in targets["targets"]
    assert "met" in targets["targets"]["success_rate"]


def test_record_health_point():
    from checkup.evolution_metrics import EvolutionMetrics
    m = EvolutionMetrics()
    m.record_health_point(76, "test")
    trend = m._load_health_trend(1)
    assert len(trend) >= 1
    assert trend[-1]["score"] == 76


# ─── EvolutionLog (existing, sanity check) ───

def test_evolution_log_create_bead():
    from checkup.evolution_log import EvolutionLog
    log = EvolutionLog()
    bead = log.create_bead(trigger="test", action="test-action")
    assert bead.id.startswith("EVOL-")
    assert bead.trigger == "test"


def test_evolution_log_stats():
    from checkup.evolution_log import EvolutionLog
    log = EvolutionLog()
    stats = log.get_stats()
    assert "total" in stats
    assert "success_rate" in stats
