# -*- coding: utf-8 -*-
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
"""
Yo context module - contains the code for interacting with/hiding OCI API
"""
import collections
import concurrent.futures
import contextlib
import dataclasses
import datetime
import enum
import json
import os
import re
import stat
import typing as t
from collections import defaultdict

import rich.console

import yo.util
from yo.util import check_args_dataclass
from yo.util import current_yo_version
from yo.util import fmt_allow_deny
from yo.util import latest_yo_version
from yo.util import one
from yo.util import standardize_name
from yo.util import YoConfig
from yo.util import YoExc

# These imports are not evaluated but are added to help type checking
if t.TYPE_CHECKING:
    from oci.core import BlockstorageClient
    from oci.core import ComputeClient
    from oci.core import VirtualNetworkClient
    from oci.identity import IdentityClient
    from oci.limits import LimitsClient
    from oci.core.models import BootVolume
    from oci.core.models import BootVolumeAttachment
    from oci.core.models import Instance
    from oci.core.models import InstanceConsoleConnection
    from oci.core.models import Vnic
    from oci.core.models import VnicAttachment
    from oci.core.models import Image
    from oci.core.models import ImageShapeCompatibilityEntry
    from oci.core.models import Shape
    from oci.core.models import Subnet
    from oci.core.models import Volume
    from oci.core.models import VolumeAttachment


_ISOFORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"

# Tag applied to instances which prevents Yo from terminating the instance. This
# is not an OCI feature, just a safeguard that Yo optionally provides.
TERMPROTECT = "yo-termination-protected"

# Tag applied to instances automatically at launch time by Yo, containing
# information about who created the instance. Used to resolve situations where
# tenancies don't have the automatic tag rule.
CREATEDBY = "yo-created-by"

# Tag applied to instances automatically at launch time by Yo, containing the
# login username. For default usernames, this can be determined without the tag
# (by finding the image and looking up its default username). But for custom
# usernames, the information must be saved.
USERNAME = "yo-username"

# Tag applied to boot volumes when Yo "saves" them. It contains the instance
# shape info, username, and previous instance name.
SAVEDATA = "yo-savedata"

AUTO_TAG_DOC_LINK = "https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingautomaticdefaulttags.htm"

OS_TO_USER = collections.defaultdict(lambda: "opc")
OS_TO_USER["Canonical Ubuntu"] = "ubuntu"


def fromisoformat(s: str) -> datetime.datetime:
    """
    Given a string representing a TZ-aware datetime (in ISO format), parse it
    and load it. This is to be used by dataclasses for deserializing.
    """
    return datetime.datetime.strptime(s, _ISOFORMAT)


def toisoformat(dt: datetime.datetime) -> str:
    """
    Did you know that for being an "ISO format", Python's isoformat() is not
    very stable across versions, and can't always be reversed using strftime?
    Let's not bother with it.
    """
    return dt.strftime(_ISOFORMAT)


def _convert_dts_to_string(
    d: t.Dict[str, t.Any], k: t.Type["YoCachedItem"]
) -> None:
    """
    Given a dictionary which about to be encoded to JSON, and k, a dataclass
    type, convert all the fields which are of datetime type to string.
    """
    for field in dataclasses.fields(k):
        if isinstance(d[field.name], datetime.datetime):
            d[field.name] = toisoformat(d[field.name])


def _convert_dts_from_string(
    d: t.Dict[str, t.Any], k: t.Type["YoCachedItem"]
) -> None:
    """
    Given a dictionary which was freshly loaded from JSON, and k, a dataclass
    type, convert all the fields which have type "datetime" from string to
    datetime.
    """
    for field in dataclasses.fields(k):
        if field.type is datetime.datetime:
            d[field.name] = fromisoformat(d[field.name])


def _maybe_simple_dc(
    d: t.Dict[str, t.Any], name: str, k: t.Type[t.Any]
) -> None:
    """
    Load an optional field from a dictionary (maybe) and turn it into a
    dataclass instance. Then place it back into the dictionary. This is to
    be used by dataclasses when they are deserializing themselves back from
    JSON.
    """
    val = d.get(name)
    if val:
        val = k(**val)
        d[name] = val


def now() -> datetime.datetime:
    """
    datetime.now() does not return a tz-aware datetime, for some strange reason.
    So, this now() helper function does just that, returning now() in the local
    system timezone.

    For our purposes, all datetimes need to be tz-aware, because we serialize
    them with timezones.
    """
    return datetime.datetime.now().astimezone()


class ImageLoad(enum.Enum):
    UNIQUE = "UNIQUE"
    LATEST = "LATEST"

    def __str__(self) -> str:
        return self.value


def flex_list(arg: t.Union[str, t.List[str]]) -> t.List[str]:
    if isinstance(arg, str):
        return arg.split(",")
    else:
        return arg


@dataclasses.dataclass
class InstanceProfile:
    # NB: non-STR types here will not automatically be parsed/casted from config
    # file. Please be sure to do appropriate processing in from_dict()
    availability_domain: str
    shape: str
    tasks: t.List[str] = dataclasses.field(default_factory=list)
    name: str = "vm-1"  # this will get prefixed and incremented as necessary
    os: t.Optional[str] = None
    image: t.Optional[str] = None
    boot_volume_size_gbs: t.Optional[int] = None
    cpu: t.Optional[float] = None
    mem: t.Optional[float] = None
    load_image: ImageLoad = ImageLoad.UNIQUE
    username: t.Optional[str] = None

    def create_arg_dict(self) -> t.Dict[str, t.Any]:
        return {
            "availability_domain": self.availability_domain,
            "boot_volume_size_gbs": self.boot_volume_size_gbs,
            "shape": self.shape,
        }

    @staticmethod
    def from_dict(d: t.Dict[str, t.Any], name: str) -> "InstanceProfile":
        d = d.copy()
        check_args_dataclass(
            InstanceProfile, d.keys(), f"~/.oci/yo.ini \\[{name}] section"
        )
        types: t.Dict[str, t.Callable[[t.Any], t.Any]] = {
            "boot_volume_size_gbs": int,
            "cpu": float,
            "mem": float,
            "load_image": ImageLoad,
            "tasks": flex_list,
        }
        for field, tp in types.items():
            if field in d:
                val = d[field]
                if val is None:
                    del d[field]  # use default from dataclass
                else:
                    d[field] = tp(d[field])
        return InstanceProfile(**d)

    def validate(self, name: str) -> None:
        if not (self.image or self.os):
            raise YoExc(
                f"Instance profile {name} must specify one of: image, os"
            )
        if self.image and self.os:
            raise YoExc(f"Instance profile {name} specifies both: image, os")


CI = t.TypeVar("CI", bound="YoCachedItem")


@dataclasses.dataclass
class YoCachedItem:
    name: str

    def to_json(self) -> t.Dict[str, t.Any]:
        d = dataclasses.asdict(self)
        _convert_dts_to_string(d, type(self))
        return d

    @classmethod
    def from_json(cls: t.Type[CI], d: t.Dict[str, t.Any]) -> CI:
        _convert_dts_from_string(d, cls)
        return cls(**d)

    def same_item(self, other: "YoCachedItem") -> bool:
        return type(self) is type(other) and self.name == other.name


@dataclasses.dataclass
class YoCachedWithId(YoCachedItem):
    id: str

    def same_item(self, other: YoCachedItem) -> bool:
        # type check here is looser, but OCI ID's should be unique across
        # different types of objects
        return isinstance(other, YoCachedWithId) and self.id == other.id


@dataclasses.dataclass
class YoInstance(YoCachedWithId):
    ad: str
    state: str
    shape: str
    memory_gb: int
    ocpu: int
    time_created: datetime.datetime
    image_id: str
    termination_protected: bool
    freeform_tags: t.Dict[str, str]
    username: t.Optional[str]  # from tag

    @classmethod
    def from_oci(cls, oci: "Instance") -> "YoInstance":
        term_protect = oci.freeform_tags.get(TERMPROTECT, "false") == "true"
        return cls(
            id=oci.id,
            name=oci.display_name,
            ad=oci.availability_domain,
            state=oci.lifecycle_state,
            shape=oci.shape,
            memory_gb=oci.shape_config.memory_in_gbs,
            ocpu=oci.shape_config.ocpus,
            time_created=oci.time_created,
            image_id=oci.image_id,
            termination_protected=term_protect,
            freeform_tags=oci.freeform_tags,
            username=oci.freeform_tags.get(USERNAME),
        )


@dataclasses.dataclass
class YoVnic(YoCachedWithId):
    ad: str
    state: str
    instance_id: str
    attachment_id: str
    subnet_id: str
    vlan_id: t.Optional[str]
    time_created: datetime.datetime
    nic_index: int
    private_ip: str
    public_ip: t.Optional[str]

    @classmethod
    def from_oci(cls, vnic: "Vnic", atch: "VnicAttachment") -> "YoVnic":
        tc = vnic.time_created
        if isinstance(tc, str):
            tc = fromisoformat(tc)
        return cls(
            id=vnic.id,
            name=vnic.display_name,
            ad=vnic.availability_domain,
            state=vnic.lifecycle_state,
            instance_id=atch.instance_id,
            attachment_id=atch.id,
            subnet_id=atch.subnet_id,
            vlan_id=atch.vlan_id,
            time_created=tc,
            nic_index=atch.nic_index,
            public_ip=vnic.public_ip,
            private_ip=vnic.private_ip,
        )


