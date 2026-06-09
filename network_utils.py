import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from db import Database

class NetworkError(Exception):
    pass


def check_url(url, timeout=5, retries=2):
    if not url:
        raise NetworkError("URL cannot be empty.")

    last_exception = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return {
                    "ok": True,
                    "status": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "length": response.headers.get("Content-Length", ""),
                }
        except urllib.error.HTTPError as exc:
            if exc.code == 405:  # Method Not Allowed, fallback to GET
                try:
                    return _fallback_get(url, timeout)
                except Exception as fallback_exc:
                    last_exception = fallback_exc
                    continue
            elif 400 <= exc.code < 500:
            
                raise NetworkError(f"HTTP client error: {exc.code} - {exc.reason}") from exc
            else:
                last_exception = exc
        except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
            last_exception = exc
        if attempt < retries:
            time.sleep(1)

    raise NetworkError(f"Network request failed after {retries} retries: {last_exception}")


def _fallback_get(url, timeout):
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read(1024)
        return {
            "ok": True,
            "status": response.status,
            "content_type": response.headers.get("Content-Type", ""),
            "length": response.headers.get("Content-Length", ""),
        }


def download_file(url, target_path, timeout=30, retries=2):
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    last_exception = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                with target.open("wb") as file:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        file.write(chunk)
            return target
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            last_exception = exc
            if attempt < retries:
                time.sleep(2)
    raise NetworkError(f"Download failed after {retries} retries: {last_exception}")

def check_url_and_record(db: Database, user_id: int, name: str, url: str,
                        timeout: int = 5, retries: int = 2) -> dict:
    """
    检测URL可达性，将结果写入 model_resources 表，并记录操作日志。
    返回检测结果字典：{"ok": True/False, "status": ..., "content_type": ..., "length": ...}
    如果检测失败，状态设为"failed"。
    """
    from network_utils import check_url, NetworkError

    result = None
    status = "failed"
    try:
        result = check_url(url, timeout=timeout, retries=retries)
        status = "reachable" if result["ok"] else "failed"
    except NetworkError as e:
        pass 
    db.upsert_model_resource(
        name=name,
        url=url,
        local_path=None,
        status=status
    )
    db.log_operation(
        user_id=user_id,
        action="url_check",
        detail=f"Resource '{name}' URL '{url}' → {status}"
    )

    return {
        "ok": status == "reachable",
        "status": result["status"] if result else None,
        "content_type": result["content_type"] if result else None,
        "length": result["length"] if result else None
    }
