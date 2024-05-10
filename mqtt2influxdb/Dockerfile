# syntax=docker/dockerfile:1

FROM python:3.10.11-slim-buster
WORKDIR /app
RUN mkdir /var/log/app
COPY . .
RUN pip3 install --no-cache-dir -r requirements.txt