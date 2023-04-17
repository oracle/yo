# Commands

Yo has an extensive list of commands. By default, yo allows you to use the
shortest unambiguous prefix as a shortcut for the command name. For example, you
may use `yo la` instead of `yo launch`. However, as new commands are added,
these aliases may stop working. For instance, `yo li` was a valid shortcut for
`yo list` until v0.23.0 added `yo limits`.

You may instead create an `[aliases]` configuration section in your
`~/.oci/yo.ini` file. This will disable the shortest-prefix aliasing, and allow
you full control over the aliases. See the configuration documentation for more
information.

## Instance Management

### yo list

Lists all instances which were created by me. (Defaults to a particular
compartment which is hard-coded, but will be configurable in the future).

    $ yo list
    ┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
    ┃ Name            ┃ Shape            ┃ Mem ┃ CPU ┃ State       ┃ Created             ┃
    ┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
    │ stepbren-vm     │ VM.Standard.E2.2 │ 16  │ 2   │ TERMINATING │ 2020-10-14 15:51:23 │
    │ stepbren-vm-1   │ VM.Standard.E2.2 │ 16  │ 2   │ TERMINATING │ 2020-10-15 15:28:48 │
    │ stepbren-vm-2   │ VM.Standard.E2.2 │ 16  │ 2   │ TERMINATING │ 2020-10-15 15:29:07 │
    │ stepbren-vm-3   │ VM.Standard.E2.2 │ 16  │ 2   │ TERMINATING │ 2020-10-15 15:29:38 │
    │ stepbren-vm-cmd │ VM.Standard.E2.2 │ 16  │ 2   │ TERMINATING │ 2020-10-15 14:15:58 │
    └─────────────────┴──────────────────┴─────┴─────┴─────────────┴─────────────────────┘

### yo launch

Launch a new instance. Optionally wait and connect to it via SSH once it is
running.

    $ yo launch -n stepbren-vm-cmd-1 --ssh
    Using subnet App-AD3-iad.sub
    Using image Oracle-Linux-8.2-2020.09.23-0
    Launching instance stepbren-vm-cmd-1
    Wait for Instance stepbren-vm-cmd-1 to enter state RUNNING
    Instance stepbren-vm-cmd-1 starts in state PROVISIONING
    WAIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
    Instance stepbren-vm-cmd-1 has reached state RUNNING!
    Found instance ip 100.100.243.108
    SSH is up!
    Wait for SSH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
    ssh opc@100.100.243.108...
    Host key fingerprint is SHA256:j3g4WFJ2fDtLvawGmzqIhLgQ81ZEdMTcFc/1UB5XNg4
    +---[ECDSA 256]---+
    |   oo+o. .o. Eo+*|
    |    ..o..  o .o=+|
    |   .  o o . o  .o|
    |o   .o . . o     |
    |.= .. . S + .    |
    |+ +  + o.+ + .   |
    |.+ ...+ o+o o    |
    |. . . .oo ..     |
    |      .o ..      |
    +----[SHA256]-----+
    Activate the web console with: systemctl enable --now cockpit.socket

    [opc@stepbren-vm-cmd-1 ~]$ logout
    Connection to 100.100.243.108 closed.

Accepts args:

* `-p, --profile` - specify the "instance profile" (a group of instance
  settings) to use for this instance. See the "instance profile" section below
  for details.
* `--name, -n` - name the instance
* `--wait, -w` - wait until the instance is in the running state
* `--ssh, -s` - ssh into the instance once it is running (implies `--wait`)
* `--os` - specify operating system and version separated by colon, eg:
  `--os 'Canonical Ubuntu:20.04'`. This option is designed to make it easy to
  get the up-to-date image best suited to the OS you want to run. However, if
  you need to directly specify an image, see the `--image` option below.
- `--image` - specify the name of a custom image (also residing inside of the
  same compartment you use for instances) to use.
* `--shape` - specify the shape to use. Currently, flex shapes (with custom OCPU
  and memory selections) cannot be customized and will use their default values.

### yo ssh

