flask db upgrade && gunicorn --bind=0.0.0.0 --timeout 600 run:app
