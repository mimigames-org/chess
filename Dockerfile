FROM python:3.12-slim

WORKDIR /app

RUN pip install uv --no-cache-dir

# Install deps first (cached layer)
COPY pyproject.toml ./
RUN uv sync --no-dev

# Copy source
COPY . .

EXPOSE 8001
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
