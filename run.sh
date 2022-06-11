#! /bin/sh

# 1920x1080 typical wide screen
/usr/bin/xvfb-run -a -s "-screen 0 1920x1080x24" /usr/bin/python3 /root/grapshot.py
