"""
Google Cloud Integration Module
================================
Handles all Google technologies:
- Google Gemini AI (Duplicate analysis)
- Firebase (Scan history & storage)
- Google Cloud Storage (GCS scanning)

This module encapsulates all external service integrations,
making main.py clean and focused on core logic.
"""

import os
import json
from datetime import datetime
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==================== GEMINI AI INTEGRATION ====================

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-genai not installed. Gemini AI disabled.")

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = None

if GEMINI_AVAILABLE and GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("[OK] Gemini AI configured")
    except Exception as e:
        print(f"⚠️  Gemini initialization failed: {str(e)}")
        GEMINI_AVAILABLE = False
else:
    if not GEMINI_API_KEY:
        print("⚠️  GEMINI_API_KEY not set in .env file")
    GEMINI_AVAILABLE = False


def ask_gemini_about_files(file1_name, file1_size, file1_age, file2_name, file2_size, file2_age):
    """
    Use Gemini AI to determine if two files are duplicates based on metadata.
    
    Args:
        file1_name (str): First file name
        file1_size (int): First file size in bytes
        file1_age (float): Days since modification
        file2_name (str): Second file name
        file2_size (int): Second file size in bytes
        file2_age (float): Days since modification
    
    Returns:
        Tuple: (yes_or_no: str, reason: str)
    """
    if not GEMINI_AVAILABLE or not gemini_client:
        return "ERROR", "Gemini API unavailable"
    
    try:
        file1_type = file1_name.split('.')[-1] if '.' in file1_name else "unknown"
        file2_type = file2_name.split('.')[-1] if '.' in file2_name else "unknown"
        file1_size_kb = file1_size / 1024
        file2_size_kb = file2_size / 1024
        
        prompt = f"""You are an AI assistant helping to identify duplicate files.

Below is metadata of two files.
Based ONLY on this metadata, decide whether both files represent the same data.

File 1:
- Name: {file1_name}
- Type: {file1_type}
- Size: {file1_size_kb:.1f} KB
- Last modified: {file1_age:.1f} days ago

File 2:
- Name: {file2_name}
- Type: {file2_type}
- Size: {file2_size_kb:.1f} KB
- Last modified: {file2_age:.1f} days ago

Instructions:
1. Answer ONLY "YES" or "NO".
2. Give ONE short reason in simple English.
3. Do not assume file content. Use metadata only.

Format your response like this:
YES - <short reason>
or
NO - <short reason>
"""
        
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        answer = response.text.strip()
        
        if answer.startswith("YES"):
            return "YES", answer[4:].strip()
        elif answer.startswith("NO"):
            return "NO", answer[3:].strip()
        else:
            return "UNCLEAR", answer[:50]
    
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "resource_exhausted" in error_str:
            return "ERROR", "Gemini quota reached"
        return "ERROR", "Gemini API unavailable"


def ask_gemini_gcs_duplicates(file1_name, file1_size, file1_age, file2_name, file2_size, file2_age):
    """
    Verify near-duplicates for GCS files using ONLY metadata via Gemini.
    
    Args:
        file1_name, file1_size, file1_age: First file metadata
        file2_name, file2_size, file2_age: Second file metadata
    
    Returns:
        dict: { "is_duplicate": bool, "similarity": 0-100, "reason": str }
    """
    if not GEMINI_AVAILABLE or not gemini_client:
        return {"is_duplicate": False, "similarity": 0, "reason": "Gemini unavailable"}
    
    try:
        file1_type = file1_name.split('.')[-1] if '.' in file1_name else "unknown"
        file2_type = file2_name.split('.')[-1] if '.' in file2_name else "unknown"
        file1_size_kb = file1_size / 1024
        file2_size_kb = file2_size / 1024
        
        prompt = f"""You analyze cloud storage files based on metadata ONLY.
Given two files in GCS, decide if they are likely near-duplicates or versions.

File 1: {file1_name}
  Type: .{file1_type} | Size: {file1_size_kb:.1f} KB | Modified: {file1_age:.1f} days ago

File 2: {file2_name}
  Type: .{file2_type} | Size: {file2_size_kb:.1f} KB | Modified: {file2_age:.1f} days ago

Respond ONLY in JSON:
{{
  "is_duplicate": true or false,
  "similarity": 0 to 100,
  "reason": "one short sentence"
}}"""
        
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
        
        data = json.loads(text.strip())
        return data
    
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "resource_exhausted" in error_str:
            return {"is_duplicate": False, "similarity": 0, "reason": "Quota exceeded"}
        return {"is_duplicate": False, "similarity": 0, "reason": "API unavailable"}


