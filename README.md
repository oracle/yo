# yo - fast and simple OCI client

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
  simple as `yo launch` (or, for the lazier, `yo la`).
- yo lets you refer to your instances by name. You should never need to memorize
  an IP address again.
- yo aggressively caches data to make operations as quick as possible.

## Installation

A minimum of Python 3.6 is required in order to use Yo.

**Via Pip:**

    pip install yo oci-cli

This will install the standard OCI CLI alongside Yo, which can be useful as
well.  After installation, you'll need to configure Yo to work with your OCI
tenancy.  Please see the [documentation][] for detailed instructions.

## Documentation

The [documentation][] contains information on the configuration file, as well as
a listing of sub-commands and features offered.

## Examples

```bash
# Launch an instance based on your default settings, and SSH into it
yo launch -s

# Launch a flexible instance with given shape, size, and name
yo launch -S VM.Standard.E4.Flex --cpu 3 --mem 12 -n my-vm

# SSH into my-vm
yo ssh my-vm

# Copy files to my-vm
yo scp ./files my-vm:

# Terminate my-vm
yo terminate my-vm
```

## Help

We hope you can find all the answers to your questions in our documentation. But
if you're still having trouble, feel free to open a Github issue and we'll try
our best to help!

## Contributing

We welcome contributions from the community. Before submitting a pull request,
please [review our contribution guide][contributing].

## Security

Please consult the [security guide][security] for our responsible security
vulnerability disclosure process.

## License

Copyright (c) 2023 Oracle and/or its affiliates.

Released under the Universal Permissive License v1.0 as shown at
https://oss.oracle.com/licenses/upl/.

[documentation]: https://oracle.github.io/yo/
[contributing]: ./CONTRIBUTING.md
[security]: ./SECURITY.md
