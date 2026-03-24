"""QueuePool overflow() is a creation counter, not a capacity proxy.

Regression guard for the #403 falsification: overflow() shifting from
-pool_size toward 0 is normal warm-up (connections being created on
demand), not evidence of capacity loss. This test uses a bare QueuePool
with a mock creator — no database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.pool import QueuePool


def _mock_creator():
    """Return a mock DBAPI connection that satisfies QueuePool."""
    conn = MagicMock()
    conn.is_valid = True
    return conn


def test_overflow_shifts_on_normal_checkout_and_stays():
    """overflow() increments when a connection is created, not when one is lost.

    A cold pool (pool_size=5) starts at overflow=-5. The first checkout
    creates a connection, shifting overflow to -4. Returning the
    connection does NOT decrement overflow — it stays at -4.

    This killed the #403 "permanent shrinkage" theory: the production
    observation of overflow=-29 with pool_size=80 simply meant 51
    connections had been created (normal warm-up under ~50 students).
    """
    pool = QueuePool(_mock_creator, pool_size=5, max_overflow=2, reset_on_return=None)

    assert pool.overflow() == -5, "Cold pool should start at 0 - pool_size"
    assert pool.checkedout() == 0

    # First checkout: creates a connection → overflow increments
    conn1 = pool.connect()
    assert pool.overflow() == -4, "First connection creation should shift overflow"
    assert pool.checkedout() == 1

    # Return it: overflow does NOT decrement
    conn1.close()
    assert pool.overflow() == -4, (
        "Checkin must not change overflow (not a capacity loss)"
    )
    assert pool.checkedin() == 1
    assert pool.checkedout() == 0

    # Second checkout reuses the pooled connection — no new creation
    conn2 = pool.connect()
    assert pool.overflow() == -4, "Reused connection should not shift overflow"
    assert pool.checkedout() == 1
    conn2.close()
