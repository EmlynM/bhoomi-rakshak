import asyncio
from playwright.async_api import async_playwright
import sqlite3
import os
import shutil
import time

DB_FILE = 'bhoomi.db'

def get_survey_data(limit=2):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Find normal survey numbers with length 4
    cursor.execute("""
        SELECT s.survey_no, s.extent, c.name as crop, cul.name as name
        FROM survey_numbers s
        JOIN crops c ON s.crop_id = c.id
        JOIN cultivators cul ON s.cultivator_id = cul.id
        WHERE length(s.survey_no) = 4
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

async def show_caption(page, text, duration_ms=3000):
    await page.evaluate(f"""() => {{
        let existing = document.getElementById('demo-caption');
        if (existing) existing.remove();
        let d = document.createElement('div');
        d.id = 'demo-caption';
        d.innerText = `{text}`;
        d.style.position = 'fixed';
        d.style.bottom = '40px';
        d.style.left = '50%';
        d.style.transform = 'translateX(-50%)';
        d.style.backgroundColor = 'rgba(11, 19, 43, 0.9)';
        d.style.color = 'white';
        d.style.padding = '15px 30px';
        d.style.fontSize = '24px';
        d.style.fontWeight = 'bold';
        d.style.borderRadius = '8px';
        d.style.boxShadow = '0 10px 25px rgba(0,0,0,0.3)';
        d.style.zIndex = '9999';
        d.style.textAlign = 'center';
        document.body.appendChild(d);
    }}""")
    await page.wait_for_timeout(duration_ms)

async def hide_caption(page):
    await page.evaluate("""() => {
        let existing = document.getElementById('demo-caption');
        if (existing) existing.remove();
    }""")

async def record_detailed_demo():
    if not os.path.exists('videos'):
        os.makedirs('videos')

    surveys = get_survey_data(2)
    s1, extent1, crop1, name1 = surveys[0]
    s2, extent2, crop2, name2 = surveys[1]
    
    # We will pick a definitely wrong crop for s2
    wrong_crop = "Soybean" if crop2 != "Soybean" else "Wheat"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir="videos/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        await page.goto("http://localhost:5000/")
        await page.wait_for_timeout(1000)

        # --- FEATURE 1: Live Lookup ---
        await show_caption(page, "Feature 1: Live Ground-Truth Lookup", 2500)
        
        await page.fill("#survey_no", s1)
        await show_caption(page, "Clerk types survey number...", 1500)
        await page.wait_for_selector("#live-register-data", state="visible")
        
        await show_caption(page, "Register data is instantly fetched to prevent manual errors.", 3000)
        await page.fill("#cultivator_name", name1)
        await page.select_option("#claimed_crop", label=crop1)
        await page.fill("#claimed_extent", str(extent1))
        
        await show_caption(page, "Submitting a perfectly clean claim...", 2000)
        await page.click("#submit-btn")
        
        await page.wait_for_selector(".message.success", state="visible")
        await show_caption(page, "Success! No flags raised.", 3000)
        await hide_caption(page)
        
        # --- FEATURE 2: Exact Duplicate Rule ---
        await page.goto("http://localhost:5000/")
        await show_caption(page, "Feature 2: Exact Duplicate Catching", 2500)
        
        await page.fill("#survey_no", s1)
        await page.wait_for_timeout(1000)
        await page.fill("#cultivator_name", name1 + " Fake")
        await page.select_option("#claimed_crop", label=crop1)
        await page.fill("#claimed_extent", str(extent1))
        
        await show_caption(page, "Someone tries to claim the same survey number again...", 3000)
        await page.click("#submit-btn")
        
        await page.wait_for_selector(".flag-annotation", state="visible")
        await show_caption(page, "System instantly flags EXACT_SURVEY_DUPLICATE!", 4000)
        await hide_caption(page)

        # --- FEATURE 3: Extent & Crop Mismatches (Multi-flags) ---
        await page.goto("http://localhost:5000/")
        await show_caption(page, "Feature 3: Multiple Rule-Based Checks", 2500)
        
        await page.fill("#survey_no", s2)
        await page.wait_for_timeout(1000)
        await page.fill("#cultivator_name", name2)
        
        # Intentional mismatches
        await page.select_option("#claimed_crop", label=wrong_crop)
        await page.fill("#claimed_extent", "999.0")
        
        await show_caption(page, "Claiming 999 acres of wrong crop (Register says " + str(extent2) + " acres of " + crop2 + ")", 4000)
        await page.click("#submit-btn")
        
        await page.wait_for_selector(".flag-annotation", state="visible")
        await show_caption(page, "System catches BOTH the Extent Mismatch AND the Crop Mismatch!", 5000)
        await hide_caption(page)
        
        # End
        await show_caption(page, "All flagged claims are now locked in the Verification Queue.", 3000)

        video_path = await page.video.path()
        await context.close()
        await browser.close()
        
        final_dest = "detailed_features_demo.webm"
        shutil.move(video_path, final_dest)
        print(f"Video saved as {final_dest}")

if __name__ == "__main__":
    asyncio.run(record_detailed_demo())
