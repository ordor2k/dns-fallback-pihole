import socket
import time
import os
import sys
import logging
import logging.handlers
import configparser
from threading import Thread
from dnslib import DNSRecord, DNSHeader, QTYPE, DNSError

# --- Configuration File Path ---
CONFIG_FILE = "/opt/dns-fallback/config.ini"

# --- Load Configuration ---
config = configparser.ConfigParser()
if not os.path.exists(CONFIG_FILE):
    sys.exit(f"Error: Configuration file not found at {CONFIG_FILE}. Please create it and place it in /opt/dns-fallback/config.ini")
try:
    config.read(CONFIG_FILE)
except Exception as e:
    sys.exit(f"Error reading configuration file {CONFIG_FILE}: {e}")

# Proxy settings
PRIMARY_DNS = config.get('Proxy', 'primary_dns', fallback="127.0.0.1")
FALLBACK_DNS = config.get('Proxy', 'fallback_dns', fallback="1.1.1.1")
DNS_PORT = config.getint('Proxy', 'dns_port', fallback=5353)
HEALTH_CHECK_INTERVAL = config.getint('Proxy', 'health_check_interval', fallback=10)
FAILURE_THRESHOLD = config.getint('Proxy', 'failure_threshold', fallback=3)
LOG_FILE = config.get('Proxy', 'log_file', fallback="/var/log/dns-fallback.log")
PID_FILE = config.get('Proxy', 'pid_file', fallback="/var/run/dns-fallback.pid")
BUFFER_SIZE = config.getint('Proxy', 'buffer_size', fallback=4096)
# --- End Load Configuration ---

# --- Logger Setup ---
log_dir = os.path.dirname(LOG_FILE)
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        sys.exit(f"Error: Could not create log directory {log_dir}: {e}")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.info("DNS Fallback Proxy logger initialized.")
# --- End Logger Setup ---

