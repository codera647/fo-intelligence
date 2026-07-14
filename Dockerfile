FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directories
RUN mkdir -p data/raw data/processed

EXPOSE 10000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "10000"]
