FROM python:3.14.2

USER root

RUN apt-get update && apt-get install zip -y && \
    apt-get clean && \
    apt-get autoremove && \
    rm -rf /var/lib/apt/lists/*