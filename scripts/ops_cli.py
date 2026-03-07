from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx

TIME_CHOICES = ["hour", "day", "week", "month", "all"]
SORT_CHOICES = ["hot", "new", "top", "rising"]
DEFAULT_TIMEOUT_SECONDS = 180.0


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    response = client.request(method, path, params=params, json=body)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {payload}")
    return payload


def _cmd_health(client: httpx.Client, _args: argparse.Namespace) -> int:
    _print_json(_request_json(client, "GET", "/health/live"))
    _print_json(_request_json(client, "GET", "/health"))
    return 0


def _cmd_ingest(client: httpx.Client, args: argparse.Namespace) -> int:
    payload = _request_json(
        client,
        "POST",
        "/ops/ingestion/run",
        params={"time": args.time, "sort": args.sort, "limit": args.limit},
    )
    _print_json(payload)
    return 0


def _cmd_review_list(client: httpx.Client, args: argparse.Namespace) -> int:
    payload = _request_json(
        client,
        "GET",
        "/review-items",
        params={"status": args.status, "limit": args.limit},
    )
    _print_json(payload)
    return 0


def _cmd_review_decide(client: httpx.Client, args: argparse.Namespace) -> int:
    payload = _request_json(
        client,
        "POST",
        f"/review-items/{args.review_item_id}/decision",
        body={
            "decision": args.decision,
            "reviewedBy": args.reviewed_by,
            "comment": args.comment,
        },
    )
    _print_json(payload)
    return 0


def _cmd_publish_run(client: httpx.Client, _args: argparse.Namespace) -> int:
    _print_json(_request_json(client, "POST", "/ops/publish/run"))
    return 0


def _cmd_publish_jobs(client: httpx.Client, args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.status:
        params["status"] = args.status
    _print_json(_request_json(client, "GET", "/publish-jobs", params=params))
    return 0


def _cmd_smoke(client: httpx.Client, args: argparse.Namespace) -> int:
    ingest = _request_json(
        client,
        "POST",
        "/ops/ingestion/run",
        params={"time": args.time, "sort": args.sort, "limit": args.limit},
    )
    print("# ingestion")
    _print_json(ingest)

    queue = _request_json(
        client,
        "GET",
        "/review-items",
        params={"status": "pending", "limit": 1},
    )
    print("# pending review item")
    _print_json(queue)

    items = queue.get("items", [])
    if not items:
        print("No pending review item. Stop here.")
        return 0

    if args.approve:
        review_item_id = items[0]["id"]
        decision = _request_json(
            client,
            "POST",
            f"/review-items/{review_item_id}/decision",
            body={"decision": "approved", "reviewedBy": args.reviewed_by},
        )
        print("# approve first pending item")
        _print_json(decision)

        publish = _request_json(client, "POST", "/ops/publish/run")
        print("# publish run")
        _print_json(publish)

        jobs = _request_json(client, "GET", "/publish-jobs")
        print("# publish jobs")
        _print_json(jobs)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Moltbook Watcher operations CLI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument(
        "--timeout",
        dest="global_timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout seconds (default: {int(DEFAULT_TIMEOUT_SECONDS)})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("health", help="Check /health/live and /health")
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_health)

    p = subparsers.add_parser("ingest", help="Run one ingestion cycle")
    p.add_argument(
        "--time",
        default="hour",
        choices=TIME_CHOICES,
        help="Upstream time filter passed directly to the Moltbook posts API",
    )
    p.add_argument("--sort", default="top", choices=SORT_CHOICES)
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_ingest)

    p = subparsers.add_parser("review-list", help="List review items")
    p.add_argument("--status", default="pending")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_review_list)

    p = subparsers.add_parser("review-decide", help="Submit review decision")
    p.add_argument("review_item_id")
    p.add_argument("--decision", choices=["approved", "rejected", "archived"], required=True)
    p.add_argument("--reviewed-by", default="operator")
    p.add_argument("--comment", default=None)
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_review_decide)

    p = subparsers.add_parser("publish-run", help="Run one publish cycle")
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_publish_run)

    p = subparsers.add_parser("publish-jobs", help="List publish jobs")
    p.add_argument("--status", default=None)
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_publish_jobs)

    p = subparsers.add_parser("smoke", help="US1->US3 quick smoke flow")
    p.add_argument(
        "--time",
        default="hour",
        choices=TIME_CHOICES,
        help="Upstream time filter passed directly to the Moltbook posts API",
    )
    p.add_argument("--sort", default="top", choices=SORT_CHOICES)
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--approve", action="store_true", help="Approve first pending item and run publish")
    p.add_argument("--reviewed-by", default="operator")
    p.add_argument("--timeout", type=float, default=None, help="Override HTTP timeout seconds for this command")
    p.set_defaults(func=_cmd_smoke)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    effective_timeout = args.timeout if args.timeout is not None else args.global_timeout

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=effective_timeout) as client:
        try:
            return int(args.func(client, args))
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
