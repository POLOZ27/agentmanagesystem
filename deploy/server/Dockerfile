FROM python:3.12-slim
# LibreOffice（只装文字处理部分，无界面）用来把合同转成和 Word 一样排版的预览图；
# Liberation / Carlito / Caladea 和 Times New Roman、Calibri、Cambria 字宽一致，文泉驿用于中文名字
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer-nogui \
        fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV AGENT_PORTAL_DATA=/data AGENT_PORTAL_HTTPS=1 PYTHONUNBUFFERED=1
EXPOSE 8800
CMD ["python", "serve.py"]
