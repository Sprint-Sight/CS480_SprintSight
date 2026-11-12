# MLflow tracking server with an explicit Postgres driver.
#
# The stock ghcr.io/mlflow/mlflow image does not promise a Postgres driver, and which one a given
# release bundles has changed: `latest` moved to MLflow 3.18 / SQLAlchemy 2.1, where
# `postgresql://` means the psycopg v3 driver, and that image contains neither psycopg nor
# psycopg2, so the server died on start-up (ModuleNotFoundError: No module named 'psycopg').
# So the version is pinned and the driver is installed here and named in the connection string
# (docker-compose.yaml), instead of depending on what the base image happens to include.
#
# Keep the tag equal to `mlflow` in ../requirements.txt: client and server must match.
FROM ghcr.io/mlflow/mlflow:v3.16.1

RUN pip install --no-cache-dir "psycopg2-binary==2.9.10"
