from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(err.message))
        
        page.goto("http://localhost:8000/index.html")
        time.sleep(2)
        
        if not errors:
            print("NO JS ERRORS FOUND")
        else:
            print("JS ERRORS:")
            for err in errors:
                print("-", err)
                
        browser.close()

if __name__ == "__main__":
    run()
