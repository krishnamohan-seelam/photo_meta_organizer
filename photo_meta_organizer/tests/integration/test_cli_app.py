"""The command line as a whole: global options, help, and how a run ends (ticket 06)."""

import pytest

from photo_meta_organizer import __version__
from photo_meta_organizer.cli import common, run


def test_version_prints_the_version_and_succeeds(capsys):
    assert run(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"photo-meta-organizer {__version__}"


def test_no_command_prints_help_and_succeeds(capsys):
    assert run([]) == 0
    out = capsys.readouterr().out
    assert "Usage:" in out
    for command in ("index", "sync", "search", "stats", "prune", "analyze", "paths"):
        assert command in out


def test_ctrl_c_ends_with_the_interrupt_exit_code(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(common.Settings, "from_env", interrupted)
    assert run(["paths"]) == 130  # 128 + SIGINT, as shells report it


def test_a_shortened_option_still_works(tmp_path, capsys):
    """argparse accepted any unambiguous prefix of a long option; scripts rely on it."""
    assert run(["sync", "--path", str(tmp_path), "--dry"]) == 0
    assert capsys.readouterr().out.startswith("[DRY RUN] ")


def test_a_shortened_option_with_a_value_still_works(tmp_path, capsys):
    assert run(["sync", "--path", str(tmp_path), "--work=2", "--dry"]) == 0
    assert "[DRY RUN]" in capsys.readouterr().out


def test_an_ambiguous_shortened_option_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        run(["sync", "--path", str(tmp_path), "--re"])
    assert exc.value.code == 2
    assert "--re" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv", [[], ["index"], ["sync"], ["search"], ["stats"], ["prune"], ["analyze"]]
)
def test_help_is_plain_text_for_users(argv, capsys):
    assert run([*argv, "--help"]) == 0
    out = capsys.readouterr().out
    assert "``" not in out
    assert "ADR" not in out
    assert "[default:" not in out  # the help texts say "(default: ...)" themselves
    assert out.isascii()
