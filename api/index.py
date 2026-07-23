"""Vercel serverless entrypoint. Exposes the Flask app as a WSGI callable named `app`."""
from app import create_app

app = create_app()
