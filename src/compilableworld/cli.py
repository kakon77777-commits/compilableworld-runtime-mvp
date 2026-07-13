from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import CompileError, compile_world, validate_world
from .gateway import TerminalGateway
from .kernel import RuntimeErrorBase, WorldRuntime
from .modules import install_builtin_modules
from .webgateway import WebGateway


def _force_utf8_io() -> None:
    """Without this, stdin/stdout fall back to the OS locale encoding (e.g.
    cp950 on Traditional Chinese Windows), and mixed ASCII+CJK input like
    `say 老鐵，這捆柴給你` fails with "'utf-8' codec can't encode ...
    surrogates not allowed" — found by actually running the CLI with real
    Chinese content, not assumed. Reconfiguring here means a user doesn't
    have to know to set PYTHONUTF8=1 themselves before every run.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cw-runtime", description="CompilableWorld Runtime reference MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="驗證 Authoring Layer")
    validate.add_argument("source")
    compile_cmd = sub.add_parser("compile", help="編譯 World Runtime Package")
    compile_cmd.add_argument("source")
    compile_cmd.add_argument("--out", required=True)
    play = sub.add_parser("play", help="以終端機執行已編譯世界")
    play.add_argument("package")
    play.add_argument("--actor", default=None, help="省略時使用 world.default_player_entity")
    play.add_argument("--event-log", default="runtime-events.jsonl")
    serve = sub.add_parser("serve", help="以網頁介面執行已編譯世界")
    serve.add_argument("package")
    serve.add_argument("--actor", default=None, help="省略時使用 world.default_player_entity")
    serve.add_argument("--event-log", default="runtime-events.jsonl")
    serve.add_argument("--port", type=int, default=8765)
    inspect = sub.add_parser("inspect", help="顯示 Runtime Package 摘要")
    inspect.add_argument("package")
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_io()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            print(json.dumps(validate_world(args.source), ensure_ascii=False, indent=2))
        elif args.command == "compile":
            path = compile_world(args.source, args.out)
            print(path)
        elif args.command == "inspect":
            package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            print(json.dumps({
                "manifest": package["manifest"], "rooms": len(package["rooms"]),
                "entities": len(package["entities"]), "states": len(package["initial_state"]),
                "checksums": package["source_checksums"],
            }, ensure_ascii=False, indent=2))
        elif args.command == "play":
            runtime = WorldRuntime.from_package(args.package, args.event_log)
            install_builtin_modules(runtime)
            actor = args.actor or runtime.package["world"].get("default_player_entity")
            if not actor:
                raise RuntimeErrorBase("世界未指定 default_player_entity，請傳入 --actor")
            TerminalGateway(runtime, actor).run()
        elif args.command == "serve":
            runtime = WorldRuntime.from_package(args.package, args.event_log)
            install_builtin_modules(runtime)
            actor = args.actor or runtime.package["world"].get("default_player_entity")
            if not actor:
                raise RuntimeErrorBase("世界未指定 default_player_entity，請傳入 --actor")
            WebGateway(runtime, actor, port=args.port).run()
        return 0
    except (CompileError, RuntimeErrorBase, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
