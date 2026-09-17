FROM python:3.12-slim

WORKDIR /app
COPY . .

ENV HOST=0.0.0.0
ENV PORT=7860
ENV OPEN_BROWSER=false

EXPOSE 7860
CMD ["python", "server.py"]