class DNSServer:
    def __init__(self, primary_dns: str, fallback_dns: str, dns_port: int,
                 health_check_interval: int, pid_file: str, buffer_size: int,
                 failure_threshold: int):
        self.primary_dns = primary_dns
        self.fallback_dns = fallback_dns
        self.port = dns_port
        self.pid_file = pid_file
        self.buffer_size = buffer_size
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold

        self.current_dns = self.primary_dns
        self.last_health_check_time = 0
        self.consecutive_health_failures = 0
        self.running = False
        self.udp_sock: socket.socket | None = None

        logger.info(f"DNS Fallback Proxy initialized.")
        logger.info(f"Primary DNS: {self.primary_dns}, Fallback DNS: {self.fallback_dns}")
        logger.info(f"Listening on port: {self.port}")
        logger.info(f"Health check interval: {self.health_check_interval} seconds, Failure threshold: {self.failure_threshold}.")

    def _create_pid_file(self):
        try:
            pid = os.getpid()
            with open(self.pid_file, "w") as f:
                f.write(str(pid))
            logger.info(f"PID file created at {self.pid_file} with PID {pid}.")
        except IOError as e:
            logger.error(f"Error creating PID file {self.pid_file}: {e}")
            sys.exit(1)

    def _cleanup(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
                logger.info(f"Removed PID file: {self.pid_file}")
            except OSError as e:
                logger.error(f"Error removing PID file {self.pid_file}: {e}")
        self.running = False
        if self.udp_sock:
            self.udp_sock.close()
            logger.info("Closed main UDP server socket.")

    def _send_dns_query(self, dns_server: str, query_data: bytes, timeout: float = 1.0, retries: int = 3) -> bytes | None:
        for attempt in range(retries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(timeout)
                    sock.sendto(query_data, (dns_server, 53))
                    response_data, _ = sock.recvfrom(self.buffer_size)
                    logger.debug(f"Successfully received response from {dns_server} on attempt {attempt + 1}/{retries}.")
                    return response_data
            except socket.timeout:
                logger.warning(f"DNS query to {dns_server} timed out on attempt {attempt + 1}/{retries}.")
            except socket.gaierror as e:
                logger.error(f"Address resolution error for {dns_server} on attempt {attempt + 1}/{retries}: {e}.")
                return None
            except socket.error as e:
                logger.warning(f"Socket error during DNS query to {dns_server} on attempt {attempt + 1}/{retries}: {e}.")
            except DNSError as e:
                logger.warning(f"Malformed DNS response from {dns_server} on attempt {attempt + 1}/{retries}: {e}.")
            except Exception as e:
                logger.exception(f"An unexpected error occurred during DNS query to {dns_server} on attempt {attempt + 1}/{retries}.")

            if attempt < retries - 1:
                time.sleep(0.1 * (2 ** attempt))

        logger.error(f"DNS query to {dns_server} failed after {retries} attempts.")
        return None

    def _check_dns_health(self, dns_server: str) -> bool:
        test_domains = ["google.com", "cloudflare.com", "wikipedia.org"]
        test_query_type = QTYPE.A

        for domain in test_domains:
            try:
                q = DNSRecord.question(domain, test_query_type)
                query_data = q.pack()
                response = self._send_dns_query(dns_server, query_data, timeout=0.5, retries=1)
                if response:
                    DNSRecord.parse(response)
                    logger.debug(f"Health check for '{domain}' on {dns_server} succeeded.")
                    return True
                else:
                    logger.debug(f"Health check for '{domain}' on {dns_server} failed (no response).")
            except DNSError:
                logger.warning(f"Health check for '{domain}' on {dns_server} returned malformed DNS response.")
            except Exception as e:
                logger.error(f"Unexpected error during health check for '{domain}' on {dns_server}: {e}")
        logger.warning(f"All health checks to {dns_server} failed.")
        return False

    def _health_check_loop(self):
        while self.running:
            current_time = time.time()
            if current_time - self.last_health_check_time >= self.health_check_interval:
                self.last_health_check_time = current_time
                is_primary_healthy = self._check_dns_health(self.primary_dns)

                if not is_primary_healthy:
                    self.consecutive_health_failures += 1
                    logger.warning(f"Primary DNS ({self.primary_dns}) health check failed. Consecutive failures: {self.consecutive_health_failures}/{self.failure_threshold}.")
                    if self.consecutive_health_failures >= self.failure_threshold and self.current_dns != self.fallback_dns:
                        logger.warning(f"Primary DNS ({self.primary_dns}) is unhealthy after {self.failure_threshold} consecutive failures. Switching to fallback ({self.fallback_dns}).")
                        self.current_dns = self.fallback_dns
                else:
                    if self.current_dns == self.fallback_dns:
                        logger.info(f"Primary DNS ({self.primary_dns}) is now healthy. Switching back.")
                        self.current_dns = self.primary_dns
                    self.consecutive_health_failures = 0
            time.sleep(1)

    def _handle_dns_request(self, data: bytes, client_address: tuple[str, int]):
        try:
            dns_query = DNSRecord.parse(data)
            logger.debug(f"Received DNS query from {client_address}: {dns_query.q.qname} (Type: {QTYPE[dns_query.q.qtype]})")
            response_data = self._send_dns_query(self.current_dns, data)
            if response_data:
                self.udp_sock.sendto(response_data, client_address)
                logger.debug(f"Forwarded response from {self.current_dns} to {client_address}.")
            else:
                logger.error(f"No response from {self.current_dns} for query {dns_query.q.qname}. Not sending response to {client_address}.")
        except DNSError as e:
            logger.error(f"Malformed DNS query from {client_address}: {e}")
            try:
                header = DNSHeader(id=0 if len(data) < 2 else data[0] << 8 | data[1], qr=1, aa=0, ra=1, rcode=2)
                servfail_response = DNSRecord(header=header).pack()
                self.udp_sock.sendto(servfail_response, client_address)
            except Exception as se:
                logger.error(f"Failed to send SERVFAIL to {client_address}: {se}")
        except socket.error as e:
            logger.error(f"Socket error while handling request from {client_address}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred while handling request from {client_address}.")

    def start_udp(self):
        self.running = True
        self._create_pid_file()

        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_sock.bind(('127.0.0.1', self.port))
            logger.info(f"DNS Fallback Proxy UDP listening on 127.0.0.1:{self.port}...")

            health_thread = Thread(target=self._health_check_loop, daemon=True)
            health_thread.start()
            logger.info("Health check thread started.")

            while self.running:
                try:
                    data, client_address = self.udp_sock.recvfrom(self.buffer_size)
                    handler_thread = Thread(target=self._handle_dns_request, args=(data, client_address), daemon=True)
                    handler_thread.start()
                except socket.timeout:
                    pass
                except OSError as e:
                    if self.running:
                        logger.error(f"OS Error in UDP main loop: {e}. Server may be shutting down or socket issue.")
                        self.running = False
                except Exception as e:
                    logger.exception(f"Unexpected error in UDP server loop: {e}")
                    self.running = False

        except OSError as e:
            logger.critical(f"Failed to bind UDP socket to 127.0.0.1:{self.port}: {e}. Is another process using this port? Exiting.")
            self.running = False
        except Exception as e:
            logger.critical(f"DNS Fallback Proxy UDP crashed: {e}", exc_info=True)
        finally:
            self._cleanup()
            logger.info("DNS Fallback Proxy UDP is shutting down.")

    # ------------------- TCP Support -------------------------
    def start_tcp(self):
        # TCP server: each client connection handled in a new thread
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', self.port))
            sock.listen(10)
            logger.info(f"DNS Fallback Proxy TCP listening on 127.0.0.1:{self.port}...")

            while self.running:
                try:
                    client_sock, client_address = sock.accept()
                    Thread(target=self._handle_tcp_request, args=(client_sock, client_address), daemon=True).start()
                except Exception as e:
                    logger.error(f"Error accepting TCP connection: {e}")
        except Exception as e:
            logger.critical(f"DNS Fallback Proxy TCP crashed: {e}", exc_info=True)

    def _handle_tcp_request(self, client_sock, client_address):
        try:
            # TCP DNS: first two bytes = message length
            length_bytes = client_sock.recv(2)
            if not length_bytes or len(length_bytes) != 2:
                client_sock.close()
                return
            msg_length = int.from_bytes(length_bytes, byteorder='big')
            data = b''
            while len(data) < msg_length:
                more = client_sock.recv(msg_length - len(data))
                if not more:
                    client_sock.close()
                    return
                data += more
            # Forward query to current active DNS server using UDP, as usual
            response_data = self._send_dns_query(self.current_dns, data)
            if response_data:
                response_with_len = len(response_data).to_bytes(2, byteorder='big') + response_data
                client_sock.sendall(response_with_len)
            else:
                logger.error(f"TCP: No response from {self.current_dns} for query from {client_address}.")
            client_sock.close()
        except Exception as e:
            logger.error(f"Exception in TCP handler for {client_address}: {e}")
            try:
                client_sock.close()
            except:
                pass
# ------------------- End TCP Support -------------------------

if __name__ == "__main__":
    server = DNSServer(
        primary_dns=PRIMARY_DNS,
        fallback_dns=FALLBACK_DNS,
        dns_port=DNS_PORT,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        pid_file=PID_FILE,
        buffer_size=BUFFER_SIZE,
        failure_threshold=FAILURE_THRESHOLD
    )
    # Start TCP server in background
    tcp_thread = Thread(target=server.start_tcp, daemon=True)
    tcp_thread.start()

    # Start UDP server (main thread, blocking)
    server.start_udp()
