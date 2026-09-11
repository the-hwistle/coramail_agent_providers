from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.evaluation.attachment_loader import SyntheticAttachmentLoader
from app.evaluation.fixtures import SyntheticFixtureGenerator
from app.evaluation.leakage import validate_dataset_leakage, write_leakage_report
from app.evaluation.loader import SyntheticEvaluationLoader
from app.evaluation.metrics import evaluate_predictions, score_predictions, write_evaluation_outputs
from app.evaluation.runner import EndToEndEvaluationRunner
from app.evaluation.synthetic_dataset import SyntheticDatasetConfig, SyntheticEvaluationDatasetGenerator
from app.llm.gateway import LocalLLMConfig, LocalLLMGateway

PROJECT_DIR = Path(__file__).resolve().parents[2]
EVALUATION_DIR = PROJECT_DIR / "data" / "evaluation"
DEFAULT_RUN_DIR = EVALUATION_DIR / "runs" / "current"
DEFAULT_DATASET = EVALUATION_DIR / "synthetic_mail_decision_dataset.json"
DEFAULT_FIXTURES = EVALUATION_DIR / "fixtures"
DEFAULT_PREDICTIONS = DEFAULT_RUN_DIR / "predictions.json"
DEFAULT_REPORT = DEFAULT_RUN_DIR / "latest_report.json"
DEFAULT_EVALUATION_REPORT = DEFAULT_RUN_DIR / "evaluation_report.json"
DEFAULT_EVALUATION_CASES = DEFAULT_RUN_DIR / "evaluation_cases.csv"
DEFAULT_EVALUATION_TRACE = DEFAULT_RUN_DIR / "evaluation_trace.jsonl"
DEFAULT_LEAKAGE_REPORT = DEFAULT_RUN_DIR / "leakage_report.json"


def _gateway() -> LocalLLMGateway:
    return LocalLLMGateway(
        LocalLLMConfig(
            base_url=os.getenv("CORAMAIL_LLM_BASE_URL", "http://127.0.0.1:11434/v1"),
            embedding_model=os.getenv("CORAMAIL_EMBEDDING_MODEL", "nomic-embed-text"),
        )
    )


def _evaluate(dataset: dict, predictions: list[dict], report_path: Path) -> int:
    report = evaluate_predictions(dataset["ground_truth"], predictions)
    report_path.resolve().parent.mkdir(parents=True, exist_ok=True)
    report_path.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def _score(args: argparse.Namespace, dataset: dict, predictions: list[dict]) -> int:
    report, traces = score_predictions(
        dataset,
        predictions,
        dataset_path=args.dataset.resolve(),
        predictions_path=args.predictions.resolve(),
        strict=args.strict,
        prediction_scope=True,
    )
    write_evaluation_outputs(
        report,
        traces,
        report_json=args.report_json.resolve(),
        cases_csv=args.cases_csv.resolve(),
        trace_jsonl=args.trace_jsonl.resolve(),
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.passed or not args.strict else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate, seed, run, and evaluate synthetic Mail Decision data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--output", type=Path, default=DEFAULT_DATASET)
    generate.add_argument("--clean", action="store_true")

    fixtures = subparsers.add_parser("fixtures")
    fixtures.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    fixtures.add_argument("--output-dir", type=Path, default=DEFAULT_FIXTURES)

    seed = subparsers.add_parser("seed")
    seed.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    seed.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES)
    seed.add_argument("--database-url", default=os.getenv("CORAMAIL_DATABASE_URL", ""))
    seed.add_argument("--qdrant-url", default=os.getenv("CORAMAIL_QDRANT_URL", "http://127.0.0.1:6333"))
    seed.add_argument("--collection", default=os.getenv("CORAMAIL_QDRANT_CASE_COLLECTION", "coramail_cases"))

    run = subparsers.add_parser("run")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    run.add_argument("--database-url", default=os.getenv("CORAMAIL_DATABASE_URL", ""))
    run.add_argument("--limit", type=int)
    run.add_argument("--email-id", action="append", default=[])

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    evaluate.add_argument("--predictions", type=Path, required=True)
    evaluate.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    score = subparsers.add_parser("score")
    score.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    score.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    score.add_argument("--report-json", type=Path, default=DEFAULT_EVALUATION_REPORT)
    score.add_argument("--cases-csv", type=Path, default=DEFAULT_EVALUATION_CASES)
    score.add_argument("--trace-jsonl", type=Path, default=DEFAULT_EVALUATION_TRACE)
    score.add_argument("--strict", action="store_true")

    validate = subparsers.add_parser("validate-leakage")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    validate.add_argument("--report-json", type=Path, default=DEFAULT_LEAKAGE_REPORT)
    validate.add_argument("--strict", action="store_true")

    e2e = subparsers.add_parser("e2e")
    e2e.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    e2e.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES)
    e2e.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    e2e.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    e2e.add_argument("--database-url", default=os.getenv("CORAMAIL_DATABASE_URL", ""))
    e2e.add_argument("--qdrant-url", default=os.getenv("CORAMAIL_QDRANT_URL", "http://127.0.0.1:6333"))
    e2e.add_argument("--collection", default=os.getenv("CORAMAIL_QDRANT_CASE_COLLECTION", "coramail_cases"))
    e2e.add_argument("--limit", type=int)
    e2e.add_argument("--email-id", action="append", default=[])

    args = parser.parse_args()
    if args.command == "generate":
        config = None
        if args.clean:
            config = SyntheticDatasetConfig(
                dataset_version="synthetic-mail-decision-v2-clean",
                id_prefix="clean-v2-",
                clean_retrieval_cases=True,
            )
        print(f"generated={SyntheticEvaluationDatasetGenerator(config).write(args.output.resolve())}")
        return 0

    dataset = json.loads(args.dataset.resolve().read_text(encoding="utf-8"))
    if args.command == "validate-leakage":
        report = validate_dataset_leakage(dataset)
        write_leakage_report(report, args.report_json.resolve())
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0 if report.passed or not args.strict else 1
    if args.command == "fixtures":
        result = SyntheticFixtureGenerator(args.output_dir.resolve()).generate(dataset)
        args.dataset.resolve().write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command in {"seed", "e2e"}:
        if not args.database_url.strip():
            parser.error("--database-url or CORAMAIL_DATABASE_URL is required")
        fixture_result = SyntheticFixtureGenerator(args.fixtures_dir.resolve()).generate(dataset)
        args.dataset.resolve().write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
        loader = SyntheticEvaluationLoader(
            database_url=args.database_url,
            qdrant_url=args.qdrant_url,
            collection=args.collection,
            embedder=_gateway().embed,
        )
        counts = loader.load(dataset)
        counts["attachments"] = SyntheticAttachmentLoader(args.database_url).load(dataset)
        counts.update(fixture_result)
        print(json.dumps(counts, ensure_ascii=False, indent=2))
        if args.command == "seed":
            return 0

    if args.command in {"run", "e2e"}:
        if not args.database_url.strip():
            parser.error("--database-url or CORAMAIL_DATABASE_URL is required")
        predictions = EndToEndEvaluationRunner(args.database_url).run(dataset, limit=args.limit, email_ids=args.email_id)
        prediction_path = EndToEndEvaluationRunner.write(predictions, args.predictions.resolve())
        print(f"predictions={prediction_path}")
        if args.command == "run":
            return 0
        return _evaluate(dataset, predictions, args.report)

    predictions = json.loads(args.predictions.resolve().read_text(encoding="utf-8"))
    if args.command == "score":
        return _score(args, dataset, predictions)
    return _evaluate(dataset, predictions, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
