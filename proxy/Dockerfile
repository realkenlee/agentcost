FROM python:3.12-slim
WORKDIR /app
COPY proxy/requirements.txt .
RUN pip install -r requirements.txt
COPY agentcost/ ./agentcost/
COPY proxy/main.py .
EXPOSE 8080
CMD ["python", "main.py"]