# ==================== FIREBASE INTEGRATION ====================

try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage as firebase_storage
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️  firebase-admin not installed. Firebase features disabled.")

# Initialize Firebase
firebase_db = None
firebase_storage_bucket = None

if FIREBASE_AVAILABLE:
    try:
        firebase_credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if firebase_credentials_path and os.path.exists(firebase_credentials_path):
            cred = credentials.Certificate(firebase_credentials_path)
            firebase_admin.initialize_app(cred)
            firebase_db = firestore.client()
            firebase_storage_bucket = firebase_storage.bucket("history-scan-database.appspot.com")
            print("[OK] Firebase Firestore & Storage connected")
        else:
            print("[WARNING] FIREBASE_CREDENTIALS_PATH not set or file not found")
            FIREBASE_AVAILABLE = False
    except Exception as e:
        print(f"[WARNING] Firebase initialization failed: {str(e)}")
        FIREBASE_AVAILABLE = False


def save_scan_history_to_firebase(scan_summary, source_type="LOCAL", source_name="data"):
    """
    Save scan history/metadata to Firebase Firestore.
    
    Args:
        scan_summary (dict): Results from analyze_duplicates()
        source_type (str): "LOCAL" or "GCS"
        source_name (str): Folder path or bucket name
    
    Returns:
        Tuple: (success: bool, scan_id: str, message: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_db:
        return False, None, "Firebase not configured or unavailable"
    
    try:
        scan_id = str(uuid.uuid4())[:8]
        
        history_record = {
            "scan_id": scan_id,
            "timestamp": datetime.now(),
            "source_type": source_type,
            "source_name": source_name,
            "total_files": scan_summary.get("total_files", 0),
            "exact_duplicates_count": len(scan_summary.get("exact_duplicates", [])),
            "near_duplicates_count": len(scan_summary.get("near_duplicates", [])),
            "ai_confirmed_count": len(scan_summary.get("ai_confirmed", [])),
            "outdated_files_count": len(scan_summary.get("outdated_files", [])),
            "archived": False,
            "ai_status": scan_summary.get("ai_status", "Unknown"),
            "total_duplicates": scan_summary.get("scan_stats", {}).get("total_duplicates", 0)
        }
        
        firebase_db.collection("scan_history").document(scan_id).set(history_record)
        return True, scan_id, f"Scan history saved (ID: {scan_id})"
    
    except Exception as e:
        return False, None, f"Failed to save history: {str(e)}"


def generate_archive_report(scan_id, source_name, archived_files_list, scan_results):
    """
    Generate a human-readable TXT report of the archive execution.
    
    Args:
        scan_id (str): Scan ID
        source_name (str): Folder or bucket name
        archived_files_list (list): List of archived file operations
        scan_results (dict): Original scan results
    
    Returns:
        str: Report content as plain text
    """
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("ARCHIVE EXECUTION REPORT")
    report_lines.append("=" * 70)
    report_lines.append("")
    
    report_lines.append(f"Scan ID: {scan_id}")
    report_lines.append(f"Source: {source_name}")
    report_lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    
    exact_dup_files = []
    near_dup_files = []
    outdated_files = []
    
    for archive_op in archived_files_list:
        file = archive_op.get("file", "")
        destination = archive_op.get("destination", "")
        
        if "exact_duplicates" in destination:
            exact_dup_files.append(file)
        elif "near_duplicates" in destination:
            near_dup_files.append(file)
        elif "outdated" in destination:
            outdated_files.append(file)
    
    report_lines.append("ARCHIVE SUMMARY")
    report_lines.append("-" * 70)
    report_lines.append(f"Total Files Archived: {len(archived_files_list)}")
    report_lines.append(f"  - Exact Duplicates: {len(exact_dup_files)}")
    report_lines.append(f"  - Near Duplicates: {len(near_dup_files)}")
    report_lines.append(f"  - Outdated Files: {len(outdated_files)}")
    report_lines.append("")
    
    if exact_dup_files:
        report_lines.append("EXACT DUPLICATES (Archived)")
        report_lines.append("-" * 70)
        for f in sorted(exact_dup_files):
            report_lines.append(f"  • {f}")
        report_lines.append("")
    
    if near_dup_files:
        report_lines.append("NEAR DUPLICATES (Archived)")
        report_lines.append("-" * 70)
        for f in sorted(near_dup_files):
            report_lines.append(f"  • {f}")
        report_lines.append("")
    
    if outdated_files:
        report_lines.append("OUTDATED FILES (Archived)")
        report_lines.append("-" * 70)
        for f in sorted(outdated_files):
            report_lines.append(f"  • {f}")
        report_lines.append("")
    
    report_lines.append("=" * 70)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 70)
    
    return "\n".join(report_lines)


def upload_report_to_firebase_storage(report_content, scan_id):
    """
    Upload archive report to Firebase Storage.
    
    Args:
        report_content (str): Plain text report content
        scan_id (str): Scan ID for filename
    
    Returns:
        Tuple: (success: bool, download_url: str, error_msg: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_storage_bucket:
        return False, None, "Firebase Storage not configured"
    
    try:
        blob_path = f"scan_reports/archive_report_{scan_id}.txt"
        blob = firebase_storage_bucket.blob(blob_path)
        blob.upload_from_string(report_content, content_type="text/plain")
        
        download_url = f"https://firebasestorage.googleapis.com/v0/b/history-scan-database.appspot.com/o/scan_reports%2Farchive_report_{scan_id}.txt?alt=media"
        
        print(f"[OK] Report uploaded to Firebase Storage: {blob_path}")
        return True, download_url, None
    
    except Exception as e:
        error_msg = f"Failed to upload report: {str(e)}"
        print(f"[WARNING] {error_msg}")
        return False, None, error_msg


def update_scan_history_archived(scan_id, report_url):
    """
    Update Firestore scan_history document after successful archive.
    
    Args:
        scan_id (str): Scan ID to update
        report_url (str): URL of the uploaded report
    
    Returns:
        Tuple: (success: bool, error_msg: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_db:
        return False, "Firebase not configured"
    
    try:
        firebase_db.collection("scan_history").document(scan_id).update({
            "archived": True,
            "archived_at": datetime.now(),
            "report_url": report_url
        })
        print(f"[OK] Updated Firestore: scan {scan_id} marked as archived")
        return True, None
    
    except Exception as e:
        error_msg = f"Failed to update Firestore: {str(e)}"
        print(f"[WARNING] {error_msg}")
        return False, error_msg


def get_scan_history_from_firebase(limit=20):
    """
    Fetch scan history from Firebase (latest first).
    
    Args:
        limit (int): Maximum number of records to fetch
    
    Returns:
        list: List of history records
    """
    if not FIREBASE_AVAILABLE or not firebase_db:
        return []
    
    try:
        docs = firebase_db.collection("scan_history").order_by(
            "timestamp", 
            direction=firestore.Query.DESCENDING
        ).limit(limit).stream()
        
        history = []
        for doc in docs:
            data = doc.to_dict()
            timestamp_str = data.get("timestamp").isoformat() if hasattr(data.get("timestamp"), 'isoformat') else str(data.get("timestamp"))
            
            history.append({
                "scan_id": data.get("scan_id"),
                "timestamp": timestamp_str,
                "source_type": data.get("source_type"),
                "source_name": data.get("source_name"),
                "total_files": data.get("total_files"),
                "exact_duplicates_count": data.get("exact_duplicates_count"),
                "near_duplicates_count": data.get("near_duplicates_count"),
                "ai_confirmed_count": data.get("ai_confirmed_count"),
                "outdated_files_count": data.get("outdated_files_count"),
                "total_duplicates": data.get("total_duplicates"),
                "archived": data.get("archived", False),
                "ai_status": data.get("ai_status")
            })
        
        return history
    
    except Exception as e:
        print(f"Error fetching history: {str(e)}")
        return []


def archive_history_record(scan_id):
    """
    Mark a history record as archived.
    
    Args:
        scan_id (str): Scan ID to mark as archived
    
    Returns:
        Tuple: (success: bool, message: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_db:
        return False, "Firebase not configured"
    
    try:
        firebase_db.collection("scan_history").document(scan_id).update({
            "archived": True,
            "archived_at": datetime.now()
        })
        return True, f"History record {scan_id} marked as archived"
    
    except Exception as e:
        return False, str(e)


# ==================== GOOGLE CLOUD STORAGE (GCS) INTEGRATION ====================

try:
    from google.cloud import storage as gcs_storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("⚠️  google-cloud-storage not installed. GCS support disabled.")


def authenticate_gcs(credentials_json):
    """
    Authenticate with GCS using provided credentials.
    
    Args:
        credentials_json (str or dict): Service account JSON key
    
    Returns:
        Tuple: (success: bool, client: gcs_storage.Client or None, error_message: str)
    """
    if not GCS_AVAILABLE:
        return False, None, "google-cloud-storage library not installed"
    
    try:
        if isinstance(credentials_json, str):
            try:
                credentials_dict = json.loads(credentials_json)
            except json.JSONDecodeError:
                return False, None, "Invalid JSON format for credentials"
        else:
            credentials_dict = credentials_json
        
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        
        client = gcs_storage.Client(credentials=credentials)
        _ = next(client.list_buckets(max_results=1), None)
        
        return True, client, "Authentication successful"
    
    except Exception as e:
        return False, None, f"GCS authentication failed: {str(e)}"


def scan_gcs_metadata(bucket_name, gcs_client, prefix=""):
    """
    Scan GCS bucket and extract ONLY metadata (no file content download).
    
    Args:
        bucket_name (str): Name of GCS bucket
        gcs_client: Authenticated GCS client
        prefix (str): Optional prefix to filter objects
    
    Returns:
        Tuple: (success: bool, metadata_list: list, error_message: str)
    """
    if not GCS_AVAILABLE:
        return False, [], "google-cloud-storage not available"
    
    try:
        bucket = gcs_client.bucket(bucket_name)
        
        if not bucket.exists():
            return False, [], f"Bucket '{bucket_name}' does not exist or is not accessible"
        
        metadata_list = []
        blobs = bucket.list_blobs(prefix=prefix)
        
        blob_count = 0
        for blob in blobs:
            if blob.name.endswith('/'):
                continue
            
            blob_count += 1
            
            file_metadata = {
                "file_name": blob.name.split('/')[-1],
                "file_path": blob.name,
                "file_size": blob.size,
                "last_modified": blob.updated.timestamp() if blob.updated else 0,
                "source": "gcs",
                "bucket": bucket_name,
                "content_type": blob.content_type
            }
            
            metadata_list.append(file_metadata)
        
        if blob_count == 0:
            return True, [], f"Bucket is empty or no objects found with prefix '{prefix}'"
        
        return True, metadata_list, f"Successfully scanned {blob_count} objects"
    
    except Exception as e:
        return False, [], f"GCS scan failed: {str(e)}"


def normalize_gcs_metadata(gcs_metadata_list):
    """
    Convert GCS metadata list into internal file_data structure.
    
    Args:
        gcs_metadata_list (list): List of GCS object metadata dicts
    
    Returns:
        dict: file_data dict in same format as local files
    """
    file_data = {}
    
    for metadata in gcs_metadata_list:
        file_name = metadata["file_name"]
        
        file_data[file_name] = {
            "file_path": metadata["file_path"],
            "size": metadata["file_size"],
            "modified_time": metadata["last_modified"],
            "source": "gcs",
            "bucket": metadata["bucket"],
            "content_type": metadata.get("content_type", "unknown"),
            "hash": None,
            "content": None
        }
    
    return file_data


def prepare_gcs_archive_move(gcs_client, bucket_name, source_path, archive_category):
    """
    Prepare GCS archive move operation.
    
    Args:
        gcs_client: Authenticated GCS client
        bucket_name (str): GCS bucket name
        source_path (str): Path of object to move
        archive_category (str): "exact_duplicates", "near_duplicates", or "outdated"
    
    Returns:
        Tuple: (success: bool, operation: dict, message: str)
    """
    try:
        valid_categories = ["exact_duplicates", "near_duplicates", "outdated"]
        if archive_category not in valid_categories:
            return False, {}, f"Invalid archive category: {archive_category}"
        
        destination_path = f"archive/{archive_category}/{source_path.split('/')[-1]}"
        
        bucket = gcs_client.bucket(bucket_name)
        source_blob = bucket.blob(source_path)
        
        if not source_blob.exists():
            return False, {}, f"Source object '{source_path}' does not exist"
        
        operation = {
            "type": "move_blob",
            "bucket": bucket_name,
            "source": source_path,
            "destination": destination_path,
            "size_bytes": source_blob.size,
            "status": "prepared"
        }
        
        return True, operation, "Archive operation prepared successfully"
    
    except Exception as e:
        return False, {}, f"Failed to prepare GCS archive: {str(e)}"


def execute_gcs_archive_move(gcs_client, bucket_name, source_path, destination_path):
    """
    Execute GCS archive move (copy + delete).
    
    Args:
        gcs_client: Authenticated GCS client
        bucket_name (str): GCS bucket name
        source_path (str): Source object path
        destination_path (str): Destination object path
    
    Returns:
        Tuple: (success: bool, message: str)
    """
    try:
        bucket = gcs_client.bucket(bucket_name)
        source_blob = bucket.blob(source_path)
        
        destination_blob = bucket.copy_blob(source_blob, bucket, destination_path)
        source_blob.delete()
        
        return True, f"Successfully moved {source_path} to {destination_path}"
    
    except Exception as e:
        return False, f"GCS archive move failed: {str(e)}"
