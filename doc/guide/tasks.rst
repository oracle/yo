Tasks
=====

.. _tasks_overview:

An Overview Of Yo Tasks
-----------------------

Tasks are a yo feature which enable you to run Bash scripts on your instance
remotely, without being connected to it. The command output and exit status are
recorded for your viewing later.

On its own, a feature like this isn't very useful, because you can just run
those scripts manually within a program like screen or tmux. What makes tasks
interesting is that yo maintains an internal library of them (and you can add
your own to it), and the tasks can be automatically started as an instance is
launched, without any human interaction.

What this means is that you can think of a task as a way to configure your
instance without having to do it manually at the beginning of every session. If
the main functionality of yo liberates you from needing to manually use the OCI
console and juggle IP addresses and SSH keys, then the task feature liberates
you from installing dependencies and setting up your instance once you've
connected to it.

Here are a few use cases for tasks, which you may want to consider:

- Automatically installing and activating a proxy so your instance has Internet
  access.
- Setting up software such as ``drgn`` or ``mosh`` without needing to understand
  the details of installation.
- Placing personal configuration files and user scripts onto the system (e.g.
  bashrc customizations and personal tools).
- Once you've figured out a way to reproduce a bug, place the configuration and
  setup steps into a task so you can easily return to it in the future.

Tasks aren't always a perfect solution. They have some limitations that you may
want to consider:

- Yo doesn't have a way to trigger a reboot from within a task, and then
  continue running more commands. So you can't easily install a custom kernel
  and reboot into it.
- Tasks that take a long time (e.g. long package installations) may not be well
  suited to re-running them each time you start an instance. You may want to
  look into creating an image from your instance after you've configured it. The
  downside of this approach is that your image will be static and based on a
  single OS version, whereas a well-written task is just a set of instructions,
  and can be run on any compatible image as newer versions are released. Of
  course, creating a custom image is difficult, and tasks are much easier to
  write!

Creating Tasks
--------------

Tasks are identified by their filename. Yo searches for them in a list of
directories, using the first one it finds:

- ``~/.oci/yo-tasks`` (referred to as the "user task directory")
- Yo's installation directory (don't modify these!)

Since the user task directory is first in the list, you're able to override any
task you'd like with a newer version. The tasks are always run with ``bash`` and
don't need to be marked executable.

Once you've created your script, there's no more bookkeeping necessary. Yo will
find the script when you ask to use it.

Special Task Syntax
-------------------

While tasks are generally normal bash scripts, there are a few special syntactic
elements which are available to you. These are implemented in a rather unique
way: as Yo loads your script, it reads each line and detects the use of the
following keywords, somewhat like a macro processor. Most of these keywords also
have a corresponding bash function that Yo provides to implement the necessary
functionality.

- ``DEPENDS_ON <task name here>`` - this declares that your task depends on
  another one. Yo will search for these lines in your script and automatically
  find and load that script too. The bash function will wait for the successful
  completion of the dependency, or else it will exit with a failure message.

- ``MAYBE_DEPENDS_ON <task name here>`` - this is similar to ``DEPENDS_ON``, but
  it is optional. If Yo finds a task with that name, then it will replace this
  with ``DEPENDS_ON`` and include the dependency . Otherwise, it will comment
  out this line and continue without error. This allows you to specify
  dependencies that only get run if they exist. A common use case for this is
  for networking configuration. Some tenancies or VCNs have no direct Internet
  access except via a proxy. Scripts should use ``MAYBE_DEPENDS_ON networking``
  if they access the Internet, which allows users who require a proxy to
  implement a ``networking`` task to configure it.

- ``CONFLICTS_WITH <task name here>`` - this could be helpful for declaring that
  your task won't work with other ones.

- ``RUN_ONCE`` - this function indicates that after a successful run, your
  script should not run again. It will detect a previous success, and exit with
  code 0. Note that this will still allow you to re-run a failed task.

- ``PREREQ_FOR <other task>`` - this declares that your task is a
  prerequisite of another. It can be thought of as the inverse of
  ``DEPENDS_ON``, but with one important caveat. This relationship only applies
  if the other task is actually loaded and run by Yo at the same time as this
  one. For example, suppose task ``A`` contains ``PREREQ_FOR B``. Then:

  - Specifying task ``A`` will not automatically run task ``B``
  - Similarly, specifying task ``B`` will not automatically run ``A``
  - However, if task ``A`` and ``B`` are both specified to run, then Yo will
    ensure that A runs to completion before task ``B`` begins.

