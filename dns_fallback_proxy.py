#!/usr/bin/env python3

from dnslib.server import DNSServer, BaseResolver
from dnslib import DNSRecord, QTYPE
import socket, time, logging
from collections import defaultdict

# Configuration
LISTEN_PORT = 5353
PRIMARY_DNS = ("127.0.0.1", 5355)
FALLBACK_DNS = ("1.1.1.1", 53)
TIMEOUT = 2.0

# Logging
logging.basicConfig(
    filename="/var/log/dns-fallback.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

total_queries = 0
fallback_hits = 0
per_domain_fallback = defaultdict(int)

class FallbackResolver(BaseResolver):
    def resolve(self, request, handler):
        global total_queries, fallback_hits, per_domain_fallback

        qname = str(request.q.qname)
        qtype = QTYPE[request.q.qtype]
        client_ip = handler.client_address[0]
        total_queries += 1
        logging.info(f"→ Query: {qname} ({qtype}) from {client_ip}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(TIMEOUT)
            sock.sendto(request.pack(), PRIMARY_DNS)
            response_data, _ = sock.recvfrom(512)
            sock.close()
            logging.info(f"✔ Primary success for {qname}")
        except socket.timeout:
            fallback_hits += 1
            per_domain_fallback[qname] += 1
            logging.warning(f"⏱ Timeout → Fallback used for {qname} (⚠️ no DNSSEC validation)")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(request.pack(), FALLBACK_DNS)
            response_data, _ = sock.recvfrom(512)
            sock.close()
            logging.info(f"✔ Fallback success for {qname}")

        # Periodic stats
        if total_queries % 10 == 0:
            logging.info(f"STATS: {total_queries} total queries, {fallback_hits} fallbacks")
            top = sorted(per_domain_fallback.items(), key=lambda x: x[1], reverse=True)[:3]
            for d, count in top:
                logging.info(f"  └─ {d}: {count} fallback(s)")

        return DNSRecord.parse(response_data)

if __name__ == "__main__":
    resolver = FallbackResolver()
    udp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=False)
    tcp_server = DNSServer(resolver, port=LISTEN_PORT, address="0.0.0.0", tcp=True)

    udp_server.start_thread()
    tcp_server.start_thread()

    logging.info(f"DNS Fallback Proxy started on UDP+TCP port {LISTEN_PORT}")
    while udp_server.isAlive() and tcp_server.isAlive():
        time.sleep(1)
