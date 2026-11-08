"""Local UI/API boundaries without an authentication service."""

from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from bottleneck_analyzer.api.settings import APISettings


class LocalBoundary:
    def __init__(self, app, port: int, settings: APISettings):
        self.app, self.port, self.settings = app, port, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope["headers"]:
            headers.setdefault(key, []).append(value.decode("latin-1"))

        async def reject(status, code):
            await JSONResponse(
                {"error": {"code": code, "message": code.replace("_", " ")}}, status_code=status
            )(scope, receive, send)

        # Preserve the original infrastructure health probes. All other routes,
        # including docs and static assets, require an explicit loopback authority.
        if scope["path"] not in ("/health", "/health/database"):
            hosts = headers.get(b"host", [])
            if len(hosts) != 1:
                return await reject(400, "invalid_host")
            try:
                authority = urlsplit("http://" + hosts[0])
                valid = (
                    authority.hostname in {"localhost", "127.0.0.1", "::1"}
                    and (authority.port or 80) == self.port
                    and authority.username is None
                    and authority.password is None
                    and not authority.path
                    and not authority.query
                    and not authority.fragment
                )
            except ValueError:
                valid = False
            if not valid:
                return await reject(400, "invalid_host")
            origins = headers.get(b"origin", [])
            if origins and (len(origins) != 1 or origins[0] != "http://" + hosts[0]):
                return await reject(403, "invalid_origin")
            if scope["method"] == "OPTIONS":
                return await reject(403, "cross_origin_disabled")
            if headers.get(b"sec-fetch-site", [""])[0] == "cross-site":
                return await reject(403, "cross_site_disabled")
        if scope["method"] == "POST":
            if headers.get(b"content-type", [""])[0].split(";")[0].strip() != "application/json":
                return await reject(415, "json_required")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.settings.maximum_body_bytes:
                    return await reject(413, "request_too_large")
                if not message.get("more_body", False):
                    break
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            incoming = replay
        else:
            incoming = receive

        async def secured(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self'; connect-src 'self'; img-src 'self'; "
                        b"object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                        b"form-action 'self'",
                    ),
                ]
            await send(message)

        await self.app(scope, incoming, secured)
