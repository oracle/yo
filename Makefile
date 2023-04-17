# Copyright (c) 2023, Oracle and/or its affiliates.
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or data
# (collectively the "Software"), free of charge and under any and all copyright
# rights in the Software, and any and all patent rights owned or freely
# licensable by each licensor hereunder covering either (i) the unmodified
# Software as contributed to or provided by such licensor, or (ii) the Larger
# Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the
#     lrgrwrks.txt file if one is included with the Software (each a "Larger
#     Work" to which the Software is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright notice
# and either this complete permission notice or at a minimum a reference to the
# UPL must be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

VERSION=$(shell grep 'VERSION =' setup.py | sed s/\"//g | awk '{print($$3)}')

PYTHON ?= python3
pyver_maj = $(shell $(PYTHON) --version | cut -d. -f1 | sed 's/Python //')
pyver_min = $(shell $(PYTHON) --version | cut -d. -f2)

.PHONY: development
development:
	@if [ $(pyver_maj) -ne 3 ] || [ $(pyver_min) -lt 6 ]; then \
	    echo error: Your Python $(pyver_maj).$(pyver_min), from command \"$(PYTHON)\", is not supported; \
	    echo Yo requires Python 3.6 or newer.; \
	    echo If you have another installed, try using make PYTHON=/path/to/python; \
	    exit 1; \
	fi
	$(PYTHON) -m pip install --user --upgrade tox pre-commit
	$(PYTHON) -m pre_commit install --install-hooks

.PHONY: test
test:
	@$(PYTHON) -m tox

.PHONY: docs
docs:
	@$(PYTHON) -m tox -e docs

.PHONY: docs-publish
docs-publish: docs
	rsync -avz .tox/docs_out/ ca-common:public_html/yo

.PHONY: _release_sanity_check
_release_sanity_check:
	@if [ ! $$(git symbolic-ref -q HEAD) = "refs/heads/master"  ]; then \
	    echo error: You must be on master to release a new version.; \
	    exit 1; \
	fi
	@if [ ! -z "$$(git status --porcelain)" ]; then \
	    echo error: Your git tree is unclean, please commit or stash it.; \
	    exit 1; \
	fi
	@if [ "$$(git describe --tags --abbrev=0)" = "$(VERSION)" ]; then \
	    echo error: It looks like you have not bumped the version since last release.; \
	    exit 1; \
	fi
	@if [ -z "$$(grep ^$(shell echo $(VERSION) | sed 's/\./\\./g') CHANGELOG.md)" ]; then \
	    echo error: It looks like you have not documented this release in CHANGELOG.md; \
	    exit 1; \
	fi
	@if [ -f dist/yo-$(VERSION).tar.gz ]; then \
	    echo error: There is already a built tarball: dist/yo-$(VERSION).tar.gz; \
	    echo Either verify you have bumped the version, or delete the; \
	    echo distributions you have built for $(VERSION); \
	    exit 1; \
	fi


.PHONY: release
release: _release_sanity_check test
	$(PYTHON) setup.py sdist
	$(PYTHON) setup.py bdist_wheel
	@echo "Built the following artifacts for yo $(VERSION):"
	@ls -l dist/yo-$(VERSION)*
	@echo "Point of no return: time to tag and upload this release"
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	@echo Confirmed
	twine upload -r oracle dist/yo-$(VERSION)*
	git push origin master
	git tag v$(VERSION)
	git push origin v$(VERSION)
