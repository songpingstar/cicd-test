#!/bin/bash
mkdir -p /testbed
git clone https://github.com/GPflow/GPflow.git /testbed/GPflow
cd /testbed/GPflow
git checkout "bd1e9c04b48dd5ccca9619d5eaa2595a358bdb08"
cd ..
