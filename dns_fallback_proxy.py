import socket
import time
import os
import sys
import logging
import logging.handlers
import configparser
import threading
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List
import fcntl  # For PID file locking

from dnslib import DNSRecord, DNSHeader, QTYPE, RCODE, DNSError

# --- Constants ---
CONFIG_FILE_PATH = Path("/opt/dns-fallback/config.ini")
DNS_STANDARD_PORT = 53

# --- Configuration & Logging Setup ---

@dataclass
class Config:
    primary_dns: str
    fallback_dns_servers: List[str] = field(default_factory=list)
    listen_address: str = '127.0.0.1'
    dns_port: int = 5355
    health_check_interval: int = 10
    log_file: Path = Path("/var/log/dns-fallback.log")
    pid_file: Path = Path("/var/run/dns-fallback.pid")
    buffer_size: int = 4096
    max_workers: int = 50
    health_check_domains: List[str] = field(default_factory=lambda: ["google.com", "cloudflare.com"])

def setup_logging(log_file: Path) -> logging.Logger:
    log_dir = log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def load_configuration(config_path: Path) -> Config:
    if not config_path.exists():
        sys.exit(f"Error: Config file not found at {config_path}")

    config_parser = configparser.ConfigParser()
    try:
        config_parser.read(config_path)
        proxy_config = config_parser['Proxy']
        health_domains = [d.strip() for d in proxy_config.get('health_check_domains', 'google.com,cloudflare.com').split(',') if d.strip()]
        fallback_servers = [s.strip() for s in proxy_config.get('fallback_dns_servers', '8.8.8.8,8.8.4.4').split(',') if s.strip()]
        return Config(
            primary_dns=proxy_config.get('primary_dns', "1.1.1.1"),
            fallback_dns_servers=fallback_servers,
            listen_address=proxy_config.get('listen_address', '127.0.0.1'),
            dns_port=proxy_config.getint('dns_port', 5355),
            health_check_interval=proxy_config.getint('health_check_interval', 10),
            log_file=Path(proxy_config.get('log_file', "/var/log/dns-fallback.log")),
            pid_file=Path(proxy_config.get('pid_file', "/var/run/dns-fallback.pid")),
            buffer_size=proxy_config.getint('buffer_size', 4096),
            max_workers=proxy_config.getint('max_workers', 50),
            health_check_domains=health_domains
        )
    except (configparser.Error, KeyError, ValueError) as e:
        sys.exit(f"Error reading or parsing config file {config_path}: {e}")

class LockedPIDFile:
    """Ensures only one process runs with this PID file, using advisory locking."""
    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self):
        self.file = open(self.path, "w")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit(f"Another instance is already running (PID file {self.path})")
        self.file.write(str(os.getpid()))
        self.file.flush()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.file:
                self.file.close()
                self.path.unlink(missing_ok=True)
        except Exception:
            pass

