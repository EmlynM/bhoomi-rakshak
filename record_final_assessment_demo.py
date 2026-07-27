import asyncio
from playwright.async_api import async_playwright
import sqlite3
import os
import shutil

DB_FILE = 'bhoomi.db'

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

async def record_demo():
    if not os.path.exists('videos'):
        os.makedirs('videos')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir="videos/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        # Step 1: The Queue
        await page.goto("http://localhost:5000/queue")
        await page.wait_for_timeout(1500)
        await show_caption(page, "1. Officer Verification Queue: Automatically populated with flagged claims", 4000)

        # Step 2: Land Dispute (Exact Duplicate)
        await show_caption(page, "Let's review a 'Land Dispute' claim caught by our deterministic rules...", 3500)
        
        # Click the first EXACT_SURVEY_DUPLICATE review button
        # Evaluate to find a link containing EXACT_SURVEY_DUPLICATE
        exact_url = await page.evaluate("""() => {
            let cards = Array.from(document.querySelectorAll('.claim-card'));
            for (let c of cards) {
                if (c.innerHTML.includes('EXACT_SURVEY_DUPLICATE')) {
                    return c.querySelector('a.action-btn').href;
                }
            }
            return null;
        }""")
        
        if exact_url:
            await page.goto(exact_url)
            await page.wait_for_timeout(1000)
            await show_caption(page, "Two completely different people claimed the exact same land!", 4000)
            await page.fill("#remark", "Fraudulent land dispute detected.")
            await page.wait_for_timeout(1000)
            await page.click("button.reject-btn")
            await page.wait_for_timeout(2000)

        # Step 3: ML Near Duplicate
        await page.goto("http://localhost:5000/queue")
        await page.wait_for_timeout(1500)
        await show_caption(page, "Next, let's review an anomaly caught by the ML Model...", 3500)
        
        near_url = await page.evaluate("""() => {
            let cards = Array.from(document.querySelectorAll('.claim-card'));
            for (let c of cards) {
                if (c.innerHTML.includes('POSSIBLE_NEAR_DUPLICATE')) {
                    return c.querySelector('a.action-btn').href;
                }
            }
            return null;
        }""")
        
        if near_url:
            await page.goto(near_url)
            await page.wait_for_timeout(1000)
            await show_caption(page, "The Logistic Regression model caught transposed digits in the survey number!", 5000)
            await page.fill("#remark", "Near duplicate detected by ML. Transposed digits.")
            await page.wait_for_timeout(1000)
            await page.click("button.reject-btn")
            await page.wait_for_timeout(2000)

        # Step 4: Clean claim Intake
        await page.goto("http://localhost:5000/")
        await page.wait_for_timeout(1000)
        await show_caption(page, "Finally, let's submit a clean claim for a valid survey number.", 3500)
        
        # Dynamically fetch an unclaimed 4-digit survey number to trigger JS lookup
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT s.survey_no FROM survey_numbers s WHERE length(s.survey_no) = 4 AND s.survey_no NOT IN (SELECT survey_no FROM claims) LIMIT 1;")
        valid_unclaimed_survey = cursor.fetchone()[0]
        conn.close()
        
        await page.fill("#survey_no", str(valid_unclaimed_survey))
        await page.wait_for_timeout(500)
        await page.fill("#cultivator_name", "Evaluator Demo")
        await page.select_option("#claimed_crop", label="Wheat")
        await page.fill("#claimed_extent", "5.5")
        
        await page.wait_for_timeout(1000)
        
        # We need to fill in valid values to submit
        # The JS auto-fills, we just need to click submit
        await page.click("#submit-btn")
        await page.wait_for_selector(".message.success", state="visible")
        
        await show_caption(page, "Perfect! The claim was processed smoothly without flags.", 4000)
        await hide_caption(page)
        await page.wait_for_timeout(2000)

        video_path = await page.video.path()
        await context.close()
        await browser.close()
        
        final_dest = "final_assessment_demo.webm"
        shutil.move(video_path, final_dest)
        print(f"Video saved as {final_dest}")

if __name__ == "__main__":
    asyncio.run(record_demo())
