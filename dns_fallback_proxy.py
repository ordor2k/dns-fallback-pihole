#!/usr/bin/env python3
from dnslib.server import DNSServer, BaseResolver
from dnslib import DNSRecord, QTYPE
import socket, time, logging, logging.handlers, os, threading, signal, sys
from collections import Counter

# Configuration from environment variables or defaults
LISTEN_PORT = int(os.getenv("DNS_LISTEN_PORT", 5353))  # Fixed: Changed from 5355 to 5353
PRIMARY_DNS = (os.getenv("PRIMARY_DNS", "127.0.0.1"), int(os.getenv("PRIMARY_DNS_PORT", 5335)))
FALLBACK_DNS = (os.getenv("FALLBACK_DNS", "1.1.1.1"), int(os.getenv("FALLBACK_DNS_PORT", 53)))
TIMEOUT = float(os.getenv("DNS_TIMEOUT", 2.0))
FALLBACK_TIMEOUT = float(os.getenv("FALLBACK_TIMEOUT", 3.0))
LOG_FILE = os.getenv("DNS_LOG_FILE", "/var/log/dns-fallback.log")
MAX_LOG_LINES = int(os.getenv("DNS_MAX_LOG_LINES", 10000))
MAX_DOMAINS_TRACKED = int(os.getenv("DNS_MAX_DOMAINS_TRACKED", 500))

# Logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Globals with thread safety
stats_lock = threading.Lock()
log_lock = threading.Lock()
total_queries = 0
fallback_hits = 0
per_domain_fallback = Counter()
log_counter = 0
servers = []

def prune_domain_stats():
    """Thread-safe domain stats pruning"""
    global per_domain_fallback
    if len(per_domain_fallback) > MAX_DOMAINS_TRACKED:
        per_domain_fallback = Counter(dict(per_domain_fallback.most_common(MAX_DOMAINS_TRACKED)))
        logging.info(f"Pruned domain stats to {MAX_DOMAINS_TRACKED} entries")

def check_and_rotate_log():
    """Thread-safe log rotation with proper locking"""
    global log_counter
    with stats_lock:  # Fixed: Protect log_counter access
        log_counter += 1
        should_check = log_counter % 100 == 0
    
    if not should_check:
        return
        
    try:
        if os.path.exists(LOG_FILE):
            with log_lock:
                with open(LOG_FILE, 'r') as f:
                    lines = f.readlines()
                if len(lines) > MAX_LOG_LINES:
                    logging.info(f"Rotating log from {len(lines)} to {MAX_LOG_LINES} lines")
                    with open(LOG_FILE, 'w') as f:
                        f.writelines(lines[-MAX_LOG_LINES:])
    except Exception as e:
        logging.error(f"Log rotation error: {str(e)}")

def signal_handler(sig, frame):
    """Graceful shutdown handler"""
    logging.info(f"Received signal {sig}, shutting down...")
    for server in servers:
        try:
            server.stop()
        except Exception as e:
            logging.error(f"Error stopping server: {e}")
    logging.info("Shutdown complete")
    sys.exit(0)

def send_query(request, dns_server, timeout):
    """Send DNS query with improved error handling and response validation"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            query_data = request.pack()
            sock.sendto(query_data, dns_server)
            
            # Fixed: Use larger buffer to handle larger responses
            response_data, _ = sock.recvfrom(4096)
            
            # Fixed: Validate response data
            if len(response_data) < 12:  # Minimum DNS header size
                raise Exception("Invalid DNS response: too short")
                
            response = DNSRecord.parse(response_data)
            
            # Fixed: Validate response matches query
            if response.header.id != request.header.id:
                raise Exception("Response ID mismatch")
                
            return response
    except socket.timeout:
        raise Exception("DNS query timeout")
    except Exception as e:
        raise Exception(f"DNS query failed: {str(e)}")

class FallbackResolver(BaseResolver):
    def resolve(self, request, handler):
        global total_queries, fallback_hits, per_domain_fallback
        qname = str(request.q.qname)
        qtype = QTYPE[request.q.qtype]
        client_ip = handler.client_address[0]

        with stats_lock:
            total_queries += 1
            current_total = total_queries

        logging.info(f"→ Query: {qname} ({qtype}) from {client_ip}")
        check_and_rotate_log()

        response = None

        # Try primary DNS first
        try:
            response = send_query(request, PRIMARY_DNS, TIMEOUT)
            # Check if the primary returned a server failure or refused response
            if response.header.rcode not in (0,):  # 0 = NOERROR
                raise Exception(f"Primary returned error rcode {response.header.rcode}")
            logging.info(f"✓ Primary success for {qname}")
        except Exception as e:
            # Fixed: Use consistent log message for dashboard parsing
            logging.warning(f"Primary failed for {qname}: {str(e)}; Fallback used for {qname}")
            
            with stats_lock:
                fallback_hits += 1
                per_domain_fallback[qname] += 1
                prune_domain_stats()
            
            # Try fallback DNS
            try:
                response = send_query(request, FALLBACK_DNS, FALLBACK_TIMEOUT)
                logging.info(f"✓ Fallback success for {qname}")
            except Exception as fallback_error:
                logging.error(f"Fallback failed for {qname}: {str(fallback_error)}")
                # Return SERVFAIL
                response = request.reply()
                response.header.rcode = 2  # SERVFAIL

        # Periodic stats logging
        if current_total % 10 == 0:
            with stats_lock:
                stats_snapshot = fallback_hits
                top_domains = per_domain_fallback.most_common(3)
            logging.info(f"STATS: {current_total} queries, {stats_snapshot} fallbacks")
            for d, count in top_domains:
                logging.info(f"  └─ {d}: {count} fallback(s)")

        return response

def main():
    """Main function with better error handling"""
    # Setup signal handlers safely
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except AttributeError:
        logging.warning("SIGTERM not available on this platform")

    # Validate configuration
    if LISTEN_PORT == PRIMARY_DNS[1]:
        logging.error(f"LISTEN_PORT ({LISTEN_PORT}) conflicts with PRIMARY_DNS_PORT ({PRIMARY_DNS[1]})")
        sys.exit(1)

    resolver = FallbackResolver()

    try:
        udp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=False)
        tcp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=True)
        
        servers.extend([udp_server, tcp_server])
        
        udp_server.start_thread()
        tcp_server.start_thread()
        
        logging.info(f"DNS Fallback Proxy started on UDP+TCP port {LISTEN_PORT}")
        logging.info(f"Primary DNS: {PRIMARY_DNS[0]}:{PRIMARY_DNS[1]}")
        logging.info(f"Fallback DNS: {FALLBACK_DNS[0]}:{FALLBACK_DNS[1]}")

        # Fixed: Better server monitoring
        while True:
            alive_servers = [s for s in servers if s.isAlive()]
            if not alive_servers:
                logging.error("All servers stopped unexpectedly")
                break
            time.sleep(1)
            
    except Exception as e:
        logging.error(f"Failed to start DNS servers: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt, shutting down...")
    finally:
        for server in servers:
            try:
                server.stop()
            except Exception as e:
                logging.error(f"Error stopping server: {e}")

    logging.info("DNS Fallback Proxy stopped")

if __name__ == "__main__":
    main()
