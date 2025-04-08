#!/usr/bin/env python3
import inspect
import os
import tarfile
import time
from pathlib import Path
from unittest import mock

import pytest

from yo.tasks import build_tarball
from yo.tasks import standardize_globs
from yo.tasks import YoTask
from yo.util import YoExc


@pytest.fixture(autouse=True)
def mock_all_tasks():
    with mock.patch("yo.tasks.list_tasks") as m:
        m.return_value = [
            "task_one",
            "task_two",
            "task_three",
            "task_four",
            "task_five",
            "task_six",
        ]
        yield


def test_depends_conflicts():
    contents = inspect.cleandoc(
        """
        DEPENDS_ON task_one
        DEPENDS_ON task_two
        MAYBE_DEPENDS_ON task_three
        MAYBE_DEPENDS_ON dne_one
        CONFLICTS_WITH task_four
        CONFLICTS_WITH dne_two
        PREREQ_FOR task_five
        PREREQ_FOR dne_three
        """
    )

    task = YoTask.create_from_string("test_task", contents)

    # the maybe_depends_on dne_one is dropped since it doesn't exist
    assert task.dependencies == ["task_one", "task_two", "task_three"]
    # all conflicts are kept
    assert task.conflicts == ["task_four", "dne_two"]
    # all prereqs are kept
    assert task.prereq_for == ["task_five", "dne_three"]

    assert task.script == contents.replace(
        "MAYBE_DEPENDS_ON dne_one",
        "# MAYBE_DEPENDS_ON dne_one",
    ).replace("MAYBE_DEPENDS_ON task_three", "DEPENDS_ON task_three")


def test_include_files():
    contents = inspect.cleandoc(
        """
        INCLUDE_FILE ~/.profile
        INCLUDE_FILE ~/Documents/"Important File.docx" /usr/share/docs/"Important File".docx
        INCLUDE_FILE ~/dotfiles/bashrc_oci.sh ~/.bashrc
        MAYBE_INCLUDE_FILE ~/.cache/yo.*.json ~/.cache/
        SENDFILE ~/data.tar.gz
        SENDFILE ~/"Special File"
        """
    )

    task = YoTask.create_from_string("test_task", contents)
    assert task.include_files == [
        ("~/.profile", "~/.profile", False),
        (
            "~/Documents/Important File.docx",
            "/usr/share/docs/Important File.docx",
            False,
        ),
        ("~/dotfiles/bashrc_oci.sh", "~/.bashrc", False),
        ("~/.cache/yo.*.json", "~/.cache/", True),
    ]
    assert task.sendfiles == [
        Path.home() / "data.tar.gz",
        Path.home() / "Special File",
    ]

    expected_contents = "\n".join("# " + line for line in contents.split("\n"))
    assert task.script == expected_contents
    assert task.script == expected_contents


def test_wrong_args():
    cases = [
        "INCLUDE_FILE",
        "MAYBE_INCLUDE_FILE",
        "INCLUDE_FILE one two three",
        "MAYBE_INCLUDE_FILE one two three",
        "SENDFILE",
        "SENDFILE one two",
    ]
    for case in cases:
        with pytest.raises(YoExc):
            YoTask.create_from_string("test_task", case)


def test_standardize_globs():
    assert standardize_globs(
        [
            # The standard: copy to the same path
            ("~/.bashrc", "~/.bashrc", False),
            # An unusual: copy from homedir to a system path
            ("~/.bashrc", "/etc/bashrc", False),
            # Also unusual: copy from system path to homedir
            ("/etc/bashrc", "~/.bashrc", True),
        ]
    ) == (
        [
            (str(Path.home() / ".bashrc"), ".bashrc", False),
            ("/etc/bashrc", ".bashrc", True),
        ],
        [
            (str(Path.home() / ".bashrc"), "etc/bashrc", False),
        ],
    )

    # neither side can be relative
    failing = [
        [("relative path", "~/.bashrc", False)],
        [("/foobar", ".bashrc", False)],
    ]
    for case in failing:
        with pytest.raises(YoExc):
            standardize_globs(case)


