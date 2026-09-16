"""Browser review persistence test, restricted to sensnetdb_test on port 8052."""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from psycopg2.extensions import parse_dsn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.Mapui.db import database

assert parse_dsn(os.environ["DAS_DATABASE_URL"])["dbname"] == "sensnetdb_test"
with database(write=True) as cur:
    cur.execute(
        "INSERT INTO events(id,time,type,value,comment) VALUES (-2002,'2025-05-01 12:00',1,123,'Browser review test')"
    )
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8052", wait_until="networkidle")
        page.get_by_label("Search events").fill("-2002")
        page.locator(".event-item").filter(has_text="#-2002").click()
        page.get_by_label("Review classification").select_option("3")
        page.get_by_label("Reviewer", exact=True).fill("Browser test")
        page.get_by_label("Review notes").fill(
            "Synthetic test fixture; verifies save and reload only."
        )
        page.get_by_role("button", name="Save review", exact=True).click()
        page.get_by_role("status").filter(has_text="Saved").wait_for()
        page.reload(wait_until="networkidle")
        page.get_by_label("Search events").fill("-2002")
        page.locator(".event-item").filter(has_text="#-2002").click()
        assert page.get_by_label("Review classification").input_value() == "3"
        assert page.locator(".review-entry").count() == 1
        assert "Synthetic test fixture" in page.locator(".review-entry").inner_text()
        page.get_by_label("Review classification").select_option("")
        page.get_by_label("Review notes").fill(
            "Revert synthetic fixture to unclassified."
        )
        page.get_by_role("button", name="Save review", exact=True).click()
        page.get_by_role("status").filter(has_text="Saved").wait_for()
        assert page.locator(".review-entry").count() == 2
        browser.close()
        assert not errors, errors
        print("Browser save, reload, reclassification and review history passed.")
finally:
    with database(write=True) as cur:
        cur.execute("DELETE FROM event_reviews WHERE event_id=-2002")
        cur.execute("DELETE FROM events WHERE id=-2002")
