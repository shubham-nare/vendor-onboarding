"""The page the browser app runs in: one static HTML file with no inline scripts, served under a strict
Content-Security-Policy. The app (/static/app.js) draws the screen from the JSON API."""

from pathlib import Path

from fastapi.responses import FileResponse

STATIC = Path(__file__).resolve().parent / "static"
# Only our own script file and Tailwind may run on app screens; no inline scripts, nothing from other sites.
APP_CSP = ("default-src 'self'; script-src 'self' https://cdn.tailwindcss.com; "
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
           "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def app_shell() -> FileResponse:
    return FileResponse(STATIC / "console.html", media_type="text/html",
                        headers={"Content-Security-Policy": APP_CSP, "Cache-Control": "no-store", "Referrer-Policy": "same-origin"})
