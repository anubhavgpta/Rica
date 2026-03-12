import argparse
import json
import sys
from rica import RicaAgent

def main():
    parser = argparse.ArgumentParser(
        description="Rica — Coding Agent"
    )
    sub = parser.add_subparsers(
        dest="command"
    )

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--goal", required=True)
    run_parser.add_argument("--workspace")
    run_parser.add_argument(
        "--api-key", required=True
    )
    run_parser.add_argument(
        "--model",
        default="gemini-2.5-flash"
    )

    args = parser.parse_args()

    if args.command == "run":
        config = {
            "api_key": args.api_key,
            "model": args.model,
        }
        agent = RicaAgent(config)
        result = agent.run(
            args.goal, args.workspace
        )
        print(json.dumps({
            "success": result.success,
            "workspace": result.workspace_dir,
            "files_created": result.files_created,
            "summary": result.summary,
            "error": result.error,
        }, indent=2))
        sys.exit(0 if result.success else 1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
