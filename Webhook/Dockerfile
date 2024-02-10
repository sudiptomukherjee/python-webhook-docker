# Use an official Python runtime
FROM python:3.10-slim

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the required port
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=webhook.py

# Run app.py when the container launches
CMD ["flask", "run", "--host=0.0.0.0"]