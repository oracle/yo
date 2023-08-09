# Changelog

## Unreleased

Any changes which are committed, but not yet present in a released version,
should appear here.

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
