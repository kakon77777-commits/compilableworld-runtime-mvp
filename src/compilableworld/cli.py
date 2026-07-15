from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .compiler import CompileError, compile_world, validate_world
from .gateway import TerminalGateway
from .kernel import RuntimeErrorBase, WorldRuntime
from .modules import install_builtin_modules
from .player_generation import generate_character, template_records
from .scenarios import run_scenario
from .studio import package_overview
from .studio_compile import compile_studio_files
from .studio_mapping import load_studio_mapping, validate_studio_mapping, write_mapping_template
from .studio_world_ir import import_eveglyph_yaml, write_migration_plan, write_world_ir
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
    _add_player_arguments(play)
    play.add_argument("--event-log", default="runtime-events.jsonl")
    _add_amk_arguments(play)
    serve = sub.add_parser("serve", help="以網頁介面執行已編譯世界")
    serve.add_argument("package")
    serve.add_argument("--actor", default=None, help="省略時使用 world.default_player_entity")
    _add_player_arguments(serve)
    serve.add_argument("--event-log", default="runtime-events.jsonl")
    serve.add_argument("--port", type=int, default=8765)
    _add_amk_arguments(serve)
    inspect = sub.add_parser("inspect", help="顯示 Runtime Package 摘要")
    inspect.add_argument("package")
    studio = sub.add_parser("studio-overview", help="輸出供 EveGlyph/Studio 使用的唯讀世界總覽")
    studio.add_argument("package")
    studio_import = sub.add_parser("studio-import", help="將 EveGlyph YAML 匯入共用 Studio World IR JSON")
    studio_import.add_argument("source", help="單一 .yaml/.yml 或包含 EveGlyph YAML 的資料夾")
    studio_import.add_argument("--out", required=True, help="輸出的 studio-world-ir.json 路徑")
    studio_import.add_argument("--plan-out", default=None, help="可選的 migration-plan.json 路徑")
    studio_import.add_argument("--allow-invalid", action="store_true", help="即使來源有診斷錯誤也保留輸出並回傳成功")
    scenario = sub.add_parser("scenario-run", help="執行一個編譯後的 ScenarioIR")
    scenario.add_argument("package")
    scenario.add_argument("scenario_id")
    scenario.add_argument("--actor", default=None, help="覆寫 ScenarioIR 的 actor_id")
    mapping_validate = sub.add_parser("studio-validate-mapping", help="Validate Studio World IR runtime mappings")
    mapping_validate.add_argument("world_ir")
    mapping_validate.add_argument("mapping")
    mapping_suggest = sub.add_parser("studio-suggest-mapping", help="Generate a review-required Studio mapping draft")
    mapping_suggest.add_argument("world_ir")
    mapping_suggest.add_argument("--out", required=True)
    studio_compile = sub.add_parser("studio-compile", help="Compile a reviewed Studio overlay on a base Runtime world")
    studio_compile.add_argument("source", help="complete base Runtime Authoring Layer directory")
    studio_compile.add_argument("world_ir", help="studio-world-ir.json")
    studio_compile.add_argument("mapping", help="reviewed studio-mapping.json")
    studio_compile.add_argument("--out", required=True, help="output directory for world.package.json")
    function_eval = sub.add_parser("function-eval", help="評估一個受限純 FunctionIR")
    function_eval.add_argument("package")
    function_eval.add_argument("function_id")
    function_eval.add_argument("--args", default="{}", help="JSON 輸入物件，例如 '{\"value\":12,\"minimum\":0,\"maximum\":10}'")
    templates = sub.add_parser("character-templates", help="列出可用的玩家角色模板")
    templates.add_argument("package", nargs="?", help="可選的 Runtime Package；省略時顯示內建模板")
    return parser


def _add_amk_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--amk-db", help="可選的 AMK SQLite metadata store；未指定時完全不啟用記憶擷取")
    command.add_argument("--amk-ledger", help="可選的 AMK Raw JSONL 路徑；預設為 <amk-db>.raw.jsonl")
    command.add_argument("--amk-tenant", default="local", help="AMK tenant ID（預設 local）")
    command.add_argument("--amk-owner", default=None, help="AMK owner ID（預設為目前 actor）")


def _add_player_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--template", default="balanced", help="玩家模板 ID（預設 balanced）")
    command.add_argument("--random-character", action="store_true", help="以 seed 隨機選擇一個玩家模板")
    command.add_argument("--name", default=None, help="玩家角色名稱；省略時由模板與 seed 產生")
    command.add_argument("--seed", type=int, default=None, help="角色生成 seed；可重現同一份隨機角色")
    command.add_argument("--attrs", default=None, help="自訂屬性，例如 str=14,con=12,mag=16")
    command.add_argument("--legacy-default", action="store_true", help="沿用 world.default_player_entity（相容舊流程）")


