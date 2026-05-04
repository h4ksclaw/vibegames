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