@dataclasses.dataclass
class ImageCompatibility:
    shape: str
    image_id: str
    min_ocpu: t.Optional[int]
    max_ocpu: t.Optional[int]
    min_mem_gbs: t.Optional[int]
    max_mem_gbs: t.Optional[int]

    @classmethod
    def from_oci(
        cls, c: "ImageShapeCompatibilityEntry"
    ) -> "ImageCompatibility":
        min_ocpu = None
        max_ocpu = None
        if c.ocpu_constraints:
            min_ocpu = c.ocpu_constraints.min
            max_ocpu = c.ocpu_constraints.max
        min_mem_gbs = None
        max_mem_gbs = None
        if c.memory_constraints:
            min_mem_gbs = c.memory_constraints.min_in_gbs
            max_mem_gbs = c.memory_constraints.max_in_gbs
        return cls(
            shape=c.shape,
            image_id=c.image_id,
            min_ocpu=min_ocpu,
            max_ocpu=max_ocpu,
            min_mem_gbs=min_mem_gbs,
            max_mem_gbs=max_mem_gbs,
        )


@dataclasses.dataclass
class YoImage(YoCachedWithId):
    ad: str
    state: str
    base_image_id: t.Optional[str]
    compartment_id: t.Optional[str]
    display_name: str
    launch_mode: str
    os: str
    os_version: str
    size_in_mbs: int
    time_created: datetime.datetime
    compatibility: t.Dict[str, ImageCompatibility]
    created_by: t.Optional[str]

    @classmethod
    def from_json(cls, d: t.Dict[str, t.Any]) -> "YoImage":
        _convert_dts_from_string(d, cls)
        d["compatibility"] = {
            k: ImageCompatibility(**v) for k, v in d["compatibility"].items()
        }
        return cls(**d)

    @classmethod
    def from_oci(cls, img: "Image") -> "YoImage":
        os_version = img.operating_system_version
        # Hack: I don't have good support for matching a GPU instance to the
        # appropriate image with GPU support. "Detect" GPU support in the image name
        # and mark it as a separate image.
        if "GPU" in img.display_name:
            os_version += " GPU"

        created_by = img.defined_tags.get("Oracle-Tags", {}).get("CreatedBy")
        if not created_by:
            created_by = img.freeform_tags.get(CREATEDBY)
        return cls(
            id=img.id,
            name=img.display_name,
            ad="",
            state=img.lifecycle_state,
            base_image_id=img.base_image_id,
            compartment_id=img.compartment_id,
            display_name=img.display_name,
            launch_mode=img.launch_mode,
            os=img.operating_system,
            os_version=os_version,
            size_in_mbs=img.size_in_mbs,
            time_created=img.time_created,
            compatibility={},
            created_by=created_by,
        )


class VolumeKind(str, enum.Enum):
    BOOT = "boot"
    BLOCK = "block"


@dataclasses.dataclass
class SavedInstanceMetadata:
    shape: str
    ocpu: int
    memory_gb: int
    username: str
    name: str

    @classmethod
    def from_str(cls, s: str) -> "SavedInstanceMetadata":
        if not s.startswith("1,"):
            raise YoExc("cannot understand saved instance metadat")
        _, shape, ocpu_str, mem_str, user, name = s.split(",", 5)
        ocpu = int(ocpu_str)
        mem = int(mem_str)
        return SavedInstanceMetadata(shape, ocpu, mem, user, name)


@dataclasses.dataclass
class YoVolume(YoCachedWithId):
    ad: str
    state: str
    kind: VolumeKind
    image_id: t.Optional[str]
    compartment_id: str
    size_in_gbs: int
    time_created: datetime.datetime
    created_by: t.Optional[str]
    alt_name: str
    freeform_tags: t.Dict[str, str]

    @classmethod
    def from_json(cls: t.Type[CI], d: t.Dict[str, t.Any]) -> CI:
        _convert_dts_from_string(d, cls)
        d["kind"] = VolumeKind(d["kind"])
        return cls(**d)

    @classmethod
    def from_oci_boot(cls, bv: "BootVolume") -> "YoVolume":
        created_by = bv.defined_tags.get("Oracle-Tags", {}).get("CreatedBy")
        if not created_by:
            created_by = bv.freeform_tags.get(CREATEDBY)
        suffix = " (Boot Volume)"
        alt_name = bv.display_name
        if alt_name.endswith(suffix):
            alt_name = alt_name[: -len(suffix)]
        return cls(
            id=bv.id,
            name=bv.display_name,
            ad=bv.availability_domain,
            state=bv.lifecycle_state,
            kind=VolumeKind.BOOT,
            image_id=bv.image_id,
            compartment_id=bv.compartment_id,
            size_in_gbs=bv.size_in_gbs,
            time_created=bv.time_created,
            created_by=created_by,
            alt_name=alt_name,
            freeform_tags=bv.freeform_tags,
        )

    @classmethod
    def from_oci_block(cls, bv: "Volume") -> "YoVolume":
        created_by = bv.defined_tags.get("Oracle-Tags", {}).get("CreatedBy")
        if not created_by:
            created_by = bv.freeform_tags.get(CREATEDBY)
        return cls(
            id=bv.id,
            name=bv.display_name,
            ad=bv.availability_domain,
            state=bv.lifecycle_state,
            kind=VolumeKind.BLOCK,
            image_id=None,
            compartment_id=bv.compartment_id,
            size_in_gbs=bv.size_in_gbs,
            time_created=bv.time_created,
            created_by=created_by,
            alt_name=bv.display_name,
            freeform_tags=bv.freeform_tags,
        )

    @property
    def saved_instance_metadata(self) -> t.Optional[SavedInstanceMetadata]:
        if not hasattr(self, "_saved_instance_metadata"):
            if SAVEDATA not in self.freeform_tags:
                self._saved_instance_metadata = None
            else:
                self._saved_instance_metadata = SavedInstanceMetadata.from_str(
                    self.freeform_tags[SAVEDATA]
                )
        return self._saved_instance_metadata


class AttachmentType(str, enum.Enum):
    ISCSI = "iscsi"
    PV = "paravirtualized"
    EMU = "emulated"
    BOOT = "boot"


@dataclasses.dataclass
class YoVolumeAttachment(YoCachedWithId):
    ad: str
    state: str
    kind: VolumeKind
    compartment_id: str
    volume_id: str
    instance_id: str
    time_created: datetime.datetime
    attachment_type: AttachmentType
    ro: bool
    shared: bool
    device: t.Optional[str]

    iscsi_ipv4: t.Optional[str]
    iscsi_port: t.Optional[int]
    iscsi_chap_username: t.Optional[str]
    iscsi_chap_password: t.Optional[str]
    iscsi_iqn: t.Optional[str]

    @classmethod
    def from_json(cls: t.Type[CI], d: t.Dict[str, t.Any]) -> CI:
        _convert_dts_from_string(d, cls)
        d["kind"] = VolumeKind(d["kind"])
        d["attachment_type"] = AttachmentType(d["attachment_type"])
        return cls(**d)

    @classmethod
    def from_oci_boot(cls, bva: "BootVolumeAttachment") -> "YoVolumeAttachment":
        return cls(
            id=bva.id,
            name=bva.display_name,
            ad=bva.availability_domain,
            state=bva.lifecycle_state,
            kind=VolumeKind.BOOT,
            compartment_id=bva.compartment_id,
            volume_id=bva.boot_volume_id,
            instance_id=bva.instance_id,
            time_created=bva.time_created,
            attachment_type=AttachmentType.BOOT,
            shared=False,
            ro=False,
            device=None,
            iscsi_ipv4=None,
            iscsi_port=None,
            iscsi_chap_username=None,
            iscsi_chap_password=None,
            iscsi_iqn=None,
        )

    @classmethod
    def from_oci_block(cls, bva: "VolumeAttachment") -> "YoVolumeAttachment":
        if bva.attachment_type == "iscsi":
            iscsi_args = {
                "iscsi_ipv4": bva.ipv4,
                "iscsi_port": bva.port,
                "iscsi_chap_username": bva.chap_username,
                "iscsi_chap_password": bva.chap_secret,
                "iscsi_iqn": bva.iqn,
            }
        else:
            iscsi_args = {
                "iscsi_ipv4": None,
                "iscsi_port": None,
                "iscsi_chap_username": None,
                "iscsi_chap_password": None,
                "iscsi_iqn": None,
            }
        return cls(
            id=bva.id,
            name=bva.display_name,
            ad=bva.availability_domain,
            state=bva.lifecycle_state,
            kind=VolumeKind.BLOCK,
            compartment_id=bva.compartment_id,
            volume_id=bva.volume_id,
            instance_id=bva.instance_id,
            time_created=bva.time_created,
            attachment_type=AttachmentType(bva.attachment_type),
            shared=bva.is_shareable,
            ro=bva.is_read_only,
            device=bva.device,
            **iscsi_args,
        )


@dataclasses.dataclass
class YoConsole(YoCachedWithId):
    ad: str
    state: str
    instance_id: str
    connection_string: str
    fingerprint: str

    @classmethod
    def from_oci(cls, con: "InstanceConsoleConnection") -> "YoConsole":
        return cls(
            id=con.id,
            name="",
            ad="",
            state=con.lifecycle_state,
            instance_id=con.instance_id,
            connection_string=con.connection_string,
            fingerprint=con.fingerprint,
        )


@dataclasses.dataclass
class YoSubnet(YoCachedWithId):
    ad: str
    state: str
    vcn_id: str
    cidr_block: str
    virtual_router_ip: str
    virtual_router_mac: str

    @classmethod
    def from_oci(cls, sub: "Subnet") -> "YoSubnet":
        return cls(
            id=sub.id,
            name=sub.display_name,
            ad=sub.availability_domain,
            state=sub.lifecycle_state,
            vcn_id=sub.vcn_id,
            cidr_block=sub.cidr_block,
            virtual_router_ip=sub.virtual_router_ip,
            virtual_router_mac=sub.virtual_router_mac,
        )


