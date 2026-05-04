import base64
import mimetypes
import re
from functools import lru_cache

import requests

from app.settings import settings


class GithubFileNotFoundError(Exception):
    """Custom exception for file not found in GitHub repository."""


class GithubNoLastCommitError(Exception):
    """Custom exception for no last commit found in GitHub repository."""


@lru_cache
def get_repo_owner_and_name(repo_url: str) -> tuple[str, str]:
    repo_url = settings.GITHUB_REPOSITORY
    repo_owner_match = re.search(r"github\.com/([^/]+)/", repo_url)
    repo_name_match = re.search(r"github\.com/[^/]+/(.+)", repo_url)
    if not repo_owner_match or not repo_name_match:
        raise ValueError("Invalid GitHub repository URL")
    repo_owner = repo_owner_match.group(1)
    repo_name = repo_name_match.group(1).removesuffix(".git")

    return repo_owner, repo_name


@lru_cache
def get_token_user() -> str:
    """Returns the username of the authenticated GitHub user."""
    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    resp = requests.get("https://api.github.com/user", headers=headers)
    resp.raise_for_status()
    return resp.json()["login"]


def _get_file_api_url(project: str, path: str) -> str:
    """Build the GitHub Contents API URL for a project file."""
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    return f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}/{path}"


def update_or_create_file(path: str, content: str, project: str) -> None:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    # Construct the GitHub API URL.
    # Files will reside under: {GAMES_PATH}/{project}/{path}
    api_url = (
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}/{path}"
    )

    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    get_resp = requests.get(api_url, headers=headers)

    # Prepare content for commit (GitHub requires the content in base64)
    content_bytes = content.encode()
    content_encoded = base64.b64encode(content_bytes).decode()

    commit_message = "Update file via API"
    data = {"message": commit_message, "content": content_encoded}

    if get_resp.status_code == 200:
        file_info = get_resp.json()
        data["sha"] = file_info.get("sha")
    elif get_resp.status_code != 404:
        # If it's neither found nor a clear "not found", something is wrong.
        get_resp.raise_for_status()

    put_resp = requests.put(api_url, json=data, headers=headers)
    put_resp.raise_for_status()


def get_file_content(project: str, path: str | None = None) -> str:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}"

    path = path or "index.html"
    base_url = f"{base_url}/{path}"
    resp = requests.get(
        base_url,
        headers={"Authorization": f"token {settings.GITHUB_API_TOKEN}", "Accept": "application/vnd.github.raw+json"},
    )
    if resp.status_code == 200:
        return resp.text
    else:
        raise GithubFileNotFoundError(f"File not found: {base_url}")


def get_raw_file_content(project: str, path: str | None = None) -> bytes:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}"

    path = path or "index.html"
    base_url = f"{base_url}/{path}"
    resp = requests.get(
        base_url,
        headers={"Authorization": f"token {settings.GITHUB_API_TOKEN}"},
    )
    if resp.status_code == 200:
        json_data = resp.json()
        if "download_url" in json_data:
            # If the file is large, GitHub provides a download URL
            download_url = json_data["download_url"]
            resp = requests.get(download_url, headers={"Authorization": f"token {settings.GITHUB_API_TOKEN}"})
            resp.raise_for_status()
            return resp.content
        # Decode the content from base64
        content = json_data.get("content")
        if content:
            decoded_content = base64.b64decode(content)
            return decoded_content
        else:
            raise GithubFileNotFoundError(f"File content is empty: {base_url}")
    else:
        raise GithubFileNotFoundError(f"File not found: {base_url}")


def get_file_content_with_type(project: str, path: str | None = None) -> tuple[bytes, str]:
    """Fetch a file via GitHub's download_url and return (content, content_type).

    Uses raw.githubusercontent.com which provides accurate Content-Type
    headers, falling back to mimetypes.guess_type() if the header is missing.
    """
    path = path or "index.html"
    api_url = _get_file_api_url(project, path)

    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    resp = requests.get(api_url, headers=headers, timeout=10)
    if resp.status_code == 404:
        raise GithubFileNotFoundError(f"File not found: {api_url}")
    resp.raise_for_status()

    json_data = resp.json()

    # GitHub returns a JSON array when the path is a directory, not a file
    if isinstance(json_data, list):
        raise GithubFileNotFoundError(f"Path is a directory, not a file: {api_url}")

    download_url = json_data.get("download_url")
    if not download_url:
        raise GithubFileNotFoundError(f"No download URL for file: {api_url}")

    # Fetch from the download URL — raw.githubusercontent.com sets correct Content-Type
    dl_resp = requests.get(download_url, headers={"Authorization": f"token {settings.GITHUB_API_TOKEN}"}, timeout=10)
    dl_resp.raise_for_status()

    content_type = dl_resp.headers.get("Content-Type", "")
    # GitHub sometimes returns charset info, strip it for cleanliness
    if ";" in content_type:
        content_type = content_type.split(";")[0].strip()

    # Fallback to mimetypes if GitHub didn't provide a useful content-type
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(path)
        if guessed:
            content_type = guessed

    return dl_resp.content, content_type or "application/octet-stream"


def get_file_url(project: str, path: str | None = None) -> str:
    """Returns github UI URL to the file."""
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    return f"https://www.github.com/{repo_owner}/{repo_name}/blob/main/{settings.PROJECTS_PATH}/{project}/{path or 'index.html'}"


def delete_file(project: str, path: str) -> None:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    api_url = (
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}/{path}"
    )
    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    # Get the SHA of the file to delete
    get_resp = requests.get(api_url, headers=headers, timeout=10)
    if get_resp.status_code == 404:
        raise GithubFileNotFoundError(f"File not found: {path}")
    get_resp.raise_for_status()
    file_info = get_resp.json()
    sha = file_info.get("sha")
    body = {
        "message": "Delete file via API",
        "sha": sha,
    }
    resp = requests.delete(api_url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    if resp.status_code != 200:
        raise GithubFileNotFoundError(f"File not found: {path}")


def delete_project(project: str) -> None:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    # Loop through all files in the project and delete them
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}/{project}"
    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    files_resp = requests.get(api_url, headers=headers, timeout=10)
    files_resp.raise_for_status()
    files = files_resp.json()
    for file in files:
        file_path = file["path"]
        delete_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        body = {
            "message": "Delete file via API",
            "sha": file["sha"],
        }
        delete_resp = requests.delete(delete_url, headers=headers, json=body, timeout=10)
        delete_resp.raise_for_status()


def get_projects() -> list[str]:
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{settings.PROJECTS_PATH}"
    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    resp = requests.get(api_url, headers=headers, timeout=10)
    resp.raise_for_status()
    return [item["name"] for item in resp.json() if item["type"] == "dir"]


def is_last_committer_token_user(project: str, path: str) -> bool:
    """
    Checks if the last person who committed to a file is the same as the token user.
    Returns True if the last committer matches the token user, False otherwise.
    """
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    file_path = f"{settings.PROJECTS_PATH}/{project}/{path}"

    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    commits_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
    params: dict[str, str | int] = {"path": file_path, "per_page": 1}

    resp = requests.get(commits_url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()

    commits = resp.json()
    if not commits:
        return False

    token_user = get_token_user()
    last_committer = commits[0]["commit"]["author"]["name"]

    return token_user == last_committer


def revert_file_to_previous_commit(project: str, path: str) -> None:
    """
    Reverts a file to its previous commit version.
    Raises GithubFileNotFoundError if the file doesn't exist.
    """
    repo_owner, repo_name = get_repo_owner_and_name(settings.GITHUB_REPOSITORY)
    file_path = f"{settings.PROJECTS_PATH}/{project}/{path}"

    headers = {"Authorization": f"token {settings.GITHUB_API_TOKEN}"}
    commits_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
    params = {"path": file_path}

    resp = requests.get(commits_url, headers=headers, params=params)
    resp.raise_for_status()

    commits = resp.json()
    if not commits:
        raise GithubFileNotFoundError(f"File not found or has no commit history: {path}")

    # Get the last commit SHA for this specific file
    if len(commits) < 2:
        raise GithubNoLastCommitError(f"No previous commit found for file: {path}")

    last_commit_sha = commits[1]["sha"]
    content_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}?ref={last_commit_sha}"

    content_resp = requests.get(content_url, headers=headers)
    if content_resp.status_code != 200:
        raise GithubFileNotFoundError(f"Could not retrieve file version: {path}")

    file_content = base64.b64decode(content_resp.json()["content"]).decode()
    update_or_create_file(path, file_content, project)
