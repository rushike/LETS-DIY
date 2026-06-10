import uvicorn
import webbrowser
from pathlib import Path

def main():
    # Serve FastAPI app
    from api import app  # your FastAPI app
    url = "http://127.0.0.1:8000/ui/ui-table.html"
    webbrowser.open(url)

    uvicorn.run(app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    main()
