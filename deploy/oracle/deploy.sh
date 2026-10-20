#!/usr/bin/env bash
# Legacy wrapper — primary path is deploy/aws/
echo "NOTE: deploy/oracle is deprecated; forwarding to deploy/aws/deploy.sh"
exec bash "$(cd "$(dirname "$0")/../aws" && pwd)/deploy.sh"
