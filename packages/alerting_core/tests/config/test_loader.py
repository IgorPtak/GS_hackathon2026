from pathlib import Path

from alerting_core.config import canonical_document, load_config_directory

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


def test_every_real_config_file_loads_and_round_trips() -> None:
    result = load_config_directory(CONFIG_DIR)
    assert result.errors == []
    assert {d.kind for d in result.documents} == {
        "source",
        "schema",
        "rule",
        "recipient",
        "team",
        "channel",
        "action",
    }
    for loaded in result.documents:
        again = type(loaded.model).model_validate(canonical_document(loaded.model))
        assert again == loaded.model


def test_errors_name_file_and_field_path(tmp_path: Path) -> None:
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "bad.yaml").write_text(
        "id: bad\nteam: t\nwhen: {field: a, op: nope}\npresent: {title: x}\n"
    )
    result = load_config_directory(tmp_path)
    assert result.documents == []
    assert any(e.file == "rules/bad.yaml" and "when" in e.path for e in result.errors)


def test_id_must_match_file_name(tmp_path: Path) -> None:
    (tmp_path / "teams").mkdir()
    (tmp_path / "teams" / "a.yaml").write_text("id: b\ndisplay_name: B\n")
    result = load_config_directory(tmp_path)
    assert [e.path for e in result.errors] == ["id"]


def test_malformed_yaml_is_reported_not_raised(tmp_path: Path) -> None:
    (tmp_path / "teams").mkdir()
    (tmp_path / "teams" / "a.yaml").write_text("id: [unclosed\n")
    result = load_config_directory(tmp_path)
    assert result.errors[0].file == "teams/a.yaml"