Connect to an instance via SSH. You can run it with no arguments if you only
have one running instance. Otherwise, specify the name of the instance as the
next argument.

    $ yo ssh
    Connecting to instance stepbren-vm-cmd
    ssh opc@100.100.243.206
    The authenticity of host '100.100.243.206 (100.100.243.206)' can't be established.
    ECDSA key fingerprint is SHA256:8nR8sFnqR+48CRKkgQuLNjLOv84ZFhNljHy3IQva4Pg.
    +---[ECDSA 256]---+
    |  . o+           |
    | ..+++.o.        |
    |o.++o.++o . .    |
    |==..o..... *     |
    |=o.o  . S.* o    |
    | oE o  +.o.+     |
    |  .o    ....o.   |
    |  o.o      +o    |
    |  .=.       o.   |
    +----[SHA256]-----+
    Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
    Warning: Permanently added '100.100.243.206' (ECDSA) to the list of known hosts.
    Activate the web console with: systemctl enable --now cockpit.socket

    [opc@stepbren-vm-cmd ~]$

Yo does its best to determine which username it should use, based on the `--os`
argument you used to launch the instance. However, for some custom images, this
won't work. In this case, you can specify the username in the same way as you
would via SSH: `yo ssh username@instance`.

You can also use `yo ssh` to execute a single command on an instance, much like
you might do with `ssh`. Simply place that command at the end of the yo command.
To avoid yo interpreting any of your arguments as part of the `yo ssh` command,
it is recommended to separate the command with a double hyphen (`--`) as this
conventionally signals the end of option processing.

    $ yo ssh ol8-2 -- ls /etc/yum.repos.d
    Connecting to instance stepbren-ol8-2
    Found instance ip 100.100.242.96
    ssh opc@100.100.242.96...
    ksplice-ol8.repo
    mysql-ol8.repo
    oci-included-ol8.repo
    oracle-epel-ol8.repo
    oraclelinux-developer-ol8.repo
    oracle-linux-ol8.repo
    uek-ol8.repo
    virt-ol8.repo

### yo mosh

Connect to an instance via Mosh. This is similar to SSH, but sessions are
persistent even in the face of heavy packet loss, disconnections, high RTT, and
more. Mosh features local echo and a slew of other niceties - but the downside
is that it doesn't allow scrollback. You may find it more useful in combination
with heavy use of pagers, screen, or tmux.

    yo mosh vm-1

To use mosh, you'll first need to install it. On Oracle Linux, it is available
in EPEL, and can be installed by the following commands:

    sudo dnf config-manager --enable ol9_developer_EPEL
    sudo dnf install -y mosh

You can even place the commands necessary to install mosh into a
[Task](tasks.rst) which can be run automatically.

### yo console

Connects you to the instance serial console.

    $ yo console
    Connecting to instance stepbren-focal-1 console
    Created instance console connection. Waiting for it to become active.
    Wait for InstanceConsoleConnection to enter state ACTIVE
    InstanceConsoleConnection starts in state CREATING
    WAIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
    InstanceConsoleConnection has reached state ACTIVE!
    About to execute:
    [
        'ssh',
        '-o',
        'ProxyCommand=ssh -W %h:%p -p 443
    ocid1.instanceconsoleconnection.oc1.iad.anuwcljsgj4tlxyc2une5ykyejfyvwgoh3heizszhahyewc6yoh7raypcqrq@instance-console.us-
        'ocid1.instance.oc1.iad.anuwcljsgj4tlxycvynmtmopr6kq3jahn6snvlgz7iqbktojcfr6m2tyiepa',
        '-o',
        'ServerAliveInterval=60',
        '-o',
        'TCPKeepAlive=yes'
    ]
    This connection will stay open for a long time.
    To exit a running SSH connection, use the escape sequence: <Return>~.
    Host key fingerprint is SHA256:NvHnkwGWIT+nHSP93xHcb2hXcN2Ud3pEkGm+fTYHZUE
    ...

### yo console-history

Fetches the most recent console history, and prints it out. This way, even if
you didn't have a serial console connection, you can still see recent data,
including crash log lines.

### yo scp

