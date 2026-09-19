import shutil
import subprocess
from pathlib import Path

from memex.infrastructure.workspace_context import project_context, project_identity

_GIT = shutil.which("git") or "/usr/bin/git"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run([_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: S603


def _repo(tmp_path: Path, name: str = "memex") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init")
    return repo


def test_github_origin_uses_git_repo_locator(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "remote", "add", "origin", "git@github.com:example/memex.git")

    context = project_context(repo)

    assert context.label == "memex"
    assert context.locator == "git-memex"
    assert project_identity(repo) == (context.project_id, "memex")


def test_self_hosted_origin_uses_git_repo_locator(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "remote", "add", "origin", "ssh://git@gitlab.enterprise.local/group/Memex.git")

    context = project_context(repo)

    assert context.locator == "git-memex"


def test_local_git_without_origin_uses_folder_locator(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Local Memex")

    context = project_context(repo)

    assert context.label == "Local Memex"
    assert context.locator == "local-memex"


def test_non_git_folder_uses_folder_locator(tmp_path: Path) -> None:
    folder = tmp_path / "Plain Workspace"
    folder.mkdir()

    context = project_context(folder)

    assert context.label == "Plain Workspace"
    assert context.locator == "plain-workspace"
