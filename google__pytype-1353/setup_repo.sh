#!/bin/bash
mkdir -p /testbed
git clone https://github.com/google/pytype.git /testbed/pytype
cd /testbed/pytype
git checkout "0b797cc8f8127419b0758bef409a9046d54a39bb"
cd ..
