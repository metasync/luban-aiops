---
kind: external_dependency
name: Operator Portal Web Server
slug: nginx
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
source_files:
    - products/operator-portal/Dockerfile
    - products/operator-portal/nginx.conf
---

The operator-portal uses nginx:1.27-alpine as a static web server to serve the frontend UI assets. The container image copies nginx configuration and web-ui files into the standard nginx HTML directory, exposing port 80 for HTTP traffic. This provides a lightweight, production-ready web server for the portal interface.