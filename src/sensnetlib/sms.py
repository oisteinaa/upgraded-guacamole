#!/usr/bin/env python3
"""Send the example Telkit SMS using TELKIT_API_KEY from the environment."""

import os
import sys

import requests

TELKIT_API_KEY = "tk_BH9M6QawD9nrim32qySe25_mtiqRac7sG8z3ulHqx9VmqT8xKJScwGkbywupAtyAi6"
def main():
    api_key = os.environ.get("TELKIT_API_KEY", TELKIT_API_KEY)
    if not api_key:
        print("Set TELKIT_API_KEY in your environment before running this script.", file=sys.stderr)
        return 1

    try:
        response = requests.post(
            "https://api.telkit.no/v1/sms",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # Reuse for retries of this message; change for a new message.
                "Idempotency-Key": "ordre-2041-hentemelding",
            },
            json={
                "to": "+4791317837",
                "text": "Hei! Pakken din er klar til henting.",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"Telkit request failed: {exc}", file=sys.stderr)
        return 1

    if not response.ok:
        print(f"Telkit HTTP {response.status_code}: {response.text}", file=sys.stderr)
        return 1

    print(response.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
