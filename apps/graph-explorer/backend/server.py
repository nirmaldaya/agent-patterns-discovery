"""Entry point used by app.yaml: runs the API on the port Databricks Apps assigns."""

import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=config.PORT, proxy_headers=True, forwarded_allow_ips="*")
