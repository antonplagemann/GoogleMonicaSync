# Deriving the latest base image
FROM python:latest


# Labels
LABEL Maintainer="antonplagemann"


# Choose working directory
WORKDIR /usr/app

# Copy all files to working dir
COPY * ./

# Install dependencies
RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt

# Create volume for credentials, token, database and log
VOLUME /app/data

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Run delta sync
CMD [ "python", "./GMSync.py", "-d"]
