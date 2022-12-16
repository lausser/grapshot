FROM mcr.microsoft.com/playwright:v1.27.0-focal
ENV DEBIAN_FRONTEND="noninteractive" TZ="UTC"
RUN apt-get update
RUN apt-get install -y vim
RUN apt-get install -y viewnior
RUN apt-get install -y x11-xserver-utils
RUN apt-get install -y x11-utils
# Drecksbuntu!!!!
#RUN apt-get install -y binutils
#RUN strip --remove-section=.note.ABI-tag /usr/lib/x86_64-linux-gnu/libQt5Core.so.5
RUN apt-get install -y python3-yaml
RUN apt-get update
# ohne das erneute update gibt es beim pip ein 404
# DRECKSBUNTU!!!!!
RUN apt-get install -y python3-pip
RUN pip install playwright

RUN apt install -y python3-pil
RUN apt install -y eog

COPY README /root
COPY VERSION /root
COPY grapshot.py /root
COPY run.sh /root
RUN chmod 755 /root/run.sh
ENTRYPOINT ["/root/run.sh"]
