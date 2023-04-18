Troubleshooting
===============

Issues With Bash Completion
---------------------------

Assuming you've setup :ref:`Bash Completion`, you can temporarily set the
following environment variable:

.. code:: bash

    export _ARC_DEBUG=1

Then try doing tab completion, for example:

.. code:: bash

    yo ssh <TAB>

You should get a flood of output. If there's no output, then the completion is
not properly configured with Bash. If there is output, check for a Python
exception traceback. If you see one, please file a Github issue and we can
investigate.

Caching
-------

Yo has a somewhat aggressive approach to caching. It turns out that loading the
OCI SDK is quite slow. Part of the reason for this is McAfee on my laptop
(scanning each individual Python file...), and part of the reason is that the
SDK library is massive and includes a lot of small Python files. In order to
load any information from OCI, you need to first load this SDK, and then make
HTTP requests, both of which are bound to be slow. To get a sense for this, run
``time yo list`` -- it's probably 3-4 seconds. Without caching, ``yo`` would ru
quite slowly for common operations. Imagine if each time you run ``yo ssh``,
we'd need to lookup the IP address, inserting a delay of several seconds.

To make this all better, we do two things:

1. Lazy load the OCI SDK -- if we don't need it, don't bother importing it.
2. Cache data from OCI

If you like reading the code ``yo/api.py`` is the internal "barrier" between yo
and the OCI library, it handles both of those strategies in a way that is mostly
transparent. We currently cache 4 types of data:

1. The list of instances
2. The list of images
3. The list of VNICs
4. The list of instance console connections

With a fully populated cache, this means that ``yo ssh``, ``yo console``, and
others can run very snappy. The downside is that you could encounter some
weirdness if you make changes to your instances outside of ``yo``. The cache
maintenance operations are a bit boring to go through, but the basic
troubleshooting steps for determining if there is a caching issue impacting you
are:

1. Run ``yo list --cached; yo list`` - this will show you the cached view of the
   world, and then refresh the cache (the default behavior of ``yo list`` is to
   refresh the cached instance list). If you see differences, then your issue
   might be resolved now.
2. Run ``rm ~/.cache/yo.json`` - this will remove the entire cache. This is
   harmless; yo can fetch everything and repopulate it.

Note that if you make changes to important configuration items, such as the OCI
region you are using, or your configured email address, then you should run ``rm
~/.cache/yo.json`` as well. The cache is not equipped to detect these changes.
