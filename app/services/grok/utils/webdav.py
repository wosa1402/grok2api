"""
WebDAV 备份上传工具

将本地缓存文件异步上传到 WebDAV 服务器做备份。
本地 URL 不变，纯后台复制。
"""

import asyncio
from pathlib import Path
from typing import Optional

import aiohttp

from app.core.config import get_config
from app.core.logger import logger


class WebDAVUploader:
    """异步 WebDAV 上传器（单例）"""

    _instance: Optional["WebDAVUploader"] = None
    _session: Optional[aiohttp.ClientSession] = None

    @classmethod
    def get_instance(cls) -> "WebDAVUploader":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _is_enabled(self) -> bool:
        return bool(get_config("webdav.enabled", False))

    def _get_url(self) -> str:
        return str(get_config("webdav.url", "")).rstrip("/")

    def _get_auth(self) -> Optional[aiohttp.BasicAuth]:
        username = get_config("webdav.username", "")
        password = get_config("webdav.password", "")
        if username:
            return aiohttp.BasicAuth(username, password)
        return None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _ensure_directory(
        self,
        session: aiohttp.ClientSession,
        dir_path: str,
        auth: Optional[aiohttp.BasicAuth],
    ) -> None:
        """通过 MKCOL 确保远程目录存在，已存在时静默忽略。"""
        base_url = self._get_url()
        url = f"{base_url}/{dir_path}/"
        try:
            async with session.request("MKCOL", url, auth=auth) as resp:
                if resp.status not in (200, 201, 301, 405, 409):
                    logger.warning(f"WebDAV MKCOL {dir_path} returned {resp.status}")
        except Exception as e:
            logger.warning(f"WebDAV MKCOL {dir_path} failed: {e}")

    async def upload(self, filepath: Path, media_type: str) -> None:
        """上传单个文件到 WebDAV。

        Args:
            filepath: 本地文件绝对路径（已写入磁盘）。
            media_type: "image" 或 "video"，作为远程目录名。
        """
        if not self._is_enabled():
            return

        base_url = self._get_url()
        if not base_url:
            return

        try:
            session = await self._ensure_session()
            auth = self._get_auth()

            await self._ensure_directory(session, media_type, auth)

            remote_url = f"{base_url}/{media_type}/{filepath.name}"
            data = await asyncio.to_thread(filepath.read_bytes)

            async with session.put(remote_url, data=data, auth=auth) as resp:
                if resp.status in (200, 201, 204):
                    logger.debug(f"WebDAV upload OK: {media_type}/{filepath.name}")
                else:
                    body = await resp.text()
                    logger.warning(
                        f"WebDAV upload failed ({resp.status}): "
                        f"{media_type}/{filepath.name} - {body[:200]}"
                    )
        except Exception as e:
            logger.warning(f"WebDAV upload error: {media_type}/{filepath.name} - {e}")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None


def webdav_backup(filepath: Path, media_type: str) -> None:
    """Fire-and-forget WebDAV 备份。可在任何异步上下文中安全调用。"""
    uploader = WebDAVUploader.get_instance()
    if not uploader._is_enabled():
        return
    asyncio.create_task(
        uploader.upload(filepath, media_type),
        name=f"webdav-upload-{media_type}-{filepath.name}",
    )
