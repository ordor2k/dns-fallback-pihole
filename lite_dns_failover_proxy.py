#!/usr/bin/env python3
import socket
import socketserver
import struct
import threading
import time
import logging
import signal
import sys
from typing import List, Tuple, Optional

# You need: pip install dnslib
from dnslib import DNSRecord, DNSHeader, DNSQuestion, DNSError

# -------------------------
# Configuration
# -------------------------
LISTEN_ADDR = "127.0.0.1"
LISTEN_PORT = 5355           # Use 53 only if you bind with the right privileges
PRIMARY_DNS = ("127.0.0.1", 5335)  # Unbound default on many Pi-hole setups
FALLBACK_DNS: List[Tuple[str, int]] = [
    ("1.1.1.1", 53),   # Cloudflare
    ("8.8.8.8", 53),   # Google
    ("9.9.9.9", 53),   # Quad9
    ("1.0.0.1", 53),   # Cloudflare secondary
]

UDP_TIMEOUT = 1.0            # seconds per try for UDP
TCP_TIMEOUT = 2.0            # seconds per try for TCP
RETRIES_PER_UPSTREAM = 1     # how many extra attempts per upstream server

LOG_LEVEL = logging.INFO     # DEBUG for more verbosity
LOG_FORMAT = "[%(asctime)s] %(levelname)s %(message)s"
# -------------------------


logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("dns-failover-proxy")

_shutdown = threading.Event()


