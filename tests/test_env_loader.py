from __future__ import annotations

from app.web.env_loader import load_dotenv_file, strip_env_quotes


def test_strip_env_quotes_handles_matching_quotes() -> None:
    assert strip_env_quotes('"value"') == "value"
    assert strip_env_quotes("'value'") == "value"
    assert strip_env_quotes("value") == "value"


def test_load_dotenv_file_reads_values_without_overwriting_existing_env(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nFIRST=one\nSECOND=\"two words\"\nEXISTING=from-file\nINVALID\n",
        encoding="utf-8",
    )
    environ = {"EXISTING": "keep-me"}

    resolved = load_dotenv_file(default_path=tmp_path / "unused", env_path=env_file, environ=environ)

    assert resolved == env_file.resolve()
    assert environ == {"FIRST": "one", "SECOND": "two words", "EXISTING": "keep-me"}


def test_load_dotenv_file_honors_configured_path(tmp_path) -> None:
    env_file = tmp_path / "configured.env"
    env_file.write_text("VALUE=configured\n", encoding="utf-8")
    environ = {"CORAMAIL_ENV_FILE": str(env_file)}

    resolved = load_dotenv_file(default_path=tmp_path / ".env", environ=environ)

    assert resolved == env_file.resolve()
    assert environ["VALUE"] == "configured"


def test_load_dotenv_file_returns_missing_path_without_mutation(tmp_path) -> None:
    missing = tmp_path / "missing.env"
    environ: dict[str, str] = {}

    resolved = load_dotenv_file(default_path=missing, environ=environ)

    assert resolved == missing.resolve()
    assert environ == {}
