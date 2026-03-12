import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional, Dict, Any
import json
import asyncio
import threading

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


_playwright = None
_browser = None
_playwright_lock = threading.Lock()
_loop = None


def _get_event_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _get_browser():
    global _playwright, _browser
    if not PLAYWRIGHT_AVAILABLE:
        return None
    if _browser is None:
        with _playwright_lock:
            if _browser is None:
                try:
                    async def _init():
                        p = await async_playwright().start()
                        return await p.chromium.launch(
                            headless=True, 
                            args=[
                                '--disable-blink-features=AutomationControlled', 
                                '--no-sandbox',
                                '--disable-dev-shm-usage',
                                '--disable-gpu',
                                '--window-size=1920,1080',
                            ],
                            ignore_default_args=['--enable-automation'],
                            stealth=True
                        )
                    loop = _get_event_loop()
                    _browser = loop.run_until_complete(_init())
                except Exception:
                    return None
    return _browser


def web_parser(
    url: str,
    extract_type: str = "article",  # article / table / list / full
    max_length: Optional[int] = 8000,  # 防止 token 超限
    include_links: bool = False
) -> Dict[str, Any]:
    """
    解析网页内容，提取结构化文本
    
    Args:
        url: 目标网页 URL，支持带/不带协议
        extract_type: 提取类型 - article(正文)/table(表格)/list(列表)/full(完整)
        max_length: 最大返回字符数，超出则截断
        include_links: 是否包含超链接信息
    
    Returns:
        dict: {
            "success": bool,
            "title": str,
            "content": str,
            "url": str,
            "metadata": dict,
            "error": str (if failed)
        }
    """
    
    url = _normalize_url(url)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    try:
        # 1. 获取网页
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'
        
        # 2. 解析 HTML
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 3. 移除干扰元素
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'advertisement']):
            tag.decompose()
        
        # 4. 提取标题
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        elif soup.find('h1'):
            title = soup.find('h1').get_text(strip=True)
        
        # 5. 按类型提取内容
        content = ""
        
        if extract_type == "article":
            # 智能提取正文（优先找 article 或 main 标签，或最长段落区域）
            article = soup.find('article') or soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
            if article:
                content = _extract_text(article, include_links)
            else:
                # 启发式：找段落最多的 div
                paragraphs = soup.find_all('p')
                if len(paragraphs) > 3:
                    content = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
                else:
                    content = _extract_text(soup.body, include_links) if soup.body else ""
        
        elif extract_type == "table":
            # 提取表格数据为 Markdown 格式
            tables = soup.find_all('table')
            content = _tables_to_markdown(tables)
            
        elif extract_type == "list":
            # 提取列表结构
            lists = soup.find_all(['ul', 'ol'])
            content = _lists_to_text(lists)
            
        else:  # full
            content = _extract_text(soup.body, include_links) if soup.body else ""
        
        # 6. 如果内容为空，尝试使用 Playwright 渲染动态页面
        content = _clean_text(content)
        
        if not content or len(content) < 50:
            browser = _get_browser()
            if browser:
                content = _fetch_with_playwright(url, browser, extract_type, include_links)
                content = _clean_text(content)
        
        if not content or len(content) < 50:
            return {
                "success": False, 
                "title": title,
                "content": "",
                "url": resp.url if 'resp' in locals() else url,
                "metadata": {
                    "original_url": url,
                    "status_code": resp.status_code if 'resp' in locals() else 0,
                    "content_type": resp.headers.get('Content-Type', '') if 'resp' in locals() else '',
                    "extract_type": extract_type,
                    "content_length": 0
                },
                "error": "页面内容为空，可能是动态渲染的 SPA 应用（如 React/Vue/Angular）或需要登录才能访问。"
            }
        
        if max_length and len(content) > max_length:
            content = content[:max_length] + f"\n\n[内容已截断，原长度: {len(content)} 字符]"
        
        # 7. 返回结构化结果
        return {
            "success": True,
            "title": title,
            "content": content,
            "url": resp.url,  # 可能是跳转后的最终 URL
            "metadata": {
                "original_url": url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get('Content-Type', ''),
                "extract_type": extract_type,
                "content_length": len(content)
            }
        }
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "请求超时，请稍后重试", "url": url}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "无法连接到目标网站", "url": url}
    except Exception as e:
        return {"success": False, "error": f"解析失败: {str(e)}", "url": url}


