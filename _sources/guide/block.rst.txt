Block Volume Management
=======================

Yo now allows you to manage block volumes. These are useful for a
variety of reasons, such as keeping long-term data around after you’ve
terminated an instance, or for having a larger storage area without
expanding a root device, or possibly for filesystem testing.

OCI has two kinds of volumes: boot volumes, and block volumes. Boot
volumes are created from the image you selected when you launch the
instance. Block volumes are blank when created, and must be manually
attached to the instance.

Once created, volumes can be “attached” in a few ways, but the most
common are:

-  “Paravirtualized” - meaning that the hypervisor will create a
   virtualized disk and notify your instance’s OS that a new disk is
   available. This is the simplest way to attach block devices, and it’s
   the default. It shouldn’t require any setup on the instance. However,
   paravirtualized disks are only available for VM instances, because BM
   instances don’t have hypervisors.
-  “iSCSI” - meaning that the disk is made available over the iSCSI
   protocol, but first your instance must be configured to connect to
   it.

A volume can be attached to more than one instance (if attached in
shared mode) and instances may of course be attached to more than one
volume.

Yo provides commands to create, list, attach, detach, and delete block
devices. For iSCSI disks, these commands can also automatically run
commands which will connect the disk.

A note about volume names
-------------------------

If you use yo frequently, you know that it has strong opinions about how
to name instances. Yo is the same about block volumes as well: you
should prefix them with your global username.

Yo will automatically add that prefix if it isn’t found, and there is
currently no ``--exact-name`` argument to disable this behavior (but it
can be added if absolutely necessary).

However, yo **will not** attempt to enforce unique naming for your
volumes. So, if you create an instance named “stepbren-volume1” and then
create a second one named “stepbren-volume1”, yo will not prevent this.
The reason is mainly for efficiency: refreshing the volume list is quite
slow, even with multiple threads. Thus, you should be careful to avoid
duplicate names. If you do create a duplicate, you may need to visit the
OCI Web Console to remedy the situation.

yo volume-create
----------------

Creates a new, blank block volume. You need to provide at least three
arguments:

-  ``name`` - we will use this to refer to your volume. This will get
   automatically prefixed by your username (if not already done), but yo
   *will not* check for duplicate names, nor automatically increment
   trailing numbers.
-  ``size_gbs`` - the size, in gigabytes, of your volume.
-  OCI places volumes into a particular availability domain, and they
   can be accessed only by instances in the same AD. By default, yo uses
   your default instance profile’s AD. However, you can customize it
   with the ``--ad   AVAILABILITY_DOMAIN`` flag. More usefully, you can
   instead provide ``--for   INSTANCE_NAME`` to tell yo to use the same
   availability domain as that instance.

Unlike some of the other commands, yo will always wait for your volume
to become ready.

Creating a volume is frequently followed by attaching a volume. So, you
can also use the ``--attach`` option to attach the volume to an instance
after it is created. If you do so, you *must* use ``--for`` to tell yo
which instance to attach it to. You can also provide the attachment
arguments accepted by ``yo attach``.

yo attach
---------

Given a volume, attach it to a running instance. You need to provide at
least two things:

-  ``volume_name`` - the name of the volume
-  ``instance_name`` - which instance to attach to

The operation won’t succeed if the instances are in different ADs. This
command will wait until the attachment succeeds. You can provide the
following arguments to customize the block volume attachment (which can
also be provided to ``yo volume-create --attach``):

-  ``--ro`` - attach read-only
-  ``--shared`` - use shared mode, to support attaching to multiple
   instances
-  ``--no-setup`` - do not run setup commands for iSCSI
-  Select the attachment method with one of ``--iscsi``, ``--pv``
   (default), ``--emulated``, ``--service-determined``. The last two
   options are provided by the API, but they are not recommended. Please
   use either ``--iscsi`` or ``--pv`` for best results.

yo detach
---------

Given a volume, attach it from a specific instance, or all. You should
provide at least the volume name, as the first argument. You can specify
what to detach by providing one of the two options:

-  ``--from INSTANCE`` - detach from a particular instance
-  ``--all`` - detach from all instances

By default, yo will run detachment commands from iSCSI instances. To
avoid this, use ``--no-teardown``.

yo volume-delete
----------------

Delete a volume. Since you typically want to ensure that the volume is
detached from all instances prior to this, yo will automatically detach
each attachment, that is still connected, including the iSCSI commands
as necessary. These can be controlled by ``--no-detach`` and
``--no-teardown`` respectively.

yo volume-list
--------------

List all volumes. This command gives an overview of all volumes,
regardless of whether they are attached to anything. The view includes
both boot and block volumes.

yo attached
-----------

This is the slightly more useful volume listing command, though it is
also a bit slower. This lists each instance which has attached boot or
block devices (which, of course, is all instances), and then shows their
attached devices. Here is an example of the output.

::

   ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
   ┃ Instance/Volume                     ┃ Kind  ┃ GiB ┃ Volume State ┃ Att. State ┃ Att. Kind       ┃
   ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
   │ stepbren-ol8-1:                     │       │     │              │            │                 │
   │ - stepbren-drgnutils-images-2       │ block │ 512 │ AVAILABLE    │ ATTACHED   │ paravirtualized │
   │ - stepbren-ol8-1 (Boot Volume)      │ boot  │ 47  │ AVAILABLE    │ ATTACHED   │ boot            │
   ├─────────────────────────────────────┼───────┼─────┼──────────────┼────────────┼─────────────────┤
   │ stepbren-flamescope:                │       │     │              │            │                 │
   │ - stepbren-flamescope (Boot Volume) │ boot  │ 47  │ AVAILABLE    │ ATTACHED   │ boot            │
   ├─────────────────────────────────────┼───────┼─────┼──────────────┼────────────┼─────────────────┤
   │ stepbren-ol8-3:                     │       │     │              │            │                 │
   │ - stepbren-ol8-3 (Boot Volume)      │ boot  │ 47  │ AVAILABLE    │ ATTACHED   │ boot            │
   ├─────────────────────────────────────┼───────┼─────┼──────────────┼────────────┼─────────────────┤
   │ stepbren-focal-1:                   │       │     │              │            │                 │
   │ - stepbren-focal-1 (Boot Volume)    │ boot  │ 47  │ AVAILABLE    │ ATTACHED   │ boot            │
   └─────────────────────────────────────┴───────┴─────┴──────────────┴────────────┴─────────────────┘
