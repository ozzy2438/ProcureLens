#!/usr/bin/env bash
set -euo pipefail

release_version="${RELEASE_VERSION:-1.0.0}"
release_name="procurelens-v${release_version}"
output_dir="dist"
package_dir="${output_dir}/${release_name}"
archive_path="${output_dir}/${release_name}.tar.gz"
snapshot_path="data/snapshots/procurelens-marts-v${release_version}.dump"
python_runner="python3"

if [[ -x .venv/bin/python ]]; then
  python_runner=".venv/bin/python"
fi

if [[ ! -f "${snapshot_path}" || ! -f mlruns/mlflow.db ]]; then
  echo "Release requires the bundled snapshot and portable MLflow registry." >&2
  exit 2
fi

"${python_runner}" scripts/sanitize_mlflow_registry.py

rm -rf "${package_dir}"
rm -f "${archive_path}" "${archive_path}.sha256"
mkdir -p "${package_dir}"

rsync -a ./ "${package_dir}/" \
  --exclude '/.git/' \
  --exclude '.env' \
  --exclude '/.venv/' \
  --exclude '/dist/' \
  --exclude '/artifacts/' \
  --exclude '/logs/' \
  --exclude '/data/raw/' \
  --exclude '/data/processed/' \
  --exclude '/dbt/target/' \
  --exclude '/dbt/logs/' \
  --exclude '/dbt/dbt_packages/' \
  --exclude '/dbt/.user.yml' \
  --exclude '.coverage' \
  --exclude 'coverage.xml' \
  --exclude 'htmlcov/' \
  --exclude '.mypy_cache/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '__pycache__/' \
  --exclude '*.egg-info/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store'

cat >"${package_dir}/RELEASE_MANIFEST.json" <<JSON
{
  "release": "v${release_version}",
  "snapshot": "procurelens-marts-v${release_version}.dump",
  "contracts": 445029,
  "agencies": 151,
  "mlflow_champion": "procurelens-amendment-risk@champion",
  "fit_scorer": "1.0.0",
  "demo_entrypoint": "make demo",
  "deployment_status": "configuration validated; not deployed"
}
JSON

"${python_runner}" scripts/release_audit.py "${package_dir}"

(
  cd "${package_dir}"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 shasum -a 256 >SHA256SUMS
)

tar -C "${output_dir}" -czf "${archive_path}" "${release_name}"
shasum -a 256 "${archive_path}" >"${archive_path}.sha256"

echo "Release package: ${archive_path}"
echo "Archive SHA-256: $(awk '{print $1}' "${archive_path}.sha256")"
