# Register Sources From Other Packages

Ecosystem packages (codio, biblio, notio) register their own sources in a shared indexio config using `sync_owned_sources`.

## Python API

```python
from indexio import sync_owned_sources

result = sync_owned_sources(
    config_path=".indexio/config.yaml",
    root="/path/to/project",
    owned_source_ids=["my-notes", "my-catalog"],
    sources=[
        {"id": "my-notes", "corpus": "notes", "glob": ".myapp/**/*.md"},
        {"id": "my-catalog", "corpus": "catalog", "glob": ".myapp/catalog.yml"},
    ],
)

print(result.added)    # source ids that were new
print(result.updated)  # source ids that changed
print(result.removed)  # source ids no longer provided
```

## How it works

1. The config file is read (or created from the default template if missing).
2. Sources whose `id` is in `owned_source_ids` are replaced with the new `sources` list.
3. Sources not owned by the caller are preserved untouched.
4. The config is written back to disk.

This allows multiple packages to coexist in the same config without overwriting each other's sources.

## Initializing a config that doesn't exist yet

Pass `force_init=True` to always start from the default template:

```python
sync_owned_sources(
    config_path=".indexio/config.yaml",
    root=".",
    owned_source_ids=["my-src"],
    sources=[{"id": "my-src", "corpus": "c", "glob": "*.md"}],
    force_init=True,
)
```
