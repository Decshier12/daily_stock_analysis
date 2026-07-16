# -*- coding: utf-8 -*-
"""Bark notification sender.

Bark is a self-hostable iOS push service. The official public server is
``https://api.day.app``, but you can run your own ``bark-server`` on a LAN /
VPS so notifications never leave your network (works even without external
internet, as long as the analysis machine can reach the Bark server).

This sender uses Bark's JSON ``/push`` endpoint:

    POST {BARK_URL}/push
    {
      "device_key": "<key>",
      "title": "...",
      "body": "...",
      "level": "active",
      "sound": "alarm",
      "group": "daily_stock_analysis"
    }

Two configuration styles are supported for ``BARK_URL``:

1. Server root only (recommended):
       BARK_URL=https://api.day.app
       BARK_DEVICE_KEY=<key>
2. Full subscription URL (App shows this directly; key is auto-extracted):
       BARK_URL=https://api.day.app/<key>
   In this case ``BARK_DEVICE_KEY`` may be left empty.

Long content (e.g. full analysis reports) is automatically split into multiple
push notifications when it exceeds ``BARK_MAX_BODY_BYTES`` (default 4000, a safe
margin under the official server's per-message nginx limit which is below ~5KB).
Self-hosted servers with a higher limit can raise this via ``BARK_MAX_BODY_BYTES``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests

from src.config import Config


logger = logging.getLogger(__name__)

# Official api.day.app sits behind nginx with a small per-message body limit
# (~8KB). Chunk below that to stay safe; self-hosted servers can raise this.
BARK_MAX_BODY_BYTES = int(os.getenv("BARK_MAX_BODY_BYTES", "4000") or "4000")


def _split_into_byte_chunks(text: str, max_bytes: int) -> List[str]:
    """Split text into chunks whose UTF-8 byte length stays under ``max_bytes``.

    Prefers splitting on line boundaries; falls back to character splitting for
    lines longer than the limit.
    """
    if max_bytes <= 0:
        max_bytes = 1
    chunks: List[str] = []
    current: List[str] = []
    current_bytes = 0

    def flush() -> None:
        nonlocal current, current_bytes
        if current:
            chunks.append("\n".join(current))
            current.clear()
            current_bytes = 0

    for line in text.split("\n"):
        line_bytes = len(line.encode("utf-8"))
        if current and current_bytes + line_bytes + 1 > max_bytes:
            flush()
        if line_bytes > max_bytes:
            # Hard-split a single over-long line by characters.
            buf = ""
            buf_bytes = 0
            for ch in line:
                ch_bytes = len(ch.encode("utf-8"))
                if buf and buf_bytes + ch_bytes > max_bytes:
                    chunks.append(buf)
                    buf = ""
                    buf_bytes = 0
                buf += ch
                buf_bytes += ch_bytes
            if buf:
                chunks.append(buf)
            continue
        current.append(line)
        current_bytes += line_bytes + 1
    flush()
    return chunks


def resolve_bark_target(
    bark_url: Optional[str], bark_device_key: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve Bark endpoint and device key from possibly-merged config.

    Returns ``(endpoint, device_key)``. The device key may come from the
    explicit ``bark_device_key`` argument, or be extracted from a single path
    segment in ``bark_url`` (the App's subscription URL form).
    """
    raw = (bark_url or "").strip().rstrip("/")
    device_key = (bark_device_key or "").strip()
    if not raw:
        return None, device_key

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None, device_key

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    # Drop a trailing /push segment if present.
    if path_segments and path_segments[-1].lower() == "push":
        path_segments = path_segments[:-1]
    # A lone path segment with no explicit key means it is the device key
    # embedded in the subscription URL (e.g. https://api.day.app/<key>).
    if not device_key and len(path_segments) == 1:
        device_key = path_segments[0]
        path_segments = []

    base_path = "/" + "/".join(path_segments) if path_segments else ""
    server_root = urlunparse(
        parsed._replace(path=base_path, params="", query="", fragment="")
    ).rstrip("/")
    return f"{server_root}/push", device_key


