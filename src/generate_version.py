import subprocess
import datetime
import os

def get_version():
    try:
        # 1. Check for a tag matching the current commit exactly
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--exact-match"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        base_version = tag
    except subprocess.CalledProcessError:
        # 2. No tag? Fall back to: YYYYMMDD-hash
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        try:
            git_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL
            ).decode("utf-8").strip()
            base_version = f"{date_str}-{git_hash}"
        except Exception:
            base_version = f"{date_str}-unknown"

    # 3. Check for local uncommitted changes
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        if status:
            base_version += "-DIRTY"
    except Exception:
        pass

    return base_version

if __name__ == "__main__":
    version = get_version()
    # Write to a file inside the source tree
    version_file = os.path.join("src", "_version.py")
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(f'__version__ = "{version}"\n')
    print(f"Generated {version_file} with version: {version}")