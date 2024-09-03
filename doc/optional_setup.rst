.. _optional features:

Optional Features
=================

Once yo is configured, you're able to use its base feature set, which is
(hopefully) described well in the Guide. However, there are a few additional
features which are optional and require some additional setup or configuration.

.. _bash completion:

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

Zsh Completion
--------------

The python argcomplete option should also work for zsh, and includes argument
listings and explanations comparable to the bash completions. However, it lacks
features native to the zsh completion system like tags, descriptions, and
argument groups.

An alternative zsh completion definition is available in contrib/yo.zsh that
implements a more native zsh experience. Add this file to a directory in your
$fpath and run ``compinit`` again. You may need to delete ~/.zcompdump to pick
up the new completion definition depending on your distribution and
configuration.

For these completions, ``jq`` is used to parse the yo cache files if it is
installed. Otherwise, argument listings for some words like instances and
shapes are not available.

Typical user zstyle configurations should now work, E.g.:

.. code::

   zstyle ':completion:*' verbose yes
   zstyle ':completion:*:yo:*' group-name ''
   zstyle ':completion:*:yo:*:descriptions' format '%F{magenta}completing%f: %d'

Notifications
-------------

Sometimes OCI operations (like launching) take a few moments to complete. These
operations can trigger desktop notifications, if you configure them correctly.
See :ref:`Global Configuration Options` for details on configuring the
``notify_prog``.
