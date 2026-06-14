FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema para rembg/onnxruntime
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cria pasta para as figurinhas geradas
RUN mkdir -p figurinhas_geradas fonts

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
