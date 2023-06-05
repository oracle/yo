# Changelog

## Unreleased

Any changes which are committed, but not yet present in a released version,
should appear here.

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
