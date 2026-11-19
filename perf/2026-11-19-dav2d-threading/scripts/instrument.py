#!/usr/bin/env python3
"""Apply temporary, Linux-only scheduler diagnostics to a disposable source tree.

Not an upstream patch. Timings include instrumentation and descheduling; counters
are observations of failed readiness checks, not time spent blocked.
"""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / 'src/thread_task.c'
s = p.read_text()
anchor = '#include "src/fg_apply.h"'
helpers = r'''
#include <time.h>
#include <stdio.h>

static _Thread_local struct {
    uint64_t held_start, work_start;
    uint64_t held_ns, lock_wait_ns, parked_ns, work_ns[16];
    unsigned long calls[16], checks[16], previous[16], references[16];
    unsigned long scans, cdf_waits, row_waits;
    unsigned type;
} prof;

static uint64_t prof_now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static void prof_work_end(void) {
    if (prof.work_start) {
        prof.work_ns[prof.type] += prof_now() - prof.work_start;
        prof.work_start = 0;
    }
}

static void prof_lock(pthread_mutex_t *lock) {
    prof_work_end();
    const uint64_t start = prof_now();
    pthread_mutex_lock(lock);
    prof.held_start = prof_now();
    prof.lock_wait_ns += prof.held_start - start;
}

static void prof_unlock(pthread_mutex_t *lock) {
    prof.held_ns += prof_now() - prof.held_start;
    pthread_mutex_unlock(lock);
    prof.work_start = prof_now();
}

static void prof_wait(pthread_cond_t *cond, pthread_mutex_t *lock) {
    prof.held_ns += prof_now() - prof.held_start;
    const uint64_t start = prof_now();
    pthread_cond_wait(cond, lock);
    prof.held_start = prof_now();
    prof.parked_ns += prof.held_start - start;
}

static void prof_dump(void) {
    flockfile(stderr);
    fprintf(stderr, "{\"held_ns\":%llu,\"lock_wait_ns\":%llu,"
            "\"parked_ns\":%llu,\"scans\":%lu,\"cdf_waits\":%lu,"
            "\"row_waits\":%lu,\"tasks\":[",
            (unsigned long long)prof.held_ns,
            (unsigned long long)prof.lock_wait_ns,
            (unsigned long long)prof.parked_ns, prof.scans, prof.cdf_waits,
            prof.row_waits);
    for (int i = 0; i < 16; i++)
        fprintf(stderr, "%s[%llu,%lu,%lu,%lu,%lu]", i ? "," : "",
                (unsigned long long)prof.work_ns[i], prof.calls[i],
                prof.checks[i], prof.previous[i], prof.references[i]);
    fprintf(stderr, "]}\n");
    funlockfile(stderr);
}
'''
# Replace existing calls before inserting wrappers, so wrappers call pthreads.
s = s.replace('pthread_mutex_lock(&ttd->lock)', 'prof_lock(&ttd->lock)')
s = s.replace('pthread_mutex_unlock(&ttd->lock)', 'prof_unlock(&ttd->lock)')
s = s.replace('pthread_cond_wait(&ttd->cond, &ttd->lock)',
              'prof_wait(&ttd->cond, &ttd->lock)')
s = s.replace(anchor, anchor + '\n' + helpers)
s = s.replace('    if (p1 < t->by64) return 1;',
              '    prof.checks[t->type]++;\n    if (p1 < t->by64) return 1;')
s = s.replace('        if (p2 <= t->by64) return 1;',
              '        if (p2 <= t->by64) { prof.previous[t->type]++; return 1; }')
s = s.replace('            if (p3 < lowest) return 1;',
              '            if (p3 < lowest) { prof.references[t->type]++; return 1; }')
s = s.replace('            while (t) {', '            while (t) {\n                prof.scans++;')
s = s.replace('                        if (p2 < t->recon_progress) goto next;',
              '                        if (p2 < t->recon_progress) { prof.row_waits++; goto next; }')
s = s.replace('                    if (p1) {',
              '                    if (!p1) prof.cdf_waits++;\n                    if (p1) {')
s = s.replace('            delayed_fg_task(c, ttd);',
              '            prof.type = ttd->delayed_fg.type;\n'
              '            prof.calls[prof.type]++;\n            delayed_fg_task(c, ttd);')
s = s.replace('    found_unlocked:;',
              '    found_unlocked:;\n        prof_work_end();\n'
              '        prof.type = t->type;\n        prof.calls[prof.type]++;\n'
              '        prof.work_start = prof_now();')
s = s.replace('    return NULL;\n}', '    prof.work_start = 0;\n    prof_dump();\n    return NULL;\n}')
p.write_text(s)
