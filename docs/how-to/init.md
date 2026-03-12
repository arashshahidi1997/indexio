# Initialize A Config

## Write the default config

```bash
indexio init-config --root /path/to/project
```

This creates `infra/indexio/config.yaml` with sensible defaults.

## Custom output path

```bash
indexio init-config --root . --output config/indexio.yaml
```

## Overwrite an existing config

```bash
indexio init-config --root . --force
```
