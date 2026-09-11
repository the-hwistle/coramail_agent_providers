from __future__ import annotations

import argparse
import json
import os
from uuid import UUID

from app.config import (
    database_url,
    embedding_base_url,
    embedding_model,
    embedding_provider,
    llm_base_url,
    llm_provider,
    qdrant_case_collection,
    qdrant_url,
)
from app.llm.gateway import LocalLLMConfig, LocalLLMGateway
from app.retrieval.qdrant_indexing import ProductionSimilarCaseIndexer, QdrantCaseIndexClient


def _indexer(args: argparse.Namespace) -> ProductionSimilarCaseIndexer:
    db_url = args.database_url.strip() or database_url()
    if not db_url:
        raise RuntimeError("--database-url or CORAMAIL_DATABASE_URL is required")
    gateway = LocalLLMGateway(
        LocalLLMConfig(
            base_url=args.llm_base_url,
            embedding_base_url=embedding_base_url(),
            embedding_model=args.embedding_model,
            provider=llm_provider(),
            embedding_provider=embedding_provider(),
        )
    )
    return ProductionSimilarCaseIndexer(
        database_url=db_url,
        qdrant_client=QdrantCaseIndexClient(base_url=args.qdrant_url, collection=args.collection),
        embedder=gateway.embed,
        embedding_model=args.embedding_model,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex and verify Qdrant similar-case routing corpus.")
    parser.add_argument("--database-url", default=os.getenv("CORAMAIL_DATABASE_URL", ""))
    parser.add_argument("--qdrant-url", default=qdrant_url())
    parser.add_argument("--collection", default=qdrant_case_collection())
    parser.add_argument("--llm-base-url", default=llm_base_url())
    parser.add_argument("--embedding-model", default=embedding_model())
    subparsers = parser.add_subparsers(dest="command", required=True)

    one = subparsers.add_parser("index-email")
    one.add_argument("email_message_id")

    reindex = subparsers.add_parser("reindex-production")
    reindex.add_argument("--provider", default="gmail")
    reindex.add_argument("--email-account-id")
    reindex.add_argument("--limit", type=int)
    reindex.add_argument("--confirmed-only", action="store_true")

    subparsers.add_parser("verify")

    args = parser.parse_args()
    indexer = _indexer(args)
    if args.command == "index-email":
        point = indexer.index_email(UUID(args.email_message_id))
        print(json.dumps({"indexed": bool(point), "point_id": point.point_id if point else None}, ensure_ascii=False))
        return 0
    if args.command == "reindex-production":
        rows = indexer.reindex(
            provider=args.provider,
            email_account_id=UUID(args.email_account_id) if args.email_account_id else None,
            limit=args.limit,
            confirmed_only=args.confirmed_only,
        )
        print(json.dumps({"indexed": len(rows), "collection": args.collection}, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "verify":
        print(json.dumps(indexer.verify_collection(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
