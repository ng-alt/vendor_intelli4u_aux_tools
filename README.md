# dir-comp.py

It's an experimental GUI tool with wxPython to compare two directories
including the original one and referred one, try to detect the similar files
with their file names because the binaries could be in /bin, /sbin, /usr/bin
or /usr/sbin, and the shared libraries are similar.

The target is to solve the problem that the file has been deployed but was in
a different location, where the common diff tool can find and treat difference
for the files.

