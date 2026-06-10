"""
验证码生成模块

提供图形验证码的生成和校验功能。
验证码存储在内存缓存中，5分钟过期。

Date: 2026/5/26
"""
import random
import string
import io
import time
import threading
import warnings
from typing import Optional, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont


class CaptchaManager:
    """
    验证码管理器

    生成图形验证码，存储验证码 key 与答案的映射关系。
    验证码有效期 5 分钟，存储在内存中。
    """

    _cache: Dict[str, dict] = {}
    _lock = threading.Lock()
    _expire_seconds: int = 300  # 5分钟过期

    @classmethod
    def _generate_code(cls, length: int = 4) -> str:
        """
        生成随机验证码字符串

        Args:
            length: 验证码长度，默认4位

        Returns:
            str: 随机字母数字组合
        """
        chars = string.ascii_uppercase + string.digits
        # 排除容易混淆的字符
        chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
        return ''.join(random.choice(chars) for _ in range(length))

    @classmethod
    def _generate_key(cls) -> str:
        """
        生成验证码唯一 key

        Returns:
            str: 随机 key 字符串
        """
        import secrets
        return secrets.token_urlsafe(32)

    @classmethod
    def _generate_image(cls, code: str) -> str:
        """
        生成验证码图片并返回 base64 编码

        Args:
            code: 验证码文本

        Returns:
            str: base64 编码的 PNG 图片
        """
        import base64

        width, height = 120, 40
        image = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 字体候选列表：跨平台兼容（Windows / Linux / macOS）
        font_candidates = [
            "arial.ttf",
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]

        font = None
        for font_name in font_candidates:
            try:
                font = ImageFont.truetype(font_name, 28)
                break
            except (IOError, OSError):
                continue

        if font is None:
            warnings.warn(
                "未找到可用的 TrueType 字体，验证码将使用默认位图字体渲染，"
                "可能导致字符过小。建议在系统中安装 fonts-dejavu-core 或类似字体包。",
                RuntimeWarning,
                stacklevel=2,
            )
            font = ImageFont.load_default()

        # 绘制验证码文字
        for i, char in enumerate(code):
            x = 10 + i * 26
            y = random.randint(2, 8)
            color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
            draw.text((x, y), char, font=font, fill=color)

        # 添加干扰线
        for _ in range(4):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200))
            draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

        # 添加干扰点
        for _ in range(50):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            draw.point((x, y), fill=color)

        # 转为 base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

        return f"data:image/png;base64,{img_base64}"

    @classmethod
    def generate(cls) -> Tuple[str, str]:
        """
        生成验证码

        Returns:
            Tuple[str, str]: (captcha_key, base64 图片)
        """
        code = cls._generate_code()
        key = cls._generate_key()
        image_base64 = cls._generate_image(code)

        # 存储到缓存
        with cls._lock:
            cls._cache[key] = {
                'code': code,
                'created_at': time.time()
            }

        # 清理过期验证码
        cls._cleanup()

        return key, image_base64

    @classmethod
    def verify(cls, captcha_key: str, captcha_code: str) -> bool:
        """
        校验验证码

        Args:
            captcha_key: 验证码 key
            captcha_code: 用户输入的验证码

        Returns:
            bool: 验证通过返回 True，key 不存在或已过期返回 False
        """
        with cls._lock:
            entry = cls._cache.pop(captcha_key, None)

        if not entry:
            return False

        # 检查是否过期
        if time.time() - entry['created_at'] > cls._expire_seconds:
            return False

        # 不区分大小写比较
        return entry['code'].upper() == captcha_code.upper()

    @classmethod
    def _cleanup(cls):
        """
        清理过期的验证码缓存
        """
        now = time.time()
        with cls._lock:
            expired_keys = [
                k for k, v in cls._cache.items()
                if now - v['created_at'] > cls._expire_seconds
            ]
            for k in expired_keys:
                del cls._cache[k]


# 全局验证码管理器实例
captcha_manager = CaptchaManager()
