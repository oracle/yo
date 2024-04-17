#!/usr/bin/env python3
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
import datetime
import typing as t
import uuid
from types import SimpleNamespace

from yo.api import now
from yo.api import TERMPROTECT
from yo.api import YoImage
from yo.api import YoInstance
from yo.util import YoConfig


AVAILABILITY_DOMAIN = "VkEH:US-ASHBURN-AD-1"

SHAPE = "VM.Standard.E2.2"

MY_EMAIL = "test@example.com"
NOT_MY_EMAIL = "test2@example.com"

MY_USERNAME = "test"

_NAME_SEQNO = 1


class FakeResponse:
    data: t.Any

    def __init__(self, data: t.Any) -> None:
        self.data = data


def _random_id() -> str:
    return str(uuid.uuid4())


def _unique_name() -> str:
    global _NAME_SEQNO
    name = "{}-vm-{}".format(MY_USERNAME, _NAME_SEQNO)
    _NAME_SEQNO += 1
    return name


def short_name(name: str, username: str = MY_USERNAME) -> str:
    assert name.startswith(username + "-")
    return name[len(username) + 1 :]


def instance_factory(**kwargs) -> YoInstance:
    defaults = {
        "name": _unique_name(),
        "id": _random_id(),
        "ad": AVAILABILITY_DOMAIN,
        "state": "RUNNING",
        "shape": SHAPE,
        "memory_gb": 16,
        "ocpu": 2,
        "time_created": now() - datetime.timedelta(seconds=60),
        "image_id": _random_id(),
        "termination_protected": False,
        "created_by": MY_EMAIL,
        "freeform_tags": {TERMPROTECT: "false"},
        "username": None,
    }
    defaults.update(kwargs)
    defaults["defined_tags"] = {
        "Oracle-Tags": {"CreatedBy": defaults.pop("created_by")},
    }
    return YoInstance(**defaults)  # type: ignore


def image_factory(**kwargs) -> YoImage:
    defaults = {  # type: ignore
        "name": _unique_name(),
        "id": _random_id(),
        "ad": AVAILABILITY_DOMAIN,
        "state": "AVAILABLE",
        "base_image_id": None,
        "compartment_id": None,
        "display_name": "Dummy-Oracle-Linux-8",
        "launch_mode": "foo",
        "os": "Oracle Linux",
        "os_version": "8",
        "size_in_mbs": 123,
        "time_created": datetime.datetime.now()
        - datetime.timedelta(seconds=60),
        "compatibility": {},
        "created_by": None,
    }
    defaults.update(kwargs)
    return YoImage(**defaults)  # type: ignore


def config_factory(**kwargs) -> YoConfig:
    defaults = {
        "instance_compartment_id": _random_id(),
        "vcn_id": _random_id(),
        "subnet_compartment_id": _random_id(),
        "my_email": MY_EMAIL,
        "my_username": "test",
        "ssh_public_key": "/fake/path/to/id_rsa.pub",
        "region": "fake-testing-region",
        "list_columns": "Name,Shape,Mem,CPU,State,Created",
        "silence_automatic_tag_warning": True,
    }
    defaults.update(kwargs)
    return YoConfig(**defaults)  # type: ignore


def oci_instance_factory(**kwargs) -> t.Any:
    defaults = {
        "id": _random_id(),
        "display_name": _unique_name(),
        "availability_domain": AVAILABILITY_DOMAIN,
        "lifecycle_state": "RUNNING",
        "time_created": now() - datetime.timedelta(seconds=60),
        "image_id": _random_id(),
        "shape": SHAPE,
        # shape_config
        "memory_in_gbs": 16,
        "ocpus": 2,
        # tags
        "created_by": MY_EMAIL,
        "freeform_tags": {TERMPROTECT: "false"},
    }
    defaults.update(kwargs)
    defaults["shape_config"] = SimpleNamespace(
        memory_in_gbs=defaults.pop("memory_in_gbs"),
        ocpus=defaults.pop("ocpus"),
    )
    defaults["defined_tags"] = {
        "Oracle-Tags": {"CreatedBy": defaults.pop("created_by")},
    }
    return SimpleNamespace(**defaults)


def oci_instance_fromyo(i: YoInstance) -> t.Any:
    return oci_instance_factory(
        id=i.id,
        display_name=i.name,
        availability_domain=i.ad,
        lifecycle_state=i.state,
        time_created=i.time_created,
        image_id=i.image_id,
        shape=i.shape,
        memory_in_gbs=i.memory_gb,
        ocpus=i.ocpu,
        freeform_tags={TERMPROTECT: str(i.termination_protected).lower()},
    )
