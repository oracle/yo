Concepts
========

Limitations of yo
-----------------

yo is **not** a general-purpose OCI client. It's all about managing instances,
and to a lesser extent, block devices. It was built in an organization where
many developers share a tenancy, and just want to manage their own instances
without stepping on others' toes.

yo is also pretty limited in functionality. It doesn't know much about VCNs or
subnets, and it can't really do anything beyond managing instances and block
devices. If you need access to those features, then you may be better off using
the Web UI or the standard command line.

These limitations are here to make yo simple and easy. The idea is to make it
trivial for a Linux developer to go from thinking "I need to setup a VM in the
cloud to test this", to being SSH'd into that very VM.

Of course, some of these limitations are due to laziness on the part of the
developer. Feel free to make the case for an omission via Github issues. Or,
even better, feel free to submit an improvement via Github pull request!

.. _instance_naming:

Instance Naming
---------------

yo manages instance names in an opinionated way. Suppose you have global
username in your organization which is is "stepbren". yo believes that:

1. All instance names should be prefixed by "stepbren-".
2. Name collisions should be avoided by appending a "-N" suffix, where N
   increments.

To enforce this, yo will automatically apply these rules on instance creation,
and when looking up an instance name, if your name doesn't already fit the
criteria. Some examples:

.. code::

    yo launch -n bug           # new instance stepbren-bug
    yo launch -n stepbren-bug  # same as above
    yo launch -n bug           # if stepbren-bug already exists, creates
                               #  stepbren-bug-1
    yo launch -n bug-1         # if stepbren-bug-1 already exists, creates
                               #  stepbren-bug-2
    yo ssh bug                 # connect to stepbren-bug

This behavior is designed with the idea of shared compartments in mind. It's
nice include your username in the name of the instance, so that other users can
easily determine who created it without needing to investigate it further.

Of course, if you don't share your compartment with anybody, or you have
specific naming requirements, then this approach can quickly get in your way.
You can avoid this behavior in two ways:

* You can pass ``--exact-name`` to various subcommands, avoiding the behavior on
  a case-by-case basis.

* You can set the configuration value :ref:`exact_name` to true in your
  configuration file. This operates globally, completely disabling the behavior.
  If necessary, you can re-enable it on a case-by-case basis with
  ``--no-exact-name``.

.. _resource visibility:

Resource Visibility
-------------------

Yo was designed to be used by teams that share compartments, and thus want to
avoid stepping on each others' toes. So in Yo's default configuration,
instances, block volumes, etc, are only shown if Yo knows that you created them.
Similarly, Yo will not allow you to manage those resources which you did not
create.

However, not all people use OCI this way. Some people have their own compartment
which is not shared with others.  In other cases, the automatic tag rules
necessary for Yo to determine the creator are not available (see :ref:`this
explanation <silence_tag>` for more details).

Whatever the reason, you can disable this visibility restriction by setting
``resource_filtering = false`` in your configuration file. See
:ref:`resource_filtering` for more details.

Instance Profile
----------------

yo allows you to create "Instance Profiles" in the configuration file. These
specify details such as the operating system, shape, name, availability domain,
and SSH keys. You can refer to these by name and simply launch an instance from
a profile via the following command:

.. code::

    yo launch -p PROFILE

If you don't specify ``-p``, you'll use the "DEFAULT" profile instead. See the
:ref:`Instance Profiles` configuration section for more information.

Instance States & Saved Instances
---------------------------------

Instances in OCI are always in a state. Common instance states include:

- PROVISIONING
- STARTING
- RUNNING
- STOPPING
- STOPPED
- TERMINATING
- TERMINATED

Most states are self-explanatory. A newly launched instance starts in
PROVISIONING, then moves to STARTING, and then enters RUNNING. If an instance is
stopped, it moves through STOPPING to STOPPED, and starting it will return it to
STARTING, followed by RUNNING. Finally, terminating an instance causes it to
enter TERMINATING, followed by TERMINATED.

Instances in the STOPPED state have special rules regarding `billing`_. Thus,
stopping an instance may be advantageous, as it may pause billing for the
instance. However, STOPPED instances still count toward service limits. Thus, Yo
implements an additional option, which is expressed to the user as an additional
instance state: "SAVED".

Instances in the SAVED state are really just saved boot volumes -- they do not
appear in the OCI console as instances. Yo attaches a small amount of metadata
to the instances, which allows it to recreate the instance with the same name
and shape. The ``yo teardown`` command is used to make an instance SAVED, and
``yo rebuild`` is used to recreate the instance (returning it to RUNNING).

.. _billing: https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm
