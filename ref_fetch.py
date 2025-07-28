#!/usr/bin/env python3
# refs_fetch.py

import os
import sys
import argparse
import json
import subprocess
import warnings
import re
import shutil
import tomli
from typing import Dict, Any, Union
import requests
from ddgs import DDGS

# --- Configuration ---

# The root directory for caching fetched repositories.
# Can be overridden by the REFS_FETCH_CACHE environment variable.
REFS_FETCH_CACHE = os.path.expanduser(
    os.environ.get("REFS_FETCH_CACHE", "~/.cache/refs-fetch")
)

# The file for storing user's repository choices.
CHOICES_CACHE_FILE = os.path.join(REFS_FETCH_CACHE, "choices.json")

def load_choices_cache() -> Dict[str, str]:
    """Loads the repository choices cache from a JSON file."""
    if not os.path.exists(CHOICES_CACHE_FILE):
        return {}
    try:
        with open(CHOICES_CACHE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_choices_cache(cache: Dict[str, str]):
    """Saves the repository choices cache to a JSON file."""
    try:
        os.makedirs(REFS_FETCH_CACHE, exist_ok=True)
        with open(CHOICES_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except IOError:
        print(f"  [WARN] Could not save choices cache to {CHOICES_CACHE_FILE}")


# Suppress the specific NotOpenSSLWarning by its message content.
warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL 1.1.1+",
)

# --- Standard Library Fetching ---

def get_core_tool_version(project_path: str, ecosystem: str) -> Union[str, None]:
    """Parses .mise.toml to find the version of the core tool (python, node, etc.)."""
    mise_path = os.path.join(project_path, '.mise.toml')
    if not os.path.exists(mise_path):
        print(f"  [WARN] '.mise.toml' not found. Cannot fetch standard library.")
        return None
    
    try:
        with open(mise_path, 'rb') as f:
            config = tomli.load(f)
        
        tool_name = 'python' if ecosystem == 'pip' else ecosystem
        version = config.get('tools', {}).get(tool_name)
        if version:
            print(f"  [INFO] Found {tool_name} version {version} in .mise.toml")
            return version
    except tomli.TOMLDecodeError as e:
        print(f"  [ERROR] Could not parse '.mise.toml': {e}")
    return None

def fetch_std_lib(project_path: str, ecosystem: str, version: str, debug: bool = False):
    """Fetches the standard library for a given ecosystem and version."""
    STD_LIB_REPOS = {
        "pip": "https://github.com/python/cpython",
        "swift": "https://github.com/apple/swift",
        "npm": "https://github.com/nodejs/node"
    }
    
    repo_url = STD_LIB_REPOS.get(ecosystem)
    if not repo_url:
        print(f"  [WARN] No standard library repository defined for '{ecosystem}'.")
        return

    pkg_name = "cpython" if ecosystem == "pip" else "swift" if ecosystem == "swift" else "node"
    print(f"\n--- Processing Standard Library: {pkg_name}=={version} ---")
    output_dir = os.path.join(project_path, 'refs', ecosystem, pkg_name, version)
    clone_and_checkout(repo_url, version, output_dir, debug)

# --- Python Ecosystem Logic ---

def get_installed_python_packages(project_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Gets a dictionary of installed Python packages with their version and any locally
    found repository URL.
    """
    venv_path = os.path.join(project_path, '.venv')
    python_executable = os.path.join(venv_path, 'bin', 'python')

    if not os.path.exists(python_executable):
        print(f"Error: Python executable not found at '{python_executable}'", file=sys.stderr)
        return {}

    script = """
import json
import sys
try:
    from importlib import metadata
except ImportError:
    import importlib_metadata as metadata

packages = {}
for dist in metadata.distributions():
    pkg_name = dist.metadata['name']
    repo_url = None
    if dist.metadata.get('project-url'):
        for url_info in dist.metadata.get_all('project-url'):
            name, url = url_info.split(', ')
            if 'source' in name.lower() or 'repository' in name.lower() or 'homepage' in name.lower():
                repo_url = url
                break
    packages[pkg_name] = {'version': dist.version, 'repo_url': repo_url}

sys.stdout.write(json.dumps(packages))
"""
    try:
        result = subprocess.run(
            [python_executable, '-c', script],
            capture_output=True, text=True, check=True
        )
        packages = json.loads(result.stdout)
        for noisy_pkg in ['pip', 'setuptools', 'wheel', 'pkg-resources', 'importlib-metadata']:
            packages.pop(noisy_pkg, None)
        return packages
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error inspecting Python environment: {e}", file=sys.stderr)
        return {}

def get_pypi_repo_url(package_name: str, debug: bool = False) -> Union[str, None]:
    """Queries the PyPI API for a package's repository URL."""
    if debug: print(f"  [DEBUG] Querying PyPI API for '{package_name}'...")
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        urls = data.get("info", {}).get("project_urls")
        if urls:
            for key, value in urls.items():
                if 'source' in key.lower() or 'repository' in key.lower() or 'homepage' in key.lower():
                    if value and is_git_repo(value):
                        return normalize_to_repo_root(value)
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        if debug: print(f"  [DEBUG] Could not query PyPI API: {e}")
        return None

# --- Node.js Ecosystem Logic ---

def get_installed_node_packages(project_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Gets a dictionary of installed Node.js packages by reading package.json
    files in node_modules.
    """
    node_modules_path = os.path.join(project_path, 'node_modules')
    if not os.path.isdir(node_modules_path):
        print(f"Error: 'node_modules' directory not found in '{project_path}'", file=sys.stderr)
        return {}

    packages = {}
    for dir_name in os.listdir(node_modules_path):
        pkg_path = os.path.join(node_modules_path, dir_name)
        if os.path.isdir(pkg_path):
            package_json_path = os.path.join(pkg_path, 'package.json')
            if os.path.exists(package_json_path):
                try:
                    with open(package_json_path, 'r') as f:
                        data = json.load(f)
                    packages[data['name']] = {'version': data['version'], 'repo_url': None}
                except (json.JSONDecodeError, KeyError):
                    continue
    return packages

def get_npm_repo_url(package_name: str, debug: bool = False) -> Union[str, None]:
    """Queries the npm registry for a package's repository URL."""
    if debug: print(f"  [DEBUG] Querying npm registry for '{package_name}'...")
    try:
        url = f"https://registry.npmjs.org/{package_name}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        repo_info = data.get('repository')
        if isinstance(repo_info, dict) and repo_info.get('url'):
            repo_url = repo_info['url']
            if repo_url.startswith('git+'): repo_url = repo_url[4:]
            if repo_url.endswith('.git'): repo_url = repo_url[:-4]
            return normalize_to_repo_root(repo_url)
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        if debug: print(f"  [DEBUG] Could not query npm registry: {e}")
        return None

# --- Swift Ecosystem Logic ---

def get_installed_swift_packages(project_path: str) -> Dict[str, Dict[str, Any]]:
    """
    Gets a dictionary of installed Swift packages by parsing the Package.resolved file.
    """
    resolved_path = os.path.join(project_path, 'Package.resolved')
    if not os.path.exists(resolved_path):
        print(f"Error: 'Package.resolved' file not found in '{project_path}'", file=sys.stderr)
        return {}

    packages = {}
    try:
        with open(resolved_path, 'r') as f:
            data = json.load(f)
        
        pins = data.get('pins', []) if 'pins' in data else data.get('objects', [])

        for pin in pins:
            if 'package' in pin: # v1 format
                pkg_name = pin['package']
                repo_url = pin['repositoryURL']
                version = pin['state'].get('version') or pin['state'].get('revision')
            else: # v2 format
                pkg_name = pin['identity']
                repo_url = pin['location']
                version = pin['state'].get('version') or pin['state'].get('revision')
            
            packages[pkg_name] = {'version': version, 'repo_url': repo_url}
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing 'Package.resolved': {e}", file=sys.stderr)
        return {}
    return packages

# --- Generic and Shared Logic ---

def search_for_repo_url(package_name: str, version: str, choices_cache: Dict[str, str], debug: bool = False) -> Union[str, None]:
    """Tier 3: Searches the web, enriches results, and prompts the user."""
    # Check for a cached choice first
    if package_name in choices_cache:
        cached_url = choices_cache[package_name]
        print(f"  [INFO] Using cached repository choice for '{package_name}': {cached_url}")
        return cached_url

    print(f"  [INFO] No registry URL found. Searching web for '{package_name}' repository...")
    query = f"{package_name} {version} source repository github"
    
    candidate_urls = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=15))
        
        if debug: print(f"  [DEBUG] Web search results for '{query}':\n{json.dumps(results, indent=2)}")

        unique_repos = set()
        for result in results:
            url = result.get("href")
            if url and is_git_repo(url):
                repo_root = normalize_to_repo_root(url)
                if repo_root and repo_root not in unique_repos:
                    unique_repos.add(repo_root)
                    candidate_urls.append(repo_root)
                    if len(candidate_urls) >= 5: break
        
        if not candidate_urls: return None

        enriched_candidates = [get_github_repo_info(url, debug) for url in candidate_urls]
        enriched_candidates = [info for info in enriched_candidates if info]

        print(f"  [PROMPT] Found multiple possible repositories for '{package_name}'. Please choose one:")
        for i, info in enumerate(enriched_candidates):
            print(f"    {i+1}) {info['url']} (★ {info['stars']}, Last Push: {info['last_push']})")
            print(f"       - {info['description']}")
        print("    0) Skip this package")

        while True:
            try:
                choice = int(input(f"  Enter your choice [0-{len(enriched_candidates)}]: "))
                if 0 <= choice <= len(enriched_candidates):
                    if choice == 0:
                        return None
                    
                    chosen_url = enriched_candidates[choice-1]['url']
                    choices_cache[package_name] = chosen_url
                    save_choices_cache(choices_cache)
                    return chosen_url
            except (ValueError, IndexError): pass
            print("  Invalid choice. Please try again.")

    except Exception as e:
        if debug: print(f"  [DEBUG] Error during web search: {e}")
    return None

def get_github_repo_info(repo_url: str, debug: bool = False) -> Union[Dict[str, Any], None]:
    """Fetches stars, last push date, and description from the GitHub API."""
    repo_root = normalize_to_repo_root(repo_url)
    if not repo_root: return None
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_root)
    if not match: return None
    owner, repo = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "url": repo_root,
            "stars": data.get("stargazers_count", 0),
            "last_push": data.get("pushed_at", "N/A").split("T")[0],
            "description": data.get("description", "No description available.")
        }
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        if debug: print(f"  [DEBUG] Could not query GitHub API for {repo_root}: {e}")
        return {"url": repo_root, "stars": "N/A", "last_push": "N/A", "description": "Could not fetch details."}

