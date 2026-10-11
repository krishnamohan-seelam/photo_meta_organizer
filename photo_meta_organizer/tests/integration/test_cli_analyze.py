"""CLI `analyze`: consent before download, incremental analysis, honest exit codes (Phase 5)."""

import hashlib
import sys
from pathlib import Path

import pytest
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.application import composition
from photo_meta_organizer.domain.models import (
    ImageDimensions,
    ImageExifData,
    ImageFileInfo,
    ImageMetadata,
)
from photo_meta_organizer.infrastructure.analysis.model_manifest import ModelFile, ModelManifest
from photo_meta_organizer.infrastructure.analysis.model_store import (
    ModelStore,
    ModelUnavailableError,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_analysis_repository import (
    SqliteAnalysisRepository,
)
from photo_meta_organizer.infrastructure.repositories.sqlite_repository import SqliteRepository
from photo_meta_organizer.main import main

MODEL_BYTES = b"pretend-model-weights" * 100


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A library of 2 photos, a 'remote' model served from disk, and a fake embedder."""
    remote = tmp_path / "remote" / "model.onnx"
    remote.parent.mkdir()
    remote.write_bytes(MODEL_BYTES)
    manifest = ModelManifest(
        model_id="cli-test-model",
        files=(
            ModelFile(
                name="model.onnx",
                url=remote.as_uri(),
                size=len(MODEL_BYTES),
                sha256=hashlib.sha256(MODEL_BYTES).hexdigest(),
            ),
        ),
        licence="MIT",
        source="example.test/model",
    )
    store = ModelStore(tmp_path / "models", manifest)
    embedder = FakeImageEmbedder("cli-embedder")
    monkeypatch.setattr(composition, "build_model_store", lambda settings: store)
    monkeypatch.setattr(composition, "build_embedder", lambda s: embedder)
    monkeypatch.setenv("PMO_MODEL_DIR", str(tmp_path / "models"))

    db = tmp_path / "photos.db"
    repo = SqliteRepository(str(db))
    for name in ("a.jpg", "b.jpg"):
        file = tmp_path / name
        file.write_bytes(name.encode())
        repo.save(
            ImageMetadata(
                file_hash=f"h-{name}",
                file_info=ImageFileInfo(
                    name=name, path=str(file), size_bytes=1, mime_type="image/jpeg"
                ),
                dimensions=ImageDimensions(width=1, height=1),
                exif=ImageExifData(),
            )
        )
    repo.close()

    class Env:
        pass

    e = Env()
    e.db, e.store, e.embedder, e.tmp = str(db), store, embedder, tmp_path
    return e


def _run(monkeypatch, *argv) -> int:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main()


def _embedded(env) -> int:
    repo = SqliteRepository(env.db)
    try:
        return SqliteAnalysisRepository(repo.connection, repo.lock).count_embeddings(
            env.embedder.model_id
        )
    finally:
        repo.close()


def _tags(env, file_hash: str):
    repo = SqliteRepository(env.db)
    try:
        return SqliteAnalysisRepository(repo.connection, repo.lock).list_ai_tags(file_hash)
    finally:
        repo.close()


class TestConsent:
    def test_without_the_model_it_explains_the_download_and_does_nothing(
        self, env, monkeypatch, capsys
    ):
        assert _run(monkeypatch, "analyze", "--db", env.db) == 1
        out = capsys.readouterr().out
        assert "--download" in out and "MIT" in out and "example.test/model" in out
        assert not env.store.is_installed()
        assert _embedded(env) == 0

    def test_a_download_needs_confirmation_when_nobody_can_answer(self, env, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", type("S", (), {"isatty": lambda self: False})())
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download") == 1
        assert "--yes" in capsys.readouterr().err
        assert not env.store.is_installed()

    def test_answering_no_downloads_nothing(self, env, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", type("S", (), {"isatty": lambda self: True})())
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download") == 1
        assert not env.store.is_installed()
        assert "nothing was downloaded" in capsys.readouterr().out.lower()

    def test_answering_yes_downloads_then_analyses(self, env, monkeypatch):
        monkeypatch.setattr(sys, "stdin", type("S", (), {"isatty": lambda self: True})())
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download") == 0
        assert env.store.is_installed()
        assert _embedded(env) == 2

    def test_yes_flag_agrees_up_front(self, env, monkeypatch):
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download", "--yes") == 0
        assert env.store.is_installed() and _embedded(env) == 2

    def test_a_failed_download_is_an_error_not_a_crash(self, env, monkeypatch, capsys):
        Path(env.tmp / "remote" / "model.onnx").write_bytes(b"x" * len(MODEL_BYTES))  # corrupt
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download", "--yes") == 1
        assert "checksum" in capsys.readouterr().err
        assert not env.store.is_installed()


class TestAnalysis:
    @pytest.fixture(autouse=True)
    def installed(self, env):
        env.store.download()

    def test_analyses_the_library_and_says_what_it_did(self, env, monkeypatch, capsys):
        assert _run(monkeypatch, "analyze", "--db", env.db) == 0
        assert "Analyzed 2 photo(s)" in capsys.readouterr().out
        assert _embedded(env) == 2

    def test_a_second_run_has_nothing_to_do(self, env, monkeypatch, capsys):
        _run(monkeypatch, "analyze", "--db", env.db)
        capsys.readouterr()
        assert _run(monkeypatch, "analyze", "--db", env.db) == 0
        assert "Nothing to analyze" in capsys.readouterr().out

    def test_suggests_tags_unless_told_not_to(self, env, monkeypatch):
        _run(monkeypatch, "analyze", "--db", env.db, "--threshold", "0")
        assert _tags(env, "h-a.jpg")
        env_clear = SqliteRepository(env.db)
        SqliteAnalysisRepository(env_clear.connection, env_clear.lock).clear_embeddings()
        env_clear.connection.execute("DELETE FROM photo_ai_tags")
        env_clear.connection.commit()
        env_clear.close()
        _run(monkeypatch, "analyze", "--db", env.db, "--no-tags")
        assert _tags(env, "h-a.jpg") == []
        assert _embedded(env) == 2

    def test_reanalyze_redoes_everything(self, env, monkeypatch, capsys):
        _run(monkeypatch, "analyze", "--db", env.db)
        capsys.readouterr()
        assert _run(monkeypatch, "analyze", "--db", env.db, "--reanalyze") == 0
        assert "Analyzed 2 photo(s)" in capsys.readouterr().out

    def test_limit_caps_a_run(self, env, monkeypatch, capsys):
        assert _run(monkeypatch, "analyze", "--db", env.db, "--limit", "1") == 0
        assert "Analyzed 1 photo(s)" in capsys.readouterr().out
        assert _embedded(env) == 1

    def test_a_file_that_fails_is_listed_and_the_exit_code_is_2(self, env, monkeypatch, capsys):
        (env.tmp / "b.jpg").unlink()
        assert _run(monkeypatch, "analyze", "--db", env.db) == 2
        out = capsys.readouterr().out
        assert "Analyzed 1 photo(s)" in out and "b.jpg" in out

    def test_the_error_list_survives_a_console_that_cannot_print_unicode(
        self, env, monkeypatch, capsys
    ):
        """Regression: a cp1252 stdout crashed on the mark that used to precede each error."""
        import io

        (env.tmp / "b.jpg").unlink()
        raw = io.BytesIO()
        monkeypatch.setattr(
            sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        )
        assert _run(monkeypatch, "analyze", "--db", env.db) == 2
        sys.stdout.flush()
        assert b"b.jpg" in raw.getvalue()

    def test_a_missing_ai_extra_is_a_clear_error(self, env, monkeypatch, capsys):
        def broken(store):
            raise ModelUnavailableError("The AI features need the optional 'ai' extra")

        monkeypatch.setattr(composition, "build_embedder", broken)
        assert _run(monkeypatch, "analyze", "--db", env.db) == 1
        assert "'ai' extra" in capsys.readouterr().err


class TestRetag:
    def test_recomputes_tags_without_embedding_again(self, env, monkeypatch, capsys):
        assert _run(monkeypatch, "analyze", "--db", env.db, "--download", "--yes") == 0
        capsys.readouterr()
        calls = []
        real = env.embedder.embed_image
        monkeypatch.setattr(
            env.embedder, "embed_image", lambda *a, **k: calls.append(1) or real(*a, **k)
        )
        assert _run(monkeypatch, "analyze", "--db", env.db, "--retag", "--threshold", "0") == 0
        assert calls == []
        assert _tags(env, "h-a.jpg")

    def test_with_nothing_analysed_says_so(self, env, monkeypatch, capsys):
        env.store.download()
        assert _run(monkeypatch, "analyze", "--db", env.db, "--retag") == 0
        assert "Nothing to retag" in capsys.readouterr().out

    def test_cannot_be_combined_with_no_tags(self, env, monkeypatch, capsys):
        env.store.download()
        assert _run(monkeypatch, "analyze", "--db", env.db, "--retag", "--no-tags") == 1
        assert "--no-tags" in capsys.readouterr().err
