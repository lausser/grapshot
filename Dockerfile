#FROM mcr.microsoft.com/playwright:v1.43.0-jammy
FROM mcr.microsoft.com/playwright:v1.49.0-noble
ENV DEBIAN_FRONTEND="noninteractive" TZ="UTC"
RUN apt-get update
RUN apt-get install -y vim
RUN apt-get install -y viewnior
RUN apt-get install -y x11-xserver-utils
RUN apt-get install -y x11-utils
RUN apt-get install -y eog

RUN apt-get install -y python3-yaml
RUN apt-get install -y python3-pip
RUN apt-get install -y python3-pil
RUN pip install --break-system-packages playwright

COPY README /root
COPY VERSION /root
COPY grapshot.py /root
COPY run.sh /root
RUN chmod 755 /root/run.sh
ENTRYPOINT ["/root/run.sh"]
