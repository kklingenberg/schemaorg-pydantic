FROM python:3.9.1-alpine3.12

RUN apk add --update --no-cache build-base=0.5-r2

ARG COMMIT=local
ENV COMMIT=${COMMIT}

ARG SCHEMAORG_VERSION=12.0
ENV SCHEMAORG_VERSION=${SCHEMAORG_VERSION}

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    wget https://raw.githubusercontent.com/schemaorg/schemaorg/main/data/releases/${SCHEMAORG_VERSION}/schemaorg-current-http.jsonld

COPY models.py.tpl generate.py ./

ENTRYPOINT ["python", "generate.py"]
