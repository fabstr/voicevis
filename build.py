import subprocess
import sys
import PyInstaller.__main__
import os
from src.generate_version import write_version

def remove_generated_files():
    files = [
        os.path.join("resources", "SBOM.json"),
        os.path.join("resources", "docs", "99_dependencies.json"),
        os.path.join("src", "_version.py")
    ]

    for file in files:
        if os.path.exists(file):
            os.remove(file)

def write_dependencies():
    print("Generating License Markdown file...")
    path = os.path.join("resources", "docs", "99_dependencies.md")
    try:
        # Run pip-licenses to generate the human-readable Markdown SBOM
        subprocess.run([
            "pip-licenses",
            "--format=markdown",
            "--with-urls",
            "--with-description",
            "--with-authors",
            f"--output-file={path}"
        ], check=True)

    except subprocess.CalledProcessError as e:
        print(f"Failed to generate SBOMs. Build aborted. Error: {e}")
        sys.exit(1)

    # Prepend a heading
    with open(path, "r", encoding="utf-8") as f:
        sbom_content = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Dependencies\n\n")
        f.write("An SBOM in JSON is available in the resources folder.\n\n")
        f.write(sbom_content)


def write_sbom():
    print("Generating CycloneDX JSON SBOM...")
    try:
        # Run cyclonedx-py to generate the machine-readable JSON SBOM
        subprocess.run([
            "cyclonedx-py",
            "requirements",
            "requirements.txt",
            "--output-format", "JSON",
            "-o", str(os.path.join("resources", "SBOM.json"))
        ], check=True)

    except FileNotFoundError as e:
        print(f"Tool not found: {e.filename}. Ensure cyclonedx-bom are installed.")
        sys.exit(1)


def build():
    try:
        remove_generated_files()

        write_version()
        write_dependencies()
        write_sbom()

        print("Starting PyInstaller build...")
        PyInstaller.__main__.run(['VoiceVis.spec'])

    finally:
        remove_generated_files()


if __name__ == "__main__":
    build()