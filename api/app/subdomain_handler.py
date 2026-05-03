import mimetypes

from fastapi import HTTPException
from fastapi import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from starlette.requests import Request
from starlette.responses import Response as StarletteResponse

from app import github
from app.database import get_db
from app.project_naming import extract_subdomain
from app.project_naming import find_project_by_name_case_insensitive
from app.project_naming import get_host_from_headers
from app.project_naming import sanitize_project_name
from app.settings import settings


def _guess_media_type(path: str, content: bytes | str) -> str:
    """Guess the media type from the file path, falling back to sniffing."""
    guessed, _ = mimetypes.guess_type(path)
    if guessed:
        return guessed
    # Fallback: check for common binary signatures
    if isinstance(content, bytes):
        if content[:4] == b"\x89PNG":
            return "image/png"
        if content[:2] == b"\xff\xd8":
            return "image/jpeg"
        if content[:4] == b"GIF8":
            return "image/gif"
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        if content[:4] == b"\x1a\x45\xdf\xa3":
            return "video/webm"
        if content[:4] == b"fLaC":
            return "audio/flac"
        if content[:8] == b"\x00\x00\x00\x18ftypmp4" or content[:8] == b"\x00\x00\x00\x1cftypmp4":
            return "video/mp4"
        if content[:3] == b"ID3" or content[:4] == b"\xff\xfb" or content[:4] == b"\xff\xf3":
            return "audio/mpeg"
        if content[:8] == b"\x89PNG\x0d\x0a\x1a\x0a":
            return "image/png"
    # Default
    return "application/octet-stream"


class SubdomainStaticFiles(StaticFiles):
    """Custom StaticFiles that handles subdomain-based game serving."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope) -> StarletteResponse:
        """Override to check for subdomain games first."""

        if settings.ENABLE_SUBDOMAINS:
            request = Request(scope)
            host = get_host_from_headers(dict(request.headers))

            if host:
                subdomain = extract_subdomain(host, settings.BASE_DOMAIN)
                if subdomain:
                    # Try to serve the game directly
                    db: Session = next(get_db())
                    try:
                        # Find project with case-insensitive sanitized lookup
                        game = find_project_by_name_case_insensitive(db, subdomain)

                        if game:
                            # Try serving the requested path first
                            requested_path = path if path else "index.html"
                            try:
                                # Check if this looks like a binary file (has an extension
                                # that's typically binary)
                                guessed_type, _ = mimetypes.guess_type(requested_path)
                                is_binary = guessed_type and not guessed_type.startswith("text/")

                                if is_binary:
                                    content = github.get_raw_file_content(game.project, requested_path)
                                else:
                                    content = github.get_file_content(game.project, requested_path)

                                media_type = _guess_media_type(requested_path, content)

                                # Update the number of opens for the game.
                                game.num_opens += 1
                                flag_modified(game, "num_opens")
                                db.commit()
                                return Response(content, media_type=media_type)
                            except github.GithubFileNotFoundError:
                                # If the specific file wasn't found, fall back to index.html
                                # (SPA-style routing)
                                if requested_path != "index.html":
                                    try:
                                        content = github.get_file_content(game.project, "index.html")
                                        # Update the number of opens for the game.
                                        game.num_opens += 1
                                        flag_modified(game, "num_opens")
                                        db.commit()
                                        return Response(content, media_type="text/html")
                                    except github.GithubFileNotFoundError:
                                        pass
                                raise

                        # If project not found, return detailed 404
                        sanitized_subdomain = sanitize_project_name(subdomain)
                        raise HTTPException(
                            status_code=404,
                            detail=f"Game project '{subdomain}' (sanitized: '{sanitized_subdomain}') not found",
                        )
                    finally:
                        db.close()

        # Fall back to regular static file serving
        return await super().get_response(path, scope)
