# Large file policy

## Current audit

A full-history audit was run on 2026-09-01 using `git ls-files`, `git rev-list --objects --all`, and `git cat-file --batch-check`.

- Largest currently tracked file: `data/demo/attachments/Quotation_QT-2026-0812-03.pdf` — 16,694,128 bytes (about 15.9 MiB).
- Largest historical blob: the same file at 16,694,128 bytes.
- Other historical PDF blobs observed in the audit were about 13.8 MB, 13.8 MB, 2.6 MB, and 1.9 MB.
- No tracked or historical blob in the audit approached GitHub's 100 MB hard file-size limit.

The repository currently marks `*.pdf` as binary in `.gitattributes`; it does not use Git LFS.

## Policy

1. Keep ordinary source, test, fixture, and documentation files in normal Git.
2. Before adding a binary file above 25 MiB, decide whether it belongs in the repository at all. Prefer generated fixtures, external object storage, or release artifacts when the file is reproducible or operational data.
3. Before adding a binary file above 50 MiB, require an explicit repository-maintenance review. Git LFS is the preferred mechanism when the binary must remain versioned with the repository.
4. Do not add files at or above GitHub's 100 MB per-file limit to normal Git.
5. If Git LFS is introduced, add LFS tracking rules before committing the new large binary so the first committed version is an LFS pointer.

## Existing history

No history rewrite was performed as part of this audit. Converting already-committed blobs to Git LFS with commands such as `git lfs migrate import` rewrites commit history and changes object IDs. That operation must be treated as a separate destructive migration with explicit approval, clone/fork coordination, a force-push plan, and rollback instructions.

At the current measured sizes, a history rewrite is not justified solely for repository size reduction.

## Repeatable audit

Use the following commands from a full clone (`git fetch --all --tags` first):

```bash
while IFS= read -r -d '' path; do
  if [ -f "$path" ]; then
    printf '%12d  %s\n' "$(wc -c < "$path")" "$path"
  fi
done < <(git ls-files -z) | sort -nr | sed -n '1,40p'

git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1 == "blob" { printf "%12d  %s\n", $3, $4 }' \
  | sort -nr \
  | sed -n '1,40p'
```
