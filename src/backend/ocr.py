"""
多模型 OCR 后端（OpenAI 兼容 / Anthropic）
==========================================
用户流程：
1. 输入 Base URL + API Key → POST /api/ocr/models 获取可用模型
2. 选择模型 → POST /api/ocr/verify 验证模型可用
3. 粘贴图片 → POST /api/ocr/stream 识别（固定 OCR prompt）

端点：
- POST /api/ocr/models  — 列出可用模型
- POST /api/ocr/verify  — 验证模型连接
- POST /api/ocr         — 图片 OCR（非流式）
- POST /api/ocr/stream  — 图片 OCR（SSE 流式）
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models import OCRRequest, OCRVerifyRequest

logger = logging.getLogger("ocr")
router = APIRouter(tags=["ocr"])

# ─── 固定 OCR Prompt ───────────────────────────────────────────

OCR_PROMPT = (
    "你是一个专业的汉字提取器。请严格按以下规则从图片中提取汉字及相关信息：\n"
    "\n"
    "【核心规则】\n"
    "1. 只提取图片中出现的汉字，忽略标点、数字、拼音、英文、国际音标、彝文等非汉字内容。\n"
    "2. 每一项后面跟着的是释义，提取冒号前的内容。后面是例句、例词，首先是彝文，然后是音标，最后是汉字。我们只要汉字的部分，然后用【】括住。\n"
    "3. 一项之后的释义不一定只有一个汉字，比如：“2. 释、译”，那么我们要的部分就是 “释、译”。\n"
    "4. 例句、例词中的内容也可能是很多个字，也许有标点，这些都要保留。比如：“……猜测，猜想……” 那么我们要的结果就是 “【猜测，猜想】。\n"
    "5. 一项后面可能有多个例词、例句，它们用 【】 括住之后，中间不用加标点。比如：“……猜谜……猜拳……” 那么我们要的结果就是 “【猜谜】【猜拳】”。\n"
    "6. 整条输出必须以中文句号（。）结尾。\n"
    "7. 所有内容必须写在一行内，不得换行。\n"
    "8. 如果内容中有括号，括号里面有中文，那么结果中也要包含。比如：“2. （父子）俩……” 那么我们要的结果是 “（父子）俩” 而不是 “父子俩”。\n"
    "\n"
    "【格式模板】\n"
    "释义A【例句1】【例句2】。释义B【例句1】【例句2】。释义C【例句1】。\n"
    "\n"
    "请严格遵守以上规则，直接输出结果，不要添加任何解释或前缀。"
)


# ─── Provider 配置 ─────────────────────────────────────────────

_PROVIDERS = {
    "openai": {
        "chat_path": "/chat/completions",
        "models_path": "/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "extra_headers": {},
        "extra_body": {},
        "image_content": lambda b64: {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
        },
        "parse_response": lambda data: (data.get("choices", [{}])[0].get("message", {}).get("content", "")),
        "parse_stream_delta": lambda data: (data.get("choices", [{}])[0].get("delta", {}).get("content", "")),
        "is_stream_done": lambda data: (data.get("choices", [{}])[0].get("finish_reason") is not None),
    },
    "anthropic": {
        "chat_path": "/messages",
        "models_path": "/models",
        "auth_header": "x-api-key",
        "auth_prefix": "",
        "extra_headers": {"anthropic-version": "2023-06-01"},
        "extra_body": {"thinking": {"type": "disabled"}},
        "image_content": lambda b64: {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        },
        "parse_response": lambda data: next(
            (block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"),
            "",
        ),
        "parse_stream_delta": lambda data: (
            data.get("delta", {}).get("text", "") if data.get("type") == "content_block_delta" else ""
        ),
        "is_stream_done": lambda data: data.get("type") == "message_stop",
    },
}


# ─── 内部 HTTP 客户端 ──────────────────────────────────────────


class _OCRClient:
    def __init__(self, api_key: str, base_url: str, model: str, provider: str):
        if provider not in _PROVIDERS:
            raise ValueError(f"不支持的协议: {provider}")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.cfg = _PROVIDERS[provider]

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            **self.cfg["extra_headers"],
            self.cfg["auth_header"]: f"{self.cfg['auth_prefix']}{self.api_key}",
        }

    def _chat_url(self) -> str:
        return f"{self.base_url}{self.cfg['chat_path']}"

    def _models_url(self) -> str:
        return f"{self.base_url}{self.cfg['models_path']}"

    def _chat_body(self, messages: list, stream: bool, max_tokens: int = 256) -> dict:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": stream,
            **self.cfg["extra_body"],
            "messages": messages,
        }
        # 豆包/火山方舟等 OpenAI 兼容接口：强制关闭思维链
        # https://www.volcengine.com/docs/82379/1302008
        if self.model.lower().startswith(("doubao", "deepseek")):
            body.setdefault("reasoning_effort", "minimal")
        return body

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        status = response.status_code
        try:
            body = response.json()
        except Exception:
            return f"HTTP {status}: {response.text[:300]}"
        # OpenAI 格式
        if isinstance(body.get("error"), dict):
            return body["error"].get("message") or f"HTTP {status}"
        # Anthropic / 通用
        if "message" in body:
            return body["message"]
        return f"HTTP {status}"

    # ── 模型列表 ──────────────────────────────────────────────

    async def list_models(self) -> tuple[list[str], str]:
        """返回 (模型名列表, 提示信息)。\n\n        如果平台不支持 /models，返回空列表并附带提示。\n"""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._models_url(), headers=self._headers())
        except httpx.ConnectError:
            raise Exception(f"无法连接到 {self.base_url}")
        except httpx.TimeoutException:
            raise Exception(f"连接 {self.base_url} 超时")

        if response.status_code in (401, 403):
            raise Exception(f"API Key 无效: {self._error_message(response)}")

        if response.status_code == 404:
            # 平台未实现 /models，允许用户手动填写模型名
            return [], "该平台不支持自动列出模型，请手动输入模型名"

        if response.status_code >= 400:
            raise Exception(f"获取模型列表失败: {self._error_message(response)}")

        data = response.json()
        models = data.get("data", data.get("models", []))
        names = sorted(
            {m.get("id", m.get("name", str(m))) for m in models if isinstance(m, dict)},
            key=str.lower,
        )
        return names, f"已加载 {len(names)} 个模型"

    # ── 验证 ──────────────────────────────────────────────────

    async def verify(self) -> str:
        if not self.model:
            raise Exception("请先选择或输入模型名")

        # 优先通过 /models 确认模型存在；很多平台 chat 端点返回的 404 并不表示模型不存在
        try:
            models, _ = await self.list_models()
        except Exception as e:
            logger.debug("verify: list_models failed: %s", e)
            models = []

        if models and self.model in models:
            return "连接成功"

        # /models 不可用或模型不在列表中：用轻量 chat 请求兜底验证
        messages = [{"role": "user", "content": "hi"}]
        body = self._chat_body(messages, stream=False, max_tokens=1)

        logger.debug("verify: POST %s body=%s", self._chat_url(), body)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self._chat_url(), json=body, headers=self._headers())
        except httpx.ConnectError:
            raise Exception(f"无法连接到 {self.base_url}")
        except httpx.TimeoutException:
            raise Exception(f"连接 {self.base_url} 超时")

        raw_text = response.text[:1000]
        logger.warning("verify: status=%s url=%s body=%s", response.status_code, self._chat_url(), raw_text)
        if response.status_code < 400:
            return "连接成功"

        err = self._error_message(response)
        if response.status_code in (401, 403):
            raise Exception(f"API Key 无效: {err}")
        raise Exception(f"{err} (url: {self._chat_url()}, model: {self.model})")

    # ── 识别 ──────────────────────────────────────────────────

    async def recognize(self, base64_image: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [self.cfg["image_content"](base64_image), {"type": "text", "text": OCR_PROMPT}],
            }
        ]
        body = self._chat_body(messages, stream=False)

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(self._chat_url(), json=body, headers=self._headers())
            if response.status_code >= 400:
                raise Exception(self._error_message(response))
            return self.cfg["parse_response"](response.json())

    async def recognize_stream(self, base64_image: str):
        messages = [
            {
                "role": "user",
                "content": [self.cfg["image_content"](base64_image), {"type": "text", "text": OCR_PROMPT}],
            }
        ]
        body = self._chat_body(messages, stream=True)

        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", self._chat_url(), json=body, headers=self._headers()) as response:
                if response.status_code >= 400:
                    raise Exception(self._error_message(response))

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()

                    if chunk == "[DONE]":
                        yield "[DONE]"
                        continue

                    try:
                        data = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue

                    text = self.cfg["parse_stream_delta"](data)
                    if text:
                        yield text

                    if self.cfg["is_stream_done"](data):
                        yield "[DONE]"


# ─── API 路由 ──────────────────────────────────────────────────


@router.post("/api/ocr/models")
async def api_list_models(req: OCRVerifyRequest):
    """输入 Base URL + API Key，返回可用模型列表。"""
    try:
        client = _OCRClient(req.api_key, req.base_url, req.model, req.provider)
        models, message = await client.list_models()
        return {"models": models, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败: {e}")


@router.post("/api/ocr/verify")
async def api_verify(req: OCRVerifyRequest):
    """选择模型后，验证 Base URL + API Key + Model 是否可用。"""
    try:
        client = _OCRClient(req.api_key, req.base_url, req.model, req.provider)
        message = await client.verify()
        return {"ok": True, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"验证失败: {e}")


@router.post("/api/ocr")
async def api_ocr(req: OCRRequest):
    """单张图片 OCR（非流式）。"""
    try:
        client = _OCRClient(req.api_key, req.base_url, req.model, req.provider)
        text = await client.recognize(req.image)
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OCR 失败: {e}")


@router.post("/api/ocr/stream")
async def api_ocr_stream(req: OCRRequest):
    """单张图片 OCR（SSE 流式）。"""

    async def event_stream():
        try:
            client = _OCRClient(req.api_key, req.base_url, req.model, req.provider)
            async for chunk in client.recognize_stream(req.image):
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
