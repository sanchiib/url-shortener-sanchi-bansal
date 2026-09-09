"""
Entry point. Run with:

    python app.py

or, for production-style serving:

    flask --app app run
"""

from dotenv import load_dotenv

# Load variables from a local .env file (if present) into the process
# environment *before* create_app() reads them via os.environ. Safe to
# call even if .env doesn't exist - it's a no-op in that case, so real
# environment variables (e.g. set in production) still take priority
# if both happen to be set.
load_dotenv()

from shortener import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
