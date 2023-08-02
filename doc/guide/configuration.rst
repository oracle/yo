Configuration
=============

yo's configuration file should be located in the directory ``~/.oci/yo.ini``. It
uses a standard INI-style syntax (just like the OCI SDK configuration file).

Global Configuration Options
----------------------------

The global configuration is stored in the section ``[yo]``.

.. _instance_compartment_id:

``instance_compartment_id``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

(String, Required) The OCI compartment in which every instance is created. This
should be an OCID identifier: eg ``ocid1.compartment....``

If you're not sure which compartment ID you need, then consult your team's
documentation on use of OCI -- it should tell you what compartment you create
your instances in. Alternatively, go through the instance creation steps on the
OCI console, and check which compartment it automatically populates for you.
Once you have the name, run the command ``oci iam compartment list`` and find
the entry for your compartment in the JSON output. Find the ``id`` field and use
that for this configuration parameter.

A few common compartment IDs are listed in the sample yo.ini file, see below or
in the yo source code for those.

``region``
~~~~~~~~~~

(String, Required) Set the OCI region. This takes precedence over anything in
``~/.oci/config``. It should match the ``availability_domain`` configs you have
in this file, as well as the ``vcn_id`` config.

``vcn_id``
~~~~~~~~~~

(String, Required) The VCN (virtual cloud network) in which your instances will
get created. This should be an OCID as well.

``subnet_id``
~~~~~~~~~~~~~~~~~~~~~~~~~

(String, Optional) The OCI subnet ID to which your instances will be
connected.

One of either ``subnet_id`` or ``subnet_compartment_id`` is required,
with ``subnet_id`` being preferred if both are specified.

``subnet_compartment_id``
~~~~~~~~~~~~~~~~~~~~~~~~~

(String, Optional) The OCI compartment which contains the subnets your instances
should be created within. In OCI, the IDs of subnets change depending on which
AD (availability domain) they're in. So, yo has a weird approach, where it lists
every subnet in this compartment and AD, and simply picks the first one.

One of either ``subnet_id`` or ``subnet_compartment_id`` is required,
with ``subnet_id`` being preferred if both are specified.

``my_email``
~~~~~~~~~~~~

(String, Required) The email address you use to log into OCI.

``my_username``
~~~~~~~~~~~~~~~

(String, Required) Set a username. This is just used as a unique string to
include in the name of your instance, helping people to see that it belongs to
you. If your organization has global username IDs, it's best to use that.
Otherwise, you could use your first name or whatever you prefer. This will not
get used as the login name for your instances; it's just an identifier used in
the names.

.. _ssh_public_key:

``ssh_public_key``
~~~~~~~~~~~~~~~~~~

(String, Optional) The file path to your SSH public key. If omitted, the default
of ``~/.ssh/id_rsa.pub`` is used.

This public key is provided to OCI when launching instances, as well as creating
instance console connections. Yo also passes the ``-i path/to/key`` argument to
the SSH command, instructing it to use that given key file. This means that you
can have many SSH keys in your ``~/.ssh`` folder, and pick one of them for use
with Yo. However, you should know that the ``-i`` argument does not prevent SSH
from using a different key, if suitable. If you want to ensure that Yo *only*
uses this key, you should add ``-o IdentitiesOnly=yes`` to the :ref:`ssh_args
<ssh_args>` configuration field.

Password protected SSH keys may result in Yo prompting you for passwords
repeatedly, as sometimes Yo executes some SSH commands non-interactively. It is
recommended that you either use an SSH agent, or store the key without password
protection -- if this is appropriate for your environment and security
requirements.

Please note, when launching instances, Yo provides your SSH public key and it is
included in your instance's ``~/.ssh/authorized_keys`` file. However, if you
change the configuration value, Yo has no way to detect this and update the
instance's authorized keys. Thus, changing the configuration value could result
in some instances being inaccessible.

At the time of writing, the Intstance Console Connection feature (i.e. ``yo
console`` command) is not compatible with ED25519 keys. It is recommended that
you use 4096-bit RSA keys with Yo for the time being. You can generate one via
the following command:

.. code-block::

   ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_yo

.. _vnc_prog:

``vnc_prog``
~~~~~~~~~~~~

(String, Optional) Set a desired program to launch for VNC (remote desktop).
This string will be interpreted by your shell, but first Python's format method
will replace the following strings:

