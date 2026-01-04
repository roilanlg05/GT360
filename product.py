"""
Test: Connection Watchdog Effectiveness

This test demonstrates:
1. Pool exhaustion WITHOUT watchdog (hangs when pool is full)
2. Watchdog in WARNING mode (logs but doesn't recover)
3. Watchdog in AGGRESSIVE mode (terminates stale connections, pool recovers)

Run with: python test_watchdog.py
"""
import asyncio
import time
from psqlmodel import create_async_engine

# Configuration - adjust to your environment
DB_CONFIG = {
    "username": "gt360",
    "password": "Rlg*020305", 
    "database": "test_db",
    "host": "localhost",
    "port": 5432,
}


# ============================================================
# TEST 1: Pool exhaustion WITHOUT watchdog
# ============================================================
async def test_pool_exhaustion_no_watchdog():
    """
    This test will HANG because all connections are leaked.
    The pool has 5 connections, we leak all 5, then try to get a 6th.
    """
    print("\n" + "="*60)
    print("TEST 1: Pool Exhaustion WITHOUT Watchdog")
    print("="*60)
    print("Pool size: 5, Holding 5 connections for 30s...")
    print("This WILL HANG when trying to acquire 6th connection!")
    print("-"*60)
    
    engine = create_async_engine(
        **DB_CONFIG,
        pool_size=5,
        max_pool_size=5,
        enable_watchdog=False,  # ⬅️ Watchdog DISABLED
        debug=True,
        ensure_database=True,
        ensure_tables=False,
    )
    
    await engine.startup_async()
    
    try:
        # Leak 5 connections directly from pool (not sessions with savepoints)
        leaked_connections = []
        for i in range(5):
            conn = await engine.acquire()
            leaked_connections.append(conn)
            print(f"  [LEAK] Connection {i+1}/5 acquired directly from pool")
        
        print("\n  Attempting to acquire 6th connection (pool is full)...")
        print("  ⏳ This will hang until timeout...")
        
        try:
            start = time.monotonic()
            # This should hang because pool is exhausted
            new_conn = await asyncio.wait_for(engine.acquire(), timeout=10.0)
            elapsed = time.monotonic() - start
            print(f"  ✅ Got connection after {elapsed:.1f}s (unexpected!)")
            await engine.release(new_conn)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            print(f"  ❌ Timeout after {elapsed:.1f}s! Pool exhausted (expected)")
            
    finally:
        # Cleanup - release leaked connections
        for conn in leaked_connections:
            try:
                await engine.release(conn)
            except:
                pass
        await engine.dispose_async()
        print("\n  [CLEANUP] Done")


# ============================================================
# TEST 2: Watchdog in WARNING mode (logs but doesn't recover)
# ============================================================
async def test_watchdog_warning_mode():
    """
    Watchdog detects leaks and logs warnings, but pool still exhausts.
    """
    print("\n" + "="*60)
    print("TEST 2: Watchdog WARNING Mode")
    print("="*60)
    print("Pool size: 5, max_lifetime: 5s, interval: 2s")
    print("Will LOG warnings but pool still exhausts.")
    print("-"*60)
    
    engine = create_async_engine(
        **DB_CONFIG,
        pool_size=5,
        max_pool_size=5,
        enable_watchdog=True,
        watchdog_mode="warning",  # ⬅️ WARNING mode (default)
        watchdog_interval=2.0,
        connection_max_lifetime=5.0,
        debug=True,
        ensure_database=True,
        ensure_tables=False,
    )
    
    await engine.startup_async()
    
    try:
        # Leak 5 connections directly from pool
        leaked_connections = []
        for i in range(5):
            conn = await engine.acquire()
            # Track for watchdog
            if hasattr(engine, '_track_connection_acquired'):
                engine._track_connection_acquired(conn)
            leaked_connections.append(conn)
            print(f"  [LEAK] Connection {i+1}/5 acquired")
        
        print("\n  ⏳ Waiting 8s for watchdog to detect leaks...")
        await asyncio.sleep(8)
        
        print("\n  Attempting to acquire 6th connection...")
        print("  ⏳ Will hang because WARNING mode doesn't free connections...")
        
        try:
            start = time.monotonic()
            new_conn = await asyncio.wait_for(engine.acquire(), timeout=5.0)
            elapsed = time.monotonic() - start
            print(f"  ✅ Unexpectedly got connection in {elapsed:.1f}s!")
            await engine.release(new_conn)
        except asyncio.TimeoutError:
            print("  ❌ Timeout! Pool exhausted (expected in WARNING mode)")
            
    finally:
        for conn in leaked_connections:
            try:
                if hasattr(engine, '_track_connection_released'):
                    engine._track_connection_released(conn)
                await engine.release(conn)
            except:
                pass
        await engine.dispose_async()
        print("\n  [CLEANUP] Done")


