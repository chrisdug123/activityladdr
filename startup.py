flask db upgrade && gunicorn --bind=0.0.0.0:8000 --timeout 600 run:app
