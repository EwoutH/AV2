"""Optional Linux/x86-64 user-space PMU counters, inherited across child execs.

The parent event remains disabled. enable_on_exec starts each inherited child
event, and exit accounting accumulates decoder/worker counts into the parent FD.
"""
import ctypes
import os
import platform
import struct


class ChildCounters:
    def __init__(self):
        self.fds = {}
        self.error = None
        if platform.machine() != 'x86_64':
            self.error = 'perf_event_open syscall number is only defined here for x86-64'
            return
        libc = ctypes.CDLL(None, use_errno=True)
        # disabled | inherit | exclude_kernel | exclude_hv | enable_on_exec
        flags = (1 << 0) | (1 << 1) | (1 << 5) | (1 << 6) | (1 << 12)
        for name, kind, config in [('cycles', 0, 0), ('instructions', 0, 1), ('task_clock', 1, 1)]:
            # PERF_FORMAT_TOTAL_TIME_ENABLED | PERF_FORMAT_TOTAL_TIME_RUNNING
            attr = ctypes.create_string_buffer(struct.pack(
                'IIQQQQQIIQ', kind, 64, config, 0, 0, 3, flags, 0, 0, 0))
            fd = libc.syscall(298, ctypes.byref(attr), 0, -1, -1, 0)
            if fd < 0:
                self.error = os.strerror(ctypes.get_errno())
                self.close()
                break
            self.fds[name] = fd

    def finish(self):
        result = {}
        if self.error:
            return dict(error=self.error)
        try:
            for name, fd in self.fds.items():
                count, enabled, running = struct.unpack('QQQ', os.read(fd, 24))
                result[name] = dict(raw=count, enabled_ns=enabled, running_ns=running,
                                    scaled=count * enabled / running if running else None)
        finally:
            self.close()
        return result

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()
