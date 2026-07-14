"""Production WSGI entrypoint for TalentBeacon."""
from run import create_app


app = create_app()
