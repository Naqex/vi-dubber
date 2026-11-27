from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest
import vi_dubber.separation as separation_module
import yaml
from vi_dubber.separation import (
    BLOCKED_SEPARATION_MODEL_PATTERNS,
    CommercialLicenseError,
    separate_dialogue,
    validate_separation_model_license,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "vi_dubber"
BANNED_IMPORT_ROOTS = {"diffq", "diffq_fixed", "demucs", "htdemucs"}


@pytest.mark.parametrize(
    "blocked_model",
    [
        "htdemucs_ft.yaml",
        "HTDEMUCS_6s.yaml",
        "demucs_v4",
        "models/Demucs_v4.th",
        "diffq_model.ckpt",
        "checkpoint_DIFFQ_quantized.pt",
    ],
)
def test_runtime_denylist_blocks_demucs_htdemucs_and_diffq_before_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_model: str,
) -> None:
    with pytest.raises(CommercialLicenseError) as exc_info:
        validate_separation_model_license(blocked_model)
    assert isinstance(exc_info.value, ValueError)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Separator must not be instantiated for blocked models")

    fake_package = types.ModuleType("audio_separator")
    fake_separator_module = types.ModuleType("audio_separator.separator")
    fake_separator_module.Separator = fail_if_called
    monkeypatch.setitem(sys.modules, "audio_separator", fake_package)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", fake_separator_module)

    output_dir = tmp_path / "out"
    model_dir = tmp_path / "models"
    with pytest.raises(CommercialLicenseError):
        separate_dialogue(
            tmp_path / "input.wav",
            output_dir,
            model_dir,
            blocked_model,
        )

    assert not output_dir.exists()
    assert not model_dir.exists()


@pytest.mark.parametrize(
    "blocked_arch",
    [
        "DemucsSeparator",
        "htdemucs",
        "diffq_quantizer",
    ],
)
def test_runtime_denylist_blocks_disallowed_model_arch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_arch: str,
) -> None:
    with pytest.raises(CommercialLicenseError):
        validate_separation_model_license("model.ckpt", model_arch=blocked_arch)

    separate_called = False

    class FakeModel:
        model_type = blocked_arch

    class FakeSeparator:
        def __init__(self, **_kwargs):
            self.model_instance = None

        def load_model(self, model_filename: str):
            del model_filename
            self.model_instance = FakeModel()

        def separate(self, _audio_file_path: str):
            nonlocal separate_called
            separate_called = True
            return ["Vocals.wav", "Instrumental.wav"]

    fake_package = types.ModuleType("audio_separator")
    fake_separator_module = types.ModuleType("audio_separator.separator")
    fake_separator_module.Separator = FakeSeparator
    fake_torch = types.ModuleType("torch")

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch.cuda = FakeCuda()
    monkeypatch.setitem(sys.modules, "audio_separator", fake_package)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", fake_separator_module)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    with pytest.raises(CommercialLicenseError):
        separate_dialogue(
            tmp_path / "input.wav",
            tmp_path / "out",
            tmp_path / "models",
            "model.ckpt",
        )

    assert separate_called is False


@pytest.mark.parametrize(
    "allowed_model",
    [
        "model.ckpt",
        "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        "model_bs_roformer_ep_368_sdr_12.9628.ckpt",
        "mel_band_roformer_karaoke.ckpt",
    ],
)
def test_runtime_denylist_allows_compatible_and_roformer_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allowed_model: str,
) -> None:
    assert validate_separation_model_license(allowed_model) == allowed_model

    loaded_models: list[str] = []

    class FakeSeparator:
        def __init__(self, **_kwargs):
            pass

        def load_model(self, model_filename: str):
            loaded_models.append(model_filename)

        def separate(self, _audio_file_path: str):
            return ["Vocals.wav", "Instrumental.wav"]

    fake_package = types.ModuleType("audio_separator")
    fake_separator_module = types.ModuleType("audio_separator.separator")
    fake_separator_module.Separator = FakeSeparator
    fake_torch = types.ModuleType("torch")

    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch.cuda = FakeCuda()
    monkeypatch.setitem(sys.modules, "audio_separator", fake_package)
    monkeypatch.setitem(sys.modules, "audio_separator.separator", fake_separator_module)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(separation_module, "media_duration", lambda _path: 10.0)

    vocals, instrumental = separate_dialogue(
        tmp_path / "input.wav",
        tmp_path / "out",
        tmp_path / "models",
        allowed_model,
    )

    assert loaded_models == [allowed_model]
    assert vocals.name == "Vocals.wav"
    assert instrumental.name == "Instrumental.wav"


@pytest.mark.parametrize("empty_model", ["", "   "])
def test_runtime_denylist_rejects_blank_model_filename(empty_model: str) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        validate_separation_model_license(empty_model)


def test_denylist_patterns_cover_required_blocked_families() -> None:
    assert {"demucs", "htdemucs", "diffq"}.issubset(set(BLOCKED_SEPARATION_MODEL_PATTERNS))


def test_default_config_separation_model_passes_license_guard() -> None:
    config = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    model_name = config["separation"]["model"]
    assert validate_separation_model_license(model_name) == model_name
    assert "roformer" in model_name.lower()


def test_ast_guard_zero_diffq_or_demucs_imports_in_src() -> None:
    """Verify first-party code never imports diffq/diffq_fixed/demucs.

    Note: Do not assert ``importlib.util.find_spec("diffq") is None`` here
    because dev ``.venv`` still resolves transitive ``diffq`` / ``diffq-fixed``
    from ``audio-separator==0.47.0`` (documented in
    ``docs/COMMERCIAL-LICENSE-READINESS.md``).
    """
    py_files = sorted(SRC_DIR.rglob("*.py"))
    assert len(py_files) >= 10, f"Expected vi_dubber source tree under {SRC_DIR}"

    hits: list[str] = []
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0].lower()
                    if root in BANNED_IMPORT_ROOTS:
                        hits.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0].lower()
                if root in BANNED_IMPORT_ROOTS:
                    hits.append(f"{rel}:{node.lineno}: from {node.module} import ...")

    assert hits == [], f"Blocked CC-BY-NC imports found: {hits}"
