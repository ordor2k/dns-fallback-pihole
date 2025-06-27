import socket
import time
import os
import sys
import logging
import logging.handlers
import configparser
from threading import Thread
from dnslib import DNSRecord, DNSHeader, QTYPE, RR, A, CNAME, TXT, MX, NS, SOA, PTR, SRV, AAAA, DNSLabel, DNSError

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
PRIMARY_DNS_PORT = config.get('Proxy', 'primary_dns_port', fallback=53)
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

# File handler with rotation
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10 MB per log file
    backupCount=5              # Keep 5 backup logs
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler (useful for testing/debugging outside of systemd, can be commented out for production)
# console_handler = logging.StreamHandler(sys.stdout)
# console_handler.setFormatter(formatter)
# logger.addHandler(console_handler)

logger.info("DNS Fallback Proxy logger initialized.")
# --- End Logger Setup ---


class DNSServer:
    """
    A UDP DNS proxy server that provides fallback functionality.

    It forwards DNS queries to a primary DNS server (e.g., Unbound) and
    switches to a fallback DNS server (e.g., 1.1.1.1) if the primary becomes unhealthy.
    """
    def __init__(self, primary_dns: str, primary_dns_port: int, fallback_dns: str, dns_port: int,
                 health_check_interval: int, pid_file: str, buffer_size: int,
                 failure_threshold: int):
        """
        Initializes the DNSServer instance.

        Args:
            primary_dns: The IP address of the primary DNS server.
            primary_dns_port: The Port of the primary DNS server
            fallback_dns: The IP address of the fallback DNS server.
            dns_port: The UDP port the proxy should listen on.
            health_check_interval: The interval (in seconds) between health checks.
            pid_file: The path to the PID file.
            buffer_size: The buffer size for UDP packets.
            failure_threshold: Number of consecutive health check failures before switching.
        """
        self.primary_dns = primary_dns
        self.primary_dns_port = int(primary_dns_port)
        self.fallback_dns = fallback_dns
        self.port = dns_port
        self.pid_file = pid_file
        self.buffer_size = buffer_size
        self.health_check_interval = health_check_interval
        self.failure_threshold = failure_threshold

        self.current_dns = self.primary_dns
        self.current_dns_port = self.primary_dns_port
        self.last_health_check_time = 0
        self.consecutive_health_failures = 0
        self.running = False
        self.sock: socket.socket | None = None # Explicitly type sock for clarity

        logger.info(f"DNS Fallback Proxy initialized.")
        logger.info(f"Primary DNS: {self.primary_dns}:{self.primary_dns_port}, Fallback DNS: {self.fallback_dns}")
        logger.info(f"Listening on port: {self.port}")
        logger.info(f"Health check interval: {self.health_check_interval} seconds, Failure threshold: {self.failure_threshold}.")

    def _create_pid_file(self):
        """Creates a PID file to store the process ID."""
        try:
            pid = os.getpid()
            with open(self.pid_file, "w") as f:
                f.write(str(pid))
            logger.info(f"PID file created at {self.pid_file} with PID {pid}.")
        except IOError as e:
            logger.error(f"Error creating PID file {self.pid_file}: {e}")
            sys.exit(1) # Exit if cannot create PID file

    def _cleanup(self):
        """Cleans up resources, including removing the PID file."""
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
                logger.info(f"Removed PID file: {self.pid_file}")
            except OSError as e:
                logger.error(f"Error removing PID file {self.pid_file}: {e}")
        self.running = False
        if self.sock:
            self.sock.close()
            logger.info("Closed main server socket.")

    def _send_dns_query(self, dns_server: str, query_data: bytes, dns_server_port: int = 53, timeout: float = 1.0, retries: int = 3) -> bytes | None:
        """
        Sends a DNS query to the specified DNS server with retries.

        Args:
            dns_server: The IP address of the DNS server to query.
            dns_server_port: The Port of the DNS server to query - defaults to 53
            query_data: The raw DNS query packet.
            timeout: The timeout for each socket operation in seconds.
            retries: Number of retry attempts.

        Returns:
            The raw DNS response packet, or None if an error occurs after all retries.
        """
        for attempt in range(retries):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.settimeout(timeout)
                    sock.sendto(query_data, (dns_server, dns_server_port))
                    response_data, _ = sock.recvfrom(self.buffer_size)
                    logger.debug(f"Successfully received response from {dns_server}:{dns_server_port} on attempt {attempt + 1}/{retries}.")
                    return response_data
            except socket.timeout:
                logger.warning(f"DNS query to {dns_server}:{dns_server_port} timed out on attempt {attempt + 1}/{retries}.")
            except socket.gaierror as e:
                logger.error(f"Address resolution error for {dns_server}:{dns_server_port} on attempt {attempt + 1}/{retries}: {e}. (Likely permanent error for this server)")
                return None # No point in retrying for address errors
            except socket.error as e:
                logger.warning(f"Socket error during DNS query to {dns_server}:{dns_server_port} on attempt {attempt + 1}/{retries}: {e}.")
            except DNSError as e:
                logger.warning(f"Malformed DNS response from {dns_server}:{dns_server_port} on attempt {attempt + 1}/{retries}: {e}.")
            except Exception as e:
                logger.exception(f"An unexpected error occurred during DNS query to {dns_server}:{dns_server_port} on attempt {attempt + 1}/{retries}.")

            if attempt < retries - 1:
                time.sleep(0.1 * (2 ** attempt)) # Exponential backoff: 0.1s, 0.2s, 0.4s...

        logger.error(f"DNS query to {dns_server}:{dns_server_port} failed after {retries} attempts.")
        return None

    def _check_dns_health(self, dns_server: str, dns_server_port: int = 53) -> bool:
        """
        Checks the health of a given DNS server by querying multiple well-known hosts.
        Returns True if at least one query succeeds and returns a valid DNS response,
        False otherwise.
        """
        test_domains = ["google.com", "cloudflare.com", "wikipedia.org"]
        test_query_type = QTYPE.A # A record (TYPE_A in dnslib)

        for domain in test_domains:
            try:
                q = DNSRecord.question(domain, test_query_type)
                query_data = q.pack()
                response = self._send_dns_query(dns_server, dns_server_port, query_data, timeout=0.5, retries=1) # Quick check, no retries for health check specifically
                if response:
                    # Attempt to parse response to ensure it's a valid DNS packet
                    DNSRecord.parse(response)
                    logger.debug(f"Health check for '{domain}' on {dns_server}:{dns_server_port} succeeded.")
                    return True # Found a healthy response
                else:
                    logger.debug(f"Health check for '{domain}' on {dns_server}:{dns_server_port} failed (no response).")
            except DNSError:
                logger.warning(f"Health check for '{domain}' on {dns_server}:{dns_server_port} returned malformed DNS response.")
            except Exception as e:
                logger.error(f"Unexpected error during health check for '{domain}' on {dns_server}:{dns_server_port}: {e}")

        logger.warning(f"All health checks to {dns_server}:{dns_server_port} failed.")
        return False

    def _health_check_loop(self):
        """
        Periodically checks the health of the primary DNS server and switches
        between primary and fallback if necessary.
        """
        while self.running:
            current_time = time.time()
            if current_time - self.last_health_check_time >= self.health_check_interval:
                self.last_health_check_time = current_time

                # Check primary DNS health
                is_primary_healthy = self._check_dns_health(self.primary_dns, self.primary_dns_port)

                if not is_primary_healthy:
                    self.consecutive_health_failures += 1
                    logger.warning(f"Primary DNS ({self.primary_dns}:{self.primary_dns_port}) health check failed. Consecutive failures: {self.consecutive_health_failures}/{self.failure_threshold}.")
                    if self.consecutive_health_failures >= self.failure_threshold and self.current_dns != self.fallback_dns:
                        logger.warning(f"Primary DNS ({self.primary_dns}:{self.primary_dns_port}) is unhealthy after {self.failure_threshold} consecutive failures. Switching to fallback ({self.fallback_dns}).")
                        self.current_dns = self.fallback_dns
                        self.current_dns_port = 53
                else:
                    if self.current_dns == self.fallback_dns:
                        logger.info(f"Primary DNS ({self.primary_dns}:{self.primary_dns_port}) is now healthy. Switching back.")
                        self.current_dns = self.primary_dns
                        self.current_dns_port = self.primary_dns_port
                    self.consecutive_health_failures = 0 # Reset counter on success

            time.sleep(1) # Check every second if interval is passed

    def _handle_dns_request(self, data: bytes, client_address: tuple[str, int]):
        """
        Handles an incoming DNS request from a client.
        Forwards the request to the current active DNS server and sends back the response.

        Args:
            data: The raw DNS query packet from the client.
            client_address: A tuple (IP, Port) of the client.
        """
        try:
            # Parse the incoming DNS query
            dns_query = DNSRecord.parse(data)
            logger.debug(f"Received DNS query from {client_address}: {dns_query.q.qname} (Type: {QTYPE[dns_query.q.qtype]})")

            # Forward query to the current active DNS server
            response_data = self._send_dns_query(self.current_dns, data, self.current_dns_port)

            if response_data:
                # Send the response back to the client
                self.sock.sendto(response_data, client_address)
                logger.debug(f"Forwarded response from {self.current_dns}:{self.current_dns_port} to {client_address}.")
            else:
                logger.error(f"No response from {self.current_dns}:{self.current_dns_port} for query {dns_query.q.qname}. Not sending response to {client_address}.")

        except DNSError as e:
            logger.error(f"Malformed DNS query from {client_address}: {e}")
            # Optionally send a SERVFAIL response back to the client
            try:
                # Create a DNS response with SERVFAIL (RCODE 2)
                header = DNSHeader(id=0 if len(data) < 2 else data[0] << 8 | data[1], qr=1, aa=0, ra=1, rcode=2)
                servfail_response = DNSRecord(header=header).pack()
                self.sock.sendto(servfail_response, client_address)
            except Exception as se:
                logger.error(f"Failed to send SERVFAIL to {client_address}: {se}")
        except socket.error as e:
            logger.error(f"Socket error while handling request from {client_address}: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred while handling request from {client_address}.")

    def start(self):
        """Starts the DNS proxy server, binding to the specified port."""
        self.running = True
        self._create_pid_file()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('127.0.0.1', self.port)) # Bind to localhost as it's for Pi-hole
            logger.info(f"DNS Fallback Proxy listening on 127.0.0.1:{self.port}...")

            # Start health check thread
            health_thread = Thread(target=self._health_check_loop, daemon=True)
            health_thread.start()
            logger.info("Health check thread started.")

            # Main server loop
            while self.running:
                try:
                    data, client_address = self.sock.recvfrom(self.buffer_size)
                    # Handle each request in a new thread to avoid blocking
                    handler_thread = Thread(target=self._handle_dns_request, args=(data, client_address), daemon=True)
                    handler_thread.start()
                except socket.timeout:
                    # This shouldn't typically happen with UDP recvfrom without a timeout set.
                    # If it's implemented, handle or pass.
                    pass
                except OSError as e:
                    if self.running: # Only log if not intentionally shutting down
                        logger.error(f"OS Error in main loop: {e}. Server may be shutting down or socket issue.")
                        self.running = False # Potentially unrecoverable error
                except Exception as e:
                    logger.exception(f"Unexpected error in main server loop: {e}")
                    self.running = False # Exit loop on unexpected errors

        except OSError as e:
            logger.critical(f"Failed to bind socket to 127.0.0.1:{self.port}: {e}. Is another process using this port? Exiting.")
            self.running = False # Ensure cleanup is called
        except Exception as e:
            logger.critical(f"DNS Fallback Proxy crashed: {e}", exc_info=True)
        finally:
            self._cleanup()
            logger.info("DNS Fallback Proxy is shutting down.")


if __name__ == "__main__":
    server = DNSServer(
        primary_dns=PRIMARY_DNS,
        primary_dns_port=PRIMARY_DNS_PORT,
        fallback_dns=FALLBACK_DNS,
        dns_port=DNS_PORT,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        pid_file=PID_FILE,
        buffer_size=BUFFER_SIZE,
        failure_threshold=FAILURE_THRESHOLD
    )
    server.start()
