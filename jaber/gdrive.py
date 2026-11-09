"""Google Drive সংযোগ (ঐচ্ছিক)।
সেটআপ: Google Cloud Console-এ OAuth "Desktop app" ক্রেডেনশিয়াল বানিয়ে credentials.json ফাইলটা
%APPDATA%\\Jaber\\ ফোল্ডারে রাখুন। প্রথমবার ব্রাউজারে লগইন চাইবে।"""
import io

from .config import app_dir

SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive.readonly"]
_service = None


def _svc():
    global _service
    if _service:
        return _service
    cred_file = app_dir() / "credentials.json"
    token_file = app_dir() / "google_token.json"
    if not cred_file.exists():
        raise RuntimeError(
            f"Google Drive সেটআপ করা নেই। credentials.json ফাইলটা এখানে রাখুন: {cred_file} (README দেখুন)"
        )
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _service


def search(query: str, limit: int = 10) -> str:
    q = query.replace("'", "\\'")
    res = _svc().files().list(
        q=f"name contains '{q}' and trashed = false" if query else "trashed = false",
        pageSize=limit, orderBy="modifiedTime desc",
        fields="files(id,name,mimeType,modifiedTime,webViewLink)",
    ).execute()
    files = res.get("files", [])
    if not files:
        return "কোনো ফাইল পাওয়া যায়নি।"
    return "\n".join(f"- {f['name']} | id={f['id']} | {f['mimeType']} | {f.get('modifiedTime','')[:10]} | {f.get('webViewLink','')}" for f in files)


def read(file_id: str, max_chars: int = 8000) -> str:
    svc = _svc()
    meta = svc.files().get(fileId=file_id, fields="name,mimeType").execute()
    mt = meta["mimeType"]
    if mt == "application/vnd.google-apps.document":
        data = svc.files().export(fileId=file_id, mimeType="text/plain").execute()
    elif mt == "application/vnd.google-apps.spreadsheet":
        data = svc.files().export(fileId=file_id, mimeType="text/csv").execute()
    elif mt.startswith("text/") or mt in ("application/json",):
        data = svc.files().get_media(fileId=file_id).execute()
    else:
        return f"'{meta['name']}' ({mt}) ফাইলটা টেক্সট হিসেবে পড়া যায় না।"
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
    return f"ফাইল: {meta['name']}\n\n{text[:max_chars]}"


def upload_text(name: str, content: str) -> str:
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain")
    f = _svc().files().create(body={"name": name}, media_body=media, fields="id,webViewLink").execute()
    return f"Drive-এ সেভ হয়েছে: {name} → {f.get('webViewLink')}"
