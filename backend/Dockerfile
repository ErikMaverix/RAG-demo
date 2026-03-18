FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# uploads-mappen opprettes ved oppstart via Path.mkdir(exist_ok=True) i main.py,
# men vi lager den her også så volum-mount fungerer fra start
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