- ``{host}`` host for VNC connection
- ``{port}`` port for VNC connection

When not provided, the default is ``krdc vnc://{host}:{port}`` (the KDE remote
desktop client), feel free to modify it.

.. _rdp_prog:

``rdp_prog``
~~~~~~~~~~~~

(String, Optional) Set a desired program to launch for RDP (remote desktop).
This string will be interpreted by your shell, but first Python's format method
will replace the following strings:

- ``{host}`` host for RDP connection
- ``{port}`` port for VNC connection

An example of a connection command for the KDE Remote Desktop Client (KRDC) is:
``krdc rdp://{user}@{host}``.

.. _notify_prog:

``notify_prog``
~~~~~~~~~~~~~~~

(String, Optional) Set a desired command to run in order to send notifications
for waits. For example, when launching an instance and waiting for SSH or tasks.
If unset (the default), notifications will not be sent. This string will first
be split into arguments according to shell quoting rules. Then, any occurrences
of ``{message}`` will be replaced with the notification text, via the Python
``format()`` method.

Here are some example configurations:

.. code::

    Linux:  notify-send "yo!" {message}
    Mac:    osascript -e 'display notification "{message}" with title "yo!"'

For Windows users, there is a `stack overflow post`_ which has some options for
commands you might be able to turn into scripts. For Mac users, `this post`_
suggests that a tool from homebrew called ``terminal-notifier`` may be useful,
or alternatively another tool called ``growl``. Drop me a line if you try any of
these out, so I can expand this documentation with instructions.

.. _stack overflow post: https://stackoverflow.com/questions/39535937/what-is-the-notify-send-equivalent-for-windows
.. _this post: https://apple.stackexchange.com/questions/9412/how-to-get-a-notification-when-my-commands-are-done

``preserve_volume_on_terminate``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(Boolean, Optional) Configures yo's default behavior on termination. When False
(the default when not specified), the root block device will be deleted when the
instance is terminated. Your data is not preserved in any way, and the instance
cannot be recreated later. When True, the root block device will be preserved,
so that an instance could later be created using the same root device. This
configuration option simply sets the default behavior. You may override this
behavior on the command line of ``yo terminate`` with either the
``--preserve-volume -p`` argument, or the ``--no-preserve-volume -P`` argument,
depending on your preference.

Note that these block devices are not free, and disk space in a given tenancy is
limited. Once you've terminated an instance, preserving its volume, you will
need to continue paying for it until you terminate it.  Currently, yo does not
(yet) have support for launching an instance with a given root device. So you'll
need to use some other tool to use your preserved volumes in this way.

If any of these features strikes you as important for your use case, please file
an issue (or pull request) regarding it, to help us prioritize.

``oci_profile``
~~~~~~~~~~~~~~~

(String, Optional) If you use the OCI SDK for many different tenancies or
setups, you may have multiple profiles in your ``~/.oci/config`` file. You can
specify which profile is used by setting this. The default value is "DEFAULT".

.. _ssh_args:

``ssh_args`` and ``ssh_interactive_args``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(String, Optional) You can use these options to customize the SSH command line.
In particular, you can set SSH options (``-o Key=value``) specific to your Yo
sessions. The ``ssh_args`` are added to *all* SSH commands, while the
``ssh_interactive_args`` are only added to the ones which result in an
interactive prompt. This is because Yo does a lot of SSH commands besides the
common ``yo ssh`` . Please be careful with this configuration and test it
thoroughly.


.. _config_task_dir:

``task_dir``
~~~~~~~~~~~~

(String, Optional) Set the directory in which yo :ref:`tasks<tasks_overview>`
are stored. This may be useful in case the default (``/tmp/tasks``) is ephemeral
-- that is, if it is deleted on reboot. This must be an absolute path, with the
following exception: if you begin the path with ``$HOME/`` or ``~/``, then the
path will be interpreted relative to the instance user's home directory.
However, this interpolation is performed manually by yo -- no other shell
processing occurs, and the remaining portion of the string will be interpreted
literally. Spaces and other special characters are supported in the directory
name, though not recommended.

Your instance's user needs to have permission to create the directory (and its
parents) if it does not exist.

``image_compartment_ids``
~~~~~~~~~~~~~~~~~~~~~~~~~

(String List, Optional) Set a list of additional compartments from which you
want to load images.

