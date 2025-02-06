import os
import sys
import subprocess
import pathlib

RESOURCES = "resources/"
RAW_EXT = ".dna"
COMPILED_EXT = ".pdna"

dna_files = []

os.chdir("../")

for root, _, files in os.walk(RESOURCES):
    for file in files:
        if file.endswith(RAW_EXT):
            filename = file
            filepath = pathlib.Path(root, filename)
            dna_files.append(filepath)

for file in dna_files:
    subprocess.run(f"{sys.executable} {os.path.join('tools', 'dna_compiler', 'compile.py')} {file}")