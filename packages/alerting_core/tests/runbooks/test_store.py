from alerting_contracts.common import Actor
from alerting_contracts.runbooks import RunbookFormat
from alerting_core.config import get_kind, load_config_directory
from alerting_core.runbooks import normalize_runbook, register_runbook_kind, save_runbook


def test_register_idempotent_and_loads_demo_config(config_dir):
    register_runbook_kind()
    register_runbook_kind()
    assert get_kind("runbook").directory == "runbooks"
    result = load_config_directory(config_dir)
    assert result.errors == []
    runbooks = {d.id: d.model for d in result.documents if d.kind == "runbook"}
    assert set(runbooks) == {"workflow-failed", "trade-limit-breach", "pricing-stale-feed"}
    assert runbooks["workflow-failed"].title == "Settlement workflow failed"
    assert runbooks["trade-limit-breach"].title == "Trade limit breach"
    assert runbooks["pricing-stale-feed"].title == "pricing-stale-feed"
    assert any(s.action == "open-ticket" for s in runbooks["trade-limit-breach"].steps)


def test_bad_runbook_file_reports_path(tmp_path):
    register_runbook_kind()
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "bad.yaml").write_text(
        "id: bad\ntitle: T\nsteps:\n  - {index: 0, kind: nope, text: a}\n"
    )
    (tmp_path / "runbooks" / "empty.md").write_text("")
    errors = load_config_directory(tmp_path).errors
    assert any(e.file == "runbooks/bad.yaml" and e.path.startswith("steps.0.kind") for e in errors)
    assert any(e.file == "runbooks/empty.md" for e in errors)


async def test_save_runbook(pool, redis):
    register_runbook_kind()
    rb = normalize_runbook("r1", "R", None, RunbookFormat.text, "do it", {})
    assert await save_runbook(pool, redis, rb, Actor(id="tester")) == 1
    assert await save_runbook(pool, redis, rb, Actor(id="tester")) == 2
