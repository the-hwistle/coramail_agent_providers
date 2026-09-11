from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from pydantic import BaseModel, Field

from app.llm.gateway import LLMGatewayError, LocalLLMConfig, LocalLLMGateway
from app.schemas.mail_decision import MailFacts


class BenchmarkDecision(BaseModel):
    one_line_summary: str = Field(min_length=1)
    primary_type: str = Field(min_length=1)
    urgency: str = Field(pattern="^(high|normal)$")
    review_required: bool = False
    reasons: list[str] = Field(default_factory=list)


class BenchmarkChatAnswer(BaseModel):
    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


def _fact_prompt(index: int) -> str:
    return json.dumps(
        {
            "mail": {
                "sender_name": "Synthetic Customer",
                "sender_address": f"buyer{index}@example.test",
                "subject": f"RFQ QT-2026-{index:04d} delivery confirmation",
                "body_text": (
                    "Customer requests quotation and delivery confirmation for marine valve assembly. "
                    f"Reference QT-2026-{index:04d}. Please reply by 2026-09-10."
                ),
            },
            "attachments": [
                {
                    "filename": "synthetic_quote.pdf",
                    "document_type": "rfq",
                    "extracted_text": "Item: valve assembly\nQuantity: 12\nRequested delivery: 2026-09-10",
                }
            ],
        },
        ensure_ascii=False,
    )


def _decision_prompt(index: int) -> str:
    return json.dumps(
        {
            "email": {
                "subject": f"PO-2026-{index:04d} 납기 확인 요청",
                "body_text": "선박 정비 일정 전까지 밸브 부품 납기 가능 여부를 확인해 달라는 요청입니다.",
            },
            "facts": {
                "request_types": ["delivery_confirmation"],
                "po_numbers": [f"PO-2026-{index:04d}"],
                "requested_actions": ["납기 가능 여부 확인 후 회신"],
                "requested_dates": ["2026-09-10"],
                "urgency_signals": ["2026-09-10까지 회신 요청"],
            },
            "retrieved_context": [
                {
                    "title": "routing rule",
                    "content": "delivery_confirmation for valve assembly is handled by sales operations.",
                }
            ],
        },
        ensure_ascii=False,
    )


def _chat_prompt(index: int) -> str:
    return json.dumps(
        {
            "question": f"PO-2026-{index:04d} 납기와 요청사항을 알려줘",
            "evidence": [
                {
                    "id": "E1",
                    "content": "PO requests delivery confirmation for valve assembly by 2026-09-10.",
                }
            ],
        },
        ensure_ascii=False,
    )


def _run_structured(
    gateway: LocalLLMGateway,
    *,
    workload: str,
    index: int,
    chat_model: str,
) -> None:
    if workload == "fact_extraction":
        gateway.generate_structured(
            system_prompt="Extract only grounded business mail facts. Return valid JSON.",
            user_prompt=_fact_prompt(index),
            output_schema=MailFacts,
            temperature=0.0,
        )
        return
    if workload == "decision":
        gateway.generate_structured(
            system_prompt="Create a concise Korean operational decision summary from supplied facts only.",
            user_prompt=_decision_prompt(index),
            output_schema=BenchmarkDecision,
            temperature=0.0,
        )
        return
    if workload == "mixed_chat":
        gateway.generate_structured(
            system_prompt="Answer from supplied evidence only. Return valid JSON.",
            user_prompt=_chat_prompt(index),
            output_schema=BenchmarkChatAnswer,
            model=chat_model,
            temperature=0.0,
        )
        return
    raise ValueError(f"unsupported workload: {workload}")


def _sample(
    runner: Callable[[int], None],
    *,
    request_count: int,
    concurrency: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    errors = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for index in range(request_count):
            futures.append(executor.submit(_timed_runner, runner, index))
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception:
                errors += 1
    elapsed = max(time.perf_counter() - started, 0.001)
    sorted_latencies = sorted(latencies)
    success_count = max(0, request_count - errors)
    return {
        "requests": request_count,
        "concurrency": concurrency,
        "avg_latency_ms": round(statistics.fmean(sorted_latencies), 2) if sorted_latencies else None,
        "p50_latency_ms": round(_percentile(sorted_latencies, 50), 2) if sorted_latencies else None,
        "p95_latency_ms": round(_percentile(sorted_latencies, 95), 2) if sorted_latencies else None,
        "throughput_rps": round(success_count / elapsed, 4),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 3),
    }


def _timed_runner(runner: Callable[[int], None], index: int) -> float:
    started = time.perf_counter()
    runner(index)
    return (time.perf_counter() - started) * 1000


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * (percentile / 100)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    weight = rank - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CoRA Mail LLM providers with structured workloads.")
    parser.add_argument("--engine", default="", help="Label used in the output table, for example ollama or vllm.")
    parser.add_argument("--provider", required=True, choices=["ollama", "vllm", "openai", "gemini"])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--text-model", required=True)
    parser.add_argument("--chat-text-model", default="")
    parser.add_argument("--vision-model", default="")
    parser.add_argument("--embedding-model", default="")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--requests-per-concurrency", type=int, default=10)
    parser.add_argument("--workload", choices=["fact_extraction", "decision", "mixed_chat"], default="fact_extraction")
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/llm_benchmark_latest.json"))
    args = parser.parse_args()

    gateway = LocalLLMGateway(
        LocalLLMConfig(
            base_url=args.base_url,
            text_model=args.text_model,
            vision_model=args.vision_model or args.text_model,
            embedding_model=args.embedding_model or args.text_model,
            timeout_seconds=args.timeout_seconds,
            provider=args.provider,
            text_provider=args.provider,
            vision_provider=args.provider,
            embedding_provider=args.provider,
            text_max_concurrency=max(args.concurrency),
            max_output_tokens=args.max_output_tokens,
        )
    )
    chat_model = args.chat_text_model.strip() or args.text_model
    rows = []
    for concurrency in args.concurrency:
        request_count = max(concurrency, args.requests_per_concurrency)
        result = _sample(
            lambda index: _run_structured(
                gateway,
                workload=args.workload,
                index=index,
                chat_model=chat_model,
            ),
            request_count=request_count,
            concurrency=concurrency,
        )
        rows.append(
            {
                "engine": args.engine or args.provider,
                "provider": args.provider,
                "base_url": args.base_url,
                "model": args.text_model,
                "workload": args.workload,
                **result,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"results": rows}, ensure_ascii=False, indent=2))
    return 1 if any(row["errors"] for row in rows) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LLMGatewayError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from exc
