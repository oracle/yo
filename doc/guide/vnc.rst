VNC and Remote desktop
======================

In addition to providing access to your OCI instances via SSH, it’s
possible to configure them to run a full graphical environment, which
you can access over the VNC or RDP protocols. Yo has helper commands,
``yo vnc`` and ``yo rdp``, which allow you to specify a client program
and automatically launch a connection to your OCI instance.

In order to use VNC or RDP, there are three steps

1. Setup the server on your OCI instance
2. Install and configure the client on your local computer
3. Use yo to connect

See below for details on each step.

Server Support
--------------

Setting up VNC and RDP Servers on Oracle Linux
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For Oracle Linux 8 and above, there is an `official
guide <https://docs.oracle.com/en/learn/install-vnc-oracle-linux/>`__
that demonstrates how to install and start a VNC server. Follow this
guide, but you do not need to configure X509 encryption, nor do you need
to configure firewall rules: Yo is able to automatically create an SSH
tunnel, which allows a secure connection without these steps.

It is also possible to setup an RDP server on Oracle Linux. The
following commands can install and enable the XRDP server
implementation:

::

   sudo dnf config-manager --enable ol8_developer_EPEL
   sudo dnf -y install xrdp
   sudo dnf -y groupinstall "server with gui"
   sudo systemctl enable xrdp
   sudo systemctl start xrdp
   sudo passwd opc  # make sure to set the password for your user

Similar to the above VNC guide, this configuration doesn’t create a
firewall rule allowing inbound connections from the network. You can use
yo to automatically create an SSH tunnel, which is a more secure
configuration.

You may find it quite convenient to write a `Task <tasks.rst>`__ which
scripts the installation of your preferred server, so that there are no
manual steps between launching your instance and connecting to it.

Using RDP on Windows Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Windows Server images come with RDP configured and ready to use. OCI
provides you with a default username and password, which must be changed
upon your first connection.

Yo is able to detect this, and displays your initial credentials
whenever you connect with ``yo rdp``.

Client Support
--------------

Yo supports launching VNC and RDP clients via the command line. You will
need to configure {ref}\ ``vnc_prog`` or {ref}\ ``rdp_prog`` in order to
launch your chosen client. Most clients should accept a host and port on
the command line.

One tested client for Linux is KRDC, the KDE Remote Desktop Client. It
is known to work well with Yo. The package is available in the Oracle
Linux EPEL package repository for OL8 and OL9:

::

   sudo dnf config-manager --enable ol8_developer_EPEL  # or ol9
   sudo dnf -y install krdc

Other clients are also likely to work. If you test a client and have any
issues, or would like to share your configuration steps, feel free to
file a Github issue.

Connecting with Yo
------------------

Once you have configured your client and server, you can use Yo to
connect:

::

   yo rdp $instance
   yo vnc $instance

Please note that by default, Yo tunnels the connection over SSH. This is
to encourage secure setups which do not expose remote desktop ports to
public network. However, if you have configured your instance to be
public facing (or if you are using a Windows Server instance, which
cannot do SSH tunneling), then you can disable the tunneling with
``-T``:

::

   yo rdp -T $instance
   yo vnc -T $instance
