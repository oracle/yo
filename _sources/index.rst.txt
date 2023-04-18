yo
==

yo is a command-line client for managing OCI instances. It makes launching OCI
instances as simple as rudely telling your computer "yo, launch an instance".
Its goals are speed, ease of use, and simplicity. It was originally designed to
help developers in the Oracle Linux team quickly launch disposable VMs for
testing, but is slowly gaining users outside of OL. Here are some examples of
how yo tries to improve on the OCI command line and browser tools:

- yo hides other people's VMs from you, so you can just manage your own
  instances.
- yo doesn't make you type any more than you need. Compartment IDs, common shape
  configurations, etc can all be stored in your config. It really can be as
  simple as ``yo launch`` (or, for the lazier, ``yo la``).
- yo lets you refer to your instances by name. You should never need to memorize
  an IP address again.
- yo aggressively caches data to make operations as quick as possible.

This documentation site contains instructions on how to install and configure
yo, as well as some frequently asked questions and an illustrated list of yo
sub-commands.

Contact
-------

yo is created and maintained by Oracle and contributors. Its code is hosted
`here <https://github.com/oracle-samples/yo>`_ -- feel free to file bugs or
issues there, or fork it and submit a pull request.

Contents
--------

.. toctree::
   :maxdepth: 2

   install
   guide/index
   optional_setup
   development

.. toctree::
   :maxdepth: 1

   changelog