class DNSProxy:
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.dns_server_list = [self.config.primary_dns] + self.config.fallback_dns_servers
        self._current_dns = self.dns_server_list[0]
        self._state_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=self.config.max_workers, thread_name_prefix='DNSHandler')
        self.udp_sock: Optional[socket.socket] = None
        self.tcp_sock: Optional[socket.socket] = None
        self.logger.info(f"DNS Server Priority List: {self.dns_server_list}")

    @property
    def current_dns(self) -> str:
        with self._state_lock:
            return self._current_dns

    def _parse_addr(self, addr_str: str) -> Tuple[str, int]:
        """Parse address string, e.g., '127.0.0.1:5335' or '8.8.8.8'."""
        if ':' in addr_str:
            host, port = addr_str.rsplit(':', 1)
            try:
                port = int(port)
            except ValueError:
                port = DNS_STANDARD_PORT
            return host, port
        return addr_str, DNS_STANDARD_PORT

    def _send_dns_query(self, dns_server: str, query_data: bytes, timeout: float = 2.0) -> Optional[bytes]:
        host, port = self._parse_addr(dns_server)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(query_data, (host, port))
                return sock.recvfrom(self.config.buffer_size)[0]
        except socket.timeout:
            self.logger.warning(f"DNS query to {dns_server} timed out.")
        except socket.error as e:
            self.logger.error(f"Socket error querying {dns_server}: {e}")
        return None

    def _is_server_healthy(self, dns_server: str) -> bool:
        """Health check with jitter/backoff."""
        time.sleep(random.uniform(0, 0.25))  # Add up to 250ms jitter
        domain_to_check = random.choice(self.config.health_check_domains)
        try:
            test_query = DNSRecord.question(domain_to_check, "A").pack()
            return self._send_dns_query(dns_server, test_query, timeout=1.0) is not None
        except Exception:
            return False

    def _health_check_loop(self):
        self.logger.info("Health check thread started.")
        while not self._shutdown_event.wait(self.config.health_check_interval):
            with self._state_lock:
                current_server = self._current_dns
                is_primary_active = (current_server == self.dns_server_list[0])
                if self._is_server_healthy(current_server):
                    if not is_primary_active and self._is_server_healthy(self.dns_server_list[0]):
                        self.logger.info(f"Primary DNS ({self.dns_server_list[0]}) is healthy again. Failing back.")
                        self._current_dns = self.dns_server_list[0]
                else:
                    self.logger.warning(f"Active DNS server {current_server} has failed a health check.")
                    for server in self.dns_server_list:
                        if self._is_server_healthy(server):
                            if server != current_server:
                                self.logger.critical(f"Switching to next available server: {server}")
                                self._current_dns = server
                            break
                    else:
                        self.logger.critical("All configured DNS servers are down!")

    def _get_servfail_response(self, original_request: DNSRecord) -> bytes:
        header = DNSHeader(
            id=original_request.header.id,
            qr=1, opcode=original_request.header.opcode, rcode=RCODE.SERVFAIL
        )
        return DNSRecord(header, q=original_request.q).pack()

    def _handle_udp_request(self, data: bytes, client_addr: Tuple[str, int]):
        try:
            request = DNSRecord.parse(data)
            query_name = request.q.qname
            self.logger.debug(f"UDP query for '{query_name}' from {client_addr}")
        except DNSError:
            self.logger.warning(f"Received malformed UDP DNS query from {client_addr}")
            return
        response_data = self._send_dns_query(self.current_dns, data)
        if self.udp_sock:
            try:
                if response_data:
                    self.udp_sock.sendto(response_data, client_addr)
                else:
                    self.logger.error(f"No response from upstream for '{query_name}'. Sending SERVFAIL to {client_addr}.")
                    servfail_response = self._get_servfail_response(request)
                    self.udp_sock.sendto(servfail_response, client_addr)
            except socket.error as e:
                self.logger.error(f"Failed to send UDP response to {client_addr}: {e}")

    def _handle_tcp_request(self, client_sock: socket.socket, client_addr: Tuple[str, int]):
        self.logger.debug(f"Accepted TCP connection from {client_addr}")
        with client_sock:
            try:
                length_bytes = client_sock.recv(2)
                if not length_bytes:
                    return
                msg_length = int.from_bytes(length_bytes, 'big')
                data = client_sock.recv(msg_length)
                request = DNSRecord.parse(data)
                query_name = request.q.qname
                self.logger.debug(f"TCP query for '{query_name}' from {client_addr}")
                response_data = self._send_dns_query(self.current_dns, data)
                if not response_data:
                    self.logger.error(f"No response from upstream for '{query_name}'. Sending SERVFAIL to {client_addr}.")
                    response_data = self._get_servfail_response(request)
                response_with_len = len(response_data).to_bytes(2, 'big') + response_data
                client_sock.sendall(response_with_len)
            except DNSError:
                self.logger.warning(f"Received malformed TCP DNS query from {client_addr}")
            except (socket.error, ConnectionResetError) as e:
                self.logger.warning(f"TCP connection error with {client_addr}: {e}")
            except Exception as e:
                self.logger.exception(f"Unexpected error handling TCP request from {client_addr}")

    def _start_udp_server(self):
        addr = (self.config.listen_address, self.config.dns_port)
        self.logger.info(f"Starting UDP server on {addr}...")
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(addr)
            while not self._shutdown_event.is_set():
                data, client_addr = self.udp_sock.recvfrom(self.config.buffer_size)
                self.executor.submit(self._handle_udp_request, data, client_addr)
        except socket.error as e:
            if not self._shutdown_event.is_set():
                self.logger.critical(f"UDP server socket error: {e}", exc_info=True)
                self._shutdown_event.set()
        finally:
            self.logger.info("UDP server loop finished.")

    def _start_tcp_server(self):
        addr = (self.config.listen_address, self.config.dns_port)
        self.logger.info(f"Starting TCP server on {addr}...")
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_sock.bind(addr)
            self.tcp_sock.listen(self.config.max_workers)
            while not self._shutdown_event.is_set():
                client_sock, client_addr = self.tcp_sock.accept()
                self.executor.submit(self._handle_tcp_request, client_sock, client_addr)
        except socket.error as e:
            if not self._shutdown_event.is_set():
                self.logger.critical(f"TCP server socket error: {e}", exc_info=True)
                self._shutdown_event.set()
        finally:
            self.logger.info("TCP server loop finished.")

    def run(self):
        self.logger.info("Starting DNS Fallback Proxy...")
        with LockedPIDFile(self.config.pid_file):
            threading.Thread(target=self._health_check_loop, name="HealthCheckLoop", daemon=True).start()
            threading.Thread(target=self._start_tcp_server, name="TCPServerLoop", daemon=True).start()
            self._start_udp_server()

    def shutdown(self):
        self.logger.info("Shutting down DNS Fallback Proxy...")
        self._shutdown_event.set()
        self.executor.shutdown(wait=True)
        if self.tcp_sock:
            self.tcp_sock.close()
        if self.udp_sock:
            self.udp_sock.close()
        self.logger.info("Shutdown complete.")

def main():
    config = load_configuration(CONFIG_FILE_PATH)
    logger = setup_logging(config.log_file)
    proxy = DNSProxy(config, logger)
    try:
        proxy.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        proxy.shutdown()

if __name__ == "__main__":
    main()