@dataclasses.dataclass
class ShapeOcpuOptions:
    max: float
    min: float


@dataclasses.dataclass
class ShapeMemoryOptions:
    default_per_ocpu_gbs: float
    min_gbs: float
    max_gbs: float
    min_per_ocpu_gbs: float
    max_per_ocpu_gbs: float


@dataclasses.dataclass
class ShapeNetworkingBandwidthOptions:
    min_gbps: float
    max_gbps: float
    default_per_ocpu_gbps: float


@dataclasses.dataclass
class ShapeMaxVnicAttachmentOptions:
    min: int
    max: float
    default_per_ocpu: float


@dataclasses.dataclass
class YoShape(YoCachedItem):
    shape: str
    processor_description: str
    ocpus: float
    memory_in_gbs: float
    networking_bandwidth_in_gbps: float
    max_vnic_attachments: int
    gpus: int
    gpu_description: str
    local_disks: int
    local_disks_total_size_in_gbs: float
    local_disk_description: str
    is_flexible: bool
    quota_names: t.List[str]
    ocpu_options: t.Optional[ShapeOcpuOptions]
    memory_options: t.Optional[ShapeMemoryOptions]
    networking_bandwidth_options: t.Optional[ShapeNetworkingBandwidthOptions]
    max_vnic_attachment_options: t.Optional[ShapeMaxVnicAttachmentOptions]

    @classmethod
    def from_json(cls, d: t.Dict[str, t.Any]) -> "YoShape":
        _convert_dts_from_string(d, cls)
        _maybe_simple_dc(d, "ocpu_options", ShapeOcpuOptions)
        _maybe_simple_dc(d, "memory_options", ShapeMemoryOptions)
        _maybe_simple_dc(
            d, "networking_bandwidth_options", ShapeNetworkingBandwidthOptions
        )
        _maybe_simple_dc(
            d, "max_vnic_attachment_options", ShapeMaxVnicAttachmentOptions
        )
        return cls(**d)

    @classmethod
    def from_oci(cls, s: "Shape") -> "YoShape":
        ocpu_options = None
        if s.ocpu_options:
            ocpu_options = ShapeOcpuOptions(
                s.ocpu_options.max, s.ocpu_options.min
            )
        memory_options = None
        if s.memory_options:
            memory_options = ShapeMemoryOptions(
                default_per_ocpu_gbs=s.memory_options.default_per_ocpu_in_g_bs,
                min_gbs=s.memory_options.min_in_g_bs,
                max_gbs=s.memory_options.max_in_g_bs,
                min_per_ocpu_gbs=s.memory_options.min_per_ocpu_in_gbs,
                max_per_ocpu_gbs=s.memory_options.max_per_ocpu_in_gbs,
            )
        net_opts = None
        if s.networking_bandwidth_options:
            nbo = s.networking_bandwidth_options
            net_opts = ShapeNetworkingBandwidthOptions(
                min_gbps=nbo.min_in_gbps,
                max_gbps=nbo.max_in_gbps,
                default_per_ocpu_gbps=nbo.default_per_ocpu_in_gbps,
            )
        vnic_opts = None
        if s.max_vnic_attachment_options:
            vao = s.max_vnic_attachment_options
            vnic_opts = ShapeMaxVnicAttachmentOptions(
                min=vao.min,
                max=vao.max,
                default_per_ocpu=vao.default_per_ocpu,
            )
        return cls(
            name=s.shape,
            shape=s.shape,
            processor_description=s.processor_description,
            ocpus=s.ocpus,
            memory_in_gbs=s.memory_in_gbs,
            networking_bandwidth_in_gbps=s.networking_bandwidth_in_gbps,
            max_vnic_attachments=s.max_vnic_attachments,
            gpus=s.gpus,
            gpu_description=s.gpu_description,
            local_disks=s.local_disks,
            local_disks_total_size_in_gbs=s.local_disks_total_size_in_gbs,
            local_disk_description=s.local_disk_description,
            is_flexible=s.is_flexible,
            quota_names=s.quota_names,
            ocpu_options=ocpu_options,
            memory_options=memory_options,
            networking_bandwidth_options=net_opts,
            max_vnic_attachment_options=vnic_opts,
        )


@dataclasses.dataclass
class YoAvail:
    """
    Represents the availability of a resource. This is NOT cacheable.
    """

    name: str
    scope: str
    ad: t.Optional[str]
    limit: int
    available: int
    used: int
    fractional_availability: float
    fractional_usage: float
    effective_quota_value: t.Optional[int]


@dataclasses.dataclass
class YoAvailSummary:
    """
    Represents availability for a set of resources across multiple ADs.
    """

    all_ads: t.List[str]
    ad_limits: t.List[str]
    name_to_ad_to_avail: t.Dict[str, t.Dict[str, YoAvail]]

    name_to_avail: t.Dict[str, YoAvail]


@dataclasses.dataclass
class YoShapeAvail:
    """
    Represents the overall availability of a shape
    """

    quota_to_requirement: t.Dict[str, float]
    ad_to_max_count: t.Dict[str, t.Optional[float]]
    ad_to_limiting_quotas: t.Dict[str, t.List[t.Tuple[str, float]]]
    missing_quotas: t.List[str]


U = t.TypeVar("U", bound=YoCachedItem)


class YoCache(t.Generic[U]):
    last_update: t.Optional[datetime.datetime] = None
    last_refresh: t.Optional[datetime.datetime] = None
    _data: t.List[U]

    name: str
    _type: t.Type[U]
    _version: int

    def __init__(
        self,
        type_: t.Type[U],
        name: str,
        version: int,
    ):
        """
        Initialize an empty cache of type type_. The name field is only
        informational, to be used by the caller. The version field identifies
        cached object versions, to prevent older versions of cached items from
        being loaded (and failing, because they aren't compatible).

        The returned cache is empty, and will report is_current() -> False. You
        may load() data from the cached JSON blob into it, set() its list, or
        simply continue using it as is.
        """
        self._type = type_
        self.name = name
        self._version = version
        self._data = []

    def load(self, d: t.Dict[str, t.Any]) -> None:
        """
        Load the contents of a JSON-decoded dictionary (presumably from the disk
        cache) into this cache. If it does not exist, keep this cache empty. If
        the object version is wrong, keep this cache empty.
        """

        def dtornull(s: t.Optional[str]) -> t.Optional[datetime.datetime]:
            if s:
                return fromisoformat(s)
            return None

        version = d.get("version", 0)
        if not d or version != self._version:
            return
        self.last_update = dtornull(d.get("last_update"))
        self.last_refresh = dtornull(d.get("last_refresh"))
        json_dicts = d.get("cache", [])
        self._data = [self._type.from_json(x) for x in json_dicts]

    def set(self, items: t.List[U]) -> None:
        """
        Set the current list of objects
        """
        self.last_update = now()
        self.last_refresh = now()
        self._data = list(items)

    def get_all_by(self, field: str, val: t.Any) -> t.Iterator[U]:
        for item in self._data:
            if getattr(item, field, None) == val:
                yield item

    def get_by(
        self,
        field: str,
        val: t.Any,
        unique: bool = True,
    ) -> t.Optional[U]:
        items = list(self.get_all_by(field, val))
        if not items:
            return None
        elif len(items) > 1 and unique:
            raise YoExc(f"Cache error: multiple items, same value of {field}")
        else:
            return items[0]

    def get_by_id(self, id_: str) -> t.Optional[U]:
        return self.get_by("id", id_, unique=True)

    def get_all(self) -> t.List[U]:
        return self._data[:]

    def remove_by(
        self,
        field: str,
        val: t.Any,
        unique: bool = True,
    ) -> None:
        indices = []
        for i, item in enumerate(self._data):
            if getattr(item, field, None) == val:
                indices.append(i)
        if len(indices) > 1 and unique:
            raise YoExc(f"Cache error: multiple items, same {field} {val}")
        for i in reversed(indices):
            del self._data[i]

    def mark_update(self, refresh: bool = False) -> None:
        self.last_update = now()
        if refresh:
            self.last_refresh = now()

    def dirty(self) -> None:
        self.last_update = self.last_refresh = None

    def insert(self, new_item: U) -> None:
        self.mark_update()
        for idx, item in enumerate(self._data):
            if new_item.same_item(item):
                self._data[idx] = new_item
                return
        self._data.append(new_item)

    def export(self) -> t.Dict[str, t.Any]:
        def strornull(x: t.Optional[datetime.datetime]) -> t.Optional[str]:
            if x:
                return toisoformat(x)
            return None

        return {
            "cache": [x.to_json() for x in self._data],
            "last_update": strornull(self.last_update),
            "last_refresh": strornull(self.last_refresh),
            "version": self._version,
        }

    def is_current(
        self, stale_thresh: datetime.timedelta = datetime.timedelta(hours=6)
    ) -> bool:
        if self.last_refresh is None:
            return False
        staleness = now() - self.last_refresh
        return staleness < stale_thresh


