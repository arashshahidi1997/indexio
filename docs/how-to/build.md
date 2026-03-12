# Build An Index

## Full rebuild

Clears the store and re-indexes all sources:

```bash
indexio build --config infra/indexio/config.yaml --root .
```

## Partial rebuild (specific sources)

Re-index only selected sources without clearing the rest:

```bash
indexio build --config infra/indexio/config.yaml --root . --sources docs,notes
```

## Target a specific store

```bash
indexio build --config infra/indexio/config.yaml --root . --store local
```

## JSON output

```bash
indexio build --config infra/indexio/config.yaml --root . --json
```

Returns a JSON summary with per-source stats (files, chars, chunks).
