"""Command-line entrypoint for the SuperShield API."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Run the API with container-safe defaults."""

    uvicorn.run(
        "supershield.api:app",
        host=os.getenv("SUPERSHIELD_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("SUPERSHIELD_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
