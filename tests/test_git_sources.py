import subprocess
import tempfile
import unittest
from pathlib import Path

from skill_atlas.git_sources import SourceSecurityError, sync_source
from skill_atlas.models import SourceSpec


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_all(repository: Path, message: str) -> str:
    _git("add", ".", cwd=repository)
    _git(
        "-c",
        "user.name=Skill Atlas Tests",
        "-c",
        "user.email=skill-atlas@example.invalid",
        "commit",
        "-m",
        message,
        cwd=repository,
    )
    return _git("rev-parse", "HEAD", cwd=repository)


def make_local_fixture_repository(root: Path) -> tuple[Path, str]:
    dependency = root / "dependency"
    dependency.mkdir()
    _git("init", cwd=dependency)
    (dependency / "dependency.txt").write_text("not checked out\n", encoding="utf-8")
    _commit_all(dependency, "dependency")

    repository = root / "source"
    repository.mkdir()
    _git("init", cwd=repository)
    skill = repository / "skills" / "example"
    (skill / "assets").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "references").mkdir()
    (skill / "SKILL.md").write_text("# Example\n", encoding="utf-8")
    (skill / "assets" / "template.txt").write_text("template\n", encoding="utf-8")
    (skill / "scripts" / "run.py").write_text("print('safe')\n", encoding="utf-8")
    (skill / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
    (repository / "ROOT-NOTES.md").write_text("whole direct checkout\n", encoding="utf-8")
    _commit_all(repository, "initial source")
    _git(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        dependency.as_uri(),
        "vendor/submodule",
        cwd=repository,
    )
    expected_sha = _commit_all(repository, "add untrusted submodule")
    return repository, expected_sha


def make_local_archive_repository(root: Path) -> tuple[Path, str]:
    repository = root / "archive"
    repository.mkdir()
    _git("init", cwd=repository)
    selected = repository / "skills" / "alice" / "calendar"
    (selected / "assets" / "icons").mkdir(parents=True)
    (selected / "references").mkdir()
    (selected / "SKILL.md").write_text("# Calendar\n", encoding="utf-8")
    (selected / "assets" / "icons" / "calendar.svg").write_text(
        "<svg/>\n", encoding="utf-8"
    )
    (selected / "references" / "usage.md").write_text("usage\n", encoding="utf-8")
    other = repository / "skills" / "bob" / "research"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("# Research\n", encoding="utf-8")
    (repository / "README.md").write_text("archive\n", encoding="utf-8")
    return repository, _commit_all(repository, "archive source")


class GitSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.temporary_directory.name)
        self.cache = self.tempdir / "cache"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_sync_pins_commit_without_submodules_and_keeps_complete_direct_bundle(self):
        remote, expected_sha = make_local_fixture_repository(self.tempdir)

        resolved = sync_source(SourceSpec.for_test(remote.as_uri()), self.cache)

        self.assertEqual(expected_sha, resolved.commit)
        self.assertEqual(self.cache / "test--source", resolved.checkout)
        self.assertTrue((resolved.checkout / "skills/example/SKILL.md").is_file())
        self.assertTrue(
            (resolved.checkout / "skills/example/assets/template.txt").is_file()
        )
        self.assertTrue((resolved.checkout / "skills/example/scripts/run.py").is_file())
        self.assertTrue(
            (resolved.checkout / "skills/example/references/guide.md").is_file()
        )
        self.assertTrue((resolved.checkout / "ROOT-NOTES.md").is_file())
        self.assertFalse((resolved.checkout / "vendor/submodule/.git").exists())
        self.assertFalse((resolved.checkout / "vendor/submodule/dependency.txt").exists())

    def test_archive_checkout_keeps_entire_selected_skill_and_omits_other_skills(self):
        remote, expected_sha = make_local_archive_repository(self.tempdir)
        source = SourceSpec(
            id="test/source",
            url=remote.as_uri(),
            mode="archive",
            include_paths=["skills/alice/calendar"],
        )

        resolved = sync_source(source, self.cache)

        self.assertEqual(expected_sha, resolved.commit)
        self.assertTrue((resolved.checkout / "skills/alice/calendar/SKILL.md").is_file())
        self.assertTrue(
            (
                resolved.checkout
                / "skills/alice/calendar/assets/icons/calendar.svg"
            ).is_file()
        )
        self.assertTrue(
            (resolved.checkout / "skills/alice/calendar/references/usage.md").is_file()
        )
        self.assertFalse((resolved.checkout / "skills/bob/research/SKILL.md").exists())

    def test_archive_cache_becomes_complete_when_source_changes_to_direct(self):
        remote, expected_sha = make_local_archive_repository(self.tempdir)
        archive_source = SourceSpec(
            id="test/source",
            url=remote.as_uri(),
            mode="archive",
            include_paths=["skills/alice/calendar"],
        )
        sparse = sync_source(archive_source, self.cache)
        self.assertFalse((sparse.checkout / "skills/bob/research/SKILL.md").exists())

        direct_source = SourceSpec.for_test(remote.as_uri())
        complete = sync_source(direct_source, self.cache)

        self.assertEqual(expected_sha, complete.commit)
        self.assertTrue((complete.checkout / "skills/bob/research/SKILL.md").is_file())
        sparse_state = subprocess.run(
            [
                "git",
                "-C",
                str(complete.checkout),
                "sparse-checkout",
                "list",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, sparse_state.returncode)

    def test_rejects_non_https_production_source(self):
        source = SourceSpec(id="bad/repo", url="http://example.com/repo", mode="direct")

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)

    def test_rejects_file_url_not_created_as_test_source(self):
        source = SourceSpec(
            id="owner/repo",
            url=(self.tempdir / "source").as_uri(),
            mode="direct",
        )

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)

    def test_rejects_archive_path_traversal_before_clone(self):
        source = SourceSpec(
            id="test/source",
            url=(self.tempdir / "missing").as_uri(),
            mode="archive",
            include_paths=["skills/alice/calendar", "../outside"],
        )

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)

    def test_rejects_option_shaped_git_ref_before_clone(self):
        source = SourceSpec(
            id="test/source",
            url=(self.tempdir / "missing").as_uri(),
            mode="direct",
            ref="--upload-pack=malicious",
        )

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)

    def test_existing_cache_fetches_configured_ref_detached_without_running_hook(self):
        remote, first_sha = make_local_fixture_repository(self.tempdir)
        branch = _git("branch", "--show-current", cwd=remote)
        source = SourceSpec.for_test(remote.as_uri())
        source.ref = branch
        first = sync_source(source, self.cache)
        self.assertEqual(first_sha, first.commit)

        hook_sentinel = self.tempdir / "hook-ran"
        hook = first.checkout / ".git" / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {hook_sentinel}\n", encoding="utf-8")
        hook.chmod(0o755)
        stale = first.checkout / "skills" / "stale" / "SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("# Stale\n", encoding="utf-8")

        new_reference = remote / "skills" / "example" / "references" / "new.md"
        new_reference.write_text("new\n", encoding="utf-8")
        expected_sha = _commit_all(remote, "update selected ref")

        updated = sync_source(source, self.cache)

        self.assertEqual(expected_sha, updated.commit)
        self.assertTrue(
            (updated.checkout / "skills/example/references/new.md").is_file()
        )
        self.assertFalse(stale.exists())
        self.assertFalse(hook_sentinel.exists())
        symbolic_ref = subprocess.run(
            ["git", "-C", str(updated.checkout), "symbolic-ref", "-q", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, symbolic_ref.returncode)

    def test_locked_sync_checks_out_exact_commit_without_advancing_to_remote_head(self):
        remote, locked_sha = make_local_fixture_repository(self.tempdir)
        source = SourceSpec.for_test(remote.as_uri())
        first = sync_source(source, self.cache)
        self.assertEqual(locked_sha, first.commit)

        (remote / "NEW-HEAD.txt").write_text("newer\n", encoding="utf-8")
        newer_sha = _commit_all(remote, "advance remote")
        self.assertNotEqual(locked_sha, newer_sha)

        resolved = sync_source(source, self.cache, locked_commit=locked_sha)

        self.assertEqual(locked_sha, resolved.commit)
        self.assertFalse((resolved.checkout / "NEW-HEAD.txt").exists())

    def test_rejects_git_metadata_symlinked_outside_checkout(self):
        remote, _ = make_local_fixture_repository(self.tempdir)
        source = SourceSpec.for_test(remote.as_uri())
        resolved = sync_source(source, self.cache)
        git_metadata = resolved.checkout / ".git"
        external_metadata = self.tempdir / "external-git-metadata"
        git_metadata.rename(external_metadata)
        git_metadata.symlink_to(external_metadata, target_is_directory=True)
        fetch_head_existed = (external_metadata / "FETCH_HEAD").exists()

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)

        self.assertEqual(
            fetch_head_existed,
            (external_metadata / "FETCH_HEAD").exists(),
        )

    def test_rejects_linked_worktree_git_metadata_file(self):
        remote, _ = make_local_fixture_repository(self.tempdir)
        source = SourceSpec.for_test(remote.as_uri())
        resolved = sync_source(source, self.cache)
        git_metadata = resolved.checkout / ".git"
        external_metadata = self.tempdir / "linked-worktree-metadata"
        git_metadata.rename(external_metadata)
        git_metadata.write_text(f"gitdir: {external_metadata}\n", encoding="utf-8")

        with self.assertRaises(SourceSecurityError):
            sync_source(source, self.cache)


if __name__ == "__main__":
    unittest.main()
