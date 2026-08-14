from playwright.sync_api import sync_playwright
import time
import os

def test_flow():
    print("Starting Playwright test...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        alerts_requested = False
        alerts_status = None
        
        def handle_request(route, request):
            nonlocal alerts_requested
            if "/scoring/alerts" in request.url:
                alerts_requested = True
                print(f"Captured request: {request.url}")
            route.continue_()
            
        def handle_response(response):
            nonlocal alerts_status
            if "/scoring/alerts" in response.url:
                alerts_status = response.status
                print(f"Response status: {response.status}")
                
        page.route("**/*", handle_request)
        page.on("response", handle_response)
        
        print("Navigating to http://localhost:3000")
        page.goto("http://localhost:3000")
        
        # Login if needed (might be a login form)
        print("Logging in...")
        try:
            page.fill("input[name='username'], input[placeholder='Username'], input[type='text']", "admin")
            page.fill("input[name='password'], input[placeholder='Password'], input[type='password']", "admin")
            page.click("button[type='submit'], button:has-text('Login'), button:has-text('Sign In')")
            time.sleep(2)
        except Exception as e:
            print("No login form or already logged in.")
            
        print("Looking for file upload input...")
        # Upload files
        file_paths = [
            os.path.abspath("test_upload/bank.csv"),
            os.path.abspath("test_upload/cdr.csv"),
            os.path.abspath("test_upload/ipdr.csv")
        ]
        
        # We need to wait for the page to load the ingestion section or whatever
        # Since we modified the UI to automatically navigate, let's see.
        try:
            # If not already on ingestion, click the nav
            page.click("text=Data Ingestion", timeout=3000)
        except:
            pass
            
        time.sleep(1)
        
        file_input = page.locator("input[type='file']")
        file_input.set_input_files(file_paths)
        
        print("Clicking BEGIN FUSION PIPELINE...")
        try:
            page.click("text=BEGIN FUSION PIPELINE")
        except:
            page.click("button:has-text('FUSE')")
            
        print("Waiting for transition to Anomalies...")
        # It should go to Fused, then poll, then go to Anomalies.
        # Wait up to 15 seconds.
        for i in range(15):
            if alerts_requested:
                print("Alerts requested successfully!")
                break
            time.sleep(1)
            
        if not alerts_requested:
            print("FAIL: Alerts not requested.")
        else:
            print(f"SUCCESS: Alerts requested! Status: {alerts_status}")
            
        browser.close()

if __name__ == "__main__":
    test_flow()
