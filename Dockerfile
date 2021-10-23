FROM python:3.9
EXPOSE 4000
RUN /usr/local/bin/python -m pip install --upgrade pip
WORKDIR /usr/src/app
COPY requirements.txt ./
COPY . .
RUN /usr/local/bin/python -m pip install --no-cache-dir -r .//requirements.txt
CMD ["python", "main.py"]