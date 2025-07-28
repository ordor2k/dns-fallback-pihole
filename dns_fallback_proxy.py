#!/usr/bin/env python3

import os
import subprocess
import sys
import shutil
from pathlib import Path

# --- Enhanced Auto Virtual Environment Bootstrap ---
VENV_DIR = Path("/opt/dns-fallback/venv")
PYTHON_BIN = VENV_DIR / "bin" / "python3"
PIP_BIN = VENV_DIR / "bin" / "pip"
ACTIVATE_SCRIPT = VENV_DIR / "bin" / "activate"

def is_venv_valid():
    """Check if virtual environment is properly configured"""
    return (PYTHON_BIN.exists() and 
            PIP_BIN.exists() and 
            ACTIVATE_SCRIPT.exists() and
            PYTHON_BIN.is_file())

def test_dependencies():
    """Test if required dependencies are available in the current environment"""
    try:
        import dnslib
        import flask
        return True
    except ImportError:
        return False

def create_or_repair_venv():
    """Create or repair virtual environment with proper error handling"""
    print("[INFO] Setting up virtual environment...")
    
    # Remove broken/incomplete venv if it exists
    if VENV_DIR.exists() and not is_venv_valid():
        print("[INFO] Removing incomplete virtual environment...")
        try:
            shutil.rmtree(VENV_DIR)
        except Exception as e:
            print(f"[WARNING] Failed to remove broken venv: {e}")
            # Try to continue anyway
    
    # Create fresh virtual environment
    if not VENV_DIR.exists() or not is_venv_valid():
        print("[INFO] Creating virtual environment...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], 
                         check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to create virtual environment: {e}")
            print(f"[ERROR] stdout: {e.stdout}")
            print(f"[ERROR] stderr: {e.stderr}")
            sys.exit(1)
    
    # Verify venv was created properly
    if not is_venv_valid():
        print("[ERROR] Virtual environment creation failed - missing components")
        sys.exit(1)
    
    # Upgrade pip first
    print("[INFO] Upgrading pip...")
    try:
        subprocess.run([str(PIP_BIN), "install", "--upgrade", "pip"], 
                     check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Failed to upgrade pip: {e}")
        # Continue anyway
    
    # Install required dependencies
    dependencies = ["dnslib", "flask"]
    for dep in dependencies:
        print(f"[INFO] Installing {dep}...")
        try:
            subprocess.run([str(PIP_BIN), "install", "--upgrade", dep], 
                         check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install {dep}: {e}")
            print(f"[ERROR] stdout: {e.stdout}")
            print(f"[ERROR] stderr: {e.stderr}")
            sys.exit(1)
    
    print("[INFO] Virtual environment setup complete")

# Main bootstrap logic
if sys.executable != str(PYTHON_BIN):
    # We're not running in the target virtual environment
    if not is_venv_valid() or not test_dependencies():
        create_or_repair_venv()
    
    # Test dependencies one more time after setup
    try:
        result = subprocess.run([str(PYTHON_BIN), "-c", "import dnslib, flask; print('Dependencies OK')"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print(f"[ERROR] Dependency test failed: {result.stderr}")
            create_or_repair_venv()  # Try one more time
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        print(f"[ERROR] Dependency verification failed: {e}")
        create_or_repair_venv()
    
    print("[INFO] Relaunching inside virtual environment...")
    os.execv(str(PYTHON_BIN), [str(PYTHON_BIN)] + sys.argv)

# --- Enhanced DNS Fallback Proxy Logic ---
import socket
import time
import logging
import logging.handlers
import configparser
import threading
import random
import json
import signal
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Set
from datetime import datetime, timedelta
from collections import defaultdict, deque
import fcntl
import os
import sys
import hashlib

from dnslib import DNSRecord, DNSHeader, QTYPE, RCODE, DNSError

CONFIG_FILE_PATH = Path("/opt/dns-fallback/config.ini")
DNS_STANDARD_PORT = 53

@dataclass
class DomainStats:
    unbound_failures: int = 0
    total_queries: int = 0
    last_unbound_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    bypass_until: Optional[datetime] = None

@dataclass
class QueryMetrics:
    domain: str
    client_ip: str
    resolver: str  # 'unbound', 'fallback', 'bypassed'
    response_time: float
    query_type: str
    timestamp: datetime
    success: bool

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
    # Enhanced configuration options
    unbound_timeout: float = 1.5
    fallback_timeout: float = 3.0
    intelligent_caching: bool = True
    max_domain_cache: int = 1000
    fallback_threshold: int = 3
    bypass_duration: int = 3600  # seconds
    enable_query_deduplication: bool = True
    structured_logging: bool = True

# CDN and known problematic patterns
CDN_PATTERNS = {
    'cloudfront.net', 'fastly.com', 'amazonaws.com', 'akamai.net',
    'cloudflare.com', 'jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com'
}

def setup_logging(log_file: Path, structured: bool = True) -> logging.Logger:
    log_dir = log_file.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Create handler with larger rotation
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=50 * 1024 * 1024, backupCount=10
    )
    
    if structured:
        # JSON formatter for structured logging
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                    'level': record.levelname,
                    'thread': record.threadName,
                    'message': record.getMessage()
                }
                # Add extra fields if present
                if hasattr(record, 'domain'):
                    log_entry['domain'] = record.domain
                if hasattr(record, 'client'):
                    log_entry['client'] = record.client
                if hasattr(record, 'resolver'):
                    log_entry['resolver'] = record.resolver
                if hasattr(record, 'response_time'):
                    log_entry['response_time'] = record.response_time
                if hasattr(record, 'query_type'):
                    log_entry['query_type'] = record.query_type
                return json.dumps(log_entry)
        
        handler.setFormatter(JSONFormatter())
    else:
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
            primary_dns=proxy_config.get('primary_dns', "127.0.0.1:5335"),
            fallback_dns_servers=fallback_servers,
            listen_address=proxy_config.get('listen_address', '127.0.0.1'),
            dns_port=proxy_config.getint('dns_port', 5355),
            health_check_interval=proxy_config.getint('health_check_interval', 10),
            log_file=Path(proxy_config.get('log_file', "/var/log/dns-fallback.log")),
            pid_file=Path(proxy_config.get('pid_file', "/var/run/dns-fallback.pid")),
            buffer_size=proxy_config.getint('buffer_size', 4096),
            max_workers=proxy_config.getint('max_workers', 50),
            health_check_domains=health_domains,
            # Enhanced options with defaults
            unbound_timeout=proxy_config.getfloat('unbound_timeout', 1.5),
            fallback_timeout=proxy_config.getfloat('fallback_timeout', 3.0),
            intelligent_caching=proxy_config.getboolean('intelligent_caching', True),
            max_domain_cache=proxy_config.getint('max_domain_cache', 1000),
            fallback_threshold=proxy_config.getint('fallback_threshold', 3),
            bypass_duration=proxy_config.getint('bypass_duration', 3600),
            enable_query_deduplication=proxy_config.getboolean('enable_query_deduplication', True),
            structured_logging=proxy_config.getboolean('structured_logging', True)
        )
    except (configparser.Error, KeyError, ValueError) as e:
        sys.exit(f"Error reading or parsing config file {config_path}: {e}")

class LockedPIDFile:
    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self):
        try:
            self.file = open(self.path, "w")
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

class EnhancedDNSProxy:
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
        
        # Enhanced features
        self.domain_stats: Dict[str, DomainStats] = {}
        self.query_cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))  # Recent queries per domain
        self.pending_queries: Dict[str, threading.Event] = {}  # Query deduplication
        self.query_results: Dict[str, Optional[bytes]] = {}  # Cached results for deduplication
        self.metrics_log: deque = deque(maxlen=10000)  # Recent metrics
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.logger.info(f"Enhanced DNS Proxy initialized with servers: {self.dns_server_list}")
        self.logger.info(f"Intelligent caching: {self.config.intelligent_caching}")
        self.logger.info(f"Query deduplication: {self.config.enable_query_deduplication}")

    def _signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()

    @property
    def current_dns(self) -> str:
        with self._state_lock:
            return self._current_dns

    def _parse_addr(self, addr_str: str) -> Tuple[str, int]:
        if ':' in addr_str:
            host, port = addr_str.rsplit(':', 1)
            try:
                port = int(port)
            except ValueError:
                port = DNS_STANDARD_PORT
            return host, port
        return addr_str, DNS_STANDARD_PORT

    def _is_cdn_domain(self, domain: str) -> bool:
        """Check if domain matches known CDN patterns"""
        domain_lower = domain.lower().rstrip('.')
        return any(pattern in domain_lower for pattern in CDN_PATTERNS)

    def _should_bypass_unbound(self, domain: str) -> bool:
        """Check if domain should bypass Unbound based on learned patterns"""
        if not self.config.intelligent_caching:
            return False
            
        # Check if it's a known CDN
        if self._is_cdn_domain(domain):
            return True
            
        # Check domain stats
        if domain in self.domain_stats:
            stats = self.domain_stats[domain]
            
            # Check if in bypass period
            if stats.bypass_until and datetime.now() < stats.bypass_until:
                return True
                
            # Check failure threshold
            if (stats.consecutive_failures >= self.config.fallback_threshold and 
                stats.total_queries >= 5):
                return True
                
        return False

    def _update_domain_stats(self, domain: str, success: bool, resolver: str):
        """Update domain statistics for intelligent caching"""
        if not self.config.intelligent_caching:
            return
            
        now = datetime.now()
        
        if domain not in self.domain_stats:
            self.domain_stats[domain] = DomainStats()
            
        stats = self.domain_stats[domain]
        stats.total_queries += 1
        
        if resolver == 'unbound':
            if success:
                stats.last_unbound_success = now
                stats.consecutive_failures = 0
                stats.bypass_until = None  # Clear bypass
            else:
                stats.unbound_failures += 1
                stats.consecutive_failures += 1
                stats.last_failure = now
                
                # Set bypass period if threshold reached
                if stats.consecutive_failures >= self.config.fallback_threshold:
                    stats.bypass_until = now + timedelta(seconds=self.config.bypass_duration)
                    self.logger.warning(f"Domain {domain} bypassed for {self.config.bypass_duration}s due to repeated Unbound failures")
        
        # Limit cache size
        if len(self.domain_stats) > self.config.max_domain_cache:
            # Remove oldest entries (simple LRU approximation)
            oldest_domain = min(self.domain_stats.keys(), 
                              key=lambda d: self.domain_stats[d].total_queries)
            del self.domain_stats[oldest_domain]

    def _log_query_metric(self, domain: str, client_ip: str, resolver: str, 
                         response_time: float, query_type: str, success: bool):
        """Log structured query metrics"""
        metric = QueryMetrics(
            domain=domain,
            client_ip=client_ip,
            resolver=resolver,
            response_time=response_time,
            query_type=query_type,
            timestamp=datetime.now(),
            success=success
        )
        
        self.metrics_log.append(metric)
        
        if self.config.structured_logging:
            self.logger.info("DNS_QUERY", extra={
                'domain': domain,
                'client': client_ip,
                'resolver': resolver,
                'response_time': response_time,
                'query_type': query_type,
                'success': success
            })

    def _send_dns_query(self, dns_server: str, query_data: bytes, timeout: float = 2.0) -> Optional[bytes]:
        """Send DNS query with enhanced error handling and metrics"""
        host, port = self._parse_addr(dns_server)
        start_time = time.time()
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(query_data, (host, port))
                response = sock.recvfrom(self.config.buffer_size)[0]
                response_time = time.time() - start_time
                
                # Validate response
                try:
                    DNSRecord.parse(response)
                    return response
                except DNSError:
                    self.logger.warning(f"Invalid DNS response from {dns_server}")
                    return None
                    
        except socket.timeout:
            response_time = time.time() - start_time
            self.logger.warning(f"DNS query to {dns_server} timed out after {response_time:.2f}s")
        except socket.error as e:
            response_time = time.time() - start_time
            self.logger.error(f"Socket error querying {dns_server}: {e}")
        except Exception as e:
            response_time = time.time() - start_time
            self.logger.error(f"Unexpected error querying {dns_server}: {e}")
            
        return None

    def _is_server_healthy(self, dns_server: str) -> bool:
        """Enhanced health check with multiple domain types"""
        time.sleep(random.uniform(0, 0.25))  # Prevent thundering herd
        
        # Test with different types of domains
        test_domains = self.config.health_check_domains.copy()
        
        # Add some CDN domains if testing fallback servers
        if dns_server != self.config.primary_dns:
            test_domains.extend(['cdn.jsdelivr.net', 'ajax.googleapis.com'])
        
        success_count = 0
        for domain in random.sample(test_domains, min(3, len(test_domains))):
            try:
                test_query = DNSRecord.question(domain, "A").pack()
                if self._send_dns_query(dns_server, test_query, timeout=1.5):
                    success_count += 1
            except Exception as e:
                self.logger.debug(f"Health check error for {domain} on {dns_server}: {e}")
                
        # Require at least 2/3 success rate
        return success_count >= max(1, len(test_domains) * 2 // 3)

    def _health_check_loop(self):
        """Enhanced health check with adaptive intervals"""
        self.logger.info("Enhanced health check thread started.")
        
        consecutive_failures = 0
        base_interval = self.config.health_check_interval
        
        while not self._shutdown_event.wait(base_interval):
            with self._state_lock:
                current_server = self._current_dns
                is_primary_active = (current_server == self.dns_server_list[0])
                
                if self._is_server_healthy(current_server):
                    consecutive_failures = 0
                    base_interval = self.config.health_check_interval  # Reset interval
                    
                    # Try to fail back to primary if we're using fallback
                    if not is_primary_active and self._is_server_healthy(self.dns_server_list[0]):
                        self.logger.info(f"Primary DNS ({self.dns_server_list[0]}) is healthy again. Failing back.")
                        self._current_dns = self.dns_server_list[0]
                        
                else:
                    consecutive_failures += 1
                    self.logger.warning(f"Active DNS server {current_server} failed health check (attempt {consecutive_failures})")
                    
                    # Adaptive interval - check more frequently during outages
                    base_interval = min(30, self.config.health_check_interval + consecutive_failures * 2)
                    
                    # Find next healthy server
                    for server in self.dns_server_list:
                        if server != current_server and self._is_server_healthy(server):
                            self.logger.critical(f"Switching to fallback server: {server}")
                            self._current_dns = server
                            break
                    else:
                        self.logger.critical("All DNS servers failed health checks!")

    def _get_servfail_response(self, original_request: DNSRecord) -> bytes:
        """Generate SERVFAIL response"""
        header = DNSHeader(
            id=original_request.header.id,
            qr=1, opcode=original_request.header.opcode, rcode=RCODE.SERVFAIL
        )
        return DNSRecord(header, q=original_request.q).pack()

    def _handle_query_with_fallback(self, request: DNSRecord, query_data: bytes, client_addr: Tuple[str, int]) -> Optional[bytes]:
        """Enhanced query handling with intelligent fallback"""
        domain = str(request.q.qname).rstrip('.')
        query_type = QTYPE[request.q.qtype]
        client_ip = client_addr[0]
        
        # Query deduplication
        if self.config.enable_query_deduplication:
            query_key = f"{domain}:{query_type}"
            
            # Check if same query is already in progress
            if query_key in self.pending_queries:
                # Wait for the other query to complete
                self.pending_queries[query_key].wait(timeout=5.0)
                if query_key in self.query_results:
                    result = self.query_results[query_key]
                    del self.query_results[query_key]
                    return result
            else:
                # Mark this query as in progress
                self.pending_queries[query_key] = threading.Event()
        
        try:
            response_data = None
            resolver_used = 'none'
            start_time = time.time()
            
            # Check if we should bypass Unbound
            should_bypass = self._should_bypass_unbound(domain)
            
            if should_bypass:
                self.logger.debug(f"Bypassing Unbound for {domain} (learned pattern)")
                resolver_used = 'bypassed'
            else:
                # Try Unbound first (primary DNS)
                response_data = self._send_dns_query(
                    self.config.primary_dns, 
                    query_data, 
                    timeout=self.config.unbound_timeout
                )
                
                if response_data:
                    resolver_used = 'unbound'
                    self._update_domain_stats(domain, True, 'unbound')
                else:
                    self._update_domain_stats(domain, False, 'unbound')
            
            # Fallback to public DNS if needed
            if not response_data:
                current_fallback = self.current_dns
                if current_fallback != self.config.primary_dns:
                    response_data = self._send_dns_query(
                        current_fallback, 
                        query_data, 
                        timeout=self.config.fallback_timeout
                    )
                    if response_data:
                        resolver_used = 'fallback'
            
            # Generate SERVFAIL if all failed
            if not response_data:
                response_data = self._get_servfail_response(request)
                resolver_used = 'servfail'
            
            # Log metrics
            response_time = time.time() - start_time
            success = resolver_used not in ['servfail', 'none']
            self._log_query_metric(domain, client_ip, resolver_used, response_time, query_type, success)
            
            # Handle query deduplication cleanup
            if self.config.enable_query_deduplication:
                query_key = f"{domain}:{query_type}"
                if query_key in self.pending_queries:
                    self.query_results[query_key] = response_data
                    self.pending_queries[query_key].set()
                    # Clean up after a short delay
                    threading.Timer(1.0, lambda: self.pending_queries.pop(query_key, None)).start()
            
            return response_data
            
        except Exception as e:
            self.logger.error(f"Error handling query for {domain}: {e}")
            return self._get_servfail_response(request)

    def _handle_udp_request(self, data: bytes, client_addr: Tuple[str, int]):
        """Handle UDP DNS request with enhanced processing"""
        try:
            request = DNSRecord.parse(data)
        except DNSError:
            self.logger.warning(f"Malformed UDP DNS query from {client_addr}")
            return
            
        response_data = self._handle_query_with_fallback(request, data, client_addr)
        
        if self.udp_sock and response_data:
            try:
                self.udp_sock.sendto(response_data, client_addr)
            except socket.error as e:
                self.logger.error(f"UDP send error to {client_addr}: {e}")

    def _handle_tcp_request(self, client_sock: socket.socket, client_addr: Tuple[str, int]):
        """Handle TCP DNS request with enhanced processing"""
        with client_sock:
            try:
                # Read message length
                length_bytes = client_sock.recv(2)
                if not length_bytes:
                    return
                    
                msg_length = int.from_bytes(length_bytes, 'big')
                if msg_length > self.config.buffer_size:
                    self.logger.warning(f"TCP query too large ({msg_length} bytes) from {client_addr}")
                    return
                
                # Read message data
                data = client_sock.recv(msg_length)
                if len(data) != msg_length:
                    self.logger.warning(f"Incomplete TCP query from {client_addr}")
                    return
                
                request = DNSRecord.parse(data)
                response_data = self._handle_query_with_fallback(request, data, client_addr)
                
                if response_data:
                    response_with_len = len(response_data).to_bytes(2, 'big') + response_data
                    client_sock.sendall(response_with_len)
                    
            except Exception as e:
                self.logger.warning(f"TCP error with {client_addr}: {e}")

    def _start_udp_server(self):
        """Start UDP server with enhanced error handling"""
        addr = (self.config.listen_address, self.config.dns_port)
        self.logger.info(f"Starting UDP server on {addr}")
        
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_sock.bind(addr)
            self.udp_sock.settimeout(1.0)  # Allow periodic checks for shutdown
            
            while not self._shutdown_event.is_set():
                try:
                    data, client_addr = self.udp_sock.recvfrom(self.config.buffer_size)
                    self.executor.submit(self._handle_udp_request, data, client_addr)
                except socket.timeout:
                    continue  # Check shutdown event
                except Exception as e:
                    if not self._shutdown_event.is_set():
                        self.logger.error(f"UDP server error: {e}")
                        
        except Exception as e:
            self.logger.error(f"Failed to start UDP server: {e}")
        finally:
            if self.udp_sock:
                self.udp_sock.close()
            self.logger.info("UDP server stopped.")

    def _start_tcp_server(self):
        """Start TCP server with enhanced error handling"""
        addr = (self.config.listen_address, self.config.dns_port)
        self.logger.info(f"Starting TCP server on {addr}")
        
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_sock.bind(addr)
            self.tcp_sock.listen(self.config.max_workers)
            self.tcp_sock.settimeout(1.0)  # Allow periodic checks for shutdown
            
            while not self._shutdown_event.is_set():
                try:
                    client_sock, client_addr = self.tcp_sock.accept()
                    self.executor.submit(self._handle_tcp_request, client_sock, client_addr)
                except socket.timeout:
                    continue  # Check shutdown event
                except Exception as e:
                    if not self._shutdown_event.is_set():
                        self.logger.error(f"TCP server error: {e}")
                        
        except Exception as e:
            self.logger.error(f"Failed to start TCP server: {e}")
        finally:
            if self.tcp_sock:
                self.tcp_sock.close()
            self.logger.info("TCP server stopped.")

    def get_statistics(self) -> Dict:
        """Get current proxy statistics for dashboard"""
        with self._state_lock:
            total_queries = len(self.metrics_log)
            if total_queries == 0:
                return {
                    'total_queries': 0,
                    'unbound_success_rate': 0,
                    'fallback_usage': 0,
                    'bypassed_domains': 0,
                    'current_dns': self._current_dns,
                    'top_failing_domains': []
                }
            
            # Calculate metrics from recent queries
            unbound_success = sum(1 for m in self.metrics_log if m.resolver == 'unbound' and m.success)
            fallback_usage = sum(1 for m in self.metrics_log if m.resolver == 'fallback')
            bypassed_queries = sum(1 for m in self.metrics_log if m.resolver == 'bypassed')
            
            # Top failing domains
            domain_failures = defaultdict(int)
            for domain, stats in self.domain_stats.items():
                if stats.consecutive_failures >= 2:
                    domain_failures[domain] = stats.consecutive_failures
            
            top_failing = sorted(domain_failures.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                'total_queries': total_queries,
                'unbound_success_rate': (unbound_success / max(1, sum(1 for m in self.metrics_log if m.resolver == 'unbound'))) * 100,
                'fallback_usage': (fallback_usage / total_queries) * 100,
                'bypassed_domains': len([d for d, s in self.domain_stats.items() if s.bypass_until and datetime.now() < s.bypass_until]),
                'current_dns': self._current_dns,
                'top_failing_domains': top_failing,
                'average_response_time': sum(m.response_time for m in self.metrics_log) / total_queries,
                'recent_queries': total_queries
            }

    def run(self):
        """Run the enhanced DNS proxy"""
        self.logger.info("Starting Enhanced DNS Fallback Proxy...")
        self.logger.info(f"Configuration: Unbound timeout={self.config.unbound_timeout}s, Fallback timeout={self.config.fallback_timeout}s")
        self.logger.info(f"Intelligent caching enabled: {self.config.intelligent_caching}")
        
        with LockedPIDFile(self.config.pid_file):
            # Start background threads
            threading.Thread(target=self._health_check_loop, name="HealthCheckLoop", daemon=True).start()
            threading.Thread(target=self._start_tcp_server, name="TCPServerLoop", daemon=True).start()
            
            # Run UDP server in main thread
            self._start_udp_server()

    def shutdown(self):
        """Graceful shutdown of the proxy"""
        self.logger.info("Shutting down Enhanced DNS Fallback Proxy...")
        self._shutdown_event.set()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        # Close sockets
        if self.tcp_sock:
            self.tcp_sock.close()
        if self.udp_sock:
            self.udp_sock.close()
            
        self.logger.info("Enhanced DNS Fallback Proxy shutdown complete.")

def main():
    """Main entry point with enhanced error handling"""
    try:
        config = load_configuration(CONFIG_FILE_PATH)
        logger = setup_logging(config.log_file, config.structured_logging)
        
        # Log startup information
        logger.info("=== Enhanced DNS Fallback Proxy Starting ===")
        logger.info(f"Primary DNS: {config.primary_dns}")
        logger.info(f"Fallback servers: {', '.join(config.fallback_dns_servers)}")
        logger.info(f"Listen on: {config.listen_address}:{config.dns_port}")
        logger.info(f"Intelligent caching: {config.intelligent_caching}")
        logger.info(f"Query deduplication: {config.enable_query_deduplication}")
        
        proxy = EnhancedDNSProxy(config, logger)
        proxy.run()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        try:
            proxy.shutdown()
        except:
            pass

if __name__ == "__main__":
    main()
