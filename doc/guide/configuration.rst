Configuration
=============

yo's configuration file should be located in the directory ``~/.oci/yo.ini``. It
uses a standard INI-style syntax (just like the OCI SDK configuration file).

.. _global configuration options:

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
``~/.oci/config``.

Whichever region you choose should be a valid OCI region. Further, you must
include a corresponding section below, ``[regions.NAME]``, which contains
:ref:`region-specific<regionconf>` configuration information (vcn and subnet).

The region may be overridden on the command line with ``yo -r REGION``, in which
case, a different region (with corresponding config section) will be used. Yo
maintains separate cache information for each region. Yo commands can only
operate in one region at a time.

``my_email``
~~~~~~~~~~~~

(String, Required) The email address you use to log into OCI.

.. _my_username:

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

At the time of writing, the Instance Console Connection feature (i.e. ``yo
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

.. _silence_tag:

``silence_automatic_tag_warning``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(Boolean, Optional, Default: false) Set this to true in order to silence a
rather verbose warning during ``yo list``. If you haven't seen a warning
mentioning this configuration value: you don't need to touch this configuration,
or read the remaining explanation.

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

Another possible resolution is to fully disable Yo's resource filtering. This
will result in Yo allowing you to view and manage all resources in your
compartment. See :ref:`resource_filtering` for details.

.. _automatic tag rule: https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingautomaticdefaulttags.htm

.. _exact_name:

``exact_name``
~~~~~~~~~~~~~~

(Boolean, Optional, Default: false) Set this to true to fully disable Yo's
:ref:`instance naming<instance_naming>` scheme, in which it prefixes instance
and block volume names with your username.  This allows you to create instances
with any name, and it allows you to use Yo commands to reference those
instances.

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

.. _resource_filtering:

``resource_filtering``
~~~~~~~~~~~~~~~~~~~~~~

(Boolean, Optional, Default: true) Set this to ``false`` in order to disable
Yo's resource filtering logic. This will result in Yo allowing you to view and
manage all resources within the configured OCI compartment, regardless of what
account created them.

See :ref:`Resource Visibility` for further discussion.

``check_for_update_every``
~~~~~~~~~~~~~~~~~~~~~~~~~~

(Integer, Optional, Default: 6) This is the (minimum) number of hours between
automatic checks for a newer version of Yo.

If it has been at least this many hours since the last check, then during ``yo
list``, a background thread will be spawned in order to check the latest version
from PyPI. If the current version is out of date, then Yo will suggest that you
update and provide the necessary command. Since the check is done in the
background during an operation which generally takes a few seconds, there's
almost no performance impact to this check.

You can set this configuration to zero, in which case Yo will not perform the
check at all.

``creator_tags``
~~~~~~~~~~~~~~~~

(List of strings, Optional) This is a list of tag values which Yo will use to
track instances (and other resources) as if they are your own.

When resource filtering is enabled, Yo relies on tags which can identify who
created a particular instance. Yo creates its own tag, but also can rely on a
tag which the OCI tenancy may automatically create. When OCI creates these tags,
it uses the name of your account as the tag value. Unfortunately, the name of
your account is not predictable: it could be your email address, or something
else. Yo makes a few guesses, but in case it guesses wrong, you can inspect your
instances to see what they set ``OracleTags.CreatedBy`` to, and you can add that
to this list.

You can also use this to include other people's instances in your list, if for
example you would like to monitor and help a direct report with their instances.

``list_columns``
~~~~~~~~~~~~~~~~

(String, Optional) A string containing a comma-separated list of columns to
include in the output of :ref:`yo_list`. The list of available columns can be
viewed in the documentation for ``-x`` in :ref:`yo_list`.

You can override this on the command line with ``yo list -C Col1,Col2`` and you
can extend the list on the command line with ``yo list -x Col1``.

``allow_hash_in_config_value``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

(Boolean, Optional, Default: false)

By default, Yo detects the '#' character within a configuration value, and
raises an error, becaues this is a common mistake for users. The '#' character
can only introduce a comment at the beginning of a line. If you use it after a
config value, it is included in the resulting value, which is usually not what
you want. However, if there is some case where you actually want to include a
hash in the config, set this to true to bypass the error.

.. _regionconf:

Region-Specific Configurations
------------------------------

Configurations related to the VCN and subnet used by your instance must be
region specific. Thus, these configurations are placed in a dedicated,
region-specific section You can select which region Yo will operate in via the
``region`` config in the ``[yo]`` section, and override this configuration on
the command line.

The region-specific configuration sections must be named as ``[regions.NAME]``,
replacing NAME with the region's name. For instance, ``[regions.us-ashburn-1]``.

``vcn_id``
~~~~~~~~~~

(String, Required) The VCN (virtual cloud network) in which your instances will
get created. This should be an OCID.

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


.. _instance profiles:

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

``mem``
~~~~~~~

(Integer, Optional) For flex shapes, specify the amount of memory in gigabytes
which you would like your instance configured with. This should not be provided
unless you are using a flex shape. This can be overridden on the command line as
well.

When ``mem`` is provided, it will be used as the total memory allocation for the
shape (unless this is out of the supported range, in which Yo will report the
error). If ``mem`` is omitted for a flex shape, then Yo will try to determine
the shape's default per-cpu memory allocation, and multiply that by the number
of CPUs configured, and use that value.

``cpu``
~~~~~~~

(Integer, Optional) For flex shapes, specify the number of OCPUs to configure
the instance with. This should not be provided unless you are using a flex
shape. It can be overridden on the commandline.

When ``cpu`` is provided, it will be used as the OCPU count, unless it is out of
the supported range. If ``cpu`` is not provided, the shape's default OCPU amount
is selected.

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

``username``
~~~~~~~~~~~~

(String, Optional) Specify a custom username for your instance. This can be
specified on the command line via ``--username`` or ``-u``. This will take the
place of the preexisting default user account name, and will receive all the
same privileges.

When not specified, or when set to the special value ``$DEFAULT``, Yo will not
make any changes to the default username. For most Oracle Linux images, this
means that the default user will be ``opc``, though for Ubuntu images, the
default user will be ``ubuntu``.

When the special value ``$MY_USERNAME`` is specified, Yo will use your default
username from the :ref:`my_username` field.

Otherwise, the configuration value used here will be used directly as the
username for your instance. Please take care to only provide strings which are
valid usernames for your image's operating system. Safe usernames include ASCII
letters, digits, and hyphens. Yo will not perform any validity checks on
usernames, and invalid usernames could result in failed boot and connectivity
issues.

The custom username is provided as user data to OCI's Cloud-Init. Images may
support cloud-init user data differently, so this functionality is not
guaranteed on all images. Please test this with your intended images before
relying on it.

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
