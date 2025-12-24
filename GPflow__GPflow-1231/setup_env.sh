#!/bin/bash
cd /testbed/GPflow
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
# pip install -q --upgrade pip setuptools
# pip install -q uv
###############################################

##################pip###########################
apt-get update
apt-get install -y cmake gcc g++
export SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL=True
pip install --upgrade pip setuptools
pip install -q numpy scipy pandas pytest nbformat     nbconvert ipykernel jupyter_client matplotlib pytest-xdist pytest-cov     multipledispatch mock codecov sklearn tabulate
cd /testbed/GPflow
pip install -e .
pip install -r tests_requirements.txt
pip install tensorflow==2.1.0 tensorflow-probability==0.9
###############################################