def is_git_repo(url: str) -> bool:
    """Checks if a URL is a known git hosting domain."""
    return 'github.com' in url or 'gitlab.com' in url

def normalize_to_repo_root(url: str) -> Union[str, None]:
    """Normalizes a deep-link URL to its git repository root."""
    match = re.search(r"(https://github\.com/[^/]+/[^/]+)", url)
    if match: return match.group(1)
    match = re.search(r"(https://gitlab\.com/[^/]+/[^/]+)", url)
    if match: return match.group(1)
    return None

def clone_and_checkout(repo_url: str, version: str, output_path: str, debug: bool = False):
    """
    Clones a repository from a cache or from the source, then checks out the
    specific version tag or commit into the output path.
    """
    if os.path.exists(output_path):
        print(f"  [INFO] Directory already exists: {output_path}. Skipping.")
        return

    # Generate a cache-friendly name from the repo URL
    cache_repo_name = re.sub(r'[^a-zA-Z0-9]', '_', repo_url)
    cache_repo_path = os.path.join(REFS_FETCH_CACHE, cache_repo_name)

    # --- Step 1: Ensure we have a valid, up-to-date mirror in the cache ---
    if os.path.exists(cache_repo_path):
        print(f"  [CACHE] Found existing cache: {cache_repo_path}. Fetching updates...")
        try:
            # For a mirror, 'git remote update' fetches all changes from all remotes.
            subprocess.run(['git', 'remote', 'update'],
                           cwd=cache_repo_path, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"  [WARN] Failed to update cache for {repo_url}. Removing and re-cloning. Error: {e.stderr.strip()}")
            shutil.rmtree(cache_repo_path)
            clone_to_cache(repo_url, cache_repo_path, debug)
    else:
        clone_to_cache(repo_url, cache_repo_path, debug)

    # --- Step 2: Clone from local cache to the final destination ---
    if not os.path.exists(cache_repo_path):
        print(f"  [ERROR] Failed to get a valid copy of the repository in the cache.")
        return

    try:
        print(f"  [INFO] Cloning from local cache to {output_path}...")
        # Clone from the bare repo in the cache to create a working directory
        subprocess.run(['git', 'clone', cache_repo_path, output_path],
                       check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Failed to clone from cache to output directory: {e.stderr.strip()}")
        if os.path.exists(output_path): # cleanup partial clone
            shutil.rmtree(output_path)
        return

    # --- Step 3: Checkout the correct version in the destination directory ---
    tags_to_try = [version, f'v{version}', f'release-{version}']
    checked_out = False
    for tag in tags_to_try:
        try:
            subprocess.run(['git', 'checkout', f'tags/{tag}'],
                           cwd=output_path, check=True, capture_output=True, text=True)
            print(f"  [SUCCESS] Checked out tag '{tag}' in {output_path}.")
            checked_out = True
            break
        except subprocess.CalledProcessError as e:
            if debug: print(f"  [DEBUG] Could not checkout tag '{tag}': {e.stderr.strip()}")

    if not checked_out:
        print(f"  [WARN] Could not find a matching tag for version {version}. Leaving on default branch.")

    # Clean up .git directory for a clean export
    git_dir = os.path.join(output_path, '.git')
    if os.path.exists(git_dir):
        shutil.rmtree(git_dir)

def clone_to_cache(repo_url: str, cache_path: str, debug: bool = False):
    """Clones a repository as a mirror into the specified cache directory."""
    print(f"  [CACHE] Cloning {repo_url} into cache (mirror): {cache_path}...")
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        # Clone as a bare mirror to act as a local source
        subprocess.run(['git', 'clone', '--mirror', repo_url, cache_path],
                       check=True, capture_output=True, text=True)
        print(f"  [CACHE] Successfully cloned to cache.")
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Failed to clone repository into cache: {e.stderr.strip()}")
        # If cloning fails, clean up any partial directory
        if os.path.exists(cache_path):
            shutil.rmtree(cache_path)

def main():
    """Main function to fetch library source code."""
    parser = argparse.ArgumentParser(description="Clone the source repositories for installed libraries.")
    parser.add_argument("ecosystem", choices=['pip', 'npm', 'swift'], help="The package ecosystem to process.")
    parser.add_argument("path", nargs='?', default='.', help="Path to the project directory.")
    parser.add_argument("--debug", action="store_true", help="Enable debug output for git and API commands.")
    args = parser.parse_args()

    project_path = os.path.abspath(args.path)
    if not os.path.isdir(project_path):
        print(f"Error: Path '{project_path}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    choices_cache = load_choices_cache()
    print(f"Inspecting '{args.ecosystem}' environment in: {project_path}")
    
    # Step 1: Fetch the standard library
    core_version = get_core_tool_version(project_path, args.ecosystem)
    if core_version:
        fetch_std_lib(project_path, args.ecosystem, core_version, args.debug)

    # Step 2: Fetch the ecosystem packages
    packages = {}
    if args.ecosystem == 'pip':
        packages = get_installed_python_packages(project_path)
    elif args.ecosystem == 'npm':
        packages = get_installed_node_packages(project_path)
    elif args.ecosystem == 'swift':
        packages = get_installed_swift_packages(project_path)

    if not packages:
        print("No third-party packages found to document.")
        sys.exit(0)
        
    print("\nFound third-party packages to document:")
    for pkg, info in sorted(packages.items()):
        version, repo_url = info.get('version'), info.get('repo_url')
        print(f"\n--- Processing: {pkg}=={version} ---")
        
        if repo_url and is_git_repo(repo_url):
            repo_url = normalize_to_repo_root(repo_url)
            print(f"  [INFO] Found local repository URL: {repo_url}")
        else:
            if args.ecosystem == 'pip':
                repo_url = get_pypi_repo_url(pkg, debug=args.debug)
            elif args.ecosystem == 'npm':
                repo_url = get_npm_repo_url(pkg, debug=args.debug)
            
            if repo_url:
                print(f"  [INFO] Found registry repository URL: {repo_url}")
            elif version:
                repo_url = search_for_repo_url(pkg, version, choices_cache, debug=args.debug)

        if repo_url and version:
            output_dir = os.path.join(project_path, 'refs', args.ecosystem, pkg, version)
            clone_and_checkout(repo_url, version, output_dir, debug=args.debug)
        elif not repo_url:
            print(f"  [ERROR] Could not find a repository URL for {pkg} after all attempts.")
        elif not version:
            print(f"  [ERROR] Could not determine the version for {pkg}.")

if __name__ == "__main__":
    main()
