FROM python:3.12-slim
RUN pip install --no-cache-dir openai==3.26.0
COPY . /tests/
RUN chmod +x /tests/test.sh