- ``INCLUDE_FILE <path> [destination]`` - this declares that the given path from
  the client system should be copied to the instance. If the path is a
  directory, it will be included recursively. Paths must be either absolute
  (i.e. starting with ``/``) or relative to the home directory (i.e.  starting
  with ``~/``). By default, files are copied into the corresponding location on
  the instance, but a different ``destination`` may be specified if necessary.
  The path may also be a glob -- in which case, the destination argument must be
  provided, and it will be interpreted as a directory into which each matching
  file or directory is placed.

  This command works by building a tarball of all required files for a task,
  copying it to the instance, and extracting it into place. For more details on
  file management, see the section below.

  - The variant ``MAYBE_INCLUDE_FILE <filename> [destination]`` can be used to
    include a file if it exists on the host system. No error will be raised if
    the file does not exist.

- ``SENDFILE <filename>`` - this declares that the given filename should
  be directly copied into ``$TASK_DATA_DIR/$FILENAME``. This is a somewhat
  low-level command -- no tarball is involved. See the section below for more
  details on file management.

These functions can be used anywhere in your script, however bash variable
expansion is not respected when Yo reads and pre-processes the script. So, while
the following is valid bash, it won't work with Yo:

.. code:: bash

   TASK=drgn
   DEPENDS_ON $TASK


Other Task Variables and Functions
----------------------------------

Additionally, Yo's bash task library makes a few conveniences available to you.
It sources the contents of ``/etc/os-release`` so that you can use common
variables from this file, such as ``$NAME``, ``$VERSION_ID``, etc.  In addition,
Yo provides the following variables:

- ``$ORAVER`` - an integer representing the current Oracle Linux release. The
  variable is undefined if not running on Oracle Linux. You can detect when
  Oracle Linux is running by matching the ``NAME`` variable against ``Oracle*``

- ``$UBUVER`` - an integer representing the Ubuntu version (e.g. for 24.10, this
  would be "24"). If you would like the full version (e.g. to distinguish 24.04
  and 24.10), use the ``$VERSION_ID`` field directly.

- ``$FEDVER`` - an integer representing the Fedora version

- ``$DEBVER`` - an integer representing the Debian version

- ``$PKGMGR`` - the name of the system package manager (only detected for the
  above operating systems)

And below are the simple bash functions (not interpreted by Yo) provided in the
task library:

- ``PKG_INSTALL [package [...]]`` install one or more packages. This relies on
  the detected ``$PKGMGR`` from above, and ensures that the correct options are
  used for the specific package manager, especially to avoid interactive
  confirmation.

Managing Tasks
--------------

At any time, you can view all available tasks with ``yo task-list``. You can get
details about a particular task using ``yo task-info``. This will essentially
dump the script contents to stdout, along with a header giving its file
location and other info.

You can manually start a task on an instance with ``yo task-run``. The first
argument to this command is the instance name, which can be omitted if you only
have one running. The second argument is the name of the task. For example:

.. code::

    # Only one instance is running, start "test-task" on that
    yo task-run test-task

    # Start "test-task" on instance "vm3". Wait for completion.
    yo task-run vm3 test-task --wait

You can also use ``yo task-join [inst]`` to wait for all currently running
tasks. Finally, you can get a bird's eye view of all tasks running on an
instance with ``yo task-status [inst]``. If a task fails, or if you just want
more information, you can go into the ``/tmp/tasks`` directory on your instance.
Each task gets a directory, with the following files:

- ``output`` - stdout and stderr of the task (which is executed with ``bash -x``
  so you can see each command executed).
- ``pid`` - process ID of the parent for this task
- ``status`` - exit status of the task
- ``wait`` - while a task waits for a dependency, it writes the name of the
  dependency into this file, and deletes it once the wait completes

The task directory can be configured from its default (``/tmp/tasks``) using the
:ref:`task_dir<config_task_dir>` configuration option.

Running Tasks at Launch Time
----------------------------

With the ``--task`` argument to ``yo launch``, you can request that a task be
executed at startup. This will result in your command automatically waiting for
the instance to start, and then waiting for SSH access, so that yo can then run
the task.

You can specify the ``--task`` option multiple times, so it's valid to do
something like this:

.. code:: bash

   yo launch -p ol8 -t ocid -t drgn -s

