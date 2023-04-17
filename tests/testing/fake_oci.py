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
"""
Allows us to fake the OCI SDK without getting too tied up mocking functions.
"""
import typing as t
from unittest import mock

from oci.core.models import Instance
from oci.core.models import VnicAttachment

from tests.testing.factories import FakeResponse


class FakeOCICompute:
    """
    Fakes the OCI Compute Client, but with a bit of smarts.

    Essentially, you can load up the compute client with objects that you'd like
    it to know about (e.g. to be able to list or get, or verify the existence).
    Each function of the compute client is a mock, and they generally have
    side effects which perform the validation or return the known objects.
    This means that you can still make assertions about arguments, call counts,
    etc, but you probably don't need as many assertions and you definitely don't
    need to program a fragile set of return values with a specific order.
    """

    def __init__(self):
        self._instances: t.List[Instance] = []
        self._vnic_attachments: t.List[VnicAttachment] = []

        # Create mocks for each f_ method.
        for key in dir(self):
            if key.startswith("f_"):
                setattr(
                    self, key[2:], mock.Mock(side_effect=getattr(self, key))
                )
                print(f"Create mock {key}")

        # OCI API Calls:
        # * Instances: list_instances terminate_instance get_instance
        #   launch_instance instance_action update_instance
        # * Images: get_image list_images
        # * Shapes: list_shapes
        # * Image/Shape Compat: list_image_shape_compatibility_entries
        # * Vnic: list_vnic_attachments
        # * Console Conn: create_instance_console_connection
        #   list_instance_console_connections
        # * Boot Vol: list_boot_volume_attachments attach_boot_volume
        #   detach_boot_volume get_boot_volume_attachment
        # * Block Vol: list_volume_attachments attach_volume detach_volume
        #   get_volume_attachment
        # * Console Hist: capture_console_history get_console_history
        #   get_console_history_content delete_console_history
        # * Windows: get_windows_instance_initial_credentials

    def _get_instance(self, inst_id: str) -> Instance:
        for instance in self._instances:
            if instance.id == inst_id:
                return instance
        assert False, "Instance ID not present in fake OCI"

    def f_list_instances(
        self, compartment_id: str, limit: int = 1000
    ) -> FakeResponse:
        return FakeResponse(self._instances)

    def f_terminate_instance(
        self, inst_id: str, **kwargs: t.Any
    ) -> FakeResponse:
        instance = self._get_instance(inst_id)
        instance.lifecycle_state = "TERMINATING"
        return FakeResponse(None)

    def f_get_instance(self, inst_id: str) -> FakeResponse:
        return FakeResponse(self._get_instance(inst_id))

    def f_launch_instance(self, *args: t.Any, **kwargs: t.Any):
        pass

    def f_instance_action(self, inst_id: str, action: str) -> FakeResponse:
        return FakeResponse(self._get_instance(inst_id))

    def f_update_instance(self, inst_id: str, details: t.Any) -> FakeResponse:
        return FakeResponse(self._get_instance(inst_id))


class FakeOCI:
    def __init__(self, ctx):
        self.compute = FakeOCICompute()
        self.ctx = ctx

        ctx.con = mock.Mock()
        ctx._oci = mock.Mock()
        ctx._oci.list_call_get_all_results.side_effect = (
            self.list_call_get_all_results
        )
        ctx._oci.list_call_get_all_results_generator.side_effect = (
            self.list_call_get_all_results_generator
        )
        ctx._vnet = mock.Mock()
        ctx._compute = self.compute

    def list_call_get_all_results_generator(self, fn, scope, *args, **kwargs):
        assert scope == "record"
        return fn(*args, **kwargs).data

    def list_call_get_all_results(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)
