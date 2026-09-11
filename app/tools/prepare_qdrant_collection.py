from __future__ import annotations

import argparse
import os

from app.config import qdrant_case_collection, qdrant_url
from app.retrieval.qdrant_indexing import QdrantCaseIndexClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure the CoRA Mail Qdrant similar-case collection exists.")
    parser.add_argument("--qdrant-url", default=qdrant_url())
    parser.add_argument("--collection", default=qdrant_case_collection())
    parser.add_argument("--vector-size", type=int, default=int(os.getenv("CORAMAIL_QDRANT_VECTOR_SIZE", "768")))
    args = parser.parse_args()

    if args.vector_size <= 0:
        parser.error("--vector-size must be greater than zero")

    QdrantCaseIndexClient(base_url=args.qdrant_url, collection=args.collection).ensure_collection(args.vector_size)
    print(f"qdrant_collection={args.collection} status=ready vector_size={args.vector_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
