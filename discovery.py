import socket
import logging
import threading
import time
import requests
from typing import List, Dict, Set
import netifaces

logger = logging.getLogger(__name__)


class OllamaDiscovery:
    """Discovers Ollama instances on local network"""

    COMMON_HOSTS = ["localhost", "127.0.0.1", "ollama", "host.docker.internal"]
    PORT = 11434
    SCAN_TIMEOUT = 2
    REFRESH_INTERVAL = 30
    ADDITIONAL_SUBNETS = ["192.168.1"]  # Always scan this subnet in addition to auto-detected

    def __init__(self):
        self.discovered: Set[str] = set()
        self.status: Dict[str, str] = {}  # url -> "online"/"offline"
        self.last_scan = 0
        self.lock = threading.Lock()
        self._start_refresh_thread()

    def _get_subnet(self) -> str:
        """Detect local subnet"""
        try:
            gateways = netifaces.gateways()
            if "default" in gateways:
                iface = gateways["default"][netifaces.AF_INET][1]
                addrs = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]
                ip = addrs["addr"]
                # Return base IP (e.g., 192.168.1)
                return ".".join(ip.split(".")[:3])
        except Exception as e:
            logger.warning(f"Could not detect subnet: {e}")
        return "192.168.1"  # Fallback

    def scan(self) -> List[str]:
        """Scan network for Ollama instances"""
        found = []

        # Check common hosts first
        for host in self.COMMON_HOSTS:
            url = f"http://{host}:{self.PORT}"
            if self._check_server(url):
                found.append(url)

        # Collect all subnets to scan
        subnets = set()
        subnets.add(self._get_subnet())
        subnets.update(self.ADDITIONAL_SUBNETS)

        for subnet in subnets:
            logger.info(f"Scanning subnet {subnet}.0/24 for Ollama...")

            threads = []
            results = []

            def check_ip(sub, i):
                url = f"http://{sub}.{i}:{self.PORT}"
                if self._check_server(url, timeout=self.SCAN_TIMEOUT):
                    results.append(url)

            for i in range(1, 255):
                t = threading.Thread(target=check_ip, args=(subnet, i))
                threads.append(t)
                t.start()

                # Limit concurrent threads
                if len(threads) >= 50:
                    for t in threads:
                        t.join(timeout=self.SCAN_TIMEOUT + 1)
                    threads = []

            for t in threads:
                t.join(timeout=self.SCAN_TIMEOUT + 1)

            found.extend(results)

        with self.lock:
            self.discovered = set(found)
            self.last_scan = time.time()

        logger.info(f"Discovery scan complete. Found {len(found)} Ollama instances")
        return found

    def _check_server(self, url: str, timeout: int = 3) -> bool:
        """Quick check if Ollama server is reachable"""
        try:
            resp = requests.get(f"{url}/api/tags", timeout=timeout)
            is_online = resp.status_code == 200
            with self.lock:
                self.status[url] = "online" if is_online else "offline"
            return is_online
        except:
            with self.lock:
                self.status[url] = "offline"
            return False

    def _start_refresh_thread(self):
        """Background thread to refresh server status"""

        def refresh():
            while True:
                time.sleep(self.REFRESH_INTERVAL)
                with self.lock:
                    urls = list(self.discovered)

                for url in urls:
                    self._check_server(url)

        threading.Thread(target=refresh, daemon=True).start()

    def get_servers(self) -> List[Dict]:
        """Get list of discovered servers with status"""
        with self.lock:
            return [
                {"url": url, "status": self.status.get(url, "unknown")}
                for url in self.discovered
            ]

    def get_online_servers(self) -> List[str]:
        """Get only online servers"""
        with self.lock:
            return [url for url, status in self.status.items() if status == "online"]


# Global instance
discovery = OllamaDiscovery()
