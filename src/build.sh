#!/bin/sh
mkdir -p /mnt/project-files/rta
{ printf '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n</head>\n<body>\n'; cat core.html; printf '\n</body>\n</html>\n'; } > FOH-Analyzer.html
