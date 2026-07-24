import subprocess
from datetime import datetime, timezone
import os

def write_version():
    print("Generating version...")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    tag = None
    hash = None
    dirty = False

    try:
        # Attempt to find a git tag
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--exact-match"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        # If not, find the hash
        try:
            hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL
            ).decode("utf-8").strip()
        except Exception:
            hash = "unknown-git-hash"

    # Look for uncommited changes
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        if status:
            dirty = True
    except Exception:
        pass

    if tag is not None and not dirty:
        version = f"{tag}"
    elif tag is not None and dirty:
        version = f"{tag}-DIRTY"
    elif tag is None and not dirty:
        version = f"{timestamp}-{hash}"
    else:
        version = f"{timestamp}-{hash}-DIRTY"


    version_file = os.path.join("src", "_version.py")
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(f'__version__ = "{version}"\n')
        f.write(f'__build_time__ = "{timestamp}"\n')
    print(f"Generated {version_file} with version: {version}")


if __name__ == "__main__":
    write_version()