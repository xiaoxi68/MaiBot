# 此镜像用于在部署helm chart时动态生成adapter的配置文件
FROM python:slim

WORKDIR /app

COPY . /app

RUN pip3 install --no-cache-dir -i https://mirrors.ustc.edu.cn/pypi/simple -r requirements.txt

ENTRYPOINT ["python3", "adapter-cm-generator.py"]
