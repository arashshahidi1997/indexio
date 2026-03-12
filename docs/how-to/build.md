# Build An Index

## Full rebuild

Clears the store and re-indexes all sources:

```bash
indexio build
```

## Partial rebuild (specific sources)

Re-index only selected sources without clearing the rest:

```bash
indexio build --sources docs,notes
```

## Target a specific store

```bash
indexio build --store local
```

## JSON output

```bash
indexio build --json
```

Returns a JSON summary with per-source stats (files, chars, chunks).
