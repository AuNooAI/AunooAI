#!/bin/bash
certbot renew
systemctl restart your-fastapi-service 