def _extract_text(element, include_links: bool = False) -> str:
    """提取元素中的文本，可选保留链接"""
    if include_links:
        # 将链接转为 [text](url) 格式
        for a in element.find_all('a', href=True):
            href = urljoin(str(a.get('href', '')), '')  # 简化处理
            text = a.get_text(strip=True)
            if text and href:
                a.replace_with(f"[{text}]({href})")
    
    # 获取文本并保留段落结构
    lines = []
    for elem in element.descendants:
        if elem.name in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'br']:
            text = elem.get_text(separator=' ', strip=True)
            if text:
                lines.append(text)
    
    return '\n\n'.join(line for line in lines if line)


def _tables_to_markdown(tables) -> str:
    """将 HTML 表格转为 Markdown 格式"""
    results = []
    for i, table in enumerate(tables, 1):
        rows = []
        for tr in table.find_all('tr'):
            row = []
            for cell in tr.find_all(['td', 'th']):
                text = cell.get_text(strip=True).replace('|', '\\|')
                row.append(text)
            if row:
                rows.append(row)
        
        if rows:
            # 生成 Markdown 表格
            md = [f"### 表格 {i}"]
            md.append('| ' + ' | '.join(rows[0]) + ' |')
            md.append('|' + '|'.join(['---'] * len(rows[0])) + '|')
            for row in rows[1:]:
                md.append('| ' + ' | '.join(row) + ' |')
            results.append('\n'.join(md))
    
    return '\n\n'.join(results) if results else "未找到表格"


def _lists_to_text(lists) -> str:
    """提取列表为文本"""
    results = []
    for i, lst in enumerate(lists, 1):
        items = []
        for li in lst.find_all('li', recursive=False):
            text = li.get_text(strip=True)
            if text:
                items.append(f"- {text}")
        if items:
            results.append('\n'.join(items))
    return '\n\n'.join(results)


def _clean_text(text: str) -> str:
    """清理文本格式"""
    # 合并多余空行
    lines = text.split('\n')
    cleaned = []
    prev_empty = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned.append(stripped)
            prev_empty = False
        elif not prev_empty:
            cleaned.append('')
            prev_empty = True
    return '\n'.join(cleaned).strip()


def _normalize_url(url: str) -> str:
    """规范化 URL，自动补全协议"""
    url = url.strip()
    if not url:
        raise ValueError("URL 不能为空")
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def _fetch_with_playwright(url: str, browser, extract_type: str, include_links: bool) -> str:
    """使用 Playwright 获取动态渲染的页面内容"""
    try:
        async def _fetch():
            page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
            try:
                response = await page.goto(url, wait_until='load', timeout=30000)
                if response and response.status >= 400:
                    return ""
                await page.wait_for_timeout(5000)
                final_url = page.url
                if 'sign_in' in final_url or 'login' in final_url or '/auth/' in final_url:
                    return ""
                content = await page.content()
                return content
            finally:
                await page.close()
        
        loop = _get_event_loop()
        html_content = loop.run_until_complete(_fetch())
        
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'advertisement']):
            tag.decompose()
        
        if extract_type == "article":
            article = soup.find('article') or soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
            if article:
                return _extract_text(article, include_links)
            paragraphs = soup.find_all('p')
            if len(paragraphs) > 3:
                return '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
            return _extract_text(soup.body, include_links) if soup.body else ""
        elif extract_type == "table":
            tables = soup.find_all('table')
            return _tables_to_markdown(tables)
        elif extract_type == "list":
            lists = soup.find_all(['ul', 'ol'])
            return _lists_to_text(lists)
        else:
            return _extract_text(soup.body, include_links) if soup.body else ""
            
    except Exception as e:
        return ""


# ========== 给大模型的 Tool Schema ==========

WEB_PARSER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_parser",
        "description": "解析网页内容，提取结构化文本、表格或列表。适用于获取新闻、文章、文档等网页信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要解析的网页 URL，支持带/不带协议（如 https://example.com 或 example.com）"
                },
                "extract_type": {
                    "type": "string",
                    "enum": ["article", "table", "list", "full"],
                    "description": "提取类型：article(智能提取正文)、table(提取表格)、list(提取列表)、full(完整页面)",
                    "default": "article"
                },
                "max_length": {
                    "type": "integer",
                    "description": "返回内容的最大字符数，防止超出模型上下文限制，建议 4000-8000",
                    "default": 8000
                },
                "include_links": {
                    "type": "boolean",
                    "description": "是否在正文中保留超链接（转为Markdown格式）",
                    "default": False
                }
            },
            "required": ["url"]
        }
    }
}


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 测试
    result = web_parser(
       url="https://langchain-doc.cn/v1/python/langchain/agents.html",
        max_length=4000
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))