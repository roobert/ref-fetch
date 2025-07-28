#!/usr/bin/env python3
# project_bootstrap.py

import argparse
import os
import re
import subprocess
import sys
import warnings

# Suppress the specific NotOpenSSLWarning by its message content.
# This is done before importing 'requests' to prevent the warning from
# being triggered upon its import of urllib3.
warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL 1.1.1+",
)

from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup


def get_latest_node_version() -> Optional[str]:
    """Fetches the latest stable Node.js version."""
    try:
        response = requests.get("https://nodejs.org/en/download/current")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        version_element = soup.find('p', string=re.compile(r'Version:'))
        if version_element:
            return version_element.get_text().split(':')[1].strip().lstrip('v')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Node.js version: {e}", file=sys.stderr)
    return None


def get_latest_python_version() -> Optional[str]:
    """Fetches the latest stable Python version."""
    try:
        response = requests.get("https://www.python.org/downloads/")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        version_element = soup.find('a', href=re.compile(r"/downloads/release/python-"))
        if version_element:
            return version_element.text.split()[-1]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Python version: {e}", file=sys.stderr)
    return None


def create_mise_toml(path: str, toolchain: str, versions: Dict[str, str]) -> None:
    """Creates a .mise.toml file."""
    config = ""
    if toolchain == 'python':
        config += '[env]\n'
        config += '_.python.venv = { path = ".venv", create = true }\n\n'

    config += '[tools]\n'
    for tool, version in versions.items():
        config += f'{tool} = "{version}"\n'

    with open(os.path.join(path, '.mise.toml'), 'w') as f:
        f.write(config)
    print("Created .mise.toml")


def create_version_instructions(path: str, toolchain: str) -> None:
    """Creates the .roo/rules/versions.md instruction file."""
    rules_dir = os.path.join(path, '.roo', 'rules')
    os.makedirs(rules_dir, exist_ok=True)

    content = "# Versioning Rules\n\n"
    if toolchain == 'python':
        content += "Always check the following files for version information:\n\n"
        content += "- **Python Version:** `/.mise.toml`\n"
        content += "- **Library Versions:** `/requirements.txt`\n"
    elif toolchain == 'node':
        content += "Always check the following files for version information:\n\n"
        content += "- **Node.js & npm Versions:** `/.mise.toml`\n"
        content += "- **Library Versions:** `/package.json`\n"

    rules_path = os.path.join(rules_dir, 'versions.md')
    with open(rules_path, 'w') as f:
        f.write(content)
    print(f"Created {os.path.relpath(rules_path)}")


def trust_mise_config(path: str) -> None:
    """Executes 'mise trust' in the specified directory."""
    print(f"Running 'mise trust' in {path}...")
    try:
        subprocess.run(['mise', 'trust'], cwd=path, check=True, capture_output=True, text=True)
        print("Successfully trusted .mise.toml.")
    except FileNotFoundError:
        print("Error: 'mise' command not found. Please ensure it's installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error running 'mise trust':\n{e.stderr}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main function to configure the repository."""
    parser = argparse.ArgumentParser(description="Configure a repository with the latest toolchain versions.")
    parser.add_argument("toolchain", choices=['node', 'python'], help="The toolchain to configure (node or python).")
    parser.add_argument("path", nargs='?', default='.', help="Path to the repository to configure.")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.path)
    # Create the target directory if it doesn't exist
    os.makedirs(repo_path, exist_ok=True)

    toolchain = args.toolchain
    print(f"Configuring for {toolchain} toolchain.")

    versions: Dict[str, str] = {}
    if toolchain == 'node':
        node_version = get_latest_node_version()
        if node_version:
            versions['node'] = node_version
            versions['npm'] = 'latest'
    elif toolchain == 'python':
        python_version = get_latest_python_version()
        if python_version:
            versions['python'] = python_version

    if not versions:
        print("Could not determine latest versions. Exiting.", file=sys.stderr)
        sys.exit(1)

    create_mise_toml(repo_path, toolchain, versions)
    create_version_instructions(repo_path, toolchain)
    trust_mise_config(repo_path)

    print("Repository configuration complete.")


if __name__ == "__main__":
    # Note: This script's dependencies are listed in requirements.txt
    # You can install them with: pip install -r requirements.txt
    main()
