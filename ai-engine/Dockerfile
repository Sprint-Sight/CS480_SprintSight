# 1. Use an official lightweight Python image
FROM python:3.13-slim

# 2. Set environment variables for optimized Python execution
# Prevents Python from writing .pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
# Ensures Python output is sent straight to the terminal (useful for viewing logs in real-time)
ENV PYTHONUNBUFFERED=1

# 3. Set the working directory inside the container
WORKDIR /app

# 4. Copy only the requirements file first
# We do this before copying the rest of the code to leverage Docker's layer caching.
# If your requirements haven't changed, Docker will skip reinstalling them on your next build!
COPY requirements.txt .

# 5. Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code into the container
COPY . .

# 7. Expose the port that FastAPI will run on
EXPOSE 8001

# 8. Define the command to start your FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]