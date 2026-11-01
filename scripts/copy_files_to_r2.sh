#!/usr/bin/env bash
# Copy stored files from local MinIO to Cloudflare R2, then compare the two. Object keys don't
# change, so stored_files rows still point at the right objects afterwards.
#
# Safe to re-run: files already in R2 are skipped, and nothing is ever deleted from either side.
# Reads S3_* (the source, MinIO) and R2_* (the destination) from .env. Secrets stay in rclone's
# environment, off the command line and out of the output.
#
#   scripts/copy_files_to_r2.sh                 copy, then compare
#   scripts/copy_files_to_r2.sh --dry-run       show what would be copied
#   scripts/copy_files_to_r2.sh --check-only    compare without copying
#
# Anything else is passed to rclone, e.g. --transfers 32 or --include 'operators/**/reports/**'.

set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env}"

die() {
  echo "Error: $*" >&2
  exit 1
}

# One value from the env file, without sourcing it (values aren't shell syntax).
env_value() {
  local line
  line=$(grep -E "^$1=" "$ENV_FILE" | tail -n 1) || true
  line=${line#*=}
  line=${line%\"}
  line=${line#\"}
  line=${line%\'}
  line=${line#\'}
  printf '%s' "$line"
}

require() {
  local value
  value=$(env_value "$1")
  [[ -n "$value" ]] || die "$1 is empty in $ENV_FILE"
  printf '%s' "$value"
}

mode=copy
rclone_args=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) mode=dry-run ;;
    --check-only) mode=check ;;
    -h | --help)
      sed -n '2,14p' "$0" | sed -E 's/^# ?//'
      exit 0
      ;;
    *) rclone_args+=("$arg") ;;
  esac
done

command -v rclone >/dev/null || die "rclone isn't installed (brew install rclone)"
[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found"

source_endpoint=$(require S3_ENDPOINT_URL)
source_bucket=$(require S3_BUCKET)
source_key=$(require S3_ACCESS_KEY_ID)
source_secret=$(require S3_SECRET_ACCESS_KEY)
r2_key=$(require R2_ACCESS_KEY_ID)
r2_secret=$(require R2_SECRET_ACCESS_KEY)
r2_bucket=$(require R2_BUCKET)
r2_endpoint=$(env_value R2_ENDPOINT_URL)
if [[ -z "$r2_endpoint" ]]; then
  r2_endpoint="https://$(require R2_ACCOUNT_ID).r2.cloudflarestorage.com"
fi

# The S3_* settings can point anywhere, including at R2 once an env file is set up for production.
case "$source_endpoint" in
  http://localhost:* | http://127.0.0.1:*) ;;
  *) die "S3_ENDPOINT_URL must be the local MinIO, but it's $source_endpoint" ;;
esac

export RCLONE_CONFIG_SOURCE_TYPE=s3
export RCLONE_CONFIG_SOURCE_PROVIDER=Minio
export RCLONE_CONFIG_SOURCE_ACCESS_KEY_ID="$source_key"
export RCLONE_CONFIG_SOURCE_SECRET_ACCESS_KEY="$source_secret"
export RCLONE_CONFIG_SOURCE_ENDPOINT="$source_endpoint"
export RCLONE_CONFIG_SOURCE_REGION="$(env_value S3_REGION)"

export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$r2_key"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$r2_secret"
export RCLONE_CONFIG_R2_ENDPOINT="$r2_endpoint"
export RCLONE_CONFIG_R2_REGION=auto
# A token limited to one bucket can't check for or create buckets.
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true

from="source:$source_bucket"
to="r2:$r2_bucket"
echo "From: $source_bucket at $source_endpoint"
echo "To:   $r2_bucket at $r2_endpoint"

copy_args=(--transfers 16 --checkers 16)
if [[ -t 1 ]]; then copy_args+=(--progress); else copy_args+=(--stats 1m --stats-one-line); fi

rclone lsf "$to" --max-depth 1 >/dev/null ||
  die "can't read $r2_bucket in R2; check the bucket name, account ID, and token"

echo "Source: $(rclone size "$from" --json ${rclone_args[@]+"${rclone_args[@]}"})"

case "$mode" in
  dry-run)
    rclone copy "$from" "$to" --dry-run --transfers 16 ${rclone_args[@]+"${rclone_args[@]}"}
    exit 0
    ;;
  copy)
    rclone copy "$from" "$to" "${copy_args[@]}" ${rclone_args[@]+"${rclone_args[@]}"}
    ;;
esac

echo "R2:     $(rclone size "$to" --json ${rclone_args[@]+"${rclone_args[@]}"})"
if ! rclone check "$from" "$to" --one-way --checkers 16 ${rclone_args[@]+"${rclone_args[@]}"}; then
  die "the buckets differ; re-run this script, then compare again"
fi
echo "Every source file is in R2 and matches."