A simple `scp` wrapper. As arguments, you may specify either files, or remote
filename specifiers. A remote file can be specified using the instance name
(e.g. `vm-1:dir/file.txt`), or with the instance name omitted (e.g.
`:dir/file.txt`). If the instance name is omitted from the remote file
specifier, you can provide it via the `-n` argument.

    $ yo scp hello.py vm-cmd4:
    Found instance ip 100.100.243.42
    Copying to instance stepbren-vm-cmd4 (opc@100.100.243.42)
    hello.py                                100%  888    11.4KB/s   00:00

Wherever you specify the instance name, you can also specify a username in the
normal way (`user@instance`).


### yo rsync

An `rsync` wrapper, which is very similar to scp. Note that the `rsync_args`
configuration argument is used by default. You can leave it empty or set some
useful arguments.


### yo vnc

This command allows you to use the VNC protocol to access a remote desktop for
your instance. Note that this requires instance configuration in most Linux
cases. See [VNC and Remote Desktop](vnc.md) for setup steps.

By default, this uses an SSH tunnel, which can be disabled with `--no-tunnel` or
`-T`.

To use this, you should set the {ref}`vnc_prog` configuration setting.

### yo rdp

This command allows you to use the RDP protocol  to access a remote desktop for
your instance. This also requires instance configuration. See [VNC and Remote
Desktop](vnc.md) for setup steps.

By default, this uses an SSH tunnel, which can be disabled with `--no-tunnel` or
`-T`. You will need to use this option to connect to Windows Server instances,
which do not use SSH tunneling.

To use this wrapper, you should set the {ref}`rdp_prog` configuration setting.

### yo terminate

Terminate a single instance, or all instances created by you. Unlike the
non-destructive ssh commands above, this command requires you either explicitly
specify one or more names on the command line, or pass `--all` to terminate all
instances created by you. If you have only one instance, this command will
**not** default to that instance. Further, it always requires confirmation,
unless you use `--yes`

    $ yo terminate --all
    About to terminate 5 instances:
    - stepbren-vm
    - stepbren-vm-1
    - stepbren-vm-2
    - stepbren-vm-3
    - stepbren-vm-cmd.
    Is this ok? [y/n]: y
    Confirmed.
    Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00


### yo reboot, yo stop, yo start

These commands allow you to reboot, stop, or start instances. Same as `yo
terminate`, there is no default argument; you must explicitly pass one or more
instance names (or `--all`) on the command line.

For `reboot` and `stop`, there is an additional argument `--force`. This allows
you to directly stop a machine without communicating with the operating system
via ACPI commands. While this risks data loss, it's the best option for a
completely locked up system.

    $ yo reboot focal-1
    About to reboot 1 instances:
    - stepbren-focal-1.
    Is this ok? [y/n]: y
    Confirmed.
    Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00

For `reboot` and `start`, you can use `--ssh` to wait and connect to the
instance once it is up. Of course, this only works if you specify one instance
on the command line. Please note that unfortunately, specifying a username for
SSH is not supported in these commands -- instead you'll need to manually run
`yo ssh` after the command completes.

### yo resize

This command is similar to `yo reboot`, except that you must specify a new shape
for the instance(s). If OCI determines that the shapes are compatible, then your
instance(s) will be shut down, and started up in a new shape. If you specify
only one instance, you can optionally `--ssh` (though you cannot specify a
username).

### yo rename

This command allows you to alter the name of an instance:

    yo rename ol9-1 my-precious

### yo protect

This command allows you to set or remove a tag on the instance, which signifies
that it should not be terminated. Yo will not terminate an instance with this
flag.

    yo protect ol9-1 on       # enable it
    yo terminate --yes ol9-1  # fails!
    yo protect ol9-1 off      # disable it
    yo terminate --yes ol9-1  # terminated

This ensures that you won't accidentally terminate the instance by carelessly
running a command. But please note, termination protection is a Yo feature,
**not an OCI feature**. It will prevent you from terminating the instance from
Yo, but not from the OCI console or command line. You have been warned!

### yo wait

Wait for an instance to enter a state. Typically, an instance starts in
"PROVISIONING" state, moves to "STARTING", and then "RUNNING". It moves through
other states as you interact with it. The full list of states at the time of
writing is:

    CREATING_IMAGE, MOVING, PROVISIONING, RUNNING, STARTING, STOPPED,
    STOPPING, TERMINATED, TERMINATING

