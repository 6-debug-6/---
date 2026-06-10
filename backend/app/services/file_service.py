"""
文件上传与格式转换服务

职责：
- 文件存储路径管理（按日期和类型分目录）
- 唯一文件名生成（UUID + 原始名，避免冲突）
- 图片格式转换（WebP → PNG，解决浏览器兼容）

安全约束：
- 图片最大 10MB
- 文档最大 50MB
- 白名单制文件类型校验
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image

from app.core.config import get_settings

settings = get_settings()

# ========== 允许的文件类型白名单 ==========
# 使用 MIME 类型校验，防止恶意文件上传
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOC_TYPES = {
    "application/pdf",
    "application/msword",                                                          # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",     # .docx
    "application/vnd.ms-excel",                                                    # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",          # .xlsx
    "text/csv",
}


def get_upload_dir(subdir: str = "") -> str:
    """
    获取上传目录路径，不存在则自动创建

    按子目录分类存储：
    - images/    → 图片文件
    - documents/ → 文档文件
    - others/    → 其他文件
    """
    path = os.path.join(settings.UPLOAD_DIR, subdir)
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def generate_filename(original_name: str) -> str:
    """
    生成唯一存储文件名

    格式：{日期}/{原始名}_{8位UUID}.{扩展名}
    例如：20250610/故障图_c3f8a2b1.jpg

    使用日期子目录避免单个目录文件过多影响性能。
    8 位 UUID 保证同名文件不会冲突。
    """
    date_str = datetime.now().strftime("%Y%m%d")
    ext = Path(original_name).suffix.lower()  # 统一小写扩展名
    return f"{date_str}/{Path(original_name).stem}_{uuid.uuid4().hex[:8]}{ext}"


def save_upload(file_content: bytes, original_name: str, subdir: str = "files") -> str:
    """
    保存上传文件到磁盘

    参数：
        file_content: 文件二进制内容
        original_name: 原始文件名（用于保留扩展名）
        subdir: 子目录名（images/documents/others）

    返回：相对于 UPLOAD_DIR 的文件路径
    """
    filename = generate_filename(original_name)
    filepath = os.path.join(get_upload_dir(subdir), os.path.basename(filename))
    # 确保日期子目录存在
    dirpath = os.path.dirname(filepath)
    Path(dirpath).mkdir(parents=True, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(file_content)

    return filename


def convert_webp_to_png(filepath: str) -> str:
    """
    将 WebP 格式图片转为 PNG

    原因：部分旧浏览器不支持 WebP 格式，转为 PNG 保证兼容性。
    转换后的 PNG 与原 WebP 同目录存储，文件名替换扩展名。
    已转换过的不重复转换（检查 PNG 文件是否已存在）。
    """
    if not filepath.lower().endswith(".webp"):
        return filepath

    abs_path = os.path.join(settings.UPLOAD_DIR, filepath)
    # 替换扩展名为 .png
    png_path = abs_path.replace(".webp", ".png").replace(".WEBP", ".png")

    # 避免重复转换：如果 PNG 已存在则跳过
    if not os.path.exists(png_path):
        img = Image.open(abs_path)
        img.save(png_path, "PNG")

    return filepath.replace(".webp", ".png").replace(".WEBP", ".png")


def get_content_type_from_extension(filename: str) -> str:
    """
    根据文件扩展名推断 MIME 类型

    用于上传时 content_type 缺失的情况，作为 fallback 判断逻辑。
    未知扩展名返回 application/octet-stream。
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    mapping = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "gif": "image/gif",
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
    }
    return mapping.get(ext, "application/octet-stream")
