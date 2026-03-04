#!/usr/bin/env python3
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

from tests.testing.factories import config_factory
from tests.testing.factories import FakeResponse
from tests.testing.factories import flex_shape_factory
from tests.testing.factories import instance_factory
from tests.testing.factories import oci_block_attachment_factory
from tests.testing.factories import oci_boot_attachment_factory
from tests.testing.factories import oci_boot_volume_fromyo
from tests.testing.factories import volume_attachment_factory
from tests.testing.factories import volume_factory
from yo.api import AttachmentType
from yo.api import SAVEDATA
from yo.api import VolumeKind
from yo.api import YoCtx
from yo.api import YoSubnet
from yo.util import YoExc


def _make_ctx(tmp_path, **cfg_kwargs):
    cache_file = tmp_path / "yo-cache.json"
    cfg = config_factory(**cfg_kwargs)
    ctx = YoCtx(cfg, {}, cache_file=str(cache_file))
    ctx.con = mock.Mock()
    ctx.clear_cache()
    return ctx


def test_list_volumes_filters_terminated(tmp_path):
    ctx = _make_ctx(tmp_path)
    live = volume_factory(name="live", state="AVAILABLE")
    dead = volume_factory(name="dead", state="TERMINATED")
    ctx._vols.set([live, dead])
    ctx._maybe_volume_refresh = mock.Mock()

    assert ctx.list_volumes() == [live]
    ctx._maybe_volume_refresh.assert_called_once_with(False)


def test_attach_and_detach_block_volume(tmp_path):
    ctx = _make_ctx(tmp_path)
    vol = volume_factory(name="data", kind=VolumeKind.BLOCK)
    inst_id = str(uuid.uuid4())

    ctx._oci = SimpleNamespace(
        AttachServiceDeterminedVolumeDetails=lambda **k: SimpleNamespace(**k),
        AttachIScsiVolumeDetails=lambda **k: SimpleNamespace(**k),
        AttachParavirtualizedVolumeDetails=lambda **k: SimpleNamespace(**k),
        AttachEmulatedVolumeDetails=lambda **k: SimpleNamespace(**k),
        AttachBootVolumeDetails=lambda **k: SimpleNamespace(**k),
    )
    ctx._compute = mock.Mock()
    ctx._compute.attach_volume.return_value = FakeResponse(
        oci_block_attachment_factory(
            availability_domain=vol.ad,
            compartment_id=vol.compartment_id,
            volume_id=vol.id,
            instance_id=inst_id,
        )
    )
    ctx.save_cache = mock.Mock()

    va = ctx.attach_volume(vol, inst_id)
    assert va.kind == VolumeKind.BLOCK
    assert va.volume_id == vol.id
    ctx._compute.attach_volume.assert_called_once()
    assert ctx._vas.get_by_id(va.id) == va

    detached = ctx.detach_volume(va)
    assert detached.state == "DETACHING"
    ctx._compute.detach_volume.assert_called_once_with(va.id)


def test_attach_and_detach_boot_volume(tmp_path):
    ctx = _make_ctx(tmp_path)
    vol = volume_factory(name="boot (Boot Volume)", kind=VolumeKind.BOOT)
    inst_id = str(uuid.uuid4())

    ctx._oci = SimpleNamespace(
        AttachBootVolumeDetails=lambda **k: SimpleNamespace(**k),
    )
    ctx._compute = mock.Mock()
    ctx._compute.attach_boot_volume.return_value = FakeResponse(
        oci_boot_attachment_factory(
            availability_domain=vol.ad,
            compartment_id=vol.compartment_id,
            boot_volume_id=vol.id,
            instance_id=inst_id,
        )
    )
    ctx.save_cache = mock.Mock()

    va = ctx.attach_volume(vol, inst_id, atch_type=AttachmentType.BOOT)
    assert va.kind == VolumeKind.BOOT
    ctx._compute.attach_boot_volume.assert_called_once()

    detached = ctx.detach_volume(va)
    assert detached.state == "DETACHING"
    ctx._compute.detach_boot_volume.assert_called_once_with(va.id)


