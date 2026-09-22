from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, TypeVar
from urllib.request import Request, urlopen

import requests
from pydantic import BaseModel, ValidationError


SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = logging.getLogger(__name__)


class LLMGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalLLMConfig:
    base_url: str = "http://127.0.0.1:11434/v1"
    text_base_url: str = ""
    vision_base_url: str = ""
    embedding_base_url: str = ""
    text_model: str = "llama3.2:latest"
    vision_model: str = "qwen3-vl:2b"
    embedding_model: str = "nomic-embed-text:latest"
    timeout_seconds: float = 120.0
    provider: str = "openai"
    text_provider: str = ""
    vision_provider: str = ""
    embedding_provider: str = ""
    text_max_concurrency: int = 4
    vision_max_concurrency: int = 2
    embedding_max_concurrency: int = 8
    max_output_tokens: int = 1024


@dataclass(frozen=True)
class LLMCallMetrics:
    operation: str
    role: str
    provider: str
    model: str
    started_at: datetime
    ended_at: datetime
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: bool = False
    timeout: bool = False
    status_code: int | None = None


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: Any
    name: str = ""
    tool_call_id: str = ""


class LocalLLMGateway:
    """OpenAI-compatible gateway for on-premises text, vision, and embedding models."""

    def __init__(self, config: LocalLLMConfig | None = None):
        self.config = config or LocalLLMConfig()
        self._session = requests.Session()
        self._semaphores = {
            "text": threading.BoundedSemaphore(max(1, self.config.text_max_concurrency)),
            "vision": threading.BoundedSemaphore(max(1, self.config.vision_max_concurrency)),
            "embedding": threading.BoundedSemaphore(max(1, self.config.embedding_max_concurrency)),
        }

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[SchemaT],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> SchemaT:
        return self.generate_structured_chat(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            output_schema=output_schema,
            model=model,
            temperature=temperature,
            role="text",
        )

    def generate_structured_chat(
        self,
        *,
        messages: list[LLMMessage],
        output_schema: type[SchemaT],
        model: str | None = None,
        temperature: float = 0.0,
        role: Literal["text", "vision"] = "text",
    ) -> SchemaT:
        return self._generate_structured_messages(
            model=model or self.config.text_model,
            messages=messages,
            output_schema=output_schema,
            temperature=temperature,
            role=role,
        )

    def generate_structured_vision(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_base64: str,
        image_mime_type: str,
        output_schema: type[SchemaT],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> SchemaT:
        content = [
            {"type": "text", "text": user_prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image_mime_type};base64,{image_base64}"},
            },
        ]
        return self._generate_structured_messages(
            model=model or self.config.vision_model,
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=content),
            ],
            output_schema=output_schema,
            temperature=temperature,
            role="vision",
        )

    def _generate_structured_messages(
        self,
        *,
        model: str,
        messages: list[LLMMessage],
        output_schema: type[SchemaT],
        temperature: float,
        role: str,
    ) -> SchemaT:
        if not any(message.role == "system" for message in messages):
            raise LLMGatewayError("structured LLM call requires a system message")
        if not any(message.role == "user" for message in messages):
            raise LLMGatewayError("structured LLM call requires a user message")
        schema = output_schema.model_json_schema()
        schema_instruction = f"Return only JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False)}"
        provider = self._provider(role)
        request_messages = self._request_messages(messages, schema_instruction=schema_instruction, provider=provider)
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max(1, self.config.max_output_tokens),
            "messages": request_messages,
            "response_format": {"type": "json_object"},
        }
        if provider == "ollama":
            response = self._post_ollama_chat(
                model,
                request_messages,
                temperature,
                output_schema.model_json_schema(),
                role=role,
            )
            raw_content = str(response.get("message", {}).get("content") or "")
            if not raw_content.strip() and response.get("message", {}).get("thinking"):
                raise LLMGatewayError(
                    "Ollama returned thinking text without JSON content; use a non-thinking text model."
                )
            return self._parse_structured_content(raw_content, output_schema)
        if provider == "gemini":
            response = self._post_gemini_generate_content(
                model=model,
                messages=request_messages,
                temperature=temperature,
            )
            raw_content = self._gemini_text(response)
            return self._parse_structured_content(raw_content, output_schema)
        if provider == "vllm":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "schema": schema,
                },
            }
        response = self._post_role("/chat/completions", payload, role=role)
        try:
            raw_content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGatewayError(f"invalid structured LLM response: {exc}") from exc
        return self._parse_structured_content(raw_content, output_schema)

    @staticmethod
    def _request_messages(
        messages: list[LLMMessage],
        *,
        schema_instruction: str,
        provider: str,
    ) -> list[dict[str, Any]]:
        request_messages: list[dict[str, Any]] = []
        for message in messages:
            content = message.content
            role = message.role
            wire_message: dict[str, Any]
            if role == "tool" and not message.tool_call_id:
                # Chat-completions providers reject standalone tool messages unless
                # they follow an assistant tool call. Keep the internal role split
                # while sending a provider-compatible context message.
                tool_name = message.name or "tool_context"
                role = "user"
                content = f"Tool message ({tool_name}):\n{content}"
            wire_message = {"role": role, "content": content}
            if message.name and role != "tool":
                wire_message["name"] = LocalLLMGateway._message_name(message.name)
            if role == "tool":
                wire_message["tool_call_id"] = message.tool_call_id
            request_messages.append(wire_message)
        request_messages.append(
            {
                "role": "user",
                "name": "schema_contract",
                "content": schema_instruction,
            }
        )
        return request_messages

    @staticmethod
    def _message_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value.strip())
        return cleaned[:64] or "message"

    def _post_ollama_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        output_schema: dict[str, Any],
        role: str = "text",
    ) -> dict[str, Any]:
        native_base_url = self._base_url(role).rstrip("/")
        if native_base_url.endswith("/v1"):
            native_base_url = native_base_url[:-3]
        request_messages = list(messages)
        if role == "vision" and len(request_messages) >= 2 and isinstance(request_messages[1].get("content"), list):
            user_message = request_messages[1]
            text_parts: list[str] = []
            images: list[str] = []
            for item in user_message.get("content") or []:
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
                    continue
                if item.get("type") == "image_url":
                    image_url = str(item.get("image_url", {}).get("url") or "")
                    _prefix, separator, data = image_url.partition(",")
                    if separator and data:
                        images.append(data)
                        continue
                raise LLMGatewayError(f"unsupported Ollama vision content: {item!r}")
            user_message = {"role": "user", "content": "\n\n".join(part for part in text_parts if part)}
            if images:
                user_message["images"] = images
            request_messages[1] = user_message
        num_predict = max(1, self.config.max_output_tokens)
        if role == "vision":
            num_predict = max(num_predict, 8192)
        payload = {
            "model": model,
            "messages": request_messages,
            "stream": False,
            "format": output_schema,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if role == "vision":
            payload["think"] = False
        return self._request_json(
            "POST",
            f"{native_base_url}/api/chat",
            payload=payload,
            role=role,
            operation="structured_vision" if role == "vision" else "structured_chat",
            model=model,
        )

    def _post_gemini_generate_content(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> dict[str, Any]:
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        )
        contents = [
            {
                "role": "model" if message.get("role") == "assistant" else "user",
                "parts": self._gemini_parts(message.get("content")),
            }
            for message in messages
            if message.get("role") != "system"
        ]
        payload = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max(1, self.config.max_output_tokens),
                "responseMimeType": "application/json",
            },
        }
        return self._post_gemini(f"/models/{self._gemini_model_name(model)}:generateContent", payload)

    @staticmethod
    def _gemini_model_name(model: str) -> str:
        return model.removeprefix("models/").strip("/")

    @staticmethod
    def _gemini_parts(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"text": content}]
        parts: list[dict[str, Any]] = []
        for item in content:
            if item.get("type") == "text":
                parts.append({"text": str(item.get("text") or "")})
                continue
            if item.get("type") == "image_url":
                image_url = str(item.get("image_url", {}).get("url") or "")
                prefix, separator, data = image_url.partition(",")
                mime_type = prefix.removeprefix("data:").removesuffix(";base64")
                if separator and mime_type and data:
                    parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
                    continue
            raise LLMGatewayError(f"unsupported Gemini message content: {item!r}")
        return parts

    @staticmethod
    def _gemini_text(response: dict[str, Any]) -> str:
        try:
            parts = response["candidates"][0]["content"]["parts"]
            return "".join(str(part.get("text") or "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMGatewayError(f"invalid Gemini structured LLM response: {exc}") from exc

    @staticmethod
    def _parse_structured_content(raw_content: str, output_schema: type[SchemaT]) -> SchemaT:
        try:
            parsed = json.loads(raw_content)
            return output_schema.model_validate(parsed)
        except (TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise LLMGatewayError(f"invalid structured LLM response: {exc}") from exc

    def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        if self._provider("embedding") == "gemini":
            return [self._embed_gemini(text, model=model or self.config.embedding_model) for text in texts]
        response = self._post_role(
            "/embeddings",
            {"model": model or self.config.embedding_model, "input": texts},
            role="embedding",
        )
        try:
            rows = sorted(response["data"], key=lambda row: row["index"])
            return [list(map(float, row["embedding"])) for row in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMGatewayError(f"invalid embedding response: {exc}") from exc

    def healthcheck(self) -> dict[str, Any]:
        if self.config.provider == "gemini":
            return self._get_gemini("/models")
        return self._get("/models")

    def _embed_gemini(self, text: str, *, model: str) -> list[float]:
        model_name = self._gemini_model_name(model)
        response = self._post_gemini(
            f"/models/{model_name}:embedContent",
            {
                "model": f"models/{model_name}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": self._gemini_embedding_dimensions(),
                "embedContentConfig": {"outputDimensionality": self._gemini_embedding_dimensions()},
            },
        )
        try:
            return list(map(float, response["embedding"]["values"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMGatewayError(f"invalid Gemini embedding response: {exc}") from exc

    @staticmethod
    def _gemini_embedding_dimensions() -> int:
        raw_value = os.getenv("CORAMAIL_QDRANT_VECTOR_SIZE", "768").strip()
        try:
            dimensions = int(raw_value)
        except ValueError as exc:
            raise LLMGatewayError(f"invalid CORAMAIL_QDRANT_VECTOR_SIZE for Gemini embeddings: {raw_value}") from exc
        if dimensions <= 0:
            raise LLMGatewayError(f"invalid CORAMAIL_QDRANT_VECTOR_SIZE for Gemini embeddings: {raw_value}")
        return dimensions

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        role = "embedding" if path.rstrip("/").endswith("/embeddings") else "text"
        return self._post_role(path, payload, role=role)

    def _post_role(self, path: str, payload: dict[str, Any], *, role: str) -> dict[str, Any]:
        if type(self)._post is not LocalLLMGateway._post:
            return self._post(path, payload)
        return self._request_json(
            "POST",
            self._url(path, role=role),
            payload=payload,
            role=role,
            operation=self._operation_name(path, role),
            model=str(payload.get("model") or ""),
        )

    def _post_gemini(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self._gemini_url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._gemini_headers(),
            method="POST",
        )
        return self._send(request)

    def _get(self, path: str) -> dict[str, Any]:
        return self._request_json("GET", self._url(path, role="text"), payload=None, role="text", operation="healthcheck")

    def _get_gemini(self, path: str) -> dict[str, Any]:
        return self._send(Request(self._gemini_url(path), headers=self._gemini_headers(), method="GET"))

    @staticmethod
    def _gemini_headers() -> dict[str, str]:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise LLMGatewayError("GEMINI_API_KEY or GOOGLE_API_KEY is required for CORAMAIL_LLM_PROVIDER=gemini")
        return {"Content-Type": "application/json", "x-goog-api-key": api_key}

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise LLMGatewayError(f"LLM request failed: {exc}") from exc

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None,
        role: str,
        operation: str,
        model: str = "",
    ) -> dict[str, Any]:
        semaphore = self._semaphores.get(role, self._semaphores["text"])
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        timeout = False
        status_code: int | None = None
        failed = False
        try:
            with semaphore:
                response = self._session.request(
                    method,
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.config.timeout_seconds,
                )
            status_code = response.status_code
            response.raise_for_status()
            body = response.json()
            self._record_metrics(
                self._metrics(
                    operation=operation,
                    role=role,
                    model=model,
                    started_at=started_at,
                    started=started,
                    status_code=status_code,
                    response=body,
                    payload=payload,
                )
            )
            return body
        except requests.Timeout as exc:
            failed = True
            timeout = True
            raise LLMGatewayError(f"LLM request timeout: {exc}") from exc
        except requests.HTTPError as exc:
            failed = True
            body = exc.response.text if exc.response is not None else ""
            raise LLMGatewayError(f"LLM HTTP {status_code}: {body}") from exc
        except (requests.RequestException, ValueError) as exc:
            failed = True
            raise LLMGatewayError(f"LLM request failed: {exc}") from exc
        finally:
            if failed:
                self._record_metrics(
                    self._metrics(
                        operation=operation,
                        role=role,
                        model=model,
                        started_at=started_at,
                        started=started,
                        status_code=status_code,
                        payload=payload,
                        error=True,
                        timeout=timeout,
                    )
                )

    def _metrics(
        self,
        *,
        operation: str,
        role: str,
        model: str,
        started_at: datetime,
        started: float,
        status_code: int | None,
        payload: dict[str, Any] | None,
        response: dict[str, Any] | None = None,
        error: bool = False,
        timeout: bool = False,
    ) -> LLMCallMetrics:
        usage = response.get("usage") if isinstance(response, dict) else {}
        return LLMCallMetrics(
            operation=operation,
            role=role,
            provider=self._provider(role),
            model=model,
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            input_tokens=self._usage_int(usage, "prompt_tokens") or self._estimate_input_tokens(payload),
            output_tokens=self._usage_int(usage, "completion_tokens"),
            error=error,
            timeout=timeout,
            status_code=status_code,
        )

    @staticmethod
    def _record_metrics(metrics: LLMCallMetrics) -> None:
        logger.info(
            "llm_call operation=%s role=%s provider=%s model=%s latency_ms=%s input_tokens=%s "
            "output_tokens=%s error=%s timeout=%s status_code=%s started_at=%s ended_at=%s",
            metrics.operation,
            metrics.role,
            metrics.provider,
            metrics.model,
            metrics.latency_ms,
            metrics.input_tokens,
            metrics.output_tokens,
            metrics.error,
            metrics.timeout,
            metrics.status_code,
            metrics.started_at.isoformat(),
            metrics.ended_at.isoformat(),
        )

    @staticmethod
    def _usage_int(usage: Any, key: str) -> int | None:
        if not isinstance(usage, dict):
            return None
        value = usage.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _estimate_input_tokens(payload: dict[str, Any] | None) -> int | None:
        if not payload:
            return None
        text = json.dumps(payload, ensure_ascii=False, default=str)
        return max(1, len(text) // 4)

    @staticmethod
    def _operation_name(path: str, role: str) -> str:
        if path.rstrip("/").endswith("/embeddings"):
            return "embedding"
        if role == "vision":
            return "structured_vision"
        return "structured_chat"

    def _provider(self, role: str) -> str:
        if role == "vision" and self.config.vision_provider:
            return self.config.vision_provider.strip().casefold()
        if role == "embedding" and self.config.embedding_provider:
            return self.config.embedding_provider.strip().casefold()
        if role == "text" and self.config.text_provider:
            return self.config.text_provider.strip().casefold()
        return self.config.provider.strip().casefold()

    def _url(self, path: str, *, role: str = "text") -> str:
        return f"{self._base_url(role).rstrip('/')}/{path.lstrip('/')}"

    def _base_url(self, role: str) -> str:
        if role == "vision" and self.config.vision_base_url:
            return self.config.vision_base_url
        if role == "embedding" and self.config.embedding_base_url:
            return self.config.embedding_base_url
        if role == "text" and self.config.text_base_url:
            return self.config.text_base_url
        return self.config.base_url

    def _gemini_url(self, path: str) -> str:
        base_url = self.config.base_url.rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
        if base_url in {"http://127.0.0.1:11434/v1", "http://ollama:11434/v1"}:
            base_url = "https://generativelanguage.googleapis.com/v1beta"
        return f"{base_url}/{path.lstrip('/')}"
