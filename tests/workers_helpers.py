"""Module-level task functions for test_workers.py (spawned workers import them by name)."""
import os


def square_pid(x):
    return x * x, os.getpid()


def die_on(x, bad, parent_pid):
    if x == bad and os.getpid() != parent_pid:
        os._exit(3)                   # a worker killed mid-run (never the calling process)
    return x * 10


def fail_on(x, bad):
    if x == bad:
        raise ValueError(f"bad task {x}")
    return x