def test_get_attachment_commands_for_iscsi(tmp_path):
    ctx = _make_ctx(tmp_path)
    va = volume_attachment_factory(
        attachment_type=AttachmentType.ISCSI,
        iscsi_iqn="iqn.2015-12.com.oracle:abc",
        iscsi_ipv4="1.2.3.4",
        iscsi_port=3260,
    )
    attach, detach = ctx.get_attachment_commands(va)
    assert len(attach) == 3
    assert len(detach) == 2
    assert "iscsiadm" in attach[0]


def test_save_instance_tags_boot_volume_and_terminates(tmp_path):
    ctx = _make_ctx(tmp_path)
    inst = instance_factory(
        shape="VM.Standard.A1.Flex",
        ocpu=2,
        memory_gb=12,
        username="opc",
    )
    boot_vol = volume_factory(name="saved-root", kind=VolumeKind.BOOT)
    boot_attch = volume_attachment_factory(
        kind=VolumeKind.BOOT,
        attachment_type=AttachmentType.BOOT,
        volume_id=boot_vol.id,
        instance_id=inst.id,
    )

    ctx.attachments_by_instance = mock.Mock(
        return_value={inst.id: [boot_attch]}
    )
    ctx.get_volume_by_id = mock.Mock(return_value=boot_vol)
    ctx.terminate_instance = mock.Mock()
    ctx._oci = SimpleNamespace(
        UpdateBootVolumeDetails=lambda **k: SimpleNamespace(**k),
    )
    ctx._block = mock.Mock()
    ctx._block.update_boot_volume.return_value = FakeResponse(
        oci_boot_volume_fromyo(boot_vol)
    )

    ctx.save_instance(inst)

    ctx._block.update_boot_volume.assert_called_once()
    update_details = ctx._block.update_boot_volume.call_args[0][1]
    assert SAVEDATA in update_details.freeform_tags
    ctx.terminate_instance.assert_called_once_with(
        inst.id, preserve_volume=True
    )


def test_save_instance_requires_boot_attachment(tmp_path):
    ctx = _make_ctx(tmp_path)
    inst = instance_factory()
    block_attch = volume_attachment_factory(
        kind=VolumeKind.BLOCK,
        attachment_type=AttachmentType.PV,
        instance_id=inst.id,
    )
    ctx.attachments_by_instance = mock.Mock(
        return_value={inst.id: [block_attch]}
    )
    with pytest.raises(YoExc, match="boot volume"):
        ctx.save_instance(inst)


def test_resume_instance_uses_saved_metadata_and_clears_tag(tmp_path):
    ctx = _make_ctx(tmp_path)
    volume = volume_factory(
        name="saved-root",
        kind=VolumeKind.BOOT,
        freeform_tags={SAVEDATA: "1,VM.Standard.A1.Flex,2,12,opc,resume-me"},
    )

    ctx.get_instance_by_name = mock.Mock(side_effect=YoExc("not found"))
    ctx.get_shape_by_name = mock.Mock(return_value=flex_shape_factory())
    ctx.pick_subnet = mock.Mock(
        return_value=YoSubnet(
            id="subnet1",
            name="sn1",
            ad="AD-1",
            state="AVAILABLE",
            vcn_id="vcn1",
            cidr_block="10.0.0.0/24",
            virtual_router_ip="10.0.0.1",
            virtual_router_mac="00:11:22:33:44:55",
        )
    )
    launched = instance_factory(name="resume-me")
    ctx.launch_instance = mock.Mock(return_value=launched)
    ctx.remove_saved_metadata = mock.Mock()

    inst = ctx.resume_instance(volume)
    details = ctx.launch_instance.call_args[0][0]
    assert details["display_name"] == "resume-me"
    assert details["shape"] == "VM.Standard.A1.Flex"
    assert details["shape_config"] == {"ocpus": 2, "memory_in_gbs": 12}
    assert details["username"] == "opc"
    assert details["volume_id"] == volume.id
    assert details["subnet_id"] == "subnet1"
    ctx.remove_saved_metadata.assert_called_once_with(volume)
    assert inst == launched


def test_resume_instance_requires_saved_metadata(tmp_path):
    ctx = _make_ctx(tmp_path)
    volume = volume_factory(name="plain", kind=VolumeKind.BOOT)
    with pytest.raises(YoExc, match="no metadata"):
        ctx.resume_instance(volume)