def resolve_bark_push_endpoint(bark_url: Optional[str]) -> Optional[str]:
    """Backwards-compatible helper: resolve only the endpoint (ignores key)."""
    endpoint, _ = resolve_bark_target(bark_url, None)
    return endpoint


class BarkSender:
    """Send text notifications through Bark's /push JSON API."""

    def __init__(self, config: Config):
        self._bark_url = getattr(config, "bark_url", None)
        self._bark_device_key = getattr(config, "bark_device_key", None)
        self._bark_sound = getattr(config, "bark_sound", None)
        self._bark_level = getattr(config, "bark_level", None)
        self._bark_group = getattr(config, "bark_group", None)
        self._webhook_verify_ssl = getattr(config, "webhook_verify_ssl", True)

    def _resolve_bark_target(self) -> Tuple[Optional[str], Optional[str]]:
        return resolve_bark_target(self._bark_url, self._bark_device_key)

    def _is_bark_configured(self) -> bool:
        endpoint, device_key = self._resolve_bark_target()
        return bool(endpoint) and bool(device_key)

    def _post_one(
        self,
        endpoint: str,
        device_key: str,
        content: str,
        title: str,
        timeout_seconds: Optional[float],
    ) -> bool:
        payload: dict = {
            "device_key": device_key,
            "title": title,
            "body": content,
        }
        level = (self._bark_level or "").strip()
        if level:
            payload["level"] = level
        sound = (self._bark_sound or "").strip()
        if sound:
            payload["sound"] = sound
        group = (self._bark_group or "").strip()
        if group:
            payload["group"] = group

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "daily_stock_analysis",
        }
        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout_seconds or 10,
                verify=self._webhook_verify_ssl,
            )
            if 200 <= response.status_code < 300:
                return True
            logger.error("Bark 请求失败: HTTP %s", response.status_code)
            logger.debug("Bark 响应内容: %s", response.text)
            return False
        except requests.exceptions.Timeout:
            logger.error("发送 Bark 消息失败: 请求超时")
            return False
        except requests.exceptions.RequestException as exc:
            logger.error("发送 Bark 消息失败: 网络请求异常")
            logger.debug("Bark 请求异常类型: %s", type(exc).__name__)
            return False
        except Exception as exc:
            logger.error("发送 Bark 消息失败: 未知异常")
            logger.debug("Bark 未知异常类型: %s", type(exc).__name__)
            return False

    def send_to_bark(
        self,
        content: str,
        title: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> bool:
        """Publish a notification to Bark, auto-splitting over-long content."""
        endpoint, device_key = self._resolve_bark_target()
        if not endpoint or not device_key:
            logger.warning("Bark 配置不完整（需要 BARK_URL，或 BARK_URL+BARK_DEVICE_KEY），跳过推送")
            return False

        if not content or not content.strip():
            logger.warning("Bark 推送内容为空，跳过")
            return False

        if title is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            title = f"📈 股票分析报告 - {date_str}"

        total_bytes = len(content.encode("utf-8"))
        if total_bytes <= BARK_MAX_BODY_BYTES:
            ok = self._post_one(endpoint, device_key, content, title, timeout_seconds)
            if ok:
                logger.info("Bark 消息发送成功")
            return ok

        # Auto-split into multiple pushes.
        chunks = _split_into_byte_chunks(content, BARK_MAX_BODY_BYTES)
        n = len(chunks)
        logger.info("Bark 内容 %d 字节超过单条上限，拆分为 %d 条推送", total_bytes, n)
        all_ok = True
        for i, chunk in enumerate(chunks, start=1):
            part_title = f"{title} ({i}/{n})"
            if not self._post_one(endpoint, device_key, chunk, part_title, timeout_seconds):
                all_ok = False
        if all_ok:
            logger.info("Bark 分片消息全部发送成功")
        else:
            logger.error("Bark 分片消息存在发送失败")
        return all_ok
