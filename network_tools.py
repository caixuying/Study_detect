import argparse
import socket
import time
import urllib.request
import urllib.error


def cmd_speedtest():
    """Download a test file and compute bandwidth in Mbps."""
    url = "http://speedtest.tele2.net/1MB.zip"
    print(f"Downloading test file: {url}")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            total = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
        elapsed = time.perf_counter() - start
        size_mbit = (total * 8) / 1_000_000
        mbps = size_mbit / elapsed if elapsed > 0 else 0
        print(f"Downloaded: {total / 1024:.1f} KB")
        print(f"Elapsed:   {elapsed:.2f} s")
        print(f"Speed:     {mbps:.2f} Mbps")
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        print(f"Speed test failed: {exc}")


def cmd_dns(host):
    """Resolve a hostname and print all addresses."""
    print(f"Resolving: {host}")
    try:
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        print(f"DNS resolution failed: {exc}")
        return
    seen = set()
    for family, socktype, proto, canonname, addr in results:
        ip = addr[0]
        if ip not in seen:
            seen.add(ip)
            family_name = "IPv4" if family == socket.AF_INET else "IPv6"
            print(f"  {family_name}: {ip}")


def cmd_headers(url):
    """Send a HEAD request and print all response headers."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    print(f"Fetching headers from: {url}")
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            print(f"Status:      {resp.status} {resp.reason}")
            print(f"HTTP version: HTTP/{resp.version / 10:.1f}")
            print("-" * 50)
            for key, value in resp.headers.items():
                print(f"{key}: {value}")
    except urllib.error.HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}")
        print("-" * 50)
        for key, value in exc.headers.items():
            print(f"{key}: {value}")
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        print(f"Request failed: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Network diagnostic tools")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("speedtest", help="Measure download bandwidth")

    dns_parser = subparsers.add_parser("dns", help="Resolve a hostname")
    dns_parser.add_argument("host", help="Hostname to resolve")

    headers_parser = subparsers.add_parser("headers", help="Fetch HTTP response headers")
    headers_parser.add_argument("url", help="URL to inspect")

    args = parser.parse_args()

    if args.command == "speedtest":
        cmd_speedtest()
    elif args.command == "dns":
        cmd_dns(args.host)
    elif args.command == "headers":
        cmd_headers(args.url)
    else:
        parser.print_help()
