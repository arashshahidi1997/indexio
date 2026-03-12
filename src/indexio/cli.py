from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Iterable

from . import build as build_mod
from . import query as query_mod
from .config import DEFAULT_CONFIG_REL, default_config_template
from .edit import write_raw_config, load_raw_config


def _source_state(config, src, manifest_sources):
    snapshot = build_mod.source_snapshot(config, src)
    previous = manifest_sources.get(src.id) if manifest_sources else None

    if snapshot["files"] == 0:
        state = "empty match" if previous is None else "missing files"
    elif previous is None:
        state = "not yet built"
    elif (
        previous.get("matched_paths") == snapshot["matched_paths"]
        and previous.get("file_state") == snapshot["file_state"]
    ):
        state = "indexed"
    else:
        state = "changed"

    return {
        "state": state,
        "files": snapshot["files"],
        "selector": src.glob or src.path,
        "chunks": None if previous is None else previous.get("chunks"),
    }


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _resolve_bind_port(host: str, preferred_port: int, *, max_tries: int = 20) -> tuple[int, bool]:
    for offset in range(max_tries + 1):
        candidate = preferred_port + offset
        if _port_available(host, candidate):
            return candidate, candidate != preferred_port
    raise RuntimeError(
        f"Could not find a free port in range {preferred_port}-{preferred_port + max_tries}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="indexio",
        description="Semantic indexing and retrieval for project knowledge sources.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Write a starter indexio config into a project.")
    p_init.add_argument("--root", default=".", help="Project root (default: .).")
    p_init.add_argument(
        "--output",
        default=str(DEFAULT_CONFIG_REL),
        help=f"Output path relative to root (default: {DEFAULT_CONFIG_REL}).",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing file.")

    p_build = sub.add_parser("build", help="Build a Chroma index from an indexio config.")
    p_build.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_REL),
        help=f"Path to the indexio config file (default: {DEFAULT_CONFIG_REL}).",
    )
    p_build.add_argument("--root", default=".", help="Project root for resolving relative paths.")
    p_build.add_argument("--store", help="Named store from the config.")
    p_build.add_argument("--sources", help="Comma-separated source ids for partial rebuild.")
    p_build.add_argument("--json", action="store_true", help="Print JSON summary.")

    p_query = sub.add_parser("query", help="Query the Chroma index.")
    p_query.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_REL),
        help=f"Path to the indexio config file (default: {DEFAULT_CONFIG_REL}).",
    )
    p_query.add_argument("--root", default=".", help="Project root for resolving relative paths.")
    p_query.add_argument("--store", help="Named store from the config.")
    p_query.add_argument("--corpus", help="Optional corpus filter.")
    p_query.add_argument("--k", type=int, default=8, help="Number of results (default: 8).")
    p_query.add_argument("--json", action="store_true", help="Emit JSON.")
    p_query.add_argument("query", nargs="+", help="Query text.")

    p_status = sub.add_parser("status", help="Show index status for each configured store.")
    p_status.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_REL),
        help=f"Path to the indexio config file (default: {DEFAULT_CONFIG_REL}).",
    )
    p_status.add_argument("--root", default=".", help="Project root for resolving relative paths.")

    p_serve = sub.add_parser("serve", help="Start the chat server (requires indexio[chat]).")
    p_serve.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_REL),
        help=f"Path to the indexio config file (default: {DEFAULT_CONFIG_REL}).",
    )
    p_serve.add_argument("--root", default=".", help="Project root for resolving relative paths.")
    p_serve.add_argument("--store", help="Named store from the config.")
    p_serve.add_argument("--corpus", help="Optional corpus filter for retrieval.")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
    p_serve.add_argument("--port", type=int, default=9100, help="Bind port (default: 9100).")
    p_serve.add_argument("--llm-backend", default="ollama", help="LLM backend: ollama or openai (default: ollama).")
    p_serve.add_argument("--llm-model", default="llama3", help="LLM model name (default: llama3).")
    p_serve.add_argument("--llm-base-url", default="http://localhost:11434", help="LLM API base URL.")
    p_serve.add_argument("--title", default="Docs Assistant", help="Chat widget title.")

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    if args.command == "init":
        root = Path(args.root).expanduser().resolve()
        output = (root / args.output).resolve()
        if output.exists() and not args.force:
            print(f"[SKIP] Config already exists: {output}  (use --force to overwrite)")
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(default_config_template(), encoding="utf-8")
        print(f"[OK] Wrote indexio config: {output}")
        return

    if args.command == "build":
        sources_filter = None
        if args.sources:
            sources_filter = [part.strip() for part in args.sources.split(",") if part.strip()]
        payload = build_mod.build_index(
            config_path=args.config,
            root=args.root,
            store=args.store,
            sources_filter=sources_filter,
            verbose=not args.json,
        )
        if args.json:
            print(json.dumps(payload, indent=2))
            return
        print("[INFO] Index build complete.")
        print(json.dumps(payload, indent=2))
        return

    if args.command == "query":
        payload = query_mod.query_index(
            config_path=args.config,
            root=args.root,
            query=" ".join(args.query),
            store=args.store,
            corpus=args.corpus,
            k=args.k,
        )
        if args.json:
            print(json.dumps(payload, indent=2))
            return
        print(f"[QUERY] {payload['query']}")
        for idx, result in enumerate(payload["results"], start=1):
            print(f"=== Result {idx} ===")
            print(f"Corpus     : {result.get('corpus')}")
            print(f"Source ID  : {result.get('source_id')}")
            print(f"Source Path: {result.get('source_path')}")
            print(f"Chunk Index: {result.get('chunk_index')}")
            print("--- Snippet ---")
            print(result.get("snippet", ""))
            print()
        return

    if args.command == "status":
        from .config import load_indexio_config
        config = load_indexio_config(args.config, root=args.root)
        print(f"Config : {config.config_path}")
        print(f"Root   : {config.root}")

        for store in config.stores.values():
            marker = "local" if store.name == config.default_store else ("canonical" if store.name == config.canonical_store else "")
            tag = f" [{marker}]" if marker else ""
            manifest = build_mod.load_status_manifest(store.persist_directory)
            manifest_sources = {} if manifest is None else dict(manifest.get("sources", {}))
            print()
            print(f"On store '{store.name}'{tag}")
            print(f"DB      : {store.persist_directory}  [{'exists' if store.persist_directory.exists() else 'missing'}]")
            if manifest is None:
                print("Manifest: missing")
            else:
                print(f"Manifest: present  (built_at={manifest.get('built_at', 'unknown')})")

            buckets: dict[str, list[str]] = {
                "changed": [],
                "not yet built": [],
                "missing files": [],
                "empty match": [],
                "indexed": [],
            }
            for src in config.sources:
                details = _source_state(config, src, manifest_sources)
                line = f"{src.id} ({src.corpus}) - {details['files']} files"
                if details["chunks"] is not None:
                    line += f", {details['chunks']} chunks"
                line += f" [{details['selector']}]"
                buckets[details["state"]].append(line)

            print()
            for state, lines in buckets.items():
                if not lines:
                    continue
                print(f"{state}:")
                for line in lines:
                    print(f"  - {line}")

            actionable_ids: list[str] = []
            for state in ("changed", "not yet built", "missing files", "empty match"):
                actionable_ids.extend(line.split(" ", 1)[0] for line in buckets[state])
            if actionable_ids:
                print()
                print("Actions:")
                print("  Run `indexio build` to refresh the index.")
                print(f"  Or rebuild selected sources: indexio build --sources {','.join(actionable_ids)}")
        return

    if args.command == "serve":
        try:
            import uvicorn
            from .chat.settings import ChatSettings
            from .chat.app import create_app
        except ImportError as exc:
            raise SystemExit(
                f"Chat dependencies not installed. Run: pip install indexio[chat]\n({exc})"
            ) from exc

        settings = ChatSettings(
            config_path=args.config,
            root=args.root,
            store=args.store,
            corpus=args.corpus,
            host=args.host,
            port=args.port,
            llm_backend=args.llm_backend,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            title=args.title,
        )
        resolved_port, changed = _resolve_bind_port(settings.host, settings.port)
        if changed:
            print(
                f"[indexio-chat] Port {settings.port} is unavailable; using {resolved_port} instead."
            )
            settings.port = resolved_port
        app = create_app(settings)
        print(f"[indexio-chat] Serving on http://{settings.host}:{settings.port}")
        print(f"[indexio-chat] Open page:  http://{settings.host}:{settings.port}/")
        print(f"[indexio-chat] Widget at  http://{settings.host}:{settings.port}/chatbot/chatbot.js")
        uvicorn.run(app, host=settings.host, port=settings.port)
        return

    raise SystemExit(2)
