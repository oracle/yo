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
from setuptools import find_packages
from setuptools import setup

long_description = open("README.md").read()

VERSION = "1.5.0"

setup(
    name="yo",
    version=VERSION,
    description="A fast and simple CLI client for managing OCI instances",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=[
        # TaskProgressColumn
        "rich>=12.3.0",
        # Older versions of OCI SDK don't have support for things like
        # quota_names for Images. While that particular issue was resolved by an
        # version prior to 2.85.0, I think there's no reason for me not to
        # request a relatively recent version, i.e. the latest as of this
        # writing.
        "oci>=2.85.0",
        "subc>=0.8.0",
        "setuptools",
        "argcomplete",
        "dataclasses",
    ],
    url="https://github.com/oracle/yo",
    author="Oracle",
    author_email="stephen.s.brennan@oracle.com",
    license="UPL",
    packages=find_packages(include=["yo", "yo.*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Universal Permissive License (UPL)",
        "Development Status :: 5 - Production/Stable",
        "Natural Language :: English",
    ],
    keywords="oci client",
    entry_points={
        "console_scripts": [
            "yo=yo.main:main",
        ],
    },
    package_data={
        "yo": [
            "data/yo-tasks/*",
            "data/sample.yo.ini",
            "data/yo_tasklib.sh",
        ],
    },
)