def _attach_optional_amk(args: argparse.Namespace, runtime: WorldRuntime, actor_id: str) -> Any | None:
    """Bind AMK as a non-blocking Raw-evidence observer.

    This deliberately happens before built-in modules subscribe, preserving the
    Runtime EventLog's outer-event order even when a module emits a reaction.
    The adapter itself has no StateStore mutation path.
    """
    if not getattr(args, "amk_db", None):
        return None
    from agent_memory_kernel import AgentMemoryKernel, MemoryScope
    from agent_memory_kernel.adapters import CompilableWorldMemoryAdapter

    scope = MemoryScope(
        tenant_id=args.amk_tenant,
        owner_id=args.amk_owner or actor_id,
        project_id="compilableworld-runtime",
        world_id=runtime.package["manifest"]["world_id"],
    )
    amk = AgentMemoryKernel(args.amk_db, args.amk_ledger)
    CompilableWorldMemoryAdapter(amk, runtime, scope).bind()
    return amk


def _parse_attribute_overrides(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    result: dict[str, int] = {}
    for item in raw.split(","):
        key, separator, value = item.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError("--attrs 格式應為 str=14,con=12,mag=16")
        result[key.strip().lower()] = int(value.strip())
    return result


def _resolve_player_actor(args: argparse.Namespace, runtime: WorldRuntime) -> str:
    if args.actor:
        return args.actor
    if args.legacy_default:
        actor = runtime.package["world"].get("default_player_entity")
        if not actor:
            raise RuntimeErrorBase("世界未指定 default_player_entity，請移除 --legacy-default 以生成玩家")
        return actor
    profile = generate_character(
        template_id=args.template,
        name=args.name,
        seed=args.seed,
        randomize=args.random_character,
        attribute_overrides=_parse_attribute_overrides(args.attrs),
        package=runtime.package,
    )
    actor = runtime.create_player(profile, replace_default=True)
    print(json.dumps({"actor": actor, "character": profile.to_dict()}, ensure_ascii=False, indent=2))
    return actor


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
        elif args.command == "studio-overview":
            package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            print(json.dumps(package_overview(package), ensure_ascii=False, indent=2))
        elif args.command == "studio-import":
            world_ir = import_eveglyph_yaml(args.source)
            output = write_world_ir(world_ir, args.out)
            plan_output = write_migration_plan(world_ir, args.plan_out) if args.plan_out else None
            print(json.dumps({
                "output": str(output),
                "plan_output": None if plan_output is None else str(plan_output),
                "format": world_ir["format"],
                "compile_ready": world_ir["compile_ready"],
                "summary": world_ir["summary"],
                "diagnostics": world_ir["diagnostics"],
            }, ensure_ascii=False, indent=2))
            if world_ir["diagnostics"]["errors"] and not args.allow_invalid:
                return 1
        elif args.command == "studio-suggest-mapping":
            world_ir = json.loads(Path(args.world_ir).read_text(encoding="utf-8"))
            output = write_mapping_template(world_ir, args.out)
            print(json.dumps({"output": str(output), "format": "compilableworld.studio-mapping/v0.1"}, ensure_ascii=False, indent=2))
        elif args.command == "studio-validate-mapping":
            world_ir = json.loads(Path(args.world_ir).read_text(encoding="utf-8"))
            mapping = load_studio_mapping(args.mapping)
            report = validate_studio_mapping(world_ir, mapping)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["mapping_complete"] else 1
        elif args.command == "studio-compile":
            package_path = compile_studio_files(args.source, args.world_ir, args.mapping, args.out)
            print(json.dumps({"package": str(package_path), "format": "compilableworld.runtime-package/v0.1"}, ensure_ascii=False, indent=2))
        elif args.command == "scenario-run":
            package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            report = run_scenario(package, args.scenario_id, actor_id=args.actor)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["passed"] else 1
        elif args.command == "function-eval":
            package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            values = json.loads(args.args)
            runtime = WorldRuntime.from_package(args.package)
            result = runtime.functions.evaluate(args.function_id, values)
            print(json.dumps({"function_id": args.function_id, "inputs": values, "result": result}, ensure_ascii=False, indent=2))
        elif args.command == "character-templates":
            package = None
            if args.package:
                package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            print(json.dumps(template_records(package), ensure_ascii=False, indent=2))
        elif args.command == "play":
            runtime = WorldRuntime.from_package(args.package, args.event_log)
            actor = _resolve_player_actor(args, runtime)
            if not actor:
                raise RuntimeErrorBase("世界未指定 default_player_entity，請傳入 --actor")
            amk = _attach_optional_amk(args, runtime, actor)
            try:
                install_builtin_modules(runtime)
                TerminalGateway(runtime, actor).run()
            finally:
                if amk is not None:
                    amk.close()
        elif args.command == "serve":
            runtime = WorldRuntime.from_package(args.package, args.event_log)
            actor = _resolve_player_actor(args, runtime)
            if not actor:
                raise RuntimeErrorBase("世界未指定 default_player_entity，請傳入 --actor")
            amk = _attach_optional_amk(args, runtime, actor)
            try:
                install_builtin_modules(runtime)
                WebGateway(runtime, actor, port=args.port).run()
            finally:
                if amk is not None:
                    amk.close()
        return 0
    except (CompileError, RuntimeErrorBase, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
