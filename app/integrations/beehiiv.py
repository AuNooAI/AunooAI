import os
import logging
from typing import Dict

import requests

logger = logging.getLogger(__name__)


class BeehiivClient:
    """Simple client for interacting with the Beehiiv API.

    Only the subset required for publishing a newsletter draft is implemented.
    """

    def __init__(self, api_key: str | None = None, publication_id: str | None = None):
        self.api_key: str | None = api_key or os.getenv("BEEHIIV_API_KEY")
        self.publication_id: str | None = publication_id or os.getenv("BEEHIIV_PUBLICATION_ID")

        if not self.api_key or not self.publication_id:
            raise RuntimeError(
                "Beehiiv API key or publication id are not configured. Set the "
                "`BEEHIIV_API_KEY` and `BEEHIIV_PUBLICATION_ID` environment variables."
            )

        self.base_url = "https://api.beehiiv.com/v2"  # latest v2 API

    # -----------------------------------------------------
    # Public helpers
    # -----------------------------------------------------
    def publish_markdown(self, *, title: str, markdown: str, status: str = "draft") -> Dict:
        """Convert *markdown* to HTML and create a Beehiiv post.

        Parameters
        ----------
        title: str
            Post title.
        markdown: str
            Markdown content to publish.
        status: str, default "draft"
            Beehiiv post status. Use "published" to immediately send.

        Returns
        -------
        Dict
            Raw JSON response from Beehiiv.
        """
        # Local import — avoid optional dependency at import time
        import markdown as _md

        html_body = _md.markdown(markdown, extensions=["tables", "fenced_code"])

        payload: Dict = {
            "title": title,
            "body": html_body,
            "status": status,  # "draft" or "published"
            "public": True,
        }

        url = f"{self.base_url}/publications/{self.publication_id}/posts"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info("Publishing newsletter to Beehiiv → %s", url)
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            # Attempt to extract error details from Beehiiv response
            detail: str = ""
            try:
                detail_json = response.json()
                detail = detail_json.get("error") or detail_json.get("message", "")
            except ValueError:
                # Not JSON – keep empty
                pass

            status_code = response.status_code
            if status_code == 401:
                friendly = "Unauthorized: please verify your Beehiiv API key and publication id."
            elif status_code == 403:
                friendly = "Forbidden: the Beehiiv credentials do not have permission to post."
            else:
                friendly = f"Beehiiv API returned HTTP {status_code}."

            full_msg = f"{friendly} {detail}".strip()
            logger.error(full_msg)
            raise RuntimeError(full_msg) from err

        return response.json() 