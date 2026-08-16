"""Repository-level pre-commit configuration contracts."""

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[2]
WHITESPACE_HOOKS = ("trailing-whitespace", "end-of-file-fixer")


def _hook_exclude(hook_id: str) -> str:
    """Return the exclude expression configured for a pre-commit hook."""
    config = yaml.safe_load((PROJECT_ROOT / ".pre-commit-config.yaml").read_text())
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    hook = next(candidate for candidate in hooks if candidate["id"] == hook_id)
    return hook.get("exclude", "")


@pytest.mark.parametrize("hook_id", WHITESPACE_HOOKS)
@pytest.mark.parametrize(
    "path",
    (
        "tests/fixtures/blns.txt",
        "tests/fixtures/183-libreoffice.html",
        "Becky Bennett (2).json",
        "benchmark_word_based.txt",
        "src/promptgrimoire/elements/sortable/dist/index.js.map",
        "src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js",
    ),
)
def test_whitespace_hooks_preserve_byte_sensitive_corpora_and_generated_files(
    hook_id: str,
    path: str,
) -> None:
    """Whitespace hooks must not mutate byte-sensitive or generated inputs."""
    exclude = _hook_exclude(hook_id)
    assert exclude
    assert re.search(exclude, path)


@pytest.mark.parametrize("hook_id", WHITESPACE_HOOKS)
@pytest.mark.parametrize(
    "path",
    (
        "src/promptgrimoire/cli/testing.py",
        "tests/unit/test_precommit_config.py",
        "docs/deployment.md",
    ),
)
def test_whitespace_hooks_still_apply_to_maintained_text(
    hook_id: str,
    path: str,
) -> None:
    """The preservation boundary must not disable normal text hygiene."""
    assert not re.search(_hook_exclude(hook_id), path)
