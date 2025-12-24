#!/bin/bash
mkdir -p /testbed
git clone https://github.com/marimo-team/marimo.git /testbed/marimo
cd /testbed/marimo
git checkout "964b5ef771166bd0de9f3fb33597bc6ba082841f"
cd ..
