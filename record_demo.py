import asyncio
from playwright.async_api import async_playwright
import sqlite3
import os
import shutil

DB_FILE = 'bhoomi.db'

def get_survey_data(survey_no):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.extent, c.name as crop
        FROM survey_numbers s
        JOIN crops c ON s.crop_id = c.id
        WHERE s.survey_no = ?
    """, (survey_no,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return 5.0, "Wheat"

async def record_demo():
    # Make sure videos dir exists
    if not os.path.exists('videos'):
        os.makedirs('videos')

    extent, crop = get_survey_data('154')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir="videos/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        # Step 1: Intake Screen
        await page.goto("http://localhost:5000/")
        
        # Fill Survey Number
        await page.fill("#survey_no", "154")
        
        # Wait for live data to appear
        await page.wait_for_selector("#live-register-data", state="visible")
        await page.wait_for_timeout(1000) # pause for effect
        
        # Fill the rest with a typo in the name to trigger near duplicate, 
        # but match extent and crop to avoid other flags.
        await page.fill("#cultivator_name", "Typo Name")
        await page.select_option("#claimed_crop", label=crop)
        await page.fill("#claimed_extent", str(extent))
        
        await page.wait_for_timeout(1000) # pause for effect
        
        # Submit
        await page.click("#submit-btn")
        
        # Wait for flags
        await page.wait_for_selector(".flag-annotation", state="visible")
        await page.wait_for_timeout(2000) # read flags
        
        # Step 2: Queue Screen
        await page.click("text=Verification Queue")
        
        # Wait for queue items to load
        await page.wait_for_selector(".queue-item", state="visible")
        await page.wait_for_timeout(2000) # inspect the queue
        
        # Lock the first claim
        await page.click("text=Lock for Review")
        
        # Wait for the decision panel to switch
        await page.wait_for_selector("text=Approve Claim", state="visible")
        await page.wait_for_timeout(1000)
        
        # Fill remark and reject
        await page.fill("textarea", "Auto-rejected by demo script. ML identified fraudulent near-duplicate.")
        await page.wait_for_timeout(1000)
        await page.click("text=Reject Claim")
        
        # Wait for success message
        await page.wait_for_selector(".message.success", state="visible")
        await page.wait_for_timeout(2000)
        
        # Close
        video_path = await page.video.path()
        await context.close()
        await browser.close()
        
        # Rename video
        final_dest = "demo_recording.webm"
        shutil.move(video_path, final_dest)
        print(f"Video saved as {final_dest}")

if __name__ == "__main__":
    asyncio.run(record_demo())
