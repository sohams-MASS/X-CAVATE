FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY xcavate/ xcavate/
RUN pip install --no-cache-dir ".[gui]"
EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "xcavate/gui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
