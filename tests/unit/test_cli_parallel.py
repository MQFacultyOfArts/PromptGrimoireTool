"""Tests for parallel E2E runner utilities in cli.py."""

from __future__ import annotations

from promptgrimoire.cli import _allocate_ports


def test_allocate_ports_returns_distinct_ports() -> None:
    """_allocate_ports(5) returns 5 distinct ports, all > 0."""
    ports = _allocate_ports(5)
    assert len(ports) == 5
    assert len(set(ports)) == 5, f"Ports are not distinct: {ports}"
    assert all(p > 0 for p in ports), f"All ports must be > 0: {ports}"


def test_allocate_ports_single() -> None:
    """_allocate_ports(1) returns a single port."""
    ports = _allocate_ports(1)
    assert len(ports) == 1
    assert ports[0] > 0


def test_allocate_ports_zero() -> None:
    """_allocate_ports(0) returns an empty list."""
    ports = _allocate_ports(0)
    assert ports == []