def create_test_dir(tmp_path):
    # The important cases to cover are:
    # 1. A regular file
    # 2. A directory being included recursively
    # 3. A glob matching several files or directories
    tarball = tmp_path / "tarball.tar.gz"

    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("export PS2='$ '")

    bash_history = tmp_path / ".bash_history"
    bash_history.write_text(":(){ :|:& };:")

    note_dir = tmp_path / "my-notes"
    note_dir.mkdir()
    note_one = note_dir / "one.txt"
    note_one.write_text("some data")
    note_two = note_dir / "two.txt"
    note_two.write_text("some other data")
    unmatched_note = note_dir / "not included.md"
    unmatched_note.write_text("I won't be in the tarball")

    doc_dir = tmp_path / "my-docs"
    doc_dir.mkdir()
    doc_one = doc_dir / ".hidden_document"
    doc_one.write_text("test data")
    doc_two = doc_dir / "an important, space-filled document title"
    doc_two.write_text("more test data!")
    doc_subdir = doc_dir / "Project"
    doc_subdir.mkdir()
    project_doc = doc_subdir / "Rollout plan.md"
    project_doc.write_text(
        "steps 1: write a plan, step 2: ???, step 3: profit!"
    )

    included = [
        bashrc,
        note_one,
        note_two,
        doc_dir,
        doc_one,
        doc_two,
        doc_subdir,
        project_doc,
    ]
    excluded = [unmatched_note, bash_history]
    return tarball, included, excluded


def test_build_tarball_skip(tmp_path):
    ctx = mock.Mock()
    name = "test_task"

    tarball, included, excluded = create_test_dir(tmp_path)
    base = str(tmp_path)
    include_files = [
        (f"{base}/.bashrc", ".bashrc", False),
        (f"{base}/my-notes/*.txt", "notes/", False),
        (f"{base}/my-docs/", "docs/", False),
    ]

    TEST_TIME = int(time.time())

    # Set the mtimes to be older than the tarball
    for path in included:
        os.utime(path, times=(TEST_TIME, TEST_TIME - 5))
    # Set the excluded paths to be newer than the tarball,
    # demonstrating that they don't impact the generation.
    for path in excluded:
        os.utime(path, times=(TEST_TIME, TEST_TIME + 5))

    tarball.write_text("foobar")
    os.utime(tarball, times=(TEST_TIME, TEST_TIME))

    with mock.patch("yo.tasks.subprocess") as m:
        build_tarball(ctx, include_files, tmp_path, tarball, name)
        # Subprocess should not have been called at all
        assert not m.mock_calls
        # Ctx should not have been called at all
        assert not ctx.mock_calls

    # ensure that making any file newer results in a rebuilt tarball
    for path in included:
        os.utime(path, times=(TEST_TIME, TEST_TIME + 5))
        with mock.patch("yo.tasks.subprocess") as m:
            build_tarball(ctx, include_files, tmp_path, tarball, name)
            assert m.mock_calls
            assert ctx.mock_calls
            ctx.reset_mock()
        os.utime(path, times=(TEST_TIME, TEST_TIME - 5))


def test_build_tarball(tmp_path):
    ctx = mock.Mock()
    name = "test_task"

    tarball, included, excluded = create_test_dir(tmp_path)
    base = str(tmp_path)
    include_files = [
        (f"{base}/.bashrc", ".bashrc", False),
        (f"{base}/my-notes/*.txt", "notes/", False),
        (f"{base}/my-docs/", "docs/", False),
    ]

    with mock.patch("yo.tasks.subprocess") as m:
        build_tarball(ctx, include_files, tmp_path, tarball, name)
        assert len(m.run.mock_calls) == 1
        assert m.run.mock_calls[0].args[0][:3] == ["tar", "-czhf", tarball]
        assert sorted(m.run.mock_calls[0].args[0][3:]) == sorted(
            [".bashrc", "notes/one.txt", "notes/two.txt", "docs"]
        )
        ctx.con.log.assert_called()


def test_real_tarball(tmp_path):
    ctx = mock.Mock()
    name = "test_task"

    tarball, included, excluded = create_test_dir(tmp_path)
    base = str(tmp_path)
    include_files = [
        (f"{base}/.bashrc", ".bashrc", False),
        (f"{base}/my-notes/*.txt", "notes/", False),
        (f"{base}/my-docs/", "docs/", False),
    ]

    build_tarball(ctx, include_files, tmp_path, tarball, name)
    ctx.con.log.assert_called()

    tf = tarfile.open(tarball)
    expected_members = [
        ".bashrc",
        "notes/one.txt",
        "notes/two.txt",
        "docs",
        "docs/.hidden_document",
        "docs/an important, space-filled document title",
        "docs/Project",
        "docs/Project/Rollout plan.md",
    ]
    assert sorted(tf.getnames()) == sorted(expected_members)
