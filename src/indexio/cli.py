from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from . import build as build_mod
from . import query as query_mod
from .config import default_config_template
from .edit import write_raw_config, load_raw_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="indexio",
        description="Semantic indexing and retrieval for project knowledge sources.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-config", help="Write a starter indexio config into a project.")
    p_init.add_argument("--root", default=".", help="Project root (default: .).")
    p_init.add_argument(
        "--output",
        default=".indexio/config.yaml",
        help="Output path relative to root (default: .indexio/config.yaml).",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing file.")

    p_build = sub.add_parser("build", help="Build a Chroma index from an indexio config.")
    p_build.add_argument("--config", required=True, help="Path to the indexio config file.")
    p_build.add_argument("--root", default=".", help="Project root for resolving relative paths.")
    p_build.add_argument("--store", help="Named store from the config.")
    p_build.add_argument("--sources", help="Comma-separated source ids for partial rebuild.")
    p_build.add_argument("--json", action="store_true", help="Print JSON summary.")

    p_query = sub.add_parser("query", help="Query the Chroma index.")
    p_query.add_argument("--config", required=True, help="Path to the indexio config file.")
    p_query.add_argument("--root", default=".", help="Project root for resolving relative paths.")
    p_query.add_argument("--store", help="Named store from the config.")
    p_query.add_argument("--corpus", help="Optional corpus filter.")
    p_query.add_argument("--k", type=int, default=8, help="Number of results (default: 8).")
    p_query.add_argument("--json", action="store_true", help="Emit JSON.")
    p_query.add_argument("query", nargs="+", help="Query text.")

    p_status = sub.add_parser("status", help="Show index status for each configured store.")
    p_status.add_argument("--config", required=True, help="Path to the indexio config file.")
    p_status.add_argument("--root", default=".", help="Project root for resolving relative paths.")

    p_serve = sub.add_parser("serve", help="Start the chat server (requires indexio[chat]).")
    p_serve.add_argument("--config", required=True, help="Path to the indexio config file.")
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

    if args.command == "init-config":
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
        print(f"Sources: {len(config.sources)}")
        print()
        for name, store in config.stores.items():
            exists = store.persist_directory.exists()
            marker = "local" if name == config.default_store else ("canonical" if name == config.canonical_store else "")
            tag = f" [{marker}]" if marker else ""
            status = "exists" if exists else "missing"
            print(f"  Store '{name}'{tag}: {store.persist_directory}  [{status}]")
        print()
        for src in config.sources:
            glob_or_path = src.glob or src.path
            print(f"  Source '{src.id}' corpus={src.corpus}  {glob_or_path}")
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
        app = create_app(settings)
        print(f"[indexio-chat] Serving on http://{settings.host}:{settings.port}")
        print(f"[indexio-chat] Widget at  http://{settings.host}:{settings.port}/chatbot/chatbot.js")
        uvicorn.run(app, host=settings.host, port=settings.port)
        return

    raise SystemExit(2)
