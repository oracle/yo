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
Things requiring OCI import

TODO: this module was created as a hack around how slooooowly the OCI module
loads. It turns out that this is because OCI imports every single service when
you run "import oci", unless you set an environment variable to disable this
(silly) behavior:

https://docs.oracle.com/en-us/iaas/tools/python/2.79.0/sdk_behaviors/enable_selective_service_imports.html

We now set this environment variable in yo.main.main, and since the yo.oci
module is lazily loaded (very much on purpose), that will take effect before any
of the imports here.

However, the 100 milliseconds it takes to load the relevant OCI modules probably
aren't important, so the design decision to stuff all the OCI imports into a
separate module is no longer a great one. In the future, I may get rid of this
monstrosity and need to set the environment variable at the top of the script.
"""
import time
import typing as t

import oci.core  # noqa
import oci.identity  # noqa
import oci.limits  # noqa
import rich.progress
from oci import wait_until
from oci.base_client import Response
from oci.core.models import AttachBootVolumeDetails  # noqa
from oci.core.models import AttachEmulatedVolumeDetails  # noqa
from oci.core.models import AttachIScsiVolumeDetails  # noqa
from oci.core.models import AttachParavirtualizedVolumeDetails  # noqa
from oci.core.models import AttachServiceDeterminedVolumeDetails  # noqa
from oci.core.models import CaptureConsoleHistoryDetails  # noqa
from oci.core.models import CreateInstanceConsoleConnectionDetails  # noqa
from oci.core.models import CreateVolumeDetails  # noqa
from oci.core.models import InstanceSourceViaBootVolumeDetails  # noqa
from oci.core.models import InstanceSourceViaImageDetails  # noqa
from oci.core.models import LaunchInstanceDetails  # noqa
from oci.core.models import LaunchInstanceShapeConfigDetails  # noqa
from oci.core.models import UpdateBootVolumeDetails  # noqa
from oci.core.models import UpdateInstanceDetails  # noqa
from oci.core.models import UpdateVolumeDetails  # noqa
from oci.exceptions import ServiceError  # noqa
from oci.pagination import list_call_get_all_results  # noqa
from oci.pagination import list_call_get_all_results_generator  # noqa
from rich.progress import Progress

from yo.api import YoCtx


__all__ = ["oci"]


def wait_until_progress(
    ctx: YoCtx,
    client: t.Any,
    item: Response,
    attr: str,
    state: str,
    max_interval_seconds: int = 1,
    max_wait_seconds: int = 600,
    wait_callback: t.Optional[t.Callable[[int, Response], None]] = None,
    display_name: t.Optional[str] = None,
) -> Response:
    progress = Progress(
        rich.progress.TextColumn("{task.description}"),
        rich.progress.SpinnerColumn(),
        rich.progress.TimeElapsedColumn(),
        rich.progress.TextColumn("Timeout in:"),
        rich.progress.TimeRemainingColumn(),
        console=ctx.con,
    )
    with progress:
        task = progress.add_task(
            "WAIT", start=True, total=max_wait_seconds, finished_time=1
        )
        start = time.time()
        last_update = start
        last_state = getattr(item.data, attr)
        item_kind = type(item.data).__name__
        if display_name:
            item_str = f"{item_kind} [blue]{display_name}[/blue]"
        else:
            item_str = f"{item_kind}"
        ctx.con.log(f"Wait for {item_str} to enter state [purple]{state}")
        ctx.con.log(f"{item_str} starts in state [purple]{last_state}")

        def update(check_count: int, last_response: Response) -> None:
            nonlocal last_update, last_state
            current = time.time()
            progress.advance(task, current - last_update)
            last_update = current
            current_state = getattr(last_response.data, attr)
            if current_state != last_state:
                progress.print(
                    f"{item_str} entered state [purple]{current_state}"
                )
            last_state = current_state
            if wait_callback:
                wait_callback(check_count, last_response)

        resp: Response = wait_until(
            client,
            item,
            attr,
            state,
            max_interval_seconds=1,
            max_wait_seconds=max_wait_seconds,
            wait_callback=update,
        )
        progress.advance(task, max_wait_seconds)
    ctx.con.log(f"{item_str} has reached state [purple]{state}!")
    return resp
