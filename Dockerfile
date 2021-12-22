# Deriving the latest base image from https://hub.docker.com/_/python
FROM python:alpine

# Labels
LABEL Maintainer="antonplagemann"

# Choose working directory
WORKDIR /usr/app

# Copy all files to working dir
COPY . .

# Add data and logs volume
VOLUME /usr/app/data
VOLUME /usr/app/logs

# Install dependencies
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /usr/app
USER appuser
