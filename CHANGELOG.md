# Changelog

## Unreleased

Any changes which are committed, but not yet present in a released version,
should appear here.

## 1.8.1 - Tue, Feb 18, 2025

- Fixed an issue with renaming an instance when there is a terminated instance
  of the same name.
- Included updated ZSH completions, thanks to @rpigott again!

## 1.8.0 - Fr, Nov 22, 2024

- Yo now automatically disables the less secure, legacy [IMDS v1
  endpoints](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/gettingmetadata.htm#upgrading-v2)
  by default. The configuration `allow_legacy_imds_endpoints` and corresponding
  `--allow-legacy-imds-endpoints` flag for `yo launch` have been added to
  disable this feature, but in most situations there should be no reason to
  change this.
- A new, experimental command called `yo script` allows you to write a Python
  script using Yo's helpers. Some of Yo's internals have been refactored in a
  way to make it easier to do basic operations like launching an instance
  programatically. Please note that the internal APIs of Yo aren't considered
  stable, so future updates may break compatibility with such scripts.
- OCI Service Errors are now caught and handled in a slightly nicer way. While a
  traceback is still shown, we try to de-emphasize it, and show the actual OCI
  error message. This way, users may be able to easily see what went wrong, in
  case it was a user error rather than Yo client error.
- Add some code to handle rate-limiting from the OCI API by backing off, in the
  `yo list --ip` command.
- Boot volumes can now be attached and detached.
- Improved zsh completion scripts, courtesy of @rpigott.

## 1.7.3 - Wed, Sep 11, 2024

- Fixed crash in `yo images` parsing an OS value without colon.
- Added user-friendly catch for a common error: adding a comment at the end of a
  `~/.oci/yo.ini` value.

## 1.7.2 - Mon, Sep 9, 2024

- Added zsh completion script, thanks @rpigott!
- Fixed race condition in launching tasks on some `ssh` / OS versions.
- Fixed copy/paste error in argument description of `yo compat --image-names`

## 1.7.1 - Fri, Aug 30, 2024

- Fixed a cache contamination bug when switching between OCI regions.
- `yo cache-clean` now cleans caches from all region, and the old legacy cache
- Allow extensions to customize the default config file.
- Improve the initial configuration phases a bit.

## 1.7.0 - Thu, Aug 29, 2024

- Yo now has support for multiple OCI regions!
  - Previously, if you wanted to run yo against another OCI region, you needed
    to edit your config, run `yo cache-clean`, and then run your commands.
  - Now, Yo allows you to store configuration for several OCI regions into your
    config. You set a default region in your config file, but you can override
    it with the `YO_REGION` environment variable, or `yo -r REGION` on the
    command line.
  - Please see the documentation for a migration guide:
    https://oracle.github.io/yo/guide/region.html#migrating-yo-ini-to-multi-region-support
- Switched Yo's default setup dialog to use ``oci setup keys``. Updated
  documentation accordingly.
- Yo can now use OCI API keys which have a passphrase. It will automatically
  detect that a passphrase is required, and prompt only when attempting to use
  the API. Since many API results are cached, prompts aren't terribly frequent.
- The Yo image list now uses "natural sort". This ensures that images with
  numbers like "8.10" sort after "8.9", which is important if you have an
  operating system image with that version number :P


## 1.6.0 - Wed, Apr 17, 2024

New Features:

- The `yo list` command now has a completely configurable table.
  - Columns may be specified as a list in the config file (`list_columns`)
  - An alternative list may be specified via `yo list -C a,b,c`
  - Columns can be added to the end of the table with `yo list -x Column`
- The `yo list` command includes a new column, `ResourceType`, which corresponds
  to the value of the `Oracle-Recommended-Tags.ResourceType` tag.

## 1.5.1 - Tue, Apr 9, 2024

Another tiny release, which I configure a "bugfix release".

Fixes:

- Fixed a crash with `yo nmi`
- Added `--ad` option to `yo launch` which was a bit of an oversight

## 1.5.0 - Mon, Feb 5, 2024

This is a very tiny release with just three changes.

New Features:

- The "yo attach" and "yo detach" commands now work with boot volumes.

Fixes:

- Allow "yo teardown" operation to occur in states other than RUNNING.
  Specifically, it should be possible to teardown STOPPED instances. The
  operation isn't permitted in TERMINATED or TERMINATING states.
- Respect the termination protection option for "yo teardown". Previously, "yo
  teardown" would happily terminate a protected instance.

## 1.4.0 - Fri, Dec 15, 2023

This version of Yo comes with some major improvements.

New Features:

- Two new instance actions are added: "teardown" and "rebuild". The teardown
  operation terminates the instance, but preserves the boot volume, and attaches
  some metadata to the instance so that Yo will know how to rebuild it the way
  it was. The "rebuild" operation does exactly that.
  - This operation might be preferred instead of "stop" and "start" in cases
    where your tenancy is encountering service limits. Stopped instances still
    count toward your service limits, while terminated instances do not.
  - Please note that for now, "teardown" cannot remember what block volumes were
    attached to your instance, and so "rebuild" will not reattach block volumes
    (aside from the boot volume, of course). This feature could be added if
    there is demand for it.
- You may now specify a custom username for your instances! This can be
  specified in your instance profile configuration, or on the `yo launch`
  command line. Yo will automatically keep track of the username for each
  instance using a tag, so you don't need to remember which you chose. So the
  existing `yo ssh` commands will work regardless of your username choice.
- You may now specify a boot volume to launch an instance from. If you
  terminated a volume with (`--preserve-root`), then you can launch an instance
  from the same boot volume. This operation is similar to "rebuild", except that
  you must manually specify the instance shape, name, etc.
- There is a new command, `yo copy-id`, which wraps `ssh-copy-id`. Use it to
  copy SSH keys over to an instance. For the most part, you shouldn't need this
  because Yo passes your key in anyway, but it could be useful to add more keys.

Changes:

- The default configuration of Yo now specifies the `VM.Standard.x86.Generic`
  shape with 1 CPU and 8 GiB of memory.
- The `yo list` command no longer shows instances in `TERMINATING` state.
- The `yo -h` help output is now organized into logical categories with
  well-written command summaries.
- Documentation for each Yo sub-command is now automatically generated to match
  the CLI.
- Sub-commands are now permitted: commands like `yo volume-list` are now `yo
  volume list`. However, the old spellings are still permitted, as we don't want
  to break anybody's muscle memory.
- Yo's command aliasing is now improved. Prior to this release, Yo used
  shortest-prefix aliasing, but if you wanted to specify your own alias mapping,
  then shortest-prefix mappings were disabled. This limitation has now been
  removed. If you specify custom aliases, then Yo will use them, and will still
  create shortest-prefix aliases for the rest of the commands.

Fixes:

- Fixes an error due to a missing minimum version of the `rich` library.
- If you have provided memory / cpu configurations in an instance profile, but
  you then override the profile with a non-flex shape, Yo used to raise an
  error. However, this isn't a very helpful error: it's clear the user wants the
  non-flex shape and forgot about the default flex configuration. So we've
  removed this unnecessary error.

## 1.3.1 - Wed, Sept 6, 2023

Fixes:

- Fix `FileExistsError` on Windows.

## 1.3.0 - Fri, Sept 1, 2023

Changes:

- The look & feel of Yo has been updated a bit. Progress bars have been removed
  in favor of spinners, since we can't accurately predict progress most of the
  time anyway. The spinners also show the time elapsed even after completion, so
  that you know how long Yo spent waiting for each action. Most of the printouts
  now also include a timestamp.
- Yo now catches Ctrl-C gracefully and exits without a traceback.
- The `creator_tags` configuration option is added. This configuration is
  related to how Yo tracks instances which you've created. If Yo is already
  working for you, there's no need to care about it.

Fixes:

- Fixed some bugs related to parsing information in InstanceProfile.
- Fixed a very rare bug related to the automatic update checking.
- Fixed a bug related to the default configuration of memory for flexible CPU
  instances.

## 1.2.0 - Wed, Aug 9, 2023

New features:

- Add `yo launch --wait-ssh`, which waits for SSH to come up, but doesn't
  actually connect you to SSH.
- Add `yo list --ip`, which adds an IP address column for `yo list`.
- Improved the speed of IP address lookups, when loading IPs for several
  instances at a time (e.g. `yo list --ip` or `yo ip`).
- Add `yo list --all`, which prints info about all instances in the compartment,
  not just your own. Yo still is not capable of managing these instances, it is
  just an informational view.
- The short argument `-E` is now usable in place of `--exact-name`.
- The `--exact-name -E` arguments are now added to the block volume management
  commands. They apply both to the name of the instance, and the block volume.
- A new configuration, `exact_name`, is added to the `yo.ini`. This has the
  effect of implying `--exact-name` on every command without you needing to type
  it.
- A new argument, `--no-exact-name`, allows you to override `exact_name = true`
  in your configuration on a case-by-case basis.
- A new configuration, `resource_filtering`, is added to `yo.ini`. This allows
  Yo to view and manage all resources in your compartment, not just the ones
  you've created. This is not a recommended configuration, please be careful
  when using this.
- During `yo list`, Yo will now automatically check for newer versions in the
  background. If it finds a newer version, it will print a notice. As a default,
  the version checks are a minimum of 6 hours apart, but this can be configured
  with the config `check_for_update_every`. Setting the configuration to 0 will
  disable the feature.

Changes:

- `yo list` now sorts your instances by creation time, rather than the default
  (presumably undefined) ordering returned by the API.

Fixes:

- A rare issue with concurrent accesses to the Yo cache has been resolved.
  Cache updates are now atomic.
- Yo now refreshes the instance list prior to running the start, stop, reboot,
  terminate commands. This ensures that it is operating on the correct set of
  instances, avoiding rare but important caching bugs.
- Improved error messages that occur when looking up an instance by name, so
  that the message includes the actual instance that Yo tried to search for (as
  impacted by `--exact-name`).
- Fixed a compatibility issue with Windows due to the use of "fchmod()"
- Fixed a silly bug in which `yo cache-clean` failed if the cache file does not
  exist.

## 1.1.0 - Tue, July 18, 2023

- Yo now adds the freeform tag: `{"yo-created-by": "your.email@example.com"}` to
  every instance it launches.
  - In cases where the tenancy does not automatically add a
    `Oracle-Tags.CreatedBy` tag, we fall back to the above freeform tag to
    identify instances launched by the current Yo user.
  - If the `Oracle-Tags.CreatedBy` tag is not present on instances in your
    tenancy, Yo prints a loud warning with more information. You can silence
    this warning by setting `silence_automatic_tag_warning = true` in the
    config.
- Yo can now handle instances of `Oracle-Tags.CreatedBy` which contain a prefix
  ending in a slash (`/`) before the email address.

## 1.0.4 - Mon, June 5, 2023

- Bugfix release for the extension API changes in 1.0.3.

## 1.0.3 - Fri, June 2, 2023

- A minor change to an internal extension API, which was omitted in 1.0.2.

## 1.0.2 - Fri, June 2, 2023

- The SSH options added in 1.0.1 have been updated to improve compatibility with
  older SSH versions. If you encountered the following error during a `yo
  console`, then it's likely this fix will resolve your issue:

      command-line: line 0: Bad configuration option: pubkeyacceptedalgorithms

- Yo no longer crashes when encountering an instance with multiple VNIC
  attachments. Instead, it just warns that it is blindly taking the first VNIC.
  We'll need more user feedback to inform the correct behavior.

## 1.0.1 - Tue, May 9, 2023

- Yo is now located at `https://github.com/oracle/yo`, and documentation is now
  located at `https://oracle.github.io/yo/`. This will be its permanent home,
  please update any bookmarks.
- Some SSH options have been added for the Instance Console Connection, in order
  to make it work on newer OpenSSH versions.
- The documentation has been improved in a few places: namely regarding SSH
  configuration.

## 1.0.0 - Tue, April 18, 2023

This is the initial public release of Yo! It's the culmination of 26 minor
internal releases over 2.5 years, and we're pleased to present it to the public.
