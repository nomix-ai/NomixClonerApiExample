#!/usr/bin/env python3
"""Upload a batch CSV via NomixCloner API and download results.

User guide: README.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://check.nomixcloner.com"
DEFAULT_POLL_INTERVAL_SECONDS = 15
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_DIR = _SCRIPT_DIR / "results"
DEFAULT_ANDROID_CSV = _SCRIPT_DIR / "api_batch_clones.csv"
DEFAULT_IOS_CSV = _SCRIPT_DIR / "api_batch_clones_ios.csv"
TERMINAL_STATUSES = {"completed", "failed"}


def default_csv_for_platform(platform: str) -> Path:
    return DEFAULT_IOS_CSV if platform == "iOS" else DEFAULT_ANDROID_CSV

# Used when running from PyCharm without "Parameters" in Run Configuration.
DEFAULT_RUN_ARGS: list[str] = [
    "--platform", "Android",
    "--iterations", "1",
]

# Paste your API key here (from /apikey in the bot), or use --api-key / NOMIX_API_KEY.
API_KEY = ""


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _retry_after_seconds(response: requests.Response, default: int = 5) -> int:
    header_value = response.headers.get('Retry-After')
    if header_value:
        return int(header_value)
    try:
        body = response.json()
    except ValueError:
        return default
    return int(body.get('retry_after_seconds', default))


def _save_batch_uuid(output_dir: Path, batch_uuid: str) -> None:
    state_file = output_dir / "last_batch_uuid"
    output_dir.mkdir(parents=True, exist_ok=True)
    state_file.write_text(batch_uuid, encoding="utf-8")


def _clear_batch_uuid(output_dir: Path) -> None:
    state_file = output_dir / "last_batch_uuid"
    if state_file.is_file():
        state_file.unlink()


def create_batch(
        base_url: str,
        api_key: str,
        csv_path: Path,
        platform: str,
        timeout_seconds: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/batch"

    while True:
        with csv_path.open("rb") as csv_file:
            response = requests.post(
                url,
                headers=_headers(api_key),
                data={"platform": platform},
                files={"file": (csv_path.name, csv_file, "text/csv")},
                timeout=timeout_seconds,
            )

        if response.status_code == 429:
            retry_after = _retry_after_seconds(response)
            print(f"  rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        if response.status_code != 202:
            raise RuntimeError(
                f"POST /api/batch failed: status={response.status_code}, body={response.text}"
            )

        payload = response.json()
        break
    required_fields = {"batch_uuid", "clones_count"}
    missing = required_fields - payload.keys()
    if missing:
        raise RuntimeError(f"Unexpected create response, missing fields: {sorted(missing)}")

    return payload


def get_batch_status(
        base_url: str,
        api_key: str,
        batch_uuid: str,
        timeout_seconds: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/batch/{batch_uuid}"

    while True:
        response = requests.get(url, headers=_headers(api_key), timeout=timeout_seconds)

        if response.status_code == 429:
            retry_after = _retry_after_seconds(response)
            print(f"  rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        if response.status_code != 200:
            raise RuntimeError(
                f"GET /api/batch/{batch_uuid} failed: status={response.status_code}, body={response.text}"
            )

        return response.json()


def download_result(result_url: str, output_dir: Path, batch_uuid: str, timeout_seconds: int) -> Path:
    response = requests.get(result_url, timeout=timeout_seconds)
    response.raise_for_status()

    output_path = output_dir / f"batch_{batch_uuid}.json"
    output_path.write_text(response.text, encoding="utf-8")
    return output_path


def wait_for_batch(
        base_url: str,
        api_key: str,
        batch_uuid: str,
        poll_interval_seconds: int,
        request_timeout_seconds: int,
        wait_timeout_seconds: int,
) -> dict[str, Any]:
    started_at = time.monotonic()

    while True:
        status_payload = get_batch_status(base_url, api_key, batch_uuid, request_timeout_seconds)
        status = status_payload.get("status")
        result_ready = bool(status_payload.get("result_ready"))
        completed = status_payload.get("completed", 0)
        failed = status_payload.get("failed", 0)
        pending = status_payload.get("pending", 0)
        total = status_payload.get("total", 0)

        print(
            f"  status={status}, progress={completed}/{total}, "
            f"failed={failed}, pending={pending}, result_ready={result_ready}",
            flush=True,
        )

        if status in TERMINAL_STATUSES:
            if status == "failed" or result_ready:
                return status_payload

        time.sleep(poll_interval_seconds)

        elapsed = time.monotonic() - started_at
        if elapsed > wait_timeout_seconds:
            raise TimeoutError(f"Batch {batch_uuid} did not finish within {wait_timeout_seconds}s")


def run_iteration(
        iteration: int,
        iterations: int,
        base_url: str,
        api_key: str,
        csv_path: Path,
        platform: str,
        poll_interval_seconds: int,
        request_timeout_seconds: int,
        wait_timeout_seconds: int,
        output_dir: Path,
        download_results: bool,
) -> dict[str, Any]:
    print(f"\n=== Batch {iteration}/{iterations} ===", flush=True)
    print(f"Uploading {csv_path} ({platform})...", flush=True)

    created = create_batch(base_url, api_key, csv_path, platform, request_timeout_seconds)
    batch_uuid = created["batch_uuid"]
    clones_count = created["clones_count"]
    _save_batch_uuid(output_dir, batch_uuid)

    print(f"Accepted: batch_uuid={batch_uuid}, clones_count={clones_count}", flush=True)
    print("Waiting for completion...", flush=True)

    final_status = wait_for_batch(
        base_url=base_url,
        api_key=api_key,
        batch_uuid=batch_uuid,
        poll_interval_seconds=poll_interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        wait_timeout_seconds=wait_timeout_seconds,
    )

    if final_status.get("status") == "failed":
        error_message = final_status.get("error_message")
        raise RuntimeError(f"Batch {batch_uuid} failed: {error_message}")

    if not final_status.get("result_ready"):
        raise RuntimeError(f"Batch {batch_uuid} finished without result file")

    if download_results:
        result_url = final_status.get("result_url")
        if not result_url:
            raise RuntimeError(f"Batch {batch_uuid} has no result_url")
        saved_path = download_result(result_url, output_dir, batch_uuid, request_timeout_seconds)
        print(f"Result saved to {saved_path}", flush=True)
        try:
            result_data = json.loads(saved_path.read_text(encoding="utf-8"))
            apps_count = len(result_data.get("apps", []))
            print(f"Result contains {apps_count} app(s)", flush=True)
        except json.JSONDecodeError:
            print("Warning: result file is not valid JSON", flush=True)

    _clear_batch_uuid(output_dir)
    return final_status


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a batch CSV via NomixCloner API, wait for completion, repeat N times.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override API key (default: API_KEY in this file, then NOMIX_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("NOMIX_API_BASE_URL", DEFAULT_BASE_URL),
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Path to batch CSV file (default: api_batch_clones.csv or api_batch_clones_ios.csv)",
    )
    parser.add_argument(
        "--platform",
        choices=["Android", "iOS"],
        default="Android",
        help="Cloning platform",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="How many batches to run sequentially (default: 1)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Seconds between status polls (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=6 * 60 * 60,
        help="Max seconds to wait for each batch to complete (default: 6 hours)",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=60,
        help="HTTP request timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="Directory for downloaded result JSON files and last_batch_uuid state",
    )
    parser.add_argument(
        "--batch-uuid",
        default=None,
        help="Monitor an existing batch instead of creating a new one",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not download result JSON after each batch",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue with next iteration if a batch fails",
    )
    args = parser.parse_args(argv)
    if args.csv is None:
        args.csv = default_csv_for_platform(args.platform)
    return args


def _resolve_argv(argv: list[str] | None) -> list[str]:
    if argv is not None:
        return argv
    cli_args = sys.argv[1:]
    return cli_args if cli_args else DEFAULT_RUN_ARGS


def monitor_existing_batch(
        base_url: str,
        api_key: str,
        batch_uuid: str,
        poll_interval_seconds: int,
        request_timeout_seconds: int,
        wait_timeout_seconds: int,
        output_dir: Path,
        download_results: bool,
) -> dict[str, Any]:
    print(f"Monitoring existing batch {batch_uuid}...", flush=True)
    _save_batch_uuid(output_dir, batch_uuid)

    final_status = wait_for_batch(
        base_url=base_url,
        api_key=api_key,
        batch_uuid=batch_uuid,
        poll_interval_seconds=poll_interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        wait_timeout_seconds=wait_timeout_seconds,
    )

    if final_status.get("status") == "failed":
        error_message = final_status.get("error_message")
        raise RuntimeError(f"Batch {batch_uuid} failed: {error_message}")

    if not final_status.get("result_ready"):
        raise RuntimeError(f"Batch {batch_uuid} finished without result file")

    if download_results:
        result_url = final_status.get("result_url")
        if not result_url:
            raise RuntimeError(f"Batch {batch_uuid} has no result_url")
        saved_path = download_result(result_url, output_dir, batch_uuid, request_timeout_seconds)
        print(f"Result saved to {saved_path}", flush=True)
        try:
            result_data = json.loads(saved_path.read_text(encoding="utf-8"))
            apps_count = len(result_data.get("apps", []))
            print(f"Result contains {apps_count} app(s)", flush=True)
        except json.JSONDecodeError:
            print("Warning: result file is not valid JSON", flush=True)

    _clear_batch_uuid(output_dir)
    return final_status


def resolve_api_key(cli_api_key: str | None) -> str | None:
    if cli_api_key:
        return cli_api_key
    if API_KEY.strip():
        return API_KEY.strip()
    env_key = os.environ.get("NOMIX_API_KEY", "").strip()
    return env_key or None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(_resolve_argv(argv))
    api_key = resolve_api_key(args.api_key)

    if not api_key:
        print(
            "Error: set API_KEY at the top of this script, or pass --api-key, or set NOMIX_API_KEY",
            file=sys.stderr,
        )
        return 2

    if not args.batch_uuid and not args.csv.is_file():
        print(f"Error: CSV file not found: {args.csv}", file=sys.stderr)
        return 2

    if args.iterations < 1:
        print("Error: --iterations must be >= 1", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.batch_uuid:
        try:
            monitor_existing_batch(
                base_url=args.base_url,
                api_key=api_key,
                batch_uuid=args.batch_uuid,
                poll_interval_seconds=args.poll_interval,
                request_timeout_seconds=args.request_timeout,
                wait_timeout_seconds=args.timeout,
                output_dir=args.output_dir,
                download_results=not args.no_download,
            )
        except Exception as exc:
            print(f"Error while monitoring batch: {exc}", file=sys.stderr)
            return 1
        print("\nBatch monitoring completed successfully", flush=True)
        return 0

    failures = 0
    for iteration in range(1, args.iterations + 1):
        try:
            run_iteration(
                iteration=iteration,
                iterations=args.iterations,
                base_url=args.base_url,
                api_key=api_key,
                csv_path=args.csv,
                platform=args.platform,
                poll_interval_seconds=args.poll_interval,
                request_timeout_seconds=args.request_timeout,
                wait_timeout_seconds=args.timeout,
                output_dir=args.output_dir,
                download_results=not args.no_download,
            )
        except Exception as exc:
            failures += 1
            print(f"Error on batch {iteration}: {exc}", file=sys.stderr)
            if not args.continue_on_failure:
                return 1

    if failures:
        print(f"\nFinished with {failures} failed batch(es) out of {args.iterations}")
        return 1

    print(f"\nAll {args.iterations} batch(es) completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
