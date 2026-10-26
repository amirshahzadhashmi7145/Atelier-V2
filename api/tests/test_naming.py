"""Naming conventions for project folders, branches, commits, and PR titles."""

from __future__ import annotations

from runtime import naming


def test_slug_is_clean_kebab_case():
    assert naming.slug("Connect Four!") == "connect-four"
    assert naming.slug("  Tic / Tac  Toe  ") == "tic-tac-toe"
    assert naming.slug("") == "project"
    assert naming.slug("***") == "project"


def test_slug_caps_length_without_trailing_hyphen():
    out = naming.slug("a" * 30 + " " + "b" * 40, max_len=50)
    assert len(out) <= 50
    assert not out.endswith("-")


def test_task_branch_is_readable_with_short_id():
    assert naming.task_branch("Add a landing page", "task_1041") == "task/add-a-landing-page-1041"
    # Falls back gracefully when there is no task text.
    assert naming.task_branch("", "run_7") == "task/project-7"


def test_push_branch_is_studio_prefixed_and_timestamped():
    branch = naming.push_branch("tidy up")
    assert branch.startswith("studio/tidy-up-")
    assert "/" in branch and " " not in branch


def test_commit_and_pr_title_are_tidy():
    assert naming.commit_message("  add   dark mode  ") == "Add dark mode"
    assert naming.commit_message("") == "Update from Agent Studio"
    assert naming.pr_title("fix the thing") == "Fix the thing"
    assert len(naming.commit_message("x " * 100)) <= 72