What's more, you can even specify tasks inside an instance profile. This makes
it quite easy to automatically get an instance with particular tools installed
without thinking of it. See the configuration option :ref:`config_tasks`.

By using the ``--ssh`` or ``--wait`` arguments to ``yo launch``, along with
specifying tasks to run, you will automatically get SSH'd into your instance
once all the tasks are completed and your environment is ready. For bonus
points, consider setting up the :ref:`notify_prog` configuration, which will
allow you to receive a desktop notification when your instance is ready. This is
quite convenient to allow you to focus on another task while your instance boots
and self-configures.

Please note that tasks specified in an instance profile cannot be removed from
the profile on the command line. You can only specify _additional_ tasks to run.

Specifying Files for Tasks
--------------------------

Tasks can be included onto an instance with two mechanisms, ``INCLUDE_FILE`` and
``SENDFILE``, described above. The implementation of these commands is described
here in a bit more detail, so you can understand what's happening under the hood
and make use of them well.

Files copied by ``INCLUDE_FILE`` are split into two groups: user files (those
whose destination is prefixed by ``~/``, and thus are destined for the home
directory), and system files (those whose destination starts with ``/``). The
user files are placed into a tarball called ``user.tar.gz``, and the system
files go into ``system.tar.gz``. Yo caches these files in
``~/.cache/yo-tasks/$TASK/`` for each task. When a task is launched, Yo
enumerates all the files that will be included, and if any are more recent than
the cached tarball, it rebuilds the tarball.

The idea behind ``INCLUDE_FILE`` is that it allows you to automatically include
useful files from your client system directly onto the instance. As an example,
you might want to include your ``~/.bashrc``, ``~/.vimrc`` and a collection of
useful scripts. You can create a custom task which does so quite easily:

.. code::

   INCLUDE_FILE ~/.bashrc
   INCLUDE_FILE ~/.vimrc
   INCLUDE_FILE ~/oci-scripts ~/bin

So the hope is that this mechanism will suit most use cases. However, there may
be other cases that are more complex. For that, we have ``SENDFILE``.

Files copied by ``SENDFILE`` have none of the above logic applied to them. They
are copied directly to the instance into the ``$TASK_DATA_DIR``. Then your
script can process it however you would like. For instance, you may want to
distribute a tarball containing software that your script will install manually.
That could be achieved like so:

.. code::

   SENDFILE ~/Software/mypkg-1.2.3.tar.gz

   PKG_INSTALL dependency1-devel dependency2-devel
   mkdir build
   cd build
   tar xf $TASK_DATA_DIR/mypkg-1.2.3.tar.gz
   cd mypkg-1.2.3
   ./configure --prefix=$HOME/.local
   make -j $(nproc)
   make install
   cd ../..
   rm -rf build $TASK_DATA_DIR/mypkg-1.2.3.tar.gz

Finally, there's one implementation detail worth noting: after Yo creates the
``user.tar.gz`` and ``system.tar.gz`` tarballs, it treats them like any other
file specified with ``SENDFILE``, except for one crucial difference. Files with
those names get automatically extracted into the correct places by Yo's task
launcher stub program. This means that you can elect to build your own archives
that contain exactly what you want (rather than using ``INCLUDE_FILE`` to build
them at runtime), and then specify them using ``SENDFILE``. Yo will extract
those just the same as it does for the archives it creates.

Builtin Tasks
-------------

- ```drgn`` - install drgn and (if possible) kernel debuginfo, supported on
  Oracle Linux 8 and later.
- ``ocid`` - enable and run the ``ocid`` service, which can automatically
  respond to OCI actions like resizing block volumes in sensible ways.

The following task names are used as optional dependencies by ``yo``, but no
task is included by that name, to allow users to customize their setup:

- ``networking`` - used as an optional dependency by tasks requiring Internet
  access. The implementation should configure networking so that dependent tasks
  can automatically begin using it.

Tasks - Future Work
-------------------

Most of the work planned for tasks is now completed. However, one additional
feature which could be nice is the ability to pass variables or file data to a
task script. I'm currently waiting for a use case before building this feature.

I'd also like to be able to support rebooting an instance with a custom kernel,
this could save some preparation time in bug reproduction. However, I'm not
currently clear how to implement it, which is why it's future work.

Finally, tasks all have a timeout around 10 minutes. This timeout value is
hardcoded around the code base and not particularly customizable. If you write a
particularly long task, you risk timing out, without a clear way to resolve it.
So one final piece of work is to resolve that and allow longer task timeouts.
