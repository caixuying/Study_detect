
import hashlib
import threading
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


class CrawlerError(Exception):
    pass


class ImageCrawler:
    def __init__(self, download_dir, detector, db, user_id, debug=False):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.detector = detector
        self.db = db
        self.user_id = user_id
        self.debug = debug
        self._ensure_packages()

    def _ensure_packages(self):
        if requests is None or BeautifulSoup is None:
            raise CrawlerError("请安装 requests 和 beautifulsoup4：pip install requests beautifulsoup4")

    def crawl_page(self, page_url, max_images=30):
        try:
            session = requests.Session()
            session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
            
            resp = session.get(page_url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            img_urls = set()
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    full_url = urljoin(page_url, src)
                    img_urls.add(full_url)
                for attr in ['data-src', 'data-original', 'data-lazy-src', 'data-srcset']:
                    val = img.get(attr)
                    if val:
                        full_url = urljoin(page_url, val.split(',')[0].strip().split(' ')[0])
                        img_urls.add(full_url)

            valid_urls = []
            for url in img_urls:
                lower_url = url.lower()
                if any(ext in lower_url for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']):
                    valid_urls.append(url)
                elif 'image' in lower_url or 'photo' in lower_url:
                    valid_urls.append(url)

            if self.debug:
                print(f"[Debug] 找到 {len(img_urls)} 个候选URL，过滤后 {len(valid_urls)} 个图片URL")
                for i, u in enumerate(valid_urls[:5]):
                    print(f"  {i+1}: {u}")

            if not valid_urls:
                return 0, "页面中未找到图片URL（可能使用了动态加载）"

            downloaded = 0
            for img_url in valid_urls[:max_images]:
                try:
                    saved_path = self._download_image(img_url)
                    if saved_path:
                        downloaded += 1
                        self._detect_and_record(saved_path, img_url, page_url)
                except Exception as e:
                    err_msg = f"下载失败 {img_url}: {str(e)}"
                    if self.debug:
                        print(err_msg)
                    self.db.log_operation(self.user_id, "crawl_download_failed", err_msg)
                    continue

            return downloaded, None

        except requests.RequestException as e:
            return 0, f"网络请求失败: {str(e)}"
        except Exception as e:
            return 0, f"爬取异常: {str(e)}"

    def _download_image(self, img_url):
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        try:
            resp = session.get(img_url, timeout=15, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', '')
            ext = '.jpg'
            if 'png' in content_type:
                ext = '.png'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'bmp' in content_type:
                ext = '.bmp'
            else:
                path_ext = Path(img_url).suffix.lower()
                if path_ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                    ext = path_ext
            name = hashlib.md5(img_url.encode()).hexdigest() + ext
            save_path = self.download_dir / name
            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return save_path
        except Exception as e:
            raise Exception(f"下载失败: {str(e)}")

    def _detect_and_record(self, image_path, img_url, page_url):
        try:
            output_path, events, summary = self.detector.predict_image(str(image_path))
            alerts = summary.get("alert_labels", [])
            self.db.record_detection(
                self.user_id,
                f"crawl:{page_url} -> {img_url}",
                summary,
                alerts,
                output_path=output_path
            )
            self.db.log_operation(
                self.user_id,
                "crawl_detected",
                f"图片: {image_path.name} 告警: {alerts}"
            )
        except Exception as e:
            self.db.log_operation(self.user_id, "crawl_detect_error", str(e))
            raise


def run_crawl_task(page_url, max_images, download_dir, detector, db, user_id, callback, debug=False):
    try:
        crawler = ImageCrawler(download_dir, detector, db, user_id, debug=debug)
        count, error = crawler.crawl_page(page_url, max_images)
        if callback:
            callback(count, error)
    except Exception as e:
        if callback:
            callback(0, str(e))
