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

from yo.api import AttachmentType
from yo.api import now
from yo.api import SAVEDATA
from yo.api import ShapeMemoryOptions
from yo.api import ShapeOcpuOptions
from yo.api import TERMPROTECT
from yo.api import VolumeKind
from yo.api import YoImage
from yo.api import YoInstance
from yo.api import YoShape
from yo.api import YoVolume
from yo.api import YoVolumeAttachment
from yo.util import YoConfig
from yo.util import YoRegion


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
        "mtime": 123,
        "instance_compartment_id": _random_id(),
        "my_email": MY_EMAIL,
        "my_username": "test",
        "ssh_public_key": "/fake/path/to/id_rsa.pub",
        "region": "fake-testing-region",
        "list_columns": "Name,Shape,Mem,CPU,State,Created",
        "silence_automatic_tag_warning": True,
        "regions": {
            "fake-testing-region": YoRegion(
                name="fake-testing-region",
                vcn_id=_random_id(),
                subnet_compartment_id=_random_id(),
            ),
        },
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


def shape_factory(**kwargs) -> YoShape:
    defaults = {
        "name": SHAPE,
        "shape": SHAPE,
        "processor_description": "",
        "ocpus": 1,
        "memory_in_gbs": 1,
        "networking_bandwidth_in_gbps": 1,
        "max_vnic_attachments": 1,
        "gpus": 0,
        "gpu_description": "",
        "local_disks": 0,
        "local_disks_total_size_in_gbs": 0,
        "local_disk_description": "",
        "is_flexible": False,
        "quota_names": [],
        "ocpu_options": None,
        "memory_options": None,
        "networking_bandwidth_options": None,
        "max_vnic_attachment_options": None,
    }
    defaults.update(kwargs)
    return YoShape(**defaults)  # type: ignore


def flex_shape_factory(**kwargs) -> YoShape:
    defaults = {
        "name": "VM.Standard.A1.Flex",
        "shape": "VM.Standard.A1.Flex",
        "ocpus": 1,
        "memory_in_gbs": 6,
        "is_flexible": True,
        "ocpu_options": ShapeOcpuOptions(min=1, max=4),
        "memory_options": ShapeMemoryOptions(
            default_per_ocpu_gbs=6,
            min_gbs=6,
            max_gbs=64,
            min_per_ocpu_gbs=1,
            max_per_ocpu_gbs=24,
        ),
    }
    defaults.update(kwargs)
    return shape_factory(**defaults)


def volume_factory(**kwargs) -> YoVolume:
    defaults = {
        "id": _random_id(),
        "name": _unique_name(),
        "ad": AVAILABILITY_DOMAIN,
        "state": "AVAILABLE",
        "kind": VolumeKind.BLOCK,
        "image_id": None,
        "compartment_id": _random_id(),
        "size_in_gbs": 100,
        "time_created": now(),
        "created_by": MY_EMAIL,
        "alt_name": None,
        "freeform_tags": {},
    }
    defaults.update(kwargs)
    if defaults["kind"] == VolumeKind.BOOT and defaults["image_id"] is None:
        defaults["image_id"] = _random_id()
    if defaults["alt_name"] is None:
        defaults["alt_name"] = str(defaults["name"]).replace(
            " (Boot Volume)", ""
        )
    return YoVolume(**defaults)  # type: ignore


def saved_boot_volume_factory(name: str, **kwargs) -> YoVolume:
    saved = kwargs.pop(
        "savedata",
        f"1,VM.Standard.A1.Flex,2,12,opc,{name}",
    )
    tags = dict(kwargs.pop("freeform_tags", {}))
    tags[SAVEDATA] = saved
    defaults = {
        "name": f"{name} (Boot Volume)",
        "kind": VolumeKind.BOOT,
        "image_id": _random_id(),
        "alt_name": name,
        "freeform_tags": tags,
    }
    defaults.update(kwargs)
    return volume_factory(**defaults)


def volume_attachment_factory(**kwargs) -> YoVolumeAttachment:
    defaults = {
        "id": _random_id(),
        "name": "attachment",
        "ad": AVAILABILITY_DOMAIN,
        "state": "ATTACHED",
        "kind": VolumeKind.BLOCK,
        "compartment_id": _random_id(),
        "volume_id": _random_id(),
        "instance_id": _random_id(),
        "time_created": now(),
        "attachment_type": AttachmentType.PV,
        "ro": False,
        "shared": False,
        "device": "/dev/oracleoci/oraclevdb",
        "iscsi_ipv4": None,
        "iscsi_port": None,
        "iscsi_chap_username": None,
        "iscsi_chap_password": None,
        "iscsi_iqn": None,
    }
    defaults.update(kwargs)
    return YoVolumeAttachment(**defaults)  # type: ignore


def oci_boot_volume_fromyo(vol: YoVolume) -> t.Any:
    return SimpleNamespace(
        id=vol.id,
        display_name=vol.name,
        availability_domain=vol.ad,
        lifecycle_state=vol.state,
        image_id=vol.image_id,
        compartment_id=vol.compartment_id,
        size_in_gbs=vol.size_in_gbs,
        time_created=vol.time_created,
        defined_tags={},
        freeform_tags=vol.freeform_tags,
    )


def oci_block_attachment_factory(**kwargs) -> t.Any:
    defaults = {
        "id": _random_id(),
        "display_name": "attach-block",
        "availability_domain": AVAILABILITY_DOMAIN,
        "lifecycle_state": "ATTACHING",
        "compartment_id": _random_id(),
        "volume_id": _random_id(),
        "instance_id": _random_id(),
        "time_created": now(),
        "attachment_type": "paravirtualized",
        "is_shareable": False,
        "is_read_only": False,
        "device": "/dev/oracleoci/oraclevdb",
        "ipv4": None,
        "port": None,
        "chap_username": None,
        "chap_secret": None,
        "iqn": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def oci_boot_attachment_factory(**kwargs) -> t.Any:
    defaults = {
        "id": _random_id(),
        "display_name": "attach-boot",
        "availability_domain": AVAILABILITY_DOMAIN,
        "lifecycle_state": "ATTACHING",
        "compartment_id": _random_id(),
        "boot_volume_id": _random_id(),
        "instance_id": _random_id(),
        "time_created": now(),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)
