import os
import sys
import time
import threading
import webbrowser
import uvicorn

def open_browser():
    time.sleep(1.2)
    url = "http://127.0.0.1:8000"
    print(f"\n[+] Opening AI Job Search Agent in default browser: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    print("=" * 65)
    print("      FresherLaunch — AI Job Search Agent & Career Engine")
    print("=" * 65)
    print("[*] Host: http://127.0.0.1:8000")
    print("[*] API Docs (Swagger): http://127.0.0.1:8000/docs")
    print("[*] Verified Jobs: 26 Active Listings")
    print("[*] Press Ctrl+C in terminal to stop server.\n")

    # Start browser opener in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Start FastAPI server
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