def _udp_query(upstream: Tuple[str, int], payload: bytes, timeout: float) -> Optional[bytes]:
    """
    Send a DNS query over UDP. Return response bytes or None on timeout/error.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(payload, upstream)
            data, _ = s.recvfrom(4096)
            return data
    except (socket.timeout, OSError) as e:
        logger.debug(f"UDP query to {upstream} failed: {e}")
        return None


def _tcp_query(upstream: Tuple[str, int], payload: bytes, timeout: float) -> Optional[bytes]:
    """
    Send a DNS query over TCP (RFC 7766). Return response bytes or None on timeout/error.
    """
    try:
        with socket.create_connection(upstream, timeout=timeout) as s:
            # Prepend two-byte length field
            s.settimeout(timeout)
            s.sendall(struct.pack("!H", len(payload)) + payload)

            # First read two-byte length
            hdr = s.recv(2)
            if len(hdr) < 2:
                return None
            (length,) = struct.unpack("!H", hdr)
            buf = b""
            while len(buf) < length:
                chunk = s.recv(length - len(buf))
                if not chunk:
                    return None
                buf += chunk
            return buf
    except (socket.timeout, OSError) as e:
        logger.debug(f"TCP query to {upstream} failed: {e}")
        return None


def _try_upstream(upstream: Tuple[str, int], query: bytes) -> Optional[bytes]:
    """
    Try UDP first; if response is truncated (TC bit), retry same upstream over TCP.
    """
    # UDP first
    udp_resp = _udp_query(upstream, query, UDP_TIMEOUT)
    if udp_resp is None:
        return None

    # Check TC bit (truncated). If set, retry via TCP to same upstream.
    try:
        dns = DNSRecord.parse(udp_resp)
        if dns.header.tc:  # truncated
            logger.debug(f"Truncated UDP response from {upstream}; retrying via TCP")
            tcp_resp = _tcp_query(upstream, query, TCP_TIMEOUT)
            return tcp_resp or udp_resp  # fallback to UDP resp if TCP fails
        return udp_resp
    except DNSError:
        # If parsing failed, still try TCP as a last-ditch attempt
        logger.debug(f"Failed to parse UDP response from {upstream}; trying TCP")
        tcp_resp = _tcp_query(upstream, query, TCP_TIMEOUT)
        return tcp_resp


def resolve_with_failover(query: bytes) -> Optional[bytes]:
    """
    Attempt resolution with PRIMARY_DNS first, then walk fallbacks.
    Per-upstream: do a few retries to smooth transient hiccups.
    """
    upstreams = [PRIMARY_DNS] + FALLBACK_DNS
    for upstream in upstreams:
        for attempt in range(1 + RETRIES_PER_UPSTREAM):
            resp = _try_upstream(upstream, query)
            if resp:
                logger.debug(f"Answered via {upstream} (attempt {attempt+1})")
                return resp
            logger.debug(f"No response from {upstream} (attempt {attempt+1})")
        logger.info(f"Upstream failed: {upstream}")
    return None


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        client = self.client_address
        try:
            # Parse once for logging/ID; keep original payload for upstream
            q = DNSRecord.parse(data)
            qname = str(q.q.qname) if q.q else "<?>"
            logger.debug(f"UDP query from {client}: {qname}")

            resp = resolve_with_failover(data)
            if resp:
                sock.sendto(resp, client)
            else:
                # Build a SERVFAIL to be nice
                try:
                    rq = DNSRecord.parse(data)
                    r = DNSRecord(
                        DNSHeader(id=rq.header.id, qr=1, aa=0, ra=1, rcode=2),  # 2 = SERVFAIL
                        q=rq.q if rq.q else DNSQuestion("invalid.")
                    )
                    sock.sendto(r.pack(), client)
                except DNSError:
                    # If we cannot parse the original, just ignore
                    pass
        except DNSError:
            # Ignore malformed packets silently (common on noisy networks)
            logger.debug(f"Malformed UDP DNS from {client}; ignoring")


class TCPHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        client = self.client_address
        try:
            # TCP DNS framing: first 2 bytes are length
            hdr = self.rfile.read(2)
            if len(hdr) < 2:
                return
            (length,) = struct.unpack("!H", hdr)
            payload = self.rfile.read(length)
            if len(payload) < length:
                return

            q = DNSRecord.parse(payload)
            qname = str(q.q.qname) if q.q else "<?>"
            logger.debug(f"TCP query from {client}: {qname}")

            resp = resolve_with_failover(payload)
            if resp is None:
                # Return SERVFAIL
                try:
                    rq = DNSRecord.parse(payload)
                    r = DNSRecord(
                        DNSHeader(id=rq.header.id, qr=1, aa=0, ra=1, rcode=2),
                        q=rq.q if rq.q else DNSQuestion("invalid.")
                    ).pack()
                    self.wfile.write(struct.pack("!H", len(r)) + r)
                except DNSError:
                    return
                return

            # Send length-prefixed response
            self.wfile.write(struct.pack("!H", len(resp)) + resp)

        except DNSError:
            logger.debug(f"Malformed TCP DNS from {client}; ignoring")
        except (ConnectionResetError, BrokenPipeError):
            pass


class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _health_logger():
    """
    Optional: periodically log whether PRIMARY looks healthy.
    Non-blocking; purely informative.
    """
    while not _shutdown.is_set():
        try:
            # Build a tiny query (A record for .)
            q = DNSRecord.question(".")
            resp = _try_upstream(PRIMARY_DNS, q.pack())
            if resp:
                logger.debug("Health: PRIMARY reachable")
            else:
                logger.info("Health: PRIMARY appears down/unreachable")
        except Exception as e:
            logger.debug(f"Health check error: {e}")
        _shutdown.wait(30)  # every 30s


def main():
    logger.info(f"DNS failover proxy listening on {LISTEN_ADDR}:{LISTEN_PORT} "
                f"(primary {PRIMARY_DNS}, fallbacks {FALLBACK_DNS})")

    udp_server = ThreadedUDPServer((LISTEN_ADDR, LISTEN_PORT), UDPHandler)
    tcp_server = ThreadedTCPServer((LISTEN_ADDR, LISTEN_PORT), TCPHandler)

    t_udp = threading.Thread(target=udp_server.serve_forever, name="UDPServer", daemon=True)
    t_tcp = threading.Thread(target=tcp_server.serve_forever, name="TCPServer", daemon=True)
    t_hlt = threading.Thread(target=_health_logger, name="Health", daemon=True)

    t_udp.start()
    t_tcp.start()
    t_hlt.start()

    def stop(*_):
        logger.info("Shutting down...")
        _shutdown.set()
        udp_server.shutdown()
        tcp_server.shutdown()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        while not _shutdown.is_set():
            time.sleep(0.2)
    finally:
        udp_server.server_close()
        tcp_server.server_close()
        logger.info("Bye.")

if __name__ == "__main__":
    # Quick import check with a clear error
    try:
        import dnslib  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "Missing dependency 'dnslib'. Install with:\n  pip install dnslib\n"
        )
        sys.exit(1)
    main()