Normally, yo lists and caches the custom images in the compartment specified by
``instance_compartment_id``, to allow you to use images from the same
compartment where your instances are. However, you may want to use custom images
from another compartment: for example, images published by another team. You can
use this configuration option to list additional compartment IDs to search.

The configuration is specified as a string list, and the compartment IDs are
delimited by commas, whitespace, or even both. It may be convenient to list each
on separate lines, such as:

.. code-block::

   image_compartment_ids =
       ocid.compartment.oc1..foobarsomelongstringhere
       ocid.compartment.oc1..someotherstringgoeshere!

Please note that when you change this configuration (either by adding or
removing a value), yo's cache becomes out-of-date in a way which it cannot
detect. Once you've updated this configuration value, please run ``yo
cache-clean`` to force yo to fetch the latest image list next time you run it.

``silence_automatic_tag_warning``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(Boolean, Optional) Set this to true in order to silence a rather verbose
warning during ``yo list``. If you haven't seen a warning mentioning this
configuration value: you don't need to touch this configuration, or read the
remaining explanation.

Yo is dedicated to managing the instances which you, an individual user,
created. It was designed for the idea of a shared tenancy, in which multiple
users create and manage their own instances. When Yo lists instances, it filters
them to the ones which have the tag: ``Oracle-Tags.CreatedBy`` matching your
email address.

However, this approach depends on an `automatic tag rule`_, which was added to
new tenancies starting in December 17, 2019. Older tenancies, or tenancies whose
administrator removed the rule, lack the rule.

When the tag rule exists, Yo is able to filter to all instances you created,
*regardless* of how you launched them (e.g. via Yo, via the OCI CLI, terraform,
or the Web Console). If the tag rule does not exist, then Yo falls back to
looking for a freeform tag that it includes with every new instance:
``yo-created-by``. This means that Yo will only be able to see and manage the
instances you created within Yo. So, during ``yo list``, we print a noisy
warning providing information regarding this issue.

The best resolution is to contact your tenancy administrator and ask that they
include this automatic tag rule: not only is it now standard, but it is quite
useful for cost tracking, which should interest your administrators. However, if
this is not possible, or if you're happy with the reduced feature set entailed
by this, then you can simply set this configuration value to ``true`` in order
to stop the message from being printed.

.. _automatic tag rule: https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingautomaticdefaulttags.htm

.. _exact_name:

``exact_name``
~~~~~~~~~~~~~~

