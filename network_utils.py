import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


class NetworkError(Exception):
    pass


class DownloadError(NetworkError):
    pass


def check_url(url, timeout=5):
    """Check whether a remote resource can be reached."""
    if not url:
        raise NetworkError("URL cannot be empty.")

    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "length": response.headers.get("Content-Length", ""),
            }
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            return _fallback_get(url, timeout)
        raise NetworkError(f"HTTP error: {exc.code}") from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise NetworkError(f"Network request failed: {exc}") from exc


def _fallback_get(url, timeout):
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "length": response.headers.get("Content-Length", ""),
            }
    except (urllib.error.URLError, socket.timeout) as exc:
        raise NetworkError(f"Network request failed: {exc}") from exc


def download_file(url, target_path, timeout=30):
    """Download a resource such as a model weight file with exception handling."""
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with target.open("wb") as file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    file.write(chunk)
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise DownloadError(f"Download failed: {exc}") from exc
    return target


def test_connectivity(host="8.8.8.8", port=53, timeout=3):
    """Test basic network reachability via TCP socket connection."""
    try:
        resolved = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ip = resolved[0][4][0]
    except socket.gaierror as exc:
        return {"reachable": False, "latency_ms": None, "resolved_ip": None,
                "error": f"DNS resolution failed: {exc}"}
    try:
        start = time.perf_counter()
        sock = socket.create_connection((host, port), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000
        sock.close()
        return {"reachable": True, "latency_ms": round(latency, 1), "resolved_ip": ip}
    except (socket.timeout, OSError) as exc:
        return {"reachable": False, "latency_ms": None, "resolved_ip": ip,
                "error": str(exc)}


def check_urls_batch(urls, max_workers=5, timeout=5):
    """Check multiple URLs concurrently using a thread pool."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(check_url, url, timeout): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = {"ok": False, "error": str(exc)}
    return results


def download_image_from_url(url, output_dir=None, timeout=30):
    """Download an image from a URL and return the local file path."""
    import tempfile

    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                raise DownloadError(
                    f"URL does not point to an image. Content-Type: {content_type}"
                )
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP error {exc.code} for URL: {url}") from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise DownloadError(f"Failed to download image: {exc}") from exc

    output_dir = Path(output_dir or tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rstrip("/").rsplit("/", 1)[-1] if "/" in url else "downloaded.jpg"
    # Remove query string from filename
    if "?" in filename:
        filename = filename.split("?")[0]
    if "." not in filename.rsplit("/", 1)[-1]:
        filename += ".jpg"
    # Truncate long filenames (Windows MAX_PATH concern)
    if len(filename) > 80:
        stem, ext = filename.rsplit(".", 1) if "." in filename else (filename, "jpg")
        filename = f"{stem[:60]}.{ext}"
    dest = output_dir / filename
    if dest.exists():
        stem, ext = dest.stem, dest.suffix
        suffix = abs(hash(url)) % 100000
        dest = output_dir / f"{stem}_{suffix:05d}{ext}"
    dest.write_bytes(data)
    return dest
