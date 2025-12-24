#!/bin/bash
cd /testbed/marimo
##################pixi###########################
# pip install -q --upgrade pip setuptools
# pixi run make check-prereqs
# pixi run make fe
# pixi run make py
###############################################

##################uv###########################
# pip install -q --upgrade pip setuptools
# pip install -q uv
###############################################

##################hatch###########################
pip install -q --upgrade pip setuptools
pip install hatch
hatch version
mkdir -p marimo/_static/assets
hatch dep sync test
cp frontend/index.html marimo/_static/index.html
cp frontend/public/favicon.ico marimo/_static/favicon.ico

###############################################

##################pip###########################
# git submodule sync
# git submodule update --init --recursive --checkout
# pip install -q --upgrade pip setuptools
# pip install -e .
# pip install -r requirements.txt
# pip install -q --upgrade pytest
###############################################
