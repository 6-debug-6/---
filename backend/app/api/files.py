"""
文件上传 API

端点：
    POST /api/v1/upload — 上传文件（图片/文档/附件）

安全措施：
    - 需要登录（get_current_user 依赖）
    - MIME 类型白名单校验
    - 文件大小限制（图片 ≤10MB, 文档 ≤50MB）
    - WebP 图像自动转为 PNG 以保证浏览器兼容
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.file_service import (
    ALLOWED_IMAGE_TYPES, ALLOWED_DOC_TYPES,
    save_upload, convert_webp_to_png,
)
from app.core.config import get_settings

settings = get_settings()
router = APIRouter()

# 文件大小限制（字节）
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB — 图片
MAX_DOC_SIZE = 50 * 1024 * 1024     # 50MB — 文档和附件


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    上传文件

    流程：
    1. 校验文件名不为空
    2. 读取文件二进制内容
    3. 根据 MIME 类型或扩展名判断文件类别（图片/文档/其他）
    4. 校验文件大小在对应类别限制内
    5. 保存到磁盘（按日期分子目录存储）
    6. 如果是 WebP 图片，自动转为 PNG
    7. 返回文件访问 URL

    返回：
        {url, filename, size, content_type}
        url: /uploads/images/20250610/故障图_c3f8a2b1.png（前端可直接访问）
    """
    # Step 1: 文件名检查
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名不能为空")

    # Step 2: 读取文件内容
    content_type = file.content_type or "application/octet-stream"
    content = await file.read()

    # Step 3-4: 文件类型识别 + 大小校验
    # MIME 类型优先，MIME 未知时通过扩展名 fallback 判断
    if content_type in ALLOWED_IMAGE_TYPES:
        if len(content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="图片大小不能超过 10MB"
            )
        subdir = "images"
    elif content_type in ALLOWED_DOC_TYPES:
        if len(content) > MAX_DOC_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件大小不能超过 50MB"
            )
        subdir = "documents"
    else:
        # Fallback: 通过文件扩展名判断
        ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
        if ext in ("jpg", "jpeg", "png", "webp", "gif"):
            subdir = "images"
            if len(content) > MAX_IMAGE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="图片大小不能超过 10MB"
                )
        else:
            subdir = "others"
            if len(content) > MAX_DOC_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="文件大小不能超过 50MB"
                )

    # Step 5: 保存文件到磁盘
    filepath = save_upload(content, file.filename, subdir)

    # Step 6: WebP 格式转换（浏览器兼容性处理）
    if file.filename.lower().endswith(".webp"):
        filepath = convert_webp_to_png(filepath)

    # Step 7: 返回访问信息
    return {
        "url": f"/uploads/{filepath}",   # 前端拼接 base URL 即可访问
        "filename": file.filename,       # 原始文件名（展示用）
        "size": len(content),            # 文件大小（字节）
        "content_type": content_type,    # MIME 类型
    }
