#!/bin/bash
cd /testbed/pytype
git submodule sync
git submodule update --init --recursive --checkout
apt-get install g++ cmake bison flex ninja-build
pip install -q --upgrade pip setuptools
#pip install -e .
pip install -q importlab pyyaml six
pip install -q -r requirements.txt
#pip install -q -r test-requirements.txt
#pip install -q --upgrade pytest
pip install -v pytest==6.2.5
