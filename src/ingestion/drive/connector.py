"""
Google Drive API connector for document retrieval.

Provides OAuth2 authentication and file download capabilities
for syncing documents from Google Drive to the knowledge base.
"""

import io
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Scopes for Google Drive access (read-only)
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveConnector:
    """
    Connector for Google Drive API.

    Handles OAuth2 authentication and provides methods for
    listing and downloading files from a specified folder.
    """

    # Supported MIME types
    SUPPORTED_MIME_TYPES = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.google-apps.document": ".docx",  # Google Docs -> export as DOCX
    }

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        """
        Initialize the Google Drive connector.

        Args:
            credentials_path: Path to OAuth2 credentials JSON file
            token_path: Path to store/load token file
        """
        settings = get_settings()
        self.credentials_path = credentials_path or settings.google_credentials_path
        # In production the app directory may be read-only (Railway, Render, etc.).
        # Use /tmp which is always writable, falling back to the provided path.
        default_token_path = "/tmp/token.json" if settings.is_production else "token.json"
        self.token_path = token_path or default_token_path
        self.creds = None
        self.service = None

    def _get_client_config(self) -> Optional[Dict[str, Any]]:
        """Load client config from GOOGLE_CREDENTIALS_JSON env or credentials file."""
        settings = get_settings()
        if settings.google_credentials_json:
            try:
                return json.loads(settings.google_credentials_json)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid GOOGLE_CREDENTIALS_JSON: {e}")
                return None
        if os.path.exists(self.credentials_path):
            try:
                with open(self.credentials_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Failed to read credentials file: {e}")
                return None
        return None

    def get_authorization_url(self, redirect_uri: str) -> Optional[str]:
        """
        Generate OAuth authorization URL for web-based authentication.

        Args:
            redirect_uri: The redirect URI registered in Google Cloud Console

        Returns:
            Authorization URL, or None if failed
        """
        try:
            client_config = self._get_client_config()
            if not client_config:
                logger.error(
                    "No credentials. Set GOOGLE_CREDENTIALS_JSON env var (paste credentials.json contents) "
                    f"or place credentials.json at {self.credentials_path}"
                )
                return None

            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri,
            )
            authorization_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            return authorization_url
        except Exception as e:
            logger.error(f"Failed to generate authorization URL: {e}")
            return None

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> tuple[bool, str]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: The redirect URI used in authorization

        Returns:
            (True, "") on success, (False, error_message) on failure
        """
        client_config = self._get_client_config()
        if not client_config:
            msg = (
                "Google credentials not configured. "
                "Set GOOGLE_CREDENTIALS_JSON env var (paste the full contents of credentials.json) "
                f"or place credentials.json at {self.credentials_path}"
            )
            logger.error(msg)
            return False, msg

        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri,
            )
            flow.fetch_token(code=code)
            self.creds = flow.credentials

            # Save the token — use /tmp in production to avoid read-only filesystem errors
            try:
                with open(self.token_path, "w") as token:
                    token.write(self.creds.to_json())
                logger.info("Token saved to %s", self.token_path)
            except OSError as e:
                # Non-fatal: token is in memory for this request; log and continue
                logger.warning("Could not save token file (%s): %s — token held in memory only", self.token_path, e)

            # Build the service
            self.service = build("drive", "v3", credentials=self.creds)
            logger.info("Google Drive authentication successful")
            return True, ""

        except Exception as e:
            # Surface the real Google error (e.g. redirect_uri_mismatch, invalid_grant)
            msg = str(e)
            logger.error("Failed to exchange code for token: %s", msg)
            return False, msg

    def authenticate(self) -> bool:
        """
        Authenticate with Google Drive API.

        Will prompt for browser authentication if no valid token exists.
        Uses local server flow for desktop/CLI use.

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Load existing token
            if os.path.exists(self.token_path):
                self.creds = Credentials.from_authorized_user_file(
                    self.token_path, SCOPES
                )

            # Refresh or get new credentials
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_path):
                        logger.error(
                            f"Credentials file not found: {self.credentials_path}. "
                            "Download OAuth credentials from Google Cloud Console."
                        )
                        return False

                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    self.creds = flow.run_local_server(port=0)

                # Save the token
                with open(self.token_path, "w") as token:
                    token.write(self.creds.to_json())

            # Build the service
            self.service = build("drive", "v3", credentials=self.creds)
            logger.info("Google Drive authentication successful")
            return True

        except Exception as e:
            logger.error(f"Google Drive authentication failed: {e}")
            return False

    def list_files(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List files in a Google Drive folder.

        Args:
            folder_id: Google Drive folder ID (uses configured default if None)
            page_size: Maximum files to return

        Returns:
            List of file metadata dictionaries
        """
        if not self.service:
            if not self.authenticate():
                return []

        settings = get_settings()
        folder_id = folder_id or settings.google_drive_folder_id

        if not folder_id:
            logger.warning("No folder ID specified")
            return []

        try:
            # Build query for supported file types
            mime_queries = [
                f"mimeType='{mime}'" for mime in self.SUPPORTED_MIME_TYPES.keys()
            ]
            mime_filter = " or ".join(mime_queries)

            query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

            results = self.service.files().list(
                q=query,
                pageSize=page_size,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
            ).execute()

            files = results.get("files", [])
            logger.info(f"Found {len(files)} files in folder {folder_id}")

            return files

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    def download_file(
        self,
        file_id: str,
        file_name: str,
        mime_type: str,
        output_dir: str = "./data/documents",
    ) -> Optional[str]:
        """
        Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID
            file_name: Name for the downloaded file
            mime_type: MIME type of the file
            output_dir: Directory to save the file

        Returns:
            Path to downloaded file, or None if failed
        """
        if not self.service:
            if not self.authenticate():
                return None

        try:
            # Create output directory if needed
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # Determine file extension
            extension = self.SUPPORTED_MIME_TYPES.get(mime_type, "")

            # Handle Google Docs (need to export)
            if mime_type == "application/vnd.google-apps.document":
                request = self.service.files().export_media(
                    fileId=file_id,
                    mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            else:
                request = self.service.files().get_media(fileId=file_id)

            # Clean filename and add extension
            clean_name = "".join(c for c in file_name if c.isalnum() or c in "._- ")
            if not clean_name.endswith(extension):
                clean_name += extension

            output_path = Path(output_dir) / clean_name

            # Download
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")

            # Write to file
            with open(output_path, "wb") as f:
                f.write(fh.getvalue())

            logger.info(f"Downloaded: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Error downloading file {file_id}: {e}")
            return None

    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dictionary, or None if not found
        """
        if not self.service:
            if not self.authenticate():
                return None

        try:
            file = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, webViewLink",
            ).execute()

            return file

        except Exception as e:
            logger.error(f"Error getting file info for {file_id}: {e}")
            return None