This command allows you to wait for an instance to enter a particular state. For
example, after the reboot command, you could wait for the instance to enter the
RUNNING state:

    $ yo wait -n focal-1 -s RUNNING
    Wait for Instance stepbren-focal-1 to enter state RUNNING
    Instance stepbren-focal-1 starts in state STOPPING
    Instance stepbren-focal-1 entered state STARTING
    WAIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
    Instance stepbren-focal-1 has reached state RUNNING!

You can specify an instance by name (or the only one running is the default).
The default state to wait for is RUNNING, so `yo wait` sensibly waits for the
only active instance to become RUNNING.


### yo ip

Print the IP address for an instance. If you don't provide an instance name as
an argument, fetch all instance IPs.

    $ yo ip focal-1
    ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
    ┃ Name             ┃ IP              ┃
    ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
    │ stepbren-focal-1 │ 100.100.235.106 │
    └──────────────────┴─────────────────┘


## Informational Commands

### yo os

Print all operating systems available. The values here are taken directly from
the set of official images published on OCI. Any value here is suitable for use
in `yo.ini` for an instance OS.

    $ yo os
    ...
    Oracle Linux:6.10
    Oracle Linux:7.8
    Oracle Linux:7.9
    Oracle Linux:8
    ...

### yo images

Lists available images. Specify an operating system as the first argument to get
a list of only matching images. When called without OS, lists all official
(non-custom) images. Currently, yo does not support custom images in any way. Yo
is also completely untested on non-Linux operating systems.

    $ yo images "Oracle Linux:8"
    Here are the matching images:
    - Oracle-Linux-8.3-aarch64-2021.04.06-0 - Oracle Linux - 8
    - Oracle-Linux-8.3-2021.04.09-0 - Oracle Linux - 8
    - Oracle-Linux-8.3-2021.03.19-0 - Oracle Linux - 8
    - Oracle-Linux-8.3-2021.01.12-0 - Oracle Linux - 8
    - Oracle-Linux-8.2-2020.11.10-0 - Oracle Linux - 8
    - Oracle-Linux-8.2-2020.09.23-0 - Oracle Linux - 8
    Would use image Oracle-Linux-8.3-aarch64-2021.04.06-0

### yo shapes

Print a table of shape names and their features (memory, disk, CPU, GPU, etc).

    $ yo shapes
    ┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃ Shape                  ┃ Mem    ┃ CPUs  ┃ GPUs ┃ Disk(GiB) ┃ Net(gbps) ┃ CPU Info                                      ┃
    ┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
    │ BM.DenseIO1.36         │ 512.0  │ 36.0  │ 0    │ 29491.2   │ 10.0      │ 2.3 GHz Intel® Xeon® E5-2699 v3 (Haswell)     │
    │ BM.DenseIO2.52         │ 768.0  │ 52.0  │ 0    │ 52428.8   │ 50.0      │ 2.0 GHz Intel® Xeon® Platinum 8167M (Skylake) │
    │ BM.GPU2.2              │ 256.0  │ 28.0  │ 2    │ 0         │ 50.0      │ 2.0 GHz Intel® Xeon® Platinum 8167M (Skylake) │
    │ BM.GPU3.8              │ 768.0  │ 52.0  │ 8    │ 0         │ 50.0      │ 2.0 GHz Intel® Xeon® Platinum 8167M (Skylake) │
    ...

You can specify the kind of information you'd like to see:

- `--cpu` - the default, shows the name of the CPU model used
- `--gpu` - replaces "CPU Info" with the name of the GPU model, if relevant
- `--disk` - replaces "CPU Info" with a count of disks and a description of the
  info regarding the disks
- `--availability` - displays each AD in your region, and computes the total
  amount of instances with the each shape could "fit" into that AD according to
  the limits. This can help you choose an instance that you'll actually be able
  to launch!

### yo limits

Prints a series of tables which summarizes your tenancy's resource limits.

This command always prints the following:

- If available, a table "Resource Limits per-AD". These limits differ in each
  AD.
- If available, a table "Global or Regional Limits". These limits are the same
  across all ADs. Since yo can only operate in one OCI region, these are
  considered "global", applying the same to each AD.