class YoCtx:
    con: rich.console.Console
    config: YoConfig
    instance_profiles: t.Mapping[str, InstanceProfile]

    cache_version = 1
    last_checked_for_update: datetime.datetime

    _instances: YoCache[YoInstance] = YoCache(YoInstance, "instances", 4)
    _vnics: YoCache[YoVnic] = YoCache(YoVnic, "vnics", 2)
    _images: YoCache[YoImage] = YoCache(YoImage, "images", 6)
    _consoles: YoCache[YoConsole] = YoCache(YoConsole, "consoles", 2)
    _shapes: YoCache[YoShape] = YoCache(YoShape, "shapes", 5)
    _vols: YoCache[YoVolume] = YoCache(YoVolume, "bootvols", 5)
    _vas: YoCache[YoVolumeAttachment] = YoCache(YoVolumeAttachment, "vas", 3)

    # Put all cache names from above here too so we automatically manage them
    _caches = [
        "_instances",
        "_vnics",
        "_images",
        "_consoles",
        "_shapes",
        "_vols",
        "_vas",
    ]

    _compute: t.Optional["ComputeClient"] = None
    _vnet: t.Optional["VirtualNetworkClient"] = None
    _oci: t.Any = None
    _block: t.Optional["BlockstorageClient"] = None
    _iam: t.Optional["IdentityClient"] = None
    _limits: t.Optional["LimitsClient"] = None

    _tpe: concurrent.futures.ThreadPoolExecutor
    _oci_config: t.Dict[str, t.Any]

    def _setup_oci(self) -> None:
        import yo.oci as foo

        self._oci = foo
        self._oci_cfg = foo.oci.config.from_file(
            profile_name=self.config.oci_profile
        )
        # The OCI SDK allows you to set the region. However, that's one extra
        # config file to keep in sync with yo.ini. Yo overrides the region with
        # a value provided from its own config, to allow users to update the
        # region, VCN ID, and AD configuration, all in one place.
        self._oci_cfg["region"] = self.config.region
        self._vnet = foo.oci.core.VirtualNetworkClient(self._oci_cfg)
        self._compute = foo.oci.core.ComputeClient(self._oci_cfg)
        self._block = foo.oci.core.BlockstorageClient(self._oci_cfg)
        self._iam = foo.oci.identity.IdentityClient(self._oci_cfg)
        self._limits = foo.oci.limits.LimitsClient(self._oci_cfg)

    def __enter__(self) -> None:
        self._tpe = concurrent.futures.ThreadPoolExecutor()
        self._tpe.__enter__()

    def __exit__(
        self, exc_type: t.Any, exc_value: t.Any, traceback: t.Any
    ) -> t.Any:
        self._tpe.__exit__(exc_type, exc_value, traceback)

    @property
    def oci(self) -> t.Any:
        if not self._oci:
            self._setup_oci()
        return self._oci

    @property
    def vnet(self) -> "VirtualNetworkClient":
        if not self._oci:
            self._setup_oci()
        return self._vnet

    @property
    def compute(self) -> "ComputeClient":
        if not self._oci:
            self._setup_oci()
        return self._compute

    @property
    def block(self) -> "BlockstorageClient":
        if not self._block:
            self._setup_oci()
        return self._block

    @property
    def iam(self) -> "IdentityClient":
        if not self._iam:
            self._setup_oci()
        return self._iam

    @property
    def limits(self) -> "LimitsClient":
        if not self._limits:
            self._setup_oci()
        return self._limits

    @property
    def tenancy_id(self) -> str:
        if not self._oci_cfg:
            self._setup_oci()
        return t.cast(str, self._oci_cfg["tenancy"])

    def load_cache(self) -> None:
        cache_file = self._cache_file
        cache = {}
        if os.path.isfile(cache_file):
            with open(cache_file) as f:
                cache = json.load(f)
            cache_version = cache.pop("cache_version", 0)
            resource_filtering = cache.pop("resource_filtering", None)
            if (
                cache_version != self.cache_version
                or resource_filtering != self.config.resource_filtering
            ):
                os.unlink(cache_file)
                self.con.log(
                    "Invalidating cache due to cache version or resource filtering"
                )
                cache = {}
        if "last_checked_for_update" in cache:
            self.last_checked_for_update = fromisoformat(
                cache["last_checked_for_update"]
            )
        else:
            # There are two cases where this may happen:
            # 1. Upgrading Yo past the version which introduced
            #    "last_checked_for_update".
            # 2. The first run of Yo after installation.
            # In either case, Yo was very likely recently updated. So it makes
            # the most sense to set it to now(), rather than setting it to an
            # arbitrary date in the past. What's more, setting it to an
            # arbitrary date in the past such as Unix timestamp 0 ends up
            # causing errors on some platforms (cough... Windows).
            self.last_checked_for_update = now()
        for cache_attr in self._caches:
            yocache: YoCache[t.Any] = getattr(self, cache_attr)
            yocache.load(cache.get(yocache.name, {}))

    def save_cache(self) -> None:
        # It is possible for multiple executions of Yo to concurrently read and
        # write the cache file. In this case, the writer would truncate the
        # file, and it would be possible for the reader to retrieve only partial
        # contents. To avoid this, we write to a temporary file identified by
        # our PID. Once the contents are completely written, we can use rename()
        # which will atomically replace the cache. The concurrent reader will
        # see the old or new, but never a partial cache.
        cache_pid_file = f"{self._cache_file}.{os.getpid()}"
        cache_dir = os.path.dirname(cache_pid_file)
        cache: t.Dict[str, t.Any] = {
            "cache_version": self.cache_version,
            "resource_filtering": self.config.resource_filtering,
            "last_checked_for_update": toisoformat(
                self.last_checked_for_update
            ),
        }
        for cache_attr in self._caches:
            yc: YoCache[t.Any] = getattr(self, cache_attr)
            cache[yc.name] = yc.export()
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_pid_file, "w") as f:
            # It seems best to reduce the permission on this file, so it can
            # only be read or written by the current user (600 permissions).
            # However Windows doesn't support fchmod(), and its chmod()
            # implementation would only let us set the read-only flag. So we'll
            # just skip that if fchmod() unavailable.
            if hasattr(os, "fchmod"):
                os.fchmod(f.fileno(), stat.S_IRUSR | stat.S_IWUSR)
            json.dump(cache, f, indent=4)
        os.replace(cache_pid_file, self._cache_file)

    def __init__(
        self,
        yo_config: YoConfig,
        instance_profiles: t.Mapping[str, InstanceProfile],
        cache_file: str = "~/.cache/yo.json",
    ):
        # Escape hatch to disable the log timestamps
        log_time = "YO_LOG_WITHOUT_TIME" not in os.environ
        self.con = rich.console.Console(log_path=False, log_time=log_time)
        self.config = yo_config
        self.instance_profiles = instance_profiles
        self._cache_file = os.path.expanduser(cache_file)
        self.load_cache()

    def filter_by_creator(self, s: t.Optional[str]) -> bool:
        """Return true if the string matches a creator tag"""
        if not self.config.resource_filtering:
            return True
        return bool(s) and (s in self.config.all_creator_tags)

    @contextlib.contextmanager
    def maybe_check_for_updates(self) -> t.Iterator[None]:
        """
        A context manager which will check for updates in the background

        Since we use a thread pool, it's pretty trivial to delegate the HTTP
        request to a background thread. We can then use this context manager
        whenever we know that we will be doing some other long task (e.g.
        fetching instances via "yo list"). This ensures that we can do a version
        check and notify users to update, but do so without making any command
        run longer than it would have.
        """
        # Only check every N hours
        since_last_check = now() - self.last_checked_for_update
        hours = since_last_check.total_seconds() / 3600
        if (
            not self.config.check_for_update_every
            or hours < self.config.check_for_update_every
        ):
            yield
            return
        fut = self._tpe.submit(latest_yo_version)
        try:
            yield
        except BaseException:
            fut.cancel()
            raise
        latest = fut.result()
        if not latest:
            return
        ver = current_yo_version()
        latest_str = ".".join(map(str, latest))
        if ver < latest:
            self.con.print(
                f"Note: version {latest_str} of Yo is available, please update"
            )
            self.con.print("To update:")
            self.con.print(f"   {yo.util.UPGRADE_COMMAND}")
            self.con.print(
                "You can check the current & latest version with 'yo version'"
            )
        self.last_checked_for_update = now()
        self.save_cache()

    def list_instances(
        self, verbose: bool = False, show_all: bool = False
    ) -> t.List[YoInstance]:
        cid = self.config.instance_compartment_id
        instances_generator = self.oci.list_call_get_all_results(
            self.compute.list_instances,
            cid,
            limit=1000,
        ).data
        instances = []
        instances_cache = []
        warned_on_missing_tag = not verbose
        for instance in instances_generator:
            email = instance.defined_tags.get("Oracle-Tags", {}).get(
                "CreatedBy"
            )
            if not email:
                if not warned_on_missing_tag:
                    self.con.log(
                        "[red]warning:[/red] Instances in your tenancy "
                        "do not have the automatic Oracle-Tags.CreatedBy "
                        "tag - your tenancy may be older, or your tenancy "
                        "administrator disabled these automatic tag "
                        "defaults. As a result, Yo cannot track and manage "
                        "instances created by you on the Web Console -- "
                        "only instances which you launch via 'yo launch'.\n"
                        "Your tenancy administrator can resolve this by "
                        "reinstating the automatic tag rule for "
                        "Oracle-Tags.CreatedBy.\n"
                        "You can also set 'resource_filtering = false' in "
                        "your configuration file, which results in Yo showing "
                        "you all resources in the compartment, regardless of "
                        "who created them.\n"
                        "To learn more, please visit this documentation "
                        f"page: {AUTO_TAG_DOC_LINK}\n"
                        "To silence this warning, please add:\n"
                        "  [blue]silence_automatic_tag_warning = true[/blue]\n"
                        r"to your '~/.oci/yo.ini' file, in the \[yo] section."
                    )
                    warned_on_missing_tag = True
                email = instance.freeform_tags.get(CREATEDBY)
            yo_inst = YoInstance.from_oci(instance)
            instances.append(yo_inst)
            if self.filter_by_creator(email):
                instances_cache.append(yo_inst)
        self._instances.set(instances_cache)
        self.save_cache()
        if show_all:
            return instances
        else:
            return instances_cache

    def list_instances_cached(self) -> t.List[YoInstance]:
        if self._instances.last_refresh is None:
            # can't satisfy the request cached
            return self.list_instances()
        return self._instances.get_all()

    def _instances_named(self, names: t.Collection[str]) -> t.List[YoInstance]:
        """
        Return instances whose name is present in the names collection.
        If names is empty, then all instances are returned.
        """
        matches = []
        for inst in self._instances.get_all():
            if not names or inst.name in names:
                matches.append(inst)
        return matches

    def _filter_instances(
        self,
        instances: t.List[YoInstance],
        states_allowlist: t.Container[str],
        states_denylist: t.Container[str],
    ) -> t.List[YoInstance]:
        """
        Filter the list of instances by the allow and deny list of states.
        """
        matches = []
        for inst in instances:
            if inst.state in states_denylist:
                continue
            if states_allowlist and inst.state not in states_allowlist:
                continue
            matches.append(inst)
        return matches

    def get_instance_by_id(self, id_: str) -> YoInstance:
        inst = self._instances.get_by_id(id_)
        if inst:
            return inst
        self.list_instances()
        inst = self._instances.get_by_id(id_)
        if not inst:
            raise YoExc(f"Looking up instance id {id_}: does not exist")
        return inst

    def get_instance_by_name(
        self,
        name: str,
        states_allowlist: t.Collection[str],
        states_denylist: t.Collection[str],
        exact_name: bool = False,
    ) -> YoInstance:
        """
        A 'smart' function for fetching an instance by name.

        This function tries its darndest to find an instance by name, and
        enforce the state constraints given (in the form of allowlist and/or
        denylist). If there's no name match, we refresh our list just to be sure
        (unless cached_only=True). If there's a name match, but the state
        constraints are wrong, we refresh just that instance (faster) to verify.
        If anything goes wrong, we raise an exception with detailed information.

        This should be used by the single-instance yo commands, when you specify
        an instance name.

        :param name: user-input instance name
        :param states_allowlist: if non-empty, this is a collection of the
        allowable states for the instance to be in.
        :param states_denylist: this is a collection of states which the
        instance is forbidden to be in
        :param exact_name: whether to use --exact-name behavior
        """
        # First, try with the cached instance list
        real_name = standardize_name(name, exact_name, self.config)
        name_matches = self._instances_named([real_name])
        matches = self._filter_instances(
            name_matches, states_allowlist, states_denylist
        )
        if not matches:
            # If no matches are found, try refreshing from the API
            self.list_instances()
            name_matches = self._instances_named([real_name])
            matches = self._filter_instances(
                name_matches, states_allowlist, states_denylist
            )

        if not name_matches:
            raise YoExc("No instance named {}".format(real_name))

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            raise YoExc(
                'There are multiple instances named "{}".\n'
                "Yo can't manage instances with non-unique names.\n"
                "Please use the OCI console to fix this.".format(
                    real_name,
                )
            )

        # At this point, we have no matches when you filter by state, but we do
        # have at least one instance whose name matches. Give a pretty error
        # message to the user.
        t_instance = "Instance"
        t_its_state = "its state"
        t_does_not = "does not"
        if len(name_matches) > 1:
            t_instance = "Instances"
            t_its_state = "their states"
            t_does_not = "do not"
        state = ", ".join([inst.state for inst in name_matches])
        allow_deny = fmt_allow_deny(states_allowlist, states_denylist)
        raise YoExc(
            f'{t_instance} named "{real_name}" found, but {t_its_state} '
            f"({state}) {t_does_not} match the requirements:\n"
            f"  {allow_deny}"
        )

    def get_matching_instances(
        self,
        names_allowlist: t.Collection[str],
        states_allowlist: t.Collection[str],
        states_denylist: t.Collection[str],
        refresh: bool = False,
    ) -> t.List[YoInstance]:
        """
        Return a list of instances matching the name collection, filtered by the
        allow and deny list.
        """
        if refresh or not self._instances.is_current():
            self.list_instances()
        name_matches = self._instances_named(names_allowlist)
        return self._filter_instances(
            name_matches, states_allowlist, states_denylist
        )

    def get_only_instance(
        self,
        states_allowlist: t.Collection[str],
        states_denylist: t.Collection[str],
    ) -> YoInstance:
        """
        Return the only instance satisfying the state conditions (e.g. RUNNING).

        Raises exception if there is not exactly one matching instance.
        """
        fmt = fmt_allow_deny(states_allowlist, states_denylist)
        return one(
            self.get_matching_instances([], states_allowlist, states_denylist),
            "Looking for one instance in state {}, but found none".format(fmt),
            "Looking for one instance in state {}, but found multiple".format(
                fmt
            ),
        )

    def terminate_instance(
        self,
        inst_id: str,
        preserve_volume: bool = False,
    ) -> YoInstance:
        self.compute.terminate_instance(
            inst_id, preserve_boot_volume=preserve_volume
        )
        inst = YoInstance.from_oci(self.compute.get_instance(inst_id).data)
        self._instances.insert(inst)
        self.save_cache()
        return inst

    def get_vnic(self, inst: YoInstance, quiet: bool = False) -> YoVnic:
        yovnic = self._vnics.get_by("instance_id", inst.id)
        if not yovnic:
            if not quiet:
                self.con.log("Looking up instance IP/Vnic")
            cid = self.config.instance_compartment_id
            vnic_gen = self.oci.list_call_get_all_results_generator(
                self.compute.list_vnic_attachments,
                "record",
                cid,
                instance_id=inst.id,
            )
            vnic_attachments = list(vnic_gen)
            if not vnic_attachments:
                raise YoExc("There are no attached VNICs for this instance")
            elif len(vnic_attachments) > 1:
                self.con.log(
                    "[red]warning:[/red] your instance has multiple attached "
                    "VNICs, which may have multiple IPs. Yo is choosing to use "
                    "first one. If you encounter issues, please mention this "
                    "when reporting it."
                )
            vnic_attachment = vnic_attachments[0]
            vnic = self.vnet.get_vnic(vnic_attachment.vnic_id).data
            yovnic = YoVnic.from_oci(vnic, vnic_attachment)
            self._vnics.insert(yovnic)
            self.save_cache()
        return yovnic

    def get_instance_ip(self, inst: YoInstance, quiet: bool = False) -> str:
        yovnic = self.get_vnic(inst, quiet)
        ip = yovnic.public_ip or yovnic.private_ip
        if not quiet:
            self.con.log(f"Found instance ip [blue]{ip}")
        return ip

    def get_all_instance_ips(
        self, insts: t.List[YoInstance]
    ) -> t.Dict[str, str]:
        """
        Return a map of instance ID to IP address. Caches them as well.
        """
        # Fetch the complete cache and see which instances we need to check again
        inst_to_vnic = {v.instance_id: v for v in self._vnics.get_all()}
        insts_fetch = []
        for inst in insts:
            if inst.id not in inst_to_vnic:
                insts_fetch.append(inst)
        if insts_fetch:
            # Fetch all VnicAttachments from this compartment
            vnic_gen = self.oci.list_call_get_all_results_generator(
                self.compute.list_vnic_attachments,
                "record",
                self.config.instance_compartment_id,
            )
            inst_to_atchs = collections.defaultdict(list)
            for vnic_atch in vnic_gen:
                inst_to_atchs[vnic_atch.instance_id].append(vnic_atch)

            # Filter to only the instances we don't have cached currently
            inst_to_atchs_filtered = {}
            for inst in insts_fetch:
                if inst.id not in inst_to_atchs:
                    raise YoExc(f"No attached VNICs for instance {inst.name}")
                inst_to_atchs_filtered[inst.id] = inst_to_atchs[inst.id]

            def load_vnic(
                pair: t.Tuple[str, t.List["VnicAttachment"]]
            ) -> t.Tuple[str, YoVnic]:
                inst_id, atch_list = pair
                vnic = self.vnet.get_vnic(atch_list[0].vnic_id).data
                yovnic = YoVnic.from_oci(vnic, atch_list[0])
                return inst_id, yovnic

            # Use the thread pool to request all the vnics
            inst_to_vnic.update(
                dict(self._tpe.map(load_vnic, inst_to_atchs_filtered.items()))
            )
            self._vnics.set(list(inst_to_vnic.values()))
            self.save_cache()
        return {
            id_: (vnic.public_ip or vnic.private_ip)
            for id_, vnic in inst_to_vnic.items()
        }

    def wait_instance_state(
        self,
        inst_id: str,
        state: str,
        **kwargs: t.Any,
    ) -> YoInstance:
        resp = self.compute.get_instance(inst_id)
        inst = self.oci.wait_until_progress(
            self,
            self.compute,
            resp,
            "lifecycle_state",
            state,
            display_name=resp.data.display_name,
            **kwargs,
        ).data
        yo_inst = YoInstance.from_oci(inst)
        self._instances.insert(yo_inst)
        self.save_cache()
        return yo_inst

    def _load_image_compatibility(self, image: YoImage) -> None:
        res = self.oci.list_call_get_all_results_generator(
            self.compute.list_image_shape_compatibility_entries,
            "record",
            image.id,
        )
        image.compatibility = {
            d.shape: ImageCompatibility.from_oci(d) for d in res
        }

    def get_image(self, image_id: str) -> YoImage:
        res = self._images.get_by_id(image_id)
        if not res:
            oci_img = self.compute.get_image(image_id).data
            res = YoImage.from_oci(oci_img)
            self._load_image_compatibility(res)
            self._images.insert(res)
            self.save_cache()
        return res

    def list_all_images(self, refresh: bool = False) -> t.List[YoImage]:
        """
        List all OCI images, including custom images.
        """
        compartments = [
            self.config.instance_compartment_id
        ] + self.config.image_compartment_ids
        images = []
        if refresh or not self._images.is_current():
            self.con.log("Refreshing cached image list")
            seen_ids = set()
            for cid in compartments:
                img_gen = self.oci.list_call_get_all_results_generator(
                    self.compute.list_images,
                    "record",
                    cid,
                )
                for img in img_gen:
                    if img.id not in seen_ids:
                        images.append(YoImage.from_oci(img))
                        seen_ids.add(img.id)
            self.con.log("Loading image compatibility")
            list(self._tpe.map(self._load_image_compatibility, images))
            self._images.set(images)
            self.save_cache()
        return self._images.get_all()

    def list_official_images(self) -> t.List[YoImage]:
        """
        List all *official* images
        """
        images = []
        for img in self.list_all_images():
            if img.created_by:
                continue
            images.append(img)
        return images

    def get_image_by_name(self, name: str, load_image: ImageLoad) -> YoImage:
        matches = []
        refresh = load_image == ImageLoad.LATEST
        for img in self.list_all_images(refresh):
            if img.name == name:
                matches.append(img)
        if load_image == ImageLoad.UNIQUE:
            # Assume images are unique, expect one per name. This is the legacy
            # cached method.
            return one(
                matches,
                'Looking for one image named "{}", but found none'.format(name),
                'Looking for one image named "{}", but found multiple'.format(
                    name
                ),
            )
        elif not matches:
            raise YoExc(
                'Looking the latest image named "{}", but found none.'.format(
                    name
                )
            )
        else:
            matches.sort(key=lambda i: i.time_created, reverse=True)
            return matches[0]

    def list_shapes(self) -> t.List[YoShape]:
        cid = self.config.instance_compartment_id
        if not self._shapes.is_current():
            shape_gen = self.oci.list_call_get_all_results_generator(
                self.compute.list_shapes, "record", cid
            )
            shapes_dupes = [YoShape.from_oci(shape) for shape in shape_gen]
            shapes_dupes.sort(key=lambda x: x.shape)
            shapes = []
            current_name = None
            for shape in shapes_dupes:
                if shape.shape != current_name:
                    shapes.append(shape)
                    current_name = shape.shape
            self._shapes.set(shapes)
            self.save_cache()
        return self._shapes.get_all()

    def get_shape_by_name(self, shape: str) -> YoShape:
        for shape_obj in self.list_shapes():
            if shape_obj.shape == shape:
                return shape_obj
        raise YoExc(f"Shape {shape} not found")

    def create_console(self, instance_id: str) -> YoConsole:
        details = self.oci.CreateInstanceConsoleConnectionDetails(
            instance_id=instance_id,
            public_key=self.config.ssh_public_key_full,
        )
        resp = self.compute.create_instance_console_connection(details)
        conn = resp.data
        self.con.log(
            "Created instance console connection. Waiting for it to become "
            "active."
        )
        conn = self.oci.wait_until_progress(
            self,
            self.compute,
            self.compute.get_instance_console_connection(conn.id),
            "lifecycle_state",
            "ACTIVE",
        ).data
        yo_conn = YoConsole.from_oci(conn)
        self._consoles.insert(yo_conn)
        self.save_cache()
        return yo_conn

    def get_or_create_console(
        self,
        instance_id: str,
        refresh: bool = False,
    ) -> YoConsole:
        # First check cache, most likely a console was created by "yo console"
        # and so it appears here. Skip this if called with refresh=True.
        if not refresh:
            res = self._consoles.get_by("instance_id", instance_id)
            if res:
                return res
        else:
            # While consoles should be unique, ensure that we don't fail to
            # clear the cache here.
            self._consoles.remove_by("instance_id", instance_id, unique=False)
            self.save_cache()

        # Second, make the API call to look for an existing console. It is
        # possible that one could have been created elsewhere.
        cid = self.config.instance_compartment_id
        conns = list(
            filter(
                lambda i: i.lifecycle_state == "ACTIVE",
                self.compute.list_instance_console_connections(
                    cid, instance_id=instance_id
                ).data,
            )
        )
        if len(conns) == 1:
            yo_con = YoConsole.from_oci(conns[0])
            self._consoles.insert(yo_con)
            self.save_cache()
            return yo_con
        elif len(conns) == 0:
            # Finally, create a new console.
            return self.create_console(instance_id)
        else:
            raise YoExc(
                "Uh-oh, this instance has multiple console connections. This "
                "should never happen, please report a bug."
            )

    def pick_subnet(self, ad: str) -> YoSubnet:
        if self.config.subnet_id:
            resp = self.vnet.get_subnet(subnet_id=self.config.subnet_id)
            subnet = resp.data
            if subnet.availability_domain and subnet.availability_domain != ad:
                self.con.log(
                    "[orange]warning: the given subnet_id has a different "
                    "availability domain than the one specified in your "
                    "instance profile. Continuing, but this may not be what "
                    "you want."
                )
        elif self.config.subnet_compartment_id:
            gen = self.oci.list_call_get_all_results_generator(
                self.vnet.list_subnets,
                "record",
                self.config.subnet_compartment_id,
                vcn_id=self.config.vcn_id,
                lifecycle_state="AVAILABLE",
            )
            for subnet in gen:
                if (
                    not subnet.availability_domain
                    or subnet.availability_domain == ad
                ):
                    break
            else:
                raise YoExc("No subnets available...")
        else:
            raise YoExc("Need subnet_id or subnet_compartment_id.")
        sub = YoSubnet.from_oci(subnet)
        self.con.log(f"Using subnet [blue]{sub.name}[/blue]")
        return sub

    def launch_instance(self, details: t.Dict[str, t.Any]) -> YoInstance:
        image_id = details.pop("image_id", None)
        volume_id = details.pop("volume_id", None)
        boot_size = details.pop("boot_volume_size_gbs", None)
        username = details.pop("username")
        if image_id and volume_id:
            raise YoExc("image_id and volume_id cannot both be passed")
        elif image_id:
            kwargs = {"image_id": image_id}
            if boot_size:
                kwargs["boot_volume_size_in_gbs"] = boot_size
            details["source_details"] = self.oci.InstanceSourceViaImageDetails(
                **kwargs
            )
        elif volume_id:
            details[
                "source_details"
            ] = self.oci.InstanceSourceViaBootVolumeDetails(
                boot_volume_id=volume_id,
            )
        else:
            raise YoExc("You must pass either image_id or volume_id")
        shape_config = details.pop("shape_config", None)
        if shape_config:
            details["shape_config"] = self.oci.LaunchInstanceShapeConfigDetails(
                **shape_config,
            )
        # Most tenancies will automatically create "Oracle-Tags.CreatedBy" which
        # has the user email address, but seemingly not all of them. It is
        # definitely better to have those tags, because this allows Yo to manage
        # instances which you created on the UI. However, by creating a
        # Yo-specific tag, we can at least ensure that we will be able to list
        # and manage the instances created by Yo.
        details["freeform_tags"] = {
            CREATEDBY: self.config.my_email,
        }
        if username:
            details["freeform_tags"][USERNAME] = username
        details = self.oci.LaunchInstanceDetails(**details)
        instance = YoInstance.from_oci(
            self.compute.launch_instance(details).data
        )
        self._instances.insert(instance)
        # Launching an instance creates a vnic and a volume at least. There's no
        # need to fetch them just yet, but we should mark them dirty so that
        # future operations will be forced to reload.
        self._vnics.dirty()
        self._vols.dirty()
        self.save_cache()
        return instance

    def instance_action(self, inst_id: str, action: str) -> YoInstance:
        inst = YoInstance.from_oci(
            self.compute.instance_action(inst_id, action).data
        )
        self._instances.insert(inst)
        self.save_cache()
        return inst

    def resize_instance(self, inst_id: str, shape: str) -> YoInstance:
        deets = self.oci.UpdateInstanceDetails(shape=shape)
        newinst = YoInstance.from_oci(
            self.compute.update_instance(inst_id, deets).data
        )
        self._instances.insert(newinst)
        self.save_cache()
        return newinst

    def _list_bootdevs_atchs(
        self,
        ad: str,
    ) -> t.Tuple[t.List[YoVolume], t.List[YoVolumeAttachment]]:
        vols = []
        attchs = []
        ids = set()
        bootdev_gen = self.oci.list_call_get_all_results_generator(
            self.block.list_boot_volumes,
            "record",
            availability_domain=ad,
            compartment_id=self.config.instance_compartment_id,
        )
        for bootdev in bootdev_gen:
            bv = YoVolume.from_oci_boot(bootdev)
            if self.filter_by_creator(bv.created_by):
                vols.append(bv)
                ids.add(bv.id)
        boot_attch_gen = self.oci.list_call_get_all_results_generator(
            self.compute.list_boot_volume_attachments,
            "record",
            availability_domain=ad,
            compartment_id=self.config.instance_compartment_id,
        )
        for boot_attch in boot_attch_gen:
            bva = YoVolumeAttachment.from_oci_boot(boot_attch)
            if bva.volume_id in ids:
                attchs.append(bva)
        return vols, attchs

    def _maybe_volume_refresh(self, refresh: bool = False) -> None:
        if self._vols.is_current() and not refresh:
            return
        ad_resp = self.iam.list_availability_domains(
            self.config.instance_compartment_id
        )

        # On the thread pool, start requesting boot volumes and attachments for
        # each availability domain. Unfortunately this can't be done in one
        # call.
        futures = [
            self._tpe.submit(self._list_bootdevs_atchs, ad.name)
            for ad in ad_resp.data
        ]

        # Now fetch the standard block volumes. We filter the volumes
        # themselves, and create a set of volume IDs which we care about. With
        # that set, we can filter the volume attachments.
        vols = []
        attchs = []
        ids = set()
        blockdev_gen = self.oci.list_call_get_all_results_generator(
            self.block.list_volumes,
            "record",
            compartment_id=self.config.instance_compartment_id,
        )
        for blockdev in blockdev_gen:
            vol = YoVolume.from_oci_block(blockdev)
            if self.filter_by_creator(vol.created_by):
                vols.append(vol)
                ids.add(vol.id)

        # Now, we can start the request for volume attachments
        attch_gen = self.oci.list_call_get_all_results_generator(
            self.compute.list_volume_attachments,
            "record",
            compartment_id=self.config.instance_compartment_id,
        )

        # Before we filter the returned volume attachments, we need to retrieve
        # the boot volume list. The boot volume list contains boot volume
        # attachments, but boot volumes may also be attached as data volumes. In
        # order to properly display those attachments, we must add the boot
        # volume IDs to the set which we use to filter attachments.
        for fut in concurrent.futures.as_completed(futures):
            bootvols, bootattchs = fut.result()
            vols.extend(bootvols)
            ids.update(bv.id for bv in bootvols)
            attchs.extend(bootattchs)

        # Now grab the attachments and filter them by the set of volume IDs we
        # care about.
        for attch in attch_gen:
            va = YoVolumeAttachment.from_oci_block(attch)
            if va.volume_id in ids:
                attchs.append(va)

        self._vols.set(vols)
        self._vas.set(attchs)
        self.save_cache()

    def list_volumes(self, refresh: bool = False) -> t.List[YoVolume]:
        """
        Returns a list of boot volumes, within any AD in this region.
        """
        self._maybe_volume_refresh(refresh)
        return [
            vol for vol in self._vols.get_all() if vol.state != "TERMINATED"
        ]

    def list_volume_attachments(
        self, refresh: bool = False
    ) -> t.List[YoVolumeAttachment]:
        self._maybe_volume_refresh(refresh)
        return self._vas.get_all()

    def get_volume_by_id(self, id: str) -> YoVolume:
        vol = self._vols.get_by_id(id)
        if not vol:
            self._maybe_volume_refresh(True)
            vol = self._vols.get_by_id(id)
            if not vol:
                raise YoExc(f"Volume {id} does not exist!")
        return vol

    def get_volume(
        self, name: str, kind: t.Optional[VolumeKind] = None
    ) -> YoVolume:
        matches = []
        for vol in self.list_volumes():
            if (
                vol.name == name or vol.alt_name == name
            ) and vol.state != "TERMINATED":
                if not kind or vol.kind == kind:
                    matches.append(vol)
        typ = f" {kind.name}" if kind else ""
        return one(
            matches,
            f"no{typ} volume with name {name}",
            f"multiple{typ} volumes with name {name}",
        )

    def attachments_by_volume(self) -> t.Dict[str, t.List[YoVolumeAttachment]]:
        ret: t.Dict[str, t.List[YoVolumeAttachment]] = defaultdict(list)
        for va in self.list_volume_attachments():
            ret[va.volume_id].append(va)
        return ret

    def attachments_by_instance(
        self,
    ) -> t.Dict[str, t.List[YoVolumeAttachment]]:
        ret: t.Dict[str, t.List[YoVolumeAttachment]] = defaultdict(list)
        for va in self.list_volume_attachments():
            ret[va.instance_id].append(va)
        return ret

    def rename_volume(self, vol: YoVolume, new_name: str) -> None:
        if vol.kind == VolumeKind.BOOT:
            new = self.block.update_boot_volume(
                vol.id,
                self.oci.UpdateBootVolumeDetails(
                    display_name=new_name,
                ),
            )
            newvol = YoVolume.from_oci_boot(new.data)
        else:
            new = self.block.update_block_volume(
                vol.id,
                self.oci.UpdateVolumeDetails(
                    display_name=new_name,
                ),
            )
            newvol = YoVolume.from_oci_block(new.data)
        self._vols.insert(newvol)
        self.save_cache()

    def create_volume(self, name: str, ad: str, size_gbs: int) -> YoVolume:
        freeform_tags = {
            CREATEDBY: self.config.my_email,
        }
        details = self.oci.CreateVolumeDetails(
            compartment_id=self.config.instance_compartment_id,
            display_name=name,
            size_in_gbs=size_gbs,
            availability_domain=ad,
            freeform_tags=freeform_tags,
        )
        result = self.block.create_volume(details)
        volume = YoVolume.from_oci_block(result.data)
        self._vols.insert(volume)
        self.save_cache()
        return volume

    def delete_volume(self, volume: YoVolume) -> YoVolume:
        if volume.kind == VolumeKind.BLOCK:
            self.block.delete_volume(volume.id)
        else:
            self.block.delete_boot_volume(volume.id)

        # Normally the API returns an updated item, but in this case
        # it does not. Let's fake it so that the cache doesn't contain a volume
        # which is still available.
        volume.state = "DELETING"
        self._vols.insert(volume)
        self.save_cache()
        return volume

    def attach_volume(
        self,
        vol: YoVolume,
        inst_id: str,
        kind: t.Optional[str] = None,
        ro: bool = False,
        shared: bool = False,
    ) -> YoVolumeAttachment:
        # This function is for attaching volumes as "data volumes". Boot
        # volumes can actually attach and detach just fine as data volumes, you
        # just supply their ID like you would a block volume ID. Of course, this
        # doesn't make them bootable. For that sort of surgery, Yo isn't very
        # well suited.
        if not kind:
            kind = "service_determined"
        kind_to_details_cls = {
            "service_determined": self.oci.AttachServiceDeterminedVolumeDetails,
            "iscsi": self.oci.AttachIScsiVolumeDetails,
            "pv": self.oci.AttachParavirtualizedVolumeDetails,
            "paravirt": self.oci.AttachParavirtualizedVolumeDetails,
            "emulated": self.oci.AttachEmulatedVolumeDetails,
        }
        details_cls = kind_to_details_cls[kind]
        details = details_cls(
            display_name="yo block volume attachment",
            instance_id=inst_id,
            volume_id=vol.id,
            is_read_only=ro,
            is_shareable=shared,
        )
        resp = self.compute.attach_volume(details)
        va = YoVolumeAttachment.from_oci_block(resp.data)
        self._vas.insert(va)
        self.save_cache()
        return va

    def detach_volume(self, va: YoVolumeAttachment) -> YoVolumeAttachment:
        self.compute.detach_volume(va.id)
        # Normally the API returns an updated item, but in this case
        # it does not. Let's fake it so that the cache doesn't contain a volume
        # which is still available.
        va.state = "DETACHING"
        self._vas.insert(va)
        self.save_cache()
        return va

    def wait_volume(self, vol: YoVolume, state: str) -> YoVolume:
        if vol.kind == VolumeKind.BLOCK:
            oci_vol = self.block.get_volume(vol.id)
        else:
            oci_vol = self.block.get_boot_volume(vol.id)
        oci_new = self.oci.wait_until_progress(
            self,
            self.block,
            oci_vol,
            "lifecycle_state",
            state,
            display_name=vol.name,
        ).data
        if vol.kind == VolumeKind.BLOCK:
            new_vol = YoVolume.from_oci_block(oci_new)
        else:
            new_vol = YoVolume.from_oci_boot(oci_new)
        self._vols.insert(new_vol)
        self.save_cache()
        return new_vol

    def wait_attachment(
        self, va: YoVolumeAttachment, state: str
    ) -> YoVolumeAttachment:
        if va.kind == VolumeKind.BLOCK:
            oci_va = self.compute.get_volume_attachment(va.id)
            oci_new_va = self.oci.wait_until_progress(
                self,
                self.compute,
                oci_va,
                "lifecycle_state",
                state,
                display_name="attachment",
            ).data
            new_va = YoVolumeAttachment.from_oci_block(oci_new_va)
        else:
            oci_bva = self.compute.get_boot_volume_attachment(va.id)
            oci_new_bva = self.oci.wait_until_progress(
                self,
                self.compute,
                oci_bva,
                "lifecycle_state",
                state,
                display_name="attachment",
            ).data
            new_va = YoVolumeAttachment.from_oci_boot(oci_new_bva)
        self._vas.insert(new_va)
        self.save_cache()
        return new_va

    def get_attachment_commands(
        self, va: YoVolumeAttachment
    ) -> t.Tuple[t.List[str], t.List[str]]:
        if va.attachment_type != AttachmentType.ISCSI:
            return ([], [])
        iqn = va.iscsi_iqn
        ip = va.iscsi_ipv4
        port = va.iscsi_port
        attach = [
            f"sudo iscsiadm -m node -o new -T {iqn} -p {ip}:{port}",
            f"sudo iscsiadm -m node -o update -T {iqn} -n node.startup -v automatic",
            f"sudo iscsiadm -m node -T {iqn} -p {ip}:{port} -l",
        ]
        detach = [
            f"sudo iscsiadm -m node -T {iqn} -p {ip}:{port} -u",
            f"sudo iscsiadm -m node -o delete -T {iqn} -p {ip}:{port}",
        ]
        return attach, detach

    def report_attached(self, va: YoVolumeAttachment, auto: bool) -> None:
        self.con.print(f"Your attachment type is {va.attachment_type}")
        if va.device:
            self.con.print(f"Device: {va.device}")
        if va.attachment_type == AttachmentType.ISCSI:
            if auto:
                self.con.print(
                    "Your iSCSI device has been automatically attached."
                )
            else:
                attach, _ = self.get_attachment_commands(va)
                cmds = "\n".join(attach)
                self.con.print(f"Attachment commands:\n[code]{cmds}[/code]")

    def list_limit_availability(
        self, limits: t.Iterable[str], service: str = "compute"
    ) -> YoAvailSummary:
        """
        Lookup limits and their currently available capacity, across ADs.

        OCI has a somewhat opaque system of limits, quotas, and availability. It
        takes a lot of API calls to get your data, and the data could change
        quickly. This method returns a high-level availability summary for all
        the limits you're interested in, across all availability domains. With
        this, you can determine how much availability there is for your instance
        in each availability domain, and place it correctly as a result.

        None of the limit values are cached, which means that if you're looking
        for global statistics of all limits, then it may take a while.

        :param limits: The names of limits you want to see values for. Pass an
          empty list to retrieve all of them.
        :returns: Availability summary object
        """
        results = self.oci.list_call_get_all_results(
            self.limits.list_limit_values,
            self.tenancy_id,
            service,
            limit=1000,
        ).data
        lim_set = set(limits)

        def load_ad_availability(name: str, ad: str, value: int) -> YoAvail:
            r = self.limits.get_resource_availability(
                service,
                name,
                self.config.instance_compartment_id,
                availability_domain=ad,
            )
            return YoAvail(
                name=name,
                scope="AD",
                ad=ad,
                limit=value,
                available=r.data.available,
                used=r.data.used,
                fractional_availability=r.data.fractional_availability,
                fractional_usage=r.data.fractional_usage,
                effective_quota_value=r.data.effective_quota_value,
            )

        def load_region_availability(name: str, value: int) -> YoAvail:
            r = self.limits.get_resource_availability(
                service,
                name,
                self.config.instance_compartment_id,
            )
            return YoAvail(
                name=name,
                scope="REGION",
                ad=None,
                limit=value,
                available=r.data.available,
                used=r.data.used,
                fractional_availability=r.data.fractional_availability,
                fractional_usage=r.data.fractional_usage,
                effective_quota_value=r.data.effective_quota_value,
            )

        name_to_ad_to_fut: t.Dict[
            str, t.Dict[str, t.Any]
        ] = collections.defaultdict(dict)
        name_to_fut = {}
        ads: t.Set[str] = set()
        ad_lims: t.Set[str] = set()
        for lim in results:
            if lim_set and lim.name not in lim_set:
                continue
            if lim.scope_type == "AD":
                fut = self._tpe.submit(
                    load_ad_availability,
                    lim.name,
                    lim.availability_domain,
                    lim.value,
                )
                name_to_ad_to_fut[lim.name][lim.availability_domain] = fut
                ad_lims.add(lim.name)
                ads.add(lim.availability_domain)
            else:
                name_to_fut[lim.name] = self._tpe.submit(
                    load_region_availability, lim.name, lim.value
                )

        name_to_ad_to_avail = {}
        for name, ad_to_fut in name_to_ad_to_fut.items():
            ad_to_avail = {}
            for ad, fut in ad_to_fut.items():
                ad_to_avail[ad] = fut.result()
            name_to_ad_to_avail[name] = ad_to_avail

        name_to_avail = {lim: fut.result() for lim, fut in name_to_fut.items()}
        return YoAvailSummary(
            sorted(ads), sorted(ad_lims), name_to_ad_to_avail, name_to_avail
        )

    def compute_shape_availability(
        self, avs: YoAvailSummary, shape: YoShape
    ) -> YoShapeAvail:
        q2r = {}
        for quota in shape.quota_names:
            if "core" in quota and "count" in quota:
                q2r[quota] = shape.ocpus
            elif "memory" in quota and "count" in quota:
                q2r[quota] = shape.memory_in_gbs
            elif re.match(r"^gpu(-t)?\d+-count$", quota):
                q2r[quota] = float(shape.gpus)
            else:
                q2r[quota] = 1.0

        ad_to_max: t.Dict[str, t.Optional[float]] = {}
        ad_to_limit = collections.defaultdict(list)
        missing_quotas = set()
        for ad in avs.all_ads:
            quota_to_max = {}
            for quota, req in q2r.items():
                if quota in avs.name_to_avail:
                    avail = avs.name_to_avail[quota]
                elif quota in avs.name_to_ad_to_avail:
                    avail = avs.name_to_ad_to_avail[quota][ad]
                else:
                    missing_quotas.add(quota)
                    continue
                max_instances = avail.fractional_availability / req
                quota_to_max[quota] = max_instances
                if max_instances < 1.0:
                    ad_to_limit[ad].append(
                        (quota, avail.fractional_availability)
                    )
            if quota_to_max:
                ad_to_max[ad] = min(quota_to_max.values())
            else:
                ad_to_max[ad] = None

        return YoShapeAvail(q2r, ad_to_max, ad_to_limit, sorted(missing_quotas))

    def rename_instance(self, inst: YoInstance, new_name: str) -> YoInstance:
        update = self.oci.UpdateInstanceDetails(display_name=new_name)
        newinst = YoInstance.from_oci(
            self.compute.update_instance(inst.id, update).data
        )
        self._instances.insert(newinst)
        self.save_cache()
        return newinst

    def protect_instance(self, inst: YoInstance, enabled: bool) -> YoInstance:
        string = str(enabled).lower()
        freeform_tags = inst.freeform_tags.copy()
        freeform_tags[TERMPROTECT] = string
        update = self.oci.UpdateInstanceDetails(freeform_tags=freeform_tags)
        newinst = YoInstance.from_oci(
            self.compute.update_instance(inst.id, update).data
        )
        self._instances.insert(newinst)
        self.save_cache()
        return newinst

    def get_console_history(self, inst: YoInstance) -> bytes:
        details = self.oci.CaptureConsoleHistoryDetails(instance_id=inst.id)
        hist = self.compute.capture_console_history(details).data
        try:
            resp = self.compute.get_console_history(hist.id)
            hist = self.oci.wait_until_progress(
                self,
                self.compute,
                resp,
                "lifecycle_state",
                "SUCCEEDED",
            ).data
            result_data: bytes = self.compute.get_console_history_content(
                hist.id,
            ).data
        finally:
            self.compute.delete_console_history(hist.id)
        return result_data

    def get_windows_initial_creds(
        self, inst: YoInstance
    ) -> t.Tuple[t.Optional[str], t.Optional[str]]:
        try:
            r = self.compute.get_windows_instance_initial_credentials(inst.id)
            return r.data.username, r.data.password
        except self.oci.ServiceError:
            return None, None

    def get_ssh_user(self, inst: YoInstance) -> str:
        if inst.username:
            return inst.username
        img = self.get_image(inst.image_id)
        return OS_TO_USER[img.os]

    def remove_saved_metadata(self, volume: YoVolume) -> None:
        if SAVEDATA in volume.freeform_tags:
            freeform_tags = volume.freeform_tags
            del freeform_tags[SAVEDATA]
            update = self.oci.UpdateBootVolumeDetails(
                freeform_tags=freeform_tags
            )
            volume = YoVolume.from_oci_boot(
                self.block.update_boot_volume(volume.id, update).data
            )
            self._vols.insert(volume)
            self.save_cache()

    def save_instance(self, instance: YoInstance) -> None:
        attachments = self.attachments_by_instance()[instance.id]
        for atch in attachments:
            if atch.attachment_type == AttachmentType.BOOT:
                break
        else:
            raise YoExc("could not find boot volume!")

        # Tag values are limited to 256 unicode characters.
        # - version number: 1 byte
        # - ocpu: 3 bytes max (up to 3 digits)
        # - mem: 4 bytes max (up to 4 digits)
        # - username: commonly limited to 32 characters
        # - name: OCI already limits it to 128 characters
        # This adds up to 194 bytes, and with the 5 commas, that's a maximum of
        # 199 bytes.
        savedata = ",".join(
            [
                "1",
                instance.shape,
                str(int(instance.ocpu)),
                str(int(instance.memory_gb)),
                instance.username or "",
                instance.name,
            ]
        )
        vol = self.get_volume_by_id(atch.volume_id)
        freeform_tags = vol.freeform_tags
        freeform_tags[SAVEDATA] = savedata
        update = self.oci.UpdateBootVolumeDetails(freeform_tags=freeform_tags)
        volume = YoVolume.from_oci_boot(
            self.block.update_boot_volume(atch.volume_id, update).data
        )
        self._vols.insert(volume)  # cache is saved below
        self.terminate_instance(instance.id, preserve_volume=True)

    def resume_instance(self, volume: YoVolume) -> YoInstance:
        md = volume.saved_instance_metadata
        if not md:
            raise YoExc("the volume has no metadata attached to it")

        details: t.Dict[str, t.Any] = {
            "compartment_id": self.config.instance_compartment_id,
            "availability_domain": volume.ad,
        }
        try:
            self.get_instance_by_name(md.name, (), (), exact_name=True)
            raise YoExc("name collision (TODO)")
        except YoExc:
            pass
        details["display_name"] = md.name

        shape_obj = self.get_shape_by_name(md.shape)
        details["shape"] = md.shape
        if shape_obj.is_flexible:
            details["shape_config"] = {
                "ocpus": md.ocpu,
                "memory_in_gbs": md.memory_gb,
            }

        if md.username:
            details["username"] = md.username
        details["subnet_id"] = self.pick_subnet(volume.ad).id
        details["volume_id"] = volume.id
        inst = self.launch_instance(details)

        # Remove the savedata so that we don't continue to show it as a saved
        # instance.
        self.remove_saved_metadata(volume)
        return inst
