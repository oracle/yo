Commands
========

Yo has an extensive list of commands. This section organizes and presents the
full listing and arguments for each command.

When invoking a command, the normal way is ``yo [sub-command]``. However, Yo
also allows you to use the shortest unambiguous prefix as a shortcut for a
particular command-name. For example, ``yo la`` could be used as shorthand for
``yo launch``. However, as commands are added, these aliases may stop working.
For example, once upon a time, ``yo li`` could be used as a shorthand for ``yo
list``. But in version 0.23.0 of Yo, the ``yo limits`` command was added, and
the shorthand no longer worked.

So, you may instead create an ``[aliases]`` section in your ``~/.oci/yo.ini``
file. This will disable the shortest-prefix aliasing, and allow you full control
over the aliases. See the configuration documentation for more information.

Overview
--------

Basic Commands:

  - :ref:`yo_launch` - Launch an OCI instance.
  - :ref:`yo_list` - List your OCI instances.
  - :ref:`yo_ssh` - SSH into an instance.

Instance Management:

  - :ref:`yo_nmi` - Send diagnostic interrupt (NMI) to one or more instance (dangerous)
  - :ref:`yo_protect` - Enable or disable Yo's termination protection.
  - :ref:`yo_reboot` - Reboot one or more OCI instances.
  - :ref:`yo_rebuild` - Rebuild a saved & torn down instance.
  - :ref:`yo_rename` - Give an instance a new name.
  - :ref:`yo_resize` - Resize (change shape) and reboot an OCI instance.
  - :ref:`yo_start` - Start (boot up) one or more OCI instances.
  - :ref:`yo_stop` - Stop (shut down) one or more OCI instances
  - :ref:`yo_teardown` - Save block volume and instance metadata, then terminate.
  - :ref:`yo_terminate` - Terminate one or more instances.
  - :ref:`yo_wait` - Wait for an instance to enter a state.

Instance Communication & Interaction:

  - :ref:`yo_console` - View an instance's serial console using an SSH connection
  - :ref:`yo_console_history` - Fetch and print serial console history for an instance.
  - :ref:`yo_copy_id` - Copy an SSH public key onto an instance using ssh-copy-id.
  - :ref:`yo_ip` - Print the IP address for one or more instances.
  - :ref:`yo_mosh` - Connect to the instance via mosh.
  - :ref:`yo_rdp` - Connect to instance remote desktop using RDP.
  - :ref:`yo_rsync` - Synchronize files using the rsync command.
  - :ref:`yo_scp` - Copy files to/from an instance using the scp command
  - :ref:`yo_vnc` - Connect to instance remote desktop using VNC.

Task Management Commands:

  - :ref:`yo_task_info` - Show the basic information and script contents for a task.
  - :ref:`yo_task_join` - Wait for all tasks on a given instance to complete.
  - :ref:`yo_task_list` - List every task and its basic metadata
  - :ref:`yo_task_run` - Run a long-running task script on an instance.
  - :ref:`yo_task_status` - Report the status of all tasks on an instance.
  - :ref:`yo_task_wait` - Wait for a task to complete on an instance.

Volume Management Commands:

  - :ref:`yo_volume_attach` - Attach a block or boot volume to an instance.
  - :ref:`yo_volume_attached` - List volumes by their current instance attachment.
  - :ref:`yo_volume_create` - Create a block volume.
  - :ref:`yo_volume_delete` - Delete a block or boot volume.
  - :ref:`yo_volume_detach` - Detach a block or boot volume from an instance.
  - :ref:`yo_volume_list` - List block & boot volumes.
  - :ref:`yo_volume_rename` - Rename a block or boot volume.

Informative Commands:

  - :ref:`yo_compat` - Show a compatibility matrix of images and shapes.
  - :ref:`yo_images` - List images available to use for launching an instance.
  - :ref:`yo_limits` - Display your tenancy & region's service limits.
  - :ref:`yo_os` - List official OS and version combinations.
  - :ref:`yo_shape` - Get info about a single shape.
  - :ref:`yo_shapes` - List instance shape options.

Diagnostic Commands:

  - :ref:`yo_cache_clean` - Clear Yo's caches -- a good first troubleshooting step.
  - :ref:`yo_debug` - Open up a python prompt in the context of a command.
  - :ref:`yo_help` - Show help for yo.
  - :ref:`yo_version` - Show the version of yo and check for updates.

Command Group Index
-------------------

.. toctree::
   :maxdepth: 1

   cmd00
   cmd01
   cmd02
   cmd03
   cmd04
   cmd05
   cmd06