When you provide the `-S` argument to specify a shape, the above tables get
filtered to only the resources required for that shape. Then, two additional
tables are printed, to help you understand where that shape could fit, and why.

- "Resources Required" gives you the amount of resource that yo believes is
  necessary to launch an instance. Note that this is not terribly well
  documented by OCI. We gave it our best guess, but it could be off. Please
  report any errors you see.
- "Will it fit?" gives a row for each AD, indicating the amount of instances
  which could "fit" into that AD according to the limits. Of course, this is a
  maximum and it's not necessarily guaranteed to be 100% accurate. When
  instances don't fit (i.e. the fit/space is 0), a third column will contain
  info about which limits are applying. If necessary, you can take this to the
  relevant teams to get limits increased.

```
$ yo limits -S BM.Standard.A1.160
                                     Resource Limits per-AD
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Limit                    ┃ VkEH:US-ASHBURN-AD-1 ┃ VkEH:US-ASHBURN-AD-2 ┃ VkEH:US-ASHBURN-AD-3 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ standard-a1-core-count   │ 53.0 / 1160          │ 171.0 / 1160         │ 222.0 / 1160         │
│ standard-a1-memory-count │ 646.0 / 7704         │ 674.0 / 7704         │ 1064.0 / 7704        │
└──────────────────────────┴──────────────────────┴──────────────────────┴──────────────────────┘
                  Global or Regional Limits
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Limit                             ┃ Availability           ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ standard-a1-core-regional-count   │ 99997158.0 / 100000000 │
│ standard-a1-memory-regional-count │ 99980546.0 / 100000000 │
└───────────────────────────────────┴────────────────────────┘
─────────────────────────────────────────────────────── But... will it fit? ───────────────────────────────────────────────────────
                Resources Required
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Resource                          ┃ Requirement ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ standard-a1-memory-count          │ 1024.0      │
│ standard-a1-memory-regional-count │ 1024.0      │
│ standard-a1-core-count            │ 160.0       │
│ standard-a1-core-regional-count   │ 160.0       │
└───────────────────────────────────┴─────────────┘
                                          Will it fit?
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ AD                   ┃ Space ┃ Limiting Factor?                                              ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ VkEH:US-ASHBURN-AD-1 │ 0     │ standard-a1-memory-count: require 1024.0 but only 646.0 avail │
│                      │       │ standard-a1-core-count: require 160.0 but only 53.0 avail     │
│ VkEH:US-ASHBURN-AD-2 │ 0     │ standard-a1-memory-count: require 1024.0 but only 674.0 avail │
│ VkEH:US-ASHBURN-AD-3 │ 1     │ --                                                            │
└──────────────────────┴───────┴───────────────────────────────────────────────────────────────┘
```

### yo shape

Print detailed information about a particular shape.

    $ yo shape BM.Optimized3.36
    ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃            Topic ┃ Info                                     ┃
    ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
    │             Name │ BM.Optimized3.36                         │
    │        Processor │ 3.0 GHz Intel® Xeon® Platinum (Ice lake) │
    │           # CPUs │ 36.0                                     │
    │     Memory (GiB) │ 512.0                                    │
    │ Bandwidth (gpbs) │ 50.0                                     │
    │       Max # VNIC │ 256                                      │
    │  GPU Description │                                          │
    │           # GPUs │ 0                                        │
    │      Local Disks │ NVMe SSD Storage                         │
    │    # Local Disks │ 1                                        │
    │ Total Disk (GiB) │ 3840.0                                   │
    └──────────────────┴──────────────────────────────────────────┘

### yo task-run, task-status, task-wait, task-join, task-list, task-info

These commands allow you to manage "Tasks", a simple way to start scripts in the
background and configure your instance before you connect to it. See the "Tasks"
page in the user guide for more information about them.

### yo volume-create, volume-delete, attach, attached, detach, volume-list

These commands allow you to manage block volumes. Please see the "Block Volume
Management" page in the guide for more information about them.

### yo version

Print the current version of yo, check for updates, and give the necessary
upgrade commands.

### yo help

Print a help info, similar to what you would find in the Guide.

### yo debug

A special command which loads yo and places you inside a Python interpreter.
This is useful if you're familiar with the guts of yo and want to play with some
code.
