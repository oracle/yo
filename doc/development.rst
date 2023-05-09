Development
===========

You can find the source code for yo
`here <https://github.com/oracle/yo>`_. You are welcomed to participate
in its development in many ways:

- Report bugs via issues
- Submit merge requests with your new features or bug fixes, if you'd like.

This document contains information about how to get a development environment
set up, and how to do the main development processes.

Environment Setup
-----------------

There are some prerequisite dependencies you should have available on your
system. I develop on my Ubuntu 22.04 system, but development should be possible
on any suitably recent Linux system (or even macOS) with an appropriate Python
version (3.6 or higher). You'll need to ensure that ``~/.local/bin`` is in your
``$PATH`` environment variable, and you'll also want to double check that
standard unix tools such as make, git, cut, and sed are installed.

First, clone the repository (or your fork, if applicable) and install
development tools:

.. code:: bash

   git clone git@github.com:oracle/yo
   cd yo
   make development

This last command will use your system Python 3 (defaults to the command
``python3``, but configurable via ``make PYTHON=python_cmd``) to install some
tools to your home directory:

- tox: a Python test runner framework
- pre-commit: a tool for executing code checks and formatters before committing
  code.

Assuming you already had installed yo on this computer, then you should be all
set to begin running it directly from the git checkout, rather than the
installed copy. To run from the git checkout:

1. Ensure that your current directory is the root of the git repository.
2. Rather than using the command ``yo``, use the command ``python3 -m yo``.
   Python will see the yo package in your current working directory, and execute
   that instead.

Editable Install
~~~~~~~~~~~~~~~~

**If you enjoy living on the edge,** then you can set up your system so that
whenever you run ``yo``, it always comes from whatever is in your git checkout.
Simply run the following command from the root of the git repo:

.. code:: bash

   # only for those who want to live on the edge:
   python3 -m pip install --user --editable .

.. warning::

   Note that now, if your development copy has a bug, then yo will be unusable
   on your whole system. If you'd prefer not to have this risk, then don't use
   this method!

Creating and Testing Changes
----------------------------

If you want to contribute a change, then make sure you create a fork, and set
that as your git origin. Then, make sure your branch is up to date with
upstream/master, and create a branch to work on your changes.

When you've verified your changes work and you're happy with them, be sure to
run the tests. You should be able to run them simply with ``make test``. There
are currently only a few tests written, and it would be excellent if you add
tests for your change (see the ``tests/`` directory). The test framework will
attempt to run the tests on Python versions 3.6-3.10, but it's ok if you only
have one suitable version installed.

If the tests pass, then you can go ahead and commit your changes. The pre-commit
hooks will verify a few things:

1. Your Python code files should have type annotations for functions and
   classes.
2. The mypy type checker should verify that there are no invalid operations
   based on the declared types. Note that Python type checking is a bit finicky
   at this point. If you have any issues with this (the "mypy" pre-commit hook),
   please reach out via Github Issue and we'll try to help you out.
3. The black code formatter will automatically reformat your changes to ensure
   they meet the existing code style.
4. The flake8 static checker will run static checks for low-hanging fruit bugs.

Some of these hooks will automatically edit your code (leaving unstaged
changes). Review these changes and ``git add`` them when you're satisfied. Other
hooks will simply output error line numbers for you to fix. After one or two
tries, you should satisfy the static checks. If you have too much trouble, you
can use ``git commit --no-verify``, but please note that in your merge request
and note what the issue was.

At this point, you can now push your branch up to your Github fork and make a
review request via the UI.

Here's a checklist for things you may want to include in your changes.

- If you've added a command, be sure to document it in
  ``doc/guide/commands.md``.
- If you've added a configuration option, be sure to document it in
  ``doc/guide/configuration.rst``.
- If your change is user-facing at all (fixing a bug, adding a feature), then
  document it in the "Unreleased" section of the ``CHANGELOG.md``.
