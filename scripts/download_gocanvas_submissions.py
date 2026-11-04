"""Download every GoCanvas submission of a form.

Lists the form's submissions from `GET {base_url}/api/v3/submissions?form_id={id}&page={n}`,
page by page from 1 until a page comes back empty. Every submission is then fetched from
`GET {base_url}/api/v3/submissions/{id}` and written to `{out_dir}/{id}.json`. Files already
present are skipped, so an interrupted run can be resumed.

The bearer token is read from GOCANVAS_TOKEN (preferred, keeps it out of shell
history) or --token. Submissions are customer data: keep the output out of git.

    GOCANVAS_TOKEN=... pipenv run python scripts/download_gocanvas_submissions.py \
        5777327 --out-dir scripts/chiptole
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.gocanvas.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}


def get_json(
    client: httpx.Client, path: str, label: str, max_attempts: int, params: dict | None = None
):
    """GET JSON, retrying rate limits and server errors with backoff."""
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(path, params=params)
        except httpx.TransportError as exc:
            if attempt == max_attempts:
                raise RuntimeError(f"network error: {exc}") from exc
            delay = 2**attempt
        else:
            if response.status_code == 200:
                return response.json()
            if response.status_code not in RETRY_STATUSES or attempt == max_attempts:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
            retry_after = response.headers.get("Retry-After", "")
            delay = int(retry_after) if retry_after.isdigit() else 2**attempt
        print(f"  {label}: retrying in {delay}s (attempt {attempt}/{max_attempts})")
        time.sleep(delay)
    raise AssertionError("unreachable")


def list_submission_ids(
    client: httpx.Client, form_id: int, max_attempts: int, delay: float = 0
) -> list[int]:
    """The ids of a form's submissions, from page 1 until a page comes back empty."""
    ids: dict[int, None] = {}  # keeps order, drops duplicates
    page = 1
    while True:
        items = get_json(
            client,
            "/api/v3/submissions",
            f"page {page}",
            max_attempts,
            params={"form_id": form_id, "page": page},
        )
        if not isinstance(items, list):
            raise RuntimeError(f"page {page}: expected a JSON array, got {type(items).__name__}")
        if not items:
            return list(ids)
        new = 0
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                raise RuntimeError(f"page {page}: item {index} has no integer 'id'")
            if item["id"] not in ids:
                ids[item["id"]] = None
                new += 1
        # A server that ignores `page` would otherwise have this loop forever.
        if not new:
            raise RuntimeError(f"page {page}: repeats earlier pages, so paging isn't advancing")
        print(f"  page {page}: {len(items)} submissions")
        page += 1
        time.sleep(delay)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("form_id", type=int, help="GoCanvas form id, e.g. 5777327")
    parser.add_argument("--out-dir", type=Path, default=Path("gocanvas-submissions"))
    parser.add_argument("--token", help="bearer token (default: $GOCANVAS_TOKEN)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--delay", type=float, default=0.25, help="seconds between requests")
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    token = args.token or os.environ.get("GOCANVAS_TOKEN")
    if not token:
        parser.error("no bearer token: set GOCANVAS_TOKEN or pass --token")

    downloaded, skipped, failed = 0, 0, []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as client:
        try:
            ids = list_submission_ids(client, args.form_id, args.max_attempts, args.delay)
        except RuntimeError as exc:
            print(f"Could not list form {args.form_id}: {exc}", file=sys.stderr)
            return 1
        args.out_dir.mkdir(parents=True, exist_ok=True)
        print(f"{len(ids)} submissions -> {args.out_dir}")
        for submission_id in ids:
            target = args.out_dir / f"{submission_id}.json"
            if target.exists() and not args.force:
                skipped += 1
                continue
            try:
                submission = get_json(
                    client,
                    f"/api/v3/submissions/{submission_id}",
                    str(submission_id),
                    args.max_attempts,
                )
            except RuntimeError as exc:
                print(f"  {submission_id}: FAILED {exc}", file=sys.stderr)
                failed.append(submission_id)
                if "HTTP 401" in str(exc):
                    print("Token rejected; stopping.", file=sys.stderr)
                    break
                continue
            # Write to a temp file first so a crash never leaves a partial file behind.
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(submission, indent=4))
            tmp.replace(target)
            downloaded += 1
            print(f"  {submission_id}: ok")
            time.sleep(args.delay)

    print(f"done: {downloaded} downloaded, {skipped} skipped, {len(failed)} failed")
    if failed:
        print("failed ids: " + ", ".join(map(str, failed)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
