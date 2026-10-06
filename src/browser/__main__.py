"""Run the application in debug mode"""

from browser.api import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
