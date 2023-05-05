Installation Guide
==================

yo is known to work on Linux and Mac OS. More guinea pigs are necessary for
Windows. yo requires at least Python 3.6, and it also requires that you have
OpenSSH installed. Yo can make use of the following optionally, if you have them
installed:

- ``rsync``
- ``mosh``
- Any RDP or VNC client that can connect via the command line arguments

This document expects that you've already created an OCI tenancy, or that you
have an account on an existing tenancy. Further, we expect that you've already
launched an instance once in the Web UI, which should create some default
resources for you.

Installation
------------

First, ensure you have at least Python 3.6 installed, along with pip. For Oracle
Linux users, ``yum install python3-pip`` should do the trick.

.. code:: bash

    pip install yo oci-cli

It's recommended that you use the above command to install yo. If you run it as
a non-root user (recommended), it will install to your home directory. The above
will also install the ```oci-cli`` package, which will help you configure yo.

Initial Configuration
---------------------

If you run ``yo`` at this point, you should be greeted by a message asking you
to configure OCI and/or yo.

OCI Configuration
~~~~~~~~~~~~~~~~~

yo depends on the OCI SDK in order to manage your compute instances. If ``yo``
is installed, then the ``oci`` command line utility should also be alongside it.
The OCI SDK requires some keys to be created and associated with your account,
but thankfully, this can be easily achieved with the command:

.. code:: bash

   oci setup bootstrap

Follow the prompts to authenticate with your tenancy. If you don't know your
region, open the OCI Web UI and see what it defaults to.

yo Configuration
~~~~~~~~~~~~~~~~

If you run ``yo`` without having a configuration file setup, ``yo`` will copy
the sample configuration file to ``~/.oci/yo.ini``.

**Edit this configuration file.** You'll need to set ``my_username`` to a unique
username identifying you. Set ``my_email`` to your full email address (the one
associated with your OCI account -- see the OCI console if you're not sure).

There are a few OCI-related configurations that yo needs you to set, so it knows
how to organize your instance and which subnets to use.

1. ``region`` - Choose this to match what you configured before!

2. ``instance_compartment_id`` - Compartments are like containers for resources
   in OCI. They are useful for larger organizations. You can use the default OCI
   command line tool ``oci iam compartment list`` to explore and select the
   correct ID. If you have a personal account, you may not use compartments, and
   instead you can use `your tenancy ID <get_tenancy_id>`_.

3. ``vcn_id`` - You can explore the VCNs in your account via ``oci network vcn
   list``. Use the ``id`` field of the desired VCN.

4. ``subnet_id`` - This selects a particular subnet, you can select from the
   list in ``oci network subnet list``.

5. Under the ``[instances.DEFAULT]`` section, you'll see an
   ``availability_domain`` configuration. Choose one of the availability domains
   in your region (try ``oci iam availability-domain list`` to get their names).

.. _get_tenancy_id: https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport_topic-Finding_Your_Tenancy_OCID_Oracle_Cloud_Identifier.htm

Done!
~~~~~

At this point, you should be able to run yo commands, such as ``yo list``.
Please continue to the :ref:`User Guide` to understand the basics for how to use
Yo.

There are some optional features which yo also supports. If you want to set them
up, visit  :ref:`Optional Features` to learn more.
