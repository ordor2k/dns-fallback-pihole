#!/usr/bin/env python3
from dnslib.server import DNSServer, BaseResolver
from dnslib import DNSRecord, QTYPE
import socket, time, logging, os, threading, signal, sys
from collections import Counter

# Configuration from environment variables or defaults
LISTEN_PORT = int(os.getenv("DNS_LISTEN_PORT", 5353))
PRIMARY_DNS = (os.getenv("PRIMARY_DNS", "127.0.0.1"), int(os.getenv("PRIMARY_DNS_PORT", 5355)))
FALLBACK_DNS = [
    (os.getenv("FALLBACK_DNS1", "1.1.1.1"), int(os.getenv("FALLBACK_DNS1_PORT", 53))),
    (os.getenv("FALLBACK_DNS2", "8.8.8.8"), int(os.getenv("FALLBACK_DNS2_PORT", 53)))
]
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
    global per_domain_fallback
    if len(per_domain_fallback) > MAX_DOMAINS_TRACKED:
        per_domain_fallback = Counter(dict(per_domain_fallback.most_common(MAX_DOMAINS_TRACKED)))
        logging.info(f"Pruned domain stats to {MAX_DOMAINS_TRACKED} entries")

def check_and_rotate_log():
    global log_counter
    with stats_lock:
        log_counter += 1
        if log_counter % 100 != 0:
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
    logging.info(f"Received signal {sig}, shutting down...")
    for server in servers:
        if hasattr(server, 'stop'):
            server.stop()
    logging.info("Shutdown complete")
    sys.exit(0)

def send_query(request, dns_server, timeout):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(request.pack(), dns_server)
        response_data, _ = sock.recvfrom(512)
        return DNSRecord.parse(response_data)

class FallbackResolver(BaseResolver):
    def resolve(self, request, handler):
        global total_queries, fallback_hits, per_domain_fallback
        qname = str(request.q.qname)
        qtype = QTYPE[request.q.qtype]
        client_ip = handler.client_address[0]

        with stats_lock:
            total_queries += 1
            current_total = total_queries

        logging.info(f"\u2192 Query: {qname} ({qtype}) from {client_ip}")
        check_and_rotate_log()

        response = None

        try:
            response = send_query(request, PRIMARY_DNS, TIMEOUT)
            if response.header.rcode not in (0,):
                raise Exception(f"Primary returned error rcode {response.header.rcode}")
            logging.info(f"\u2714 Primary success for {qname}")
        except Exception as e:
            logging.warning(f"Primary failed for {qname}: {str(e)}; falling back")
            with stats_lock:
                fallback_hits += 1
                per_domain_fallback[qname] += 1
                prune_domain_stats()
            for fallback_dns in FALLBACK_DNS:
                try:
                    response = send_query(request, fallback_dns, FALLBACK_TIMEOUT)
                    logging.info(f"\u2714 Fallback success for {qname} using {fallback_dns[0]}")
                    break
                except Exception as fallback_error:
                    logging.error(f"Fallback {fallback_dns[0]} failed for {qname}: {str(fallback_error)}")
            else:
                response = request.reply()
                response.header.rcode = 2  # SERVFAIL

        if current_total % 10 == 0:
            with stats_lock:
                stats_snapshot = fallback_hits
                top_domains = per_domain_fallback.most_common(3)
            logging.info(f"STATS: {current_total} queries, {stats_snapshot} fallbacks")
            for d, count in top_domains:
                logging.info(f"  \u2514\ufe0f {d}: {count} fallback(s)")

        return response

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except AttributeError:
        logging.warning("SIGTERM not available on this platform")

    resolver = FallbackResolver()

    udp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=False)
    tcp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=True)

    servers = [udp_server, tcp_server]

    udp_server.start_thread()
    tcp_server.start_thread()

    logging.info(f"DNS Fallback Proxy started on UDP+TCP port {LISTEN_PORT}")

    try:
        while all(server.isAlive() for server in servers):
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt, shutting down...")
        for server in servers:
            if hasattr(server, 'stop'):
                server.stop()

    logging.info("DNS Fallback Proxy stopped")
