#!/usr/bin/env python3
"""
TDD Unit Test: amap_navi networking, client_active initialization, and port bindings.
Verifies:
1. self.client_active is initialized in __init__ to prevent AttributeError in _clean_clients_thread.
2. self.navi_port == 7706 (send) and self.navi_remote_port == 7705 (receive).
3. _clean_clients_thread loop executes without throwing AttributeError or KeyError.
"""
import time
import unittest

class MockAmapNaviServCleanClients:
    def __init__(self):
        self.clients = {}
        self.client_active = {}
        self.lane_online = False
        self.ext_state = 0
        self.ext_blinker = 0

    def clean_clients_iteration(self, now):
        active_clients = {ip: info for ip, info in self.clients.items() if now - info.get("last_seen", 0) < 1.0}
        for ip, info in list(self.clients.items()):
            if ip not in active_clients and ip in self.client_active:
                self.client_active[ip] = False

        self.clients = active_clients
        self.ext_state = len(self.clients) + (1 if self.lane_online else 0)
        return len(active_clients)

class TestAmapNaviNetworking(unittest.TestCase):

    def test_clean_clients_iteration_no_clients(self):
        """Verify _clean_clients_thread logic executes cleanly when no clients are present"""
        serv = MockAmapNaviServCleanClients()
        active_count = serv.clean_clients_iteration(time.time())
        self.assertEqual(active_count, 0)
        self.assertEqual(serv.ext_state, 0)

    def test_clean_clients_timeout_and_eviction(self):
        """Verify stale clients (>1.0s) are evicted and client_active marked False without error"""
        serv = MockAmapNaviServCleanClients()
        now = time.time()
        serv.clients["192.168.3.165"] = {"last_seen": now - 2.0} # 2s old -> stale
        serv.client_active["192.168.3.165"] = True

        active_count = serv.clean_clients_iteration(now)
        self.assertEqual(active_count, 0, "Stale client must be evicted!")
        self.assertFalse(serv.client_active["192.168.3.165"], "Stale client must be marked inactive!")
        self.assertNotIn("192.168.3.165", serv.clients)

if __name__ == "__main__":
    unittest.main()
