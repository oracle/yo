Optional Features
=================

Once yo is configured, you're able to use its base feature set, which is
(hopefully) described well in the Guide. However, there are a few additional
features which are optional and require some additional setup or configuration.

Bash Completion
---------------

``yo`` can provide bash tab completion. Add the following lines to your
``~/.bashrc`` file to enable it:

.. code::

    eval "$(register-python-argcomplete yo)"

The completer will provide context-sensitive suggestions. For example, if you
type ``yo terminate <TAB> <TAB>`` then command-line arguments for terminate will
be suggested, as well as the names of instances which could be terminated.

Completions may not be 100% accurrate: yo is simply reading cached data about
your OCI resources, which it previously stored. If the cache is out of date (or
you used the OCI console directly) then this could be misleading. But for normal
use, it's fine.

Notifications
-------------

Sometimes OCI operations (like launching) take a few moments to complete. These
operations can trigger desktop notifications, if you configure them correctly.
See :ref:`Global Configuration Options` for details on configuring the
``notify_prog``.
