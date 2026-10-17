# SPDX-License-Identifier: GPL-3.0-or-later
import time

from minimonitor import __main__ as entry


def test_second_instance_waits_then_gives_up():
    first = entry.single_instance(wait_seconds=0)
    assert first is not None
    start = time.monotonic()
    assert entry.single_instance(wait_seconds=0.6) is None
    assert time.monotonic() - start >= 0.5  # it waited for the first one to exit


def test_lock_is_free_again_once_the_first_instance_exits():
    first = entry.single_instance(wait_seconds=0)
    first.close()  # what the OS does when the process ends
    second = entry.single_instance(wait_seconds=0)
    assert second is not None
    second.close()
