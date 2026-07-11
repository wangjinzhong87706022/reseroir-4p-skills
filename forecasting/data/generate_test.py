#!/usr/bin/env python3
"""
generate_test.py -- TDD tests for the window model + resolve_window introduced in Task 1.

Run:
    cd SmartTwinRes-skills/forecasting/data && python3 -m pytest generate_test.py -v

These tests cover the window-resolution contract from task-1-brief.md Step 1:
  - default (no args)            : obs [NOW-30d, NOW], fc [NOW, NOW+168h]
  - --start/--end custom window  : obs [s, min(e,NOW)], fc [max(s,NOW), e]
  - --roll (breakpoint resume)   : obs_start = None sentinel, fc [NOW, NOW+168h]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

# Make the sibling generate_forecast_data.py importable when running pytest
# from inside the data/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_forecast_data import resolve_window, Window  # noqa: E402


def _ns(**kw):
    """Build an argparse.Namespace with all window-related fields defaulted."""
    base = dict(start=None, end=None, roll=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_default_demo_window():
    now = datetime(2026, 6, 23, 12, 0)
    args = _ns()
    w = resolve_window(args, now)
    assert isinstance(w, Window)
    assert w.obs_start == now - timedelta(days=30)
    assert w.obs_end == now
    assert w.fc_start == now
    assert w.fc_end == now + timedelta(hours=168)


def test_custom_window():
    now = datetime(2026, 6, 23, 12, 0)
    s = datetime(2026, 6, 1)
    e = datetime(2026, 6, 30)
    args = _ns(start=s, end=e)
    w = resolve_window(args, now)
    assert w.obs_start == s
    assert w.obs_end == min(e, now)
    assert w.fc_start == max(s, now)
    assert w.fc_end == e


def test_roll_window_uses_breakpoint_sentinel():
    """--roll: obs_start is None (extender resolves via read_breakpoint), fc=[NOW, NOW+168h]."""
    now = datetime(2026, 6, 23, 12, 0)
    args = _ns(roll=True)
    w = resolve_window(args, now)
    assert w.obs_start is None
    assert w.obs_end == now
    assert w.fc_start == now
    assert w.fc_end == now + timedelta(hours=168)


def test_start_only_defaults_end_to_forecast_horizon():
    now = datetime(2026, 6, 23, 12, 0)
    s = datetime(2026, 6, 10)
    args = _ns(start=s)
    w = resolve_window(args, now)
    # obs [s, NOW] (s < NOW), fc [NOW, NOW+168h]
    assert w.obs_start == s
    assert w.obs_end == now
    assert w.fc_start == now
    assert w.fc_end == now + timedelta(hours=168)