# ============================================================
# TEST 3: Watchdog in AGGRESSIVE mode (recovers pool)
# ============================================================
async def test_watchdog_aggressive_mode():
    """
    Watchdog detects leaks AND terminates stale connections.
    Pool recovers and new connections can be acquired.
    """
    print("\n" + "="*60)
    print("TEST 3: Watchdog AGGRESSIVE Mode")
    print("="*60)
    print("Pool size: 5, max_lifetime: 5s, interval: 2s")
    print("Will TERMINATE stale connections and RECOVER pool!")
    print("-"*60)
    
    engine = create_async_engine(
        **DB_CONFIG,
        pool_size=5,
        max_pool_size=5,
        enable_watchdog=True,
        watchdog_mode="aggressive",  # ⬅️ AGGRESSIVE mode
        watchdog_interval=2.0,
        connection_max_lifetime=5.0,
        debug=True,
        ensure_database=True,
        ensure_tables=False,
    )
    
    await engine.startup_async()
    
    try:
        # Leak 5 connections directly from pool
        leaked_connections = []
        for i in range(5):
            conn = await engine.acquire()
            # Track for watchdog
            if hasattr(engine, '_track_connection_acquired'):
                engine._track_connection_acquired(conn)
            leaked_connections.append(conn)
            print(f"  [LEAK] Connection {i+1}/5 acquired")
        
        print("\n  ⏳ Waiting 10s for watchdog to detect and TERMINATE leaks...")
        await asyncio.sleep(10)
        
        print("\n  Attempting to acquire new connection...")
        
        try:
            start = time.monotonic()
            new_conn = await asyncio.wait_for(engine.acquire(), timeout=5.0)
            elapsed = time.monotonic() - start
            print(f"  ✅ Got connection in {elapsed:.1f}s! Pool recovered!")
            await engine.release(new_conn)
        except asyncio.TimeoutError:
            print("  ❌ Timeout! Aggressive mode didn't work as expected")
        except Exception as e:
            # May get an error because connections were terminated
            print(f"  ⚠️  Exception (expected if connections were terminated): {e}")
            
    finally:
        # Note: leaked connections may fail to release because watchdog terminated them
        for conn in leaked_connections:
            try:
                if hasattr(engine, '_track_connection_released'):
                    engine._track_connection_released(conn)
                await engine.release(conn)
            except:
                pass
        await engine.dispose_async()
        print("\n  [CLEANUP] Done")


# ============================================================
# MAIN
# ============================================================
async def main():
    print("\n" + "="*60)
    print("CONNECTION WATCHDOG TESTS")
    print("="*60)
    
    # Uncomment the test you want to run
    
    # TEST 1: Will HANG - demonstrates pool exhaustion
    # await test_pool_exhaustion_no_watchdog()
    
    # TEST 2: Shows warning logs but still hangs
    await test_watchdog_warning_mode()
    
    # TEST 3: Shows aggressive mode recovering the pool
    await test_watchdog_aggressive_mode()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