(Boolean, Optional) Set this to true to fully disable Yo's :ref:`instance
naming<instance_naming>` scheme, in which it prefixes instance and block volume
names with your username.  This allows you to create instances with any name,
and it allows you to use Yo commands to reference those instances.

This functionality is available on a case-by-case basis, by providing the
argument ``--exact-name`` (or ``-E``) to any sub-command which takes an instance
or block volume name as an argument.

Should you decide to set this configuration to ``true``, then you will no longer
need to use the ``--exact-name`` argument. If you'd like to return to Yo's
instance naming behavior on a case-by-case basis, you can use the
``--no-exact-name`` argument, which can override the configuration.

If you're working in a compartment shared with many users, it's a nice idea to
keep ``exact_name = false`` (the default), which retains Yo's default behavior.
This ensures that anybody else can quickly identify the owner of an instance
just by looking at its name. However, if you do not share a compartment, or if
you have specific naming requirements, this can be a helpful config knob, to
keep Yo from getting in your way.

Instance Profiles
-----------------

There are many options which you may want to specify when launching an OCI
instance. See, for example, the output of ``yo launch --help``. An instance
profile is a named group of settings which you can use when launching an
instance. You can declare the profile by creating a section named
``[instances.NAME]`` in the configuration file. Use the profile with ``-p NAME``
on the ``yo launch`` command line. Note that all of these options can be
overridden on the command line.

Instance profiles can inherit from each other. For example, you could create a
base profile named "ol8" for running Oracle Linux 8 on a modest size machine,
and then inherit a new profile "bigol8" from that, changing only the shape.

It is **required** that you include one profile, named DEFAULT, which will be
used if you do not specify a profile on the command line.

``availability_domain``
~~~~~~~~~~~~~~~~~~~~~~~

(String, Required) Which availability domain to create the instance in.

``shape``
~~~~~~~~~

(String, Required) Which shape to use to create the instance. Don't know which
shape to use (or what's available)? Try running ``yo shapes``.

``os``
~~~~~~

(String, Optional) Which operating system to use to create the instance. This
field is a combination of a name and a version, separated by a colon. For
example, ``Oracle Linux:8``. You can list the available operating systems with
``yo os``. Please note that ``os`` is not the only way to specify which image
your instance boots with. The ``yo launch`` command also provides the option
``--image``, which can override the OS selection with a custom image name.
However, at this time there is no way to specify a custom image in an instance
profile.

This configuration value is optional: you may specify either ``os`` or ``image``
(see below). You must specify exactly one of these values, otherwise an error
will be raised on startup. These values may also be overridden on the ``yo
launch`` command line by their corresponding options.

You may encounter trouble if you try to specify ``image`` within a configuration
section that inherits from a profile that already specifies ``os`` (or vice
versa). You need to _clear_ the configuration for ``os`` so that Yo doesn't see
both values as set. To clear a configuration value, simply leave it blank. For
example:

.. code:: ini

    [instances.base]
    shape = VM.Standard.E2.2
    os = Oracle Linux:8
    availability_domain = VkEH:US-ASHBURN-AD-3
    boot_volume_size_gbs = 100

    [instances.custom]
    inherit = base
    image = my-custom-image
    # leave blank without "=" to clear the value
    os



``image``
~~~~~~~~~

(String, Optional) The name of a custom image to use. Yo will search for this
image inside the same compartment that it creates your instances
(``instance_compartment_id``).

This configuration is optional, but exactly one of ``os`` or ``image`` must be
specified. See the note directly above for more info.

``boot_volume_size_gbs``
~~~~~~~~~~~~~~~~~~~~~~~~

(Integer, Optional) Set the disk size in GiB.  Valid values are >=50 and less
than or equal to 16384 (although an OS image may have further limitations). If
unset, then we just accept whatever the default OCI gives us.

NOTE: if you use this, your instance may boot with mismatched partition table
for the disk size. You may want to use ``service ocid start`` to launch the OCI
daemon to tune these things.

``name``
~~~~~~~~

(String, Optional) The default name to apply to instances created with this
profile. Default value: "vm-1".

- Names get automatically prefixed by the global config value ``my_username``,
  if they aren't already.
- If a name ends with a hyphen followed by a number, and the name happens to be
  a duplicate, then that number would be automatically incremented. Otherwise,
  if your name to be a duplicate, then "-1" is appended.

So, if you launched several instances with the default name, they would be named
USERNAME-vm-1, USERNAME-vm-2, etc.

``inherit``
~~~~~~~~~~~

(String, Optional) Specify the name of another instance profile to inherit from.
All configuration values from that profile will be copied, and then any settings
in this config section will overwrite them.

.. _config_tasks:

``tasks``
~~~~~~~~~

(String, Optional) Specify the name or names of tasks that you want to run on
startup for this instance. Multiple tasks can be joined by a comma (no spaces
are allowed).

Please note that tasks specified in an instance profile cannot be removed from
the profile on the command line. You can only specify _additional_ tasks to run.

In order to start tasks at launch time, yo must wait for an instance to become
RUNNING, and for SSH to come up. This means that when you configure the
``tasks`` field, yo will always block waiting for SSH, regardless of whether you
pass ``--wait`` or ``--ssh`` at launch time.

``load_image``
~~~~~~~~~~~~~~

(String, Optional) Specify an image loading strategy. These strategies only
apply if the image is specified by name. The following choices are available:

- ``UNIQUE`` - this is the default behavior, which is the same as how Yo works
  in other areas. Names are expected to be unique, and they are cached. Yo will
  not always look for new images if it finds a cached image with the correct
  name.
- ``LATEST`` - in this mode, Yo does not expect that image names are unique. Yo
  will always load the latest list of images, and it will choose the most
  recently created image by a given name.

Command Aliases
---------------

The optional ``aliases`` section allows you to specify a shortcut name for a
command. When the ``aliases`` section is not provided, or when it is empty, yo
will default to the "shortest prefix" aliasing system. Here's an example of an
alias section:

.. code-block::

   [aliases]
   la = launch
   li = list
   con = console
   s = ssh

Sample Configuration File
-------------------------

This file is included in the git repository and is provided here for convenience
of copy/paste.

.. literalinclude:: ../../yo/data/sample.yo.ini
  :language: ini
