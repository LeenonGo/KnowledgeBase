"""网页 URL 数据源适配器"""

import hashlib
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class WebAdapter:
    """网页 URL 适配器"""

    def test_connection(self, config: dict) -> dict:
        """测试网页是否可访问"""
        urls = config.get("urls", [])
        if not urls:
            return {"success": False, "message": "URL 列表不能为空"}

        url = urls[0].strip()
        if not url:
            return {"success": False, "message": "URL 不能为空"}

        try:
            import httpx
            resp = httpx.get(url, timeout=10, follow_redirects=True,
                           headers={"User-Agent": "Mozilla/5.0 KG-Bot/1.0"})
            if resp.status_code == 200:
                return {"success": True, "message": f"连接成功 (HTTP {resp.status_code})"}
            else:
                return {"success": False, "message": f"HTTP {resp.status_code}"}
        except ImportError:
            return {"success": False, "message": "缺少 httpx 依赖，请安装: pip install httpx"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)[:200]}"}

    def list_files(self, config: dict) -> list[dict]:
        """抓取网页内容并返回文件列表"""
        urls = config.get("urls", [])
        crawl_mode = config.get("crawl_mode", "single")
        max_depth = config.get("max_depth", 2)
        max_pages = config.get("max_pages", 50)

        if not urls:
            return []

        import httpx
        from bs4 import BeautifulSoup

        files = []
        visited = set()
        client = httpx.Client(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KG-Bot/1.0)"},
        )

        try:
            if crawl_mode == "single":
                for url in urls[:max_pages]:
                    url = url.strip()
                    if not url or url in visited:
                        continue
                    visited.add(url)
                    try:
                        content = self._fetch_page(client, url)
                        if content:
                            files.append(content)
                    except Exception as e:
                        logger.warning(f"[WebAdapter] 抓取失败 {url}: {e}")
            else:
                # 递归爬取
                self._crawl_recursive(client, urls, visited, files,
                                     max_depth, max_pages, 0)
        finally:
            client.close()

        return files

    def _fetch_page(self, client, url: str) -> dict | None:
        """抓取单个网页，提取正文"""
        from bs4 import BeautifulSoup
        resp = client.get(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # 移除非内容元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 提取正文
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)

        if len(text) < 50:  # 内容太少跳过
            return None

        # 生成 hash
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # 生成文件名
        parsed = urlparse(url)
        safe_name = f"{parsed.netloc}{parsed.path}".replace("/", "_").strip("_")
        if not safe_name:
            safe_name = "index"
        filename = f"{safe_name}.txt"

        return {
            "path": filename,
            "name": filename,
            "hash": content_hash,
            "size": len(text.encode("utf-8")),
            "modified_at": "",
            "_url": url,
            "_title": title,
            "_text": text,
        }

    def _crawl_recursive(self, client, urls, visited, files, max_depth, max_pages, depth):
        """递归爬取同域名链接"""
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        if depth > max_depth or len(files) >= max_pages:
            return

        new_urls = []
        for url in urls:
            url = url.strip()
            if not url or url in visited:
                continue
            visited.add(url)
            if len(files) >= max_pages:
                break

            try:
                content = self._fetch_page(client, url)
                if content:
                    files.append(content)

                # 提取同域名链接
                if depth < max_depth:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        base_domain = urlparse(url).netloc
                        for a in soup.find_all("a", href=True):
                            href = urljoin(url, a["href"])
                            parsed = urlparse(href)
                            if (parsed.netloc == base_domain
                                and href not in visited
                                and not href.endswith((".png", ".jpg", ".gif", ".zip", ".pdf"))):
                                new_urls.append(href)
            except Exception as e:
                logger.warning(f"[WebAdapter] 爬取失败 {url}: {e}")

        if new_urls:
            self._crawl_recursive(client, new_urls, visited, files,
                                 max_depth, max_pages, depth + 1)

    def download_file(self, config: dict, file_info: dict, source_id: str = "unknown") -> str:
        """网页适配器的内容已缓存在 file_info 中，写入临时文件返回路径"""
        import tempfile
        text = file_info.get("_text", "")
        if not text:
            raise ValueError("网页内容为空")

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                          encoding="utf-8")
        tmp.write(text)
        tmp.close()
        return tmp.name

    def cleanup(self, source_id: str):
        """网页适配器无需清理"""
        pass

    def get_supported_extensions(self) -> list[str]:
        return [".txt", ".html"]
