# data/AGENTS.md

These rules apply to files under `data/`.

## Data Classes

Keep these categories distinct:

1. source synthetic/demo datasets and ground truth;
2. deterministic small fixtures required by tests or demos;
3. intentionally curated evaluation baselines;
4. generated run artifacts such as predictions, traces, leakage reports, temporary exports, and benchmark scratch output;
5. operating/private data.

Categories 1-3 may be tracked when their purpose is documented. Category 4 should normally live under ignored `data/evaluation/runs/`, `generated/`, or `tmp/` paths. Category 5 must not be committed.

## Synthetic Data Requirements

Synthetic datasets must document:

- purpose and target behavior;
- generation method;
- masking/privacy policy;
- expected labels or ground truth;
- important edge cases;
- known differences from operating data.

Do not use synthetic metrics as production performance claims.

## Evaluation Baselines

Promote a generated evaluation run to a tracked baseline only when it is intentionally reviewed. A curated baseline should include compact metadata describing dataset version, workflow/model/prompt version when applicable, expected metrics, and why it is retained.

Avoid committing duplicate copies of large generated files when a deterministic generator plus metadata can reproduce them.

## Binary Fixtures

Keep binary fixtures as small as practical. For large files that are essential and cannot be generated deterministically, document why they must remain tracked and consider Git LFS or an external artifact store.
