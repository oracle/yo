#!/bin/bash
# Publish documentation. Assumes documentation was already generated via the
# "make docs" target.
#
# NOTE: this is only for use by Yo maintainers. It will not work if you don't
# have push access.

YO_DIR=$(pwd)
TMPDIR=$(mktemp -d)
cleanup() {
	cd "$YO_DIR"
	rm -rf "$TMPDIR"
}
trap cleanup EXIT

echo "Preparing gh-pages commit at $TMPDIR"
git clone git@github.com:oracle/yo --depth 1 --branch gh-pages "$TMPDIR"
cd "$TMPDIR"
cp -rT "$YO_DIR/.tox/docs_out/" .
git commit -a -m "Automatic documentation update"
git push origin HEAD
