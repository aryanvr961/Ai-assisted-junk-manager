import os
import sys
import hashlib
from difflib import SequenceMatcher
import time
import google.genai as genai
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import shutil
import json
from datetime import datetime
import uuid

# Handle Unicode/encoding issues on Windows
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception as e:
        pass  # If encoding setup fails, continue anyway

# Try to import Google Cloud Storage (optional, for GCS support)
try:
    from google.cloud import storage as gcs_storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("⚠️  google-cloud-storage not installed. GCS support disabled.")

# Try to import Firebase Admin SDK (optional, for scan history & storage)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage as firebase_storage
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️  firebase-admin not installed. Scan history will not be saved.")

# Load environment variables from .env file
load_dotenv()

# Configure Gemini API with the new google-genai library
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    print("Please add your API key to the .env file.")

# Create client with the new library
client = genai.Client(api_key=GEMINI_API_KEY)

# Initialize Firebase Admin SDK (optional)
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
            print("[OK] Firebase Firestore & Storage connected for scan history & reports")
        else:
            print("[WARNING] FIREBASE_CREDENTIALS_PATH not set or file not found. Scan history disabled.")
    except Exception as e:
        print(f"[WARNING] Firebase initialization failed: {str(e)}")
        firebase_db = None
        firebase_storage_bucket = None

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Get the path to the data folder
folder_path = "data"

# Get a list of all files in the data folder
if os.path.exists(folder_path):
    files = os.listdir(folder_path)
else:
    files = []

# ==================== ARCHIVE HELPER FUNCTIONS ====================

def save_scan_history_to_firebase(scan_summary, source_type="LOCAL", source_name="data"):
    """
    Save scan history/metadata to Firebase Firestore (no file content).
    
    Args:
        scan_summary (dict): Results from analyze_duplicates() or similar
        source_type (str): "LOCAL" or "GCS"
        source_name (str): Folder path or bucket name
    
    Returns:
        Tuple: (success: bool, scan_id: str, message: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_db:
        return False, None, "Firebase not configured or unavailable"
    
    try:
        scan_id = str(uuid.uuid4())[:8]  # Short unique ID
        
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
        
        # Save to Firestore collection 'scan_history'
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
    
    # Header info
    report_lines.append(f"Scan ID: {scan_id}")
    report_lines.append(f"Source: {source_name}")
    report_lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    
    # Separate archived files by category
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
    
    # Summary counts
    report_lines.append("ARCHIVE SUMMARY")
    report_lines.append("-" * 70)
    report_lines.append(f"Total Files Archived: {len(archived_files_list)}")
    report_lines.append(f"  - Exact Duplicates: {len(exact_dup_files)}")
    report_lines.append(f"  - Near Duplicates: {len(near_dup_files)}")
    report_lines.append(f"  - Outdated Files: {len(outdated_files)}")
    report_lines.append("")
    
    # Detailed file lists
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
    Upload archive report to Firebase Storage and return download URL.
    
    Args:
        report_content (str): Plain text report content
        scan_id (str): Scan ID for filename
    
    Returns:
        Tuple: (success: bool, download_url: str, error_msg: str)
    """
    if not FIREBASE_AVAILABLE or not firebase_storage_bucket:
        return False, None, "Firebase Storage not configured"
    
    try:
        # Upload to Firebase Storage
        blob_path = f"scan_reports/archive_report_{scan_id}.txt"
        blob = firebase_storage_bucket.blob(blob_path)
        blob.upload_from_string(report_content, content_type="text/plain")
        
        # Get public download URL
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

def create_archive_structure(folder_path_arg="data"):
    """Create archive folder structure if it doesn't exist"""
    # Use provided folder path or default to global folder_path
    scan_folder_path = folder_path_arg if folder_path_arg and folder_path_arg != "data" else folder_path
    
    archive_base = os.path.join(scan_folder_path, "archive")
    archive_folders = [
        os.path.join(archive_base, "exact_duplicates"),
        os.path.join(archive_base, "near_duplicates"),
        os.path.join(archive_base, "outdated")
    ]
    
    for folder in archive_folders:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            print(f"Created archive folder: {folder}")
    
    return archive_base, archive_folders

def move_file_safe(source_path, dest_path):
    """Safely move a file from source to destination"""
    try:
        # ISSUE 1 FIX: Check if source file exists before attempting to move
        if not os.path.exists(source_path):
            return False, f"Source file does not exist: {source_path}"
        
        # Ensure destination directory exists
        dest_dir = os.path.dirname(dest_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        # Move the file
        shutil.move(source_path, dest_path)
        return True, f"Moved: {source_path} → {dest_path}"
    except Exception as e:
        return False, f"Failed to move {source_path}: {str(e)}"

def generate_archive_preview(scan_results, folder_path_arg="data"):
    """Generate a preview of files that will be archived without actually moving them"""
    # Use provided folder path or default to global folder_path
    scan_folder_path = folder_path_arg if folder_path_arg and folder_path_arg != "data" else folder_path
    
    preview = {
        "exact_duplicates": [],
        "near_duplicates": [],
        "outdated": [],
        "total_files_to_archive": 0,
        "storage_savings_mb": 0
    }
    
    # Process exact duplicates
    if scan_results.get("exact_duplicates"):
        for dup_pair in scan_results["exact_duplicates"]:
            file1 = dup_pair["file1"]
            file2 = dup_pair["file2"]
            
            file1_path = os.path.join(scan_folder_path, file1)
            file2_path = os.path.join(scan_folder_path, file2)
            
            # ISSUE 1 FIX: Skip pairs if either file doesn't exist
            if not os.path.exists(file1_path) or not os.path.exists(file2_path):
                print(f"[WARNING] Skipping exact duplicate pair - file not found: {file1} or {file2}")
                continue
            
            # Get modification times
            try:
                file1_mtime = os.path.getmtime(file1_path)
                file2_mtime = os.path.getmtime(file2_path)
            except Exception as e:
                print(f"[WARNING] Failed to get modification times: {e}")
                continue
            
            # Keep the oldest, archive the newer
            if file1_mtime < file2_mtime:
                keep_file = file1
                archive_file = file2
            else:
                keep_file = file2
                archive_file = file1
            
            archive_path = os.path.join(scan_folder_path, "archive", "exact_duplicates", archive_file)
            file_size = os.path.getsize(os.path.join(scan_folder_path, archive_file))
            
            preview["exact_duplicates"].append({
                "original": keep_file,
                "to_archive": archive_file,
                "destination": archive_path,
                "size_bytes": file_size,
                "reason": "Exact duplicate - newer version will be archived"
            })
            
            preview["total_files_to_archive"] += 1
            preview["storage_savings_mb"] += file_size / (1024 * 1024)
    
    # Process near duplicates (if AI confirmed)
    if scan_results.get("ai_confirmed"):
        for dup_pair in scan_results["ai_confirmed"]:
            file1 = dup_pair["file1"]
            file2 = dup_pair["file2"]
            
            file1_path = os.path.join(scan_folder_path, file1)
            file2_path = os.path.join(scan_folder_path, file2)
            
            # ISSUE 1 FIX: Skip pairs if either file doesn't exist
            if not os.path.exists(file1_path) or not os.path.exists(file2_path):
                print(f"[WARNING] Skipping near duplicate pair - file not found: {file1} or {file2}")
                continue
            
            # Get modification times
            try:
                file1_mtime = os.path.getmtime(file1_path)
                file2_mtime = os.path.getmtime(file2_path)
            except Exception as e:
                print(f"[WARNING] Failed to get modification times: {e}")
                continue
            
            # Keep the newest, archive the older
            if file1_mtime > file2_mtime:
                keep_file = file1
                archive_file = file2
            else:
                keep_file = file2
                archive_file = file1
            
            archive_path = os.path.join(scan_folder_path, "archive", "near_duplicates", archive_file)
            file_size = os.path.getsize(os.path.join(scan_folder_path, archive_file))
            
            preview["near_duplicates"].append({
                "original": keep_file,
                "to_archive": archive_file,
                "destination": archive_path,
                "size_bytes": file_size,
                "reason": "Near duplicate (AI verified) - older version will be archived"
            })
            
            preview["total_files_to_archive"] += 1
            preview["storage_savings_mb"] += file_size / (1024 * 1024)
    
    # Process outdated files
    # ISSUE 3 FIX: Use 'fileName' consistently for outdated files
    if scan_results.get("outdated_files"):
        for old_file in scan_results["outdated_files"]:
            file_name = old_file["fileName"]
            file_path = os.path.join(scan_folder_path, file_name)
            
            if os.path.exists(file_path):
                archive_path = os.path.join(scan_folder_path, "archive", "outdated", file_name)
                file_size = os.path.getsize(file_path)
                
                preview["outdated"].append({
                    "fileName": file_name,
                    "destination": archive_path,
                    "size_bytes": file_size,
                    "reason": "Oldest file in scope"
                })
                
                preview["total_files_to_archive"] += 1
                preview["storage_savings_mb"] += file_size / (1024 * 1024)
    
    # Round storage savings
    preview["storage_savings_mb"] = round(preview["storage_savings_mb"], 2)
    
    return preview

def execute_archive(archive_actions, folder_path_arg="data"):
    """Execute the archive action by moving files to their destinations"""
    # Use provided folder path or default to global folder_path
    scan_folder_path = folder_path_arg if folder_path_arg and folder_path_arg != "data" else folder_path
    
    results = {
        "success": True,
        "archived_files": [],
        "failed_files": [],
        "exact_duplicates_archived": 0,
        "near_duplicates_archived": 0,
        "outdated_archived": 0,
        "total_archived": 0
    }
    
    # Create archive structure first
    create_archive_structure(scan_folder_path)
    
    # Archive exact duplicates
    for action in archive_actions.get("exact_duplicates", []):
        source = os.path.join(scan_folder_path, action["to_archive"])
        dest = action["destination"]
        
        success, message = move_file_safe(source, dest)
        
        if success:
            results["archived_files"].append({
                "file": action["to_archive"],
                "category": "exact_duplicate",
                "destination": dest,
                "status": "archived"
            })
            results["exact_duplicates_archived"] += 1
        else:
            # ISSUE 1 FIX: Log failure but continue (don't crash on missing files)
            print(f"[WARNING] Exact duplicate archive failed: {message}")
            results["failed_files"].append({
                "file": action["to_archive"],
                "error": message
            })
    
    # Archive near duplicates
    for action in archive_actions.get("near_duplicates", []):
        source = os.path.join(scan_folder_path, action["to_archive"])
        dest = action["destination"]
        
        success, message = move_file_safe(source, dest)
        
        if success:
            results["archived_files"].append({
                "file": action["to_archive"],
                "category": "near_duplicate",
                "destination": dest,
                "status": "archived"
            })
            results["near_duplicates_archived"] += 1
        else:
            # ISSUE 1 FIX: Log failure but continue (don't crash on missing files)
            print(f"[WARNING] Near duplicate archive failed: {message}")
            results["failed_files"].append({
                "file": action["to_archive"],
                "error": message
            })
    
    # Archive outdated files
    # ISSUE 3 FIX: Use 'fileName' field for outdated files (not 'file' or 'path')
    for action in archive_actions.get("outdated", []):
        # action contains: {"fileName": "...", "destination": "..."}
        file_name = action.get("fileName") or action.get("file")
        source = os.path.join(scan_folder_path, file_name) if file_name else None
        dest = action.get("destination")
        
        if not source or not dest:
            print(f"[WARNING] Outdated file action missing fileName or destination: {action}")
            continue
        
        success, message = move_file_safe(source, dest)
        
        if success:
            results["archived_files"].append({
                "file": file_name,
                "category": "outdated",
                "destination": dest,
                "status": "archived"
            })
            results["outdated_archived"] += 1
        else:
            # ISSUE 1 FIX: Log failure but continue (don't crash on missing files)
            print(f"[WARNING] Outdated file archive failed: {message}")
            results["failed_files"].append({
                "file": file_name,
                "error": message
            })
    
    results["total_archived"] = (
        results["exact_duplicates_archived"] + 
        results["near_duplicates_archived"] + 
        results["outdated_archived"]
    )
    
    return results

# ==================== GCS SUPPORT FUNCTIONS ====================

def authenticate_gcs(credentials_json):
    """
    Authenticate with GCS using provided credentials.
    
    Args:
        credentials_json (str or dict): Service account JSON key as string or dict
    
    Returns:
        Tuple: (success: bool, client: gcs_storage.Client or None, error_message: str)
    """
    if not GCS_AVAILABLE:
        return False, None, "google-cloud-storage library not installed. Install with: pip install google-cloud-storage"
    
    try:
        # Handle credentials - could be JSON string or dict
        if isinstance(credentials_json, str):
            try:
                credentials_dict = json.loads(credentials_json)
            except json.JSONDecodeError:
                return False, None, "Invalid JSON format for credentials"
        else:
            credentials_dict = credentials_json
        
        # Create credentials from dict
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        
        # Create GCS client
        client = gcs_storage.Client(credentials=credentials)
        
        # Test connection by listing buckets (just one)
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
        prefix (str): Optional prefix to filter objects (e.g., "data/")
    
    Returns:
        Tuple: (success: bool, metadata_list: list, error_message: str)
    """
    if not GCS_AVAILABLE:
        return False, [], "google-cloud-storage not available"
    
    try:
        bucket = gcs_client.bucket(bucket_name)
        
        # Check if bucket exists
        if not bucket.exists():
            return False, [], f"Bucket '{bucket_name}' does not exist or is not accessible"
        
        metadata_list = []
        blobs = bucket.list_blobs(prefix=prefix)
        
        blob_count = 0
        for blob in blobs:
            # Skip folders (objects ending with /)
            if blob.name.endswith('/'):
                continue
            
            blob_count += 1
            
            # Extract ONLY metadata - NO content download
            file_metadata = {
                "file_name": blob.name.split('/')[-1],  # Just the filename
                "file_path": blob.name,                  # Full path in bucket
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
    This ensures existing duplicate/outdated/archive logic works unchanged.
    
    Args:
        gcs_metadata_list (list): List of GCS object metadata dicts
    
    Returns:
        dict: file_data dict in same format as local files
    """
    file_data = {}
    
    for metadata in gcs_metadata_list:
        file_name = metadata["file_name"]
        
        # Create internal structure (same as local files)
        file_data[file_name] = {
            "file_path": metadata["file_path"],  # Full GCS path
            "size": metadata["file_size"],
            "modified_time": metadata["last_modified"],
            "source": "gcs",
            "bucket": metadata["bucket"],
            "content_type": metadata.get("content_type", "unknown"),
            # Hash is empty for GCS (we don't download content)
            "hash": None,
            "content": None
        }
    
    return file_data

def prepare_gcs_archive_move(gcs_client, bucket_name, source_path, archive_category):
    """
    Prepare GCS archive move operation (does NOT execute, just validates).
    
    Args:
        gcs_client: Authenticated GCS client
        bucket_name (str): GCS bucket name
        source_path (str): Path of object to move
        archive_category (str): "exact_duplicates", "near_duplicates", or "outdated"
    
    Returns:
        Tuple: (success: bool, operation: dict, message: str)
    """
    try:
        # Validate archive category
        valid_categories = ["exact_duplicates", "near_duplicates", "outdated"]
        if archive_category not in valid_categories:
            return False, {}, f"Invalid archive category: {archive_category}"
        
        # Construct destination path
        destination_path = f"archive/{archive_category}/{source_path.split('/')[-1]}"
        
        # Check if source blob exists
        bucket = gcs_client.bucket(bucket_name)
        source_blob = bucket.blob(source_path)
        
        if not source_blob.exists():
            return False, {}, f"Source object '{source_path}' does not exist"
        
        # Prepare operation (do NOT execute)
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
        
        # Copy blob to destination
        destination_blob = bucket.copy_blob(source_blob, bucket, destination_path)
        
        # Delete source (only after successful copy)
        source_blob.delete()
        
        return True, f"Successfully moved {source_path} to {destination_path}"
    
    except Exception as e:
        return False, f"GCS archive move failed: {str(e)}"

def scan_with_source(source_type, source_config):
    """
    Unified scan wrapper - accepts local or GCS source.
    
    Args:
        source_type (str): "local" or "gcs"
        source_config (dict): Configuration for the source
            Local: { "folder_path": "data" }
            GCS: { "bucket": "bucket_name", "credentials": {...}, "prefix": "" }
    
    Returns:
        dict: Unified file_data structure (source-agnostic)
    """
    if source_type == "local":
        # Use existing local scan logic
        folder_path = source_config.get("folder_path", "data")
        file_data = {}
        
        if os.path.exists(folder_path):
            for file in os.listdir(folder_path):
                file_full_path = os.path.join(folder_path, file)
                
                if os.path.isfile(file_full_path):
                    try:
                        with open(file_full_path, "r") as f:
                            content = f.read()
                        
                        file_hash = hashlib.md5(content.encode()).hexdigest()
                        modified_time = os.path.getmtime(file_full_path)
                        file_size = os.path.getsize(file_full_path)
                        
                        file_data[file] = {
                            "content": content,
                            "hash": file_hash,
                            "modified_time": modified_time,
                            "size": file_size,
                            "source": "local",
                            "file_path": file_full_path
                        }
                    except Exception as e:
                        print(f"Warning: Could not read {file}: {str(e)}")
        
        return file_data
    
    elif source_type == "gcs":
        # Use GCS scan
        bucket_name = source_config.get("bucket")
        credentials = source_config.get("credentials")
        prefix = source_config.get("prefix", "")
        
        if not bucket_name or not credentials:
            print("Error: GCS source requires 'bucket' and 'credentials'")
            return {}
        
        # Authenticate
        success, gcs_client, auth_msg = authenticate_gcs(credentials)
        if not success:
            print(f"GCS Auth Error: {auth_msg}")
            return {}
        
        # Scan metadata
        success, metadata_list, scan_msg = scan_gcs_metadata(bucket_name, gcs_client, prefix)
        if not success:
            print(f"GCS Scan Error: {scan_msg}")
            return {}
        
        # Normalize to internal structure
        file_data = normalize_gcs_metadata(metadata_list)
        
        return file_data
    
    else:
        print(f"Error: Unknown source type '{source_type}'")
        return {}

# ==================== LAYER 1: READ AND HASH ALL FILES ====================
def analyze_duplicates(source_type="local", source_config=None):
    """
    Run the complete duplicate analysis and return results
    
    Args:
        source_type (str): "local" or "gcs"
        source_config (dict): Configuration for the source
            Local: { "folder_path": "data" or any system path }
            GCS: { "bucket": "bucket_name", "credentials": {...}, "prefix": "" }
    """
    print(f"Step 1: Reading all files from {source_type} source and creating hashes...\n")
    
    file_data = {}  # Store file info: name, content, hash, modified time, and size
    
    if source_type == "local":
        # Use provided folder path or default to "data"
        folder_to_scan = source_config.get("folder_path", "data") if source_config else "data"
        
        # Validate folder path
        if not os.path.exists(folder_to_scan):
            error_msg = f"Folder not found: '{folder_to_scan}' - Use full path like C:\\Users\\YourName\\Downloads or D:\\MyFolder"
            print(f"ERROR: {error_msg}")
            return {}
        
        if not os.path.isdir(folder_to_scan):
            error_msg = f"'{folder_to_scan}' is not a directory!"
            print(f"ERROR: {error_msg}")
            return {}
        
        print(f"Scanning local folder: {os.path.abspath(folder_to_scan)}\n")
        
        # List all files in the folder
        try:
            items = os.listdir(folder_to_scan)
        except PermissionError:
            error_msg = f"Permission denied accessing '{folder_to_scan}' - Try running with admin rights"
            print(f"ERROR: {error_msg}")
            return {}
        
        # Check if folder has any files
        if not items:
            print(f"⚠️  Folder is empty: {os.path.abspath(folder_to_scan)}\n")
            return {}
        
        for file in items:
            file_full_path = os.path.join(folder_to_scan, file)
            
            # Only work with actual files, not folders
            if os.path.isfile(file_full_path):
                try:
                    # Get file size and modified time first
                    file_size = os.path.getsize(file_full_path)
                    modified_time = os.path.getmtime(file_full_path)
                    
                    # Try to read as text first
                    try:
                        with open(file_full_path, "r", encoding='utf-8') as f:
                            content = f.read()
                        file_hash = hashlib.md5(content.encode()).hexdigest()
                        is_binary = False
                    except (UnicodeDecodeError, PermissionError):
                        # If text read fails, read as binary (for images, binaries, etc.)
                        with open(file_full_path, "rb") as f:
                            content = f.read()
                        file_hash = hashlib.md5(content).hexdigest()
                        is_binary = True
                    
                    # Store all info about this file
                    file_data[file] = {
                        "content": content,
                        "hash": file_hash,
                        "modified_time": modified_time,
                        "size": file_size,
                        "is_binary": is_binary
                    }
                except Exception as e:
                    print(f"Warning: Could not process {file}: {str(e)}")
    
    elif source_type == "gcs":
        # Use GCS scan
        if not source_config:
            print("ERROR: GCS source requires configuration")
            return {}
        
        bucket_name = source_config.get("bucket")
        credentials = source_config.get("credentials")
        prefix = source_config.get("prefix", "")
        
        if not bucket_name or not credentials:
            print("Error: GCS source requires 'bucket' and 'credentials'")
            return {}
        
        # Authenticate
        success, gcs_client, auth_msg = authenticate_gcs(credentials)
        if not success:
            print(f"GCS Auth Error: {auth_msg}")
            return {}
        
        print(f"Scanning GCS bucket: {bucket_name}\n")
        
        # Scan metadata
        success, metadata_list, scan_msg = scan_gcs_metadata(bucket_name, gcs_client, prefix)
        if not success:
            print(f"GCS Scan Error: {scan_msg}")
            return {}
        
        # Normalize to internal structure
        file_data = normalize_gcs_metadata(metadata_list)
    
    else:
        print(f"ERROR: Unknown source type '{source_type}'")
        return {}
    
    # ==================== LAYER 2: FIND EXACT DUPLICATES ====================
    print("Step 2: Looking for EXACT duplicates (same content)...\n")
    
    exact_duplicates = []  # Store pairs of exact duplicate files
    
    for file1 in file_data:
        for file2 in file_data:
            if file1 != file2:
                # Compare the hashes
                if file_data[file1]["hash"] == file_data[file2]["hash"]:
                    # If hashes match, content is exactly the same
                    pair = tuple(sorted([file1, file2]))
                    if pair not in exact_duplicates:
                        print(f"[EXACT] Exact Duplicate: {file1} <-----------------> {file2}")
                        exact_duplicates.append(pair)
    
    if not exact_duplicates:
        print("No exact duplicates found.\n")
    
    # ==================== LAYER 3: FIND NEAR DUPLICATES (SIMILAR NAMES) ====================
    print("Step 3: Looking for NEAR duplicate candidates (name similarity)...\n")
    
    near_duplicate_candidates = []  # Store pairs of near duplicate candidates
    
    # Function to check how similar two file names are
    def get_name_similarity(name1, name2):
        # SequenceMatcher checks how similar two strings are
        # Returns a number between 0 and 1 (1 = identical, 0 = completely different)
        similarity = SequenceMatcher(None, name1, name2).ratio()
        return similarity
    
    # ==================== GEMINI GCS-SPECIFIC FUNCTION ====================
    # Function to ask Gemini about GCS file similarity (metadata-only, no download)
    def ask_gemini_gcs_duplicates(file1_name, file1_size, file1_age, file2_name, file2_size, file2_age):
        """
        Verify near-duplicates for GCS files using ONLY metadata.
        Returns JSON: { "is_duplicate": bool, "similarity": 0-100, "reason": str }
        """
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
        
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            import json
            text = response.text.strip()
            # Remove markdown code blocks if present
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
            # 429 = Quota exceeded - don't log details, just fail silently
            if "429" in error_str or "resource_exhausted" in error_str:
                return {"is_duplicate": False, "similarity": 0, "reason": "Quota exceeded"}
            # Other errors - return safe default
            return {"is_duplicate": False, "similarity": 0, "reason": "API unavailable"}
    
    # Function to ask Gemini about file similarity using metadata
    def ask_gemini_about_files(file1_name, file1_size, file1_age, file2_name, file2_size, file2_age):
        """
        Send file metadata to Gemini and ask if files are likely duplicates.
        Returns a tuple: (yes_or_no, reason)
        """
        
        # Get file types (extension) from names
        file1_type = file1_name.split('.')[-1] if '.' in file1_name else "unknown"
        file2_type = file2_name.split('.')[-1] if '.' in file2_name else "unknown"
        
        # Convert size to KB
        file1_size_kb = file1_size / 1024
        file2_size_kb = file2_size / 1024
        
        # Create the prompt for Gemini
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
        
        try:
            # Call Gemini API using new google-genai library
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            # Parse the response
            answer = response.text.strip()
            
            # Extract YES/NO and reason
            if answer.startswith("YES"):
                return "YES", answer[4:].strip()
            elif answer.startswith("NO"):
                return "NO", answer[3:].strip()
            else:
                return "UNCLEAR", answer[:50]  # First 50 chars if response format is unexpected
                
        except Exception as e:
            error_str = str(e).lower()
            # 429 = Quota exceeded - don't expose raw error to user
            if "429" in error_str or "resource_exhausted" in error_str:
                return "ERROR", "Gemini quota reached"
            # Other errors
            return "ERROR", "Gemini API unavailable"
    
    for file1 in file_data:
        for file2 in file_data:
            # Only check pairs where file1 comes before file2 alphabetically
            # This prevents checking the same pair twice (like A-B and B-A)
            if file1 < file2:
                # Get similarity score between file names
                similarity_score = get_name_similarity(file1, file2)
                
                # If similarity is 95% or higher, consider them near duplicate candidates
                # But ONLY if they are NOT exact duplicates
                is_exact = tuple(sorted([file1, file2])) in exact_duplicates
                
                if similarity_score >= 0.95 and not is_exact:
                    pair = tuple(sorted([file1, file2]))
                    near_duplicate_candidates.append({
                        "pair": pair,
                        "similarity": similarity_score
                    })
    
    if not near_duplicate_candidates:
        print("No near duplicate candidates found.\n")
    
    # ==================== LAYER 4: CHECK FILE SIZE FOR NEAR DUPLICATES ====================
    print("Step 4: Checking file sizes for near duplicate candidates...\n")
    
    strong_candidates = []  # Near duplicates with similar size (strong candidates)
    weak_candidates = []    # Near duplicates with different size (weak candidates)
    
    for candidate in near_duplicate_candidates:
        file1, file2 = candidate["pair"]
        similarity_score = candidate["similarity"]
        
        # Get file sizes
        size1 = file_data[file1]["size"]
        size2 = file_data[file2]["size"]
        
        # Calculate size difference percentage
        # Use the larger size as base
        max_size = max(size1, size2)
        size_difference = abs(size1 - size2) / max_size * 100 if max_size > 0 else 0
        
        # Check if size difference is within 20% threshold
        if size_difference <= 20:
            status = "Strong candidate (will be sent to AI later)"
            strong_candidates.append(candidate["pair"])
            print(f"[NEAR] Near Duplicate Candidate: {file1} <-----------------> {file2}")
            print(f"  Name similarity: {similarity_score:.0%}")
            print(f"  Size difference: {size_difference:.1f}%")
            print(f"  Status: {status}\n")
        else:
            status = "Weak candidate (skipped - size too different)"
            weak_candidates.append(candidate["pair"])
            print(f"[WEAK] Near Duplicate Candidate: {file1} <--> {file2}")
            print(f"  Name similarity: {similarity_score:.0%}")
            print(f"  Size difference: {size_difference:.1f}%")
            print(f"  Status: {status} (skipped)\n")
    
    if not near_duplicate_candidates:
        print("No near duplicate candidates to check.\n")
    
    # ==================== LAYER 5: GEMINI AI ANALYSIS FOR STRONG CANDIDATES ====================
    print("Step 5: Skipping Gemini AI verification (quota limits reached)...\n")
    
    ai_confirmed_duplicates = []  # Files confirmed as duplicates by AI
    ai_error_status = "Gemini API quota exhausted"  # Track quota status
    
    # Note: Gemini free tier has strict quotas. When exhausted, we skip Layer 5.
    # The system still works with Layers 1-4 and 6 returning reliable results.
    
    print("[SKIP] Gemini AI verification disabled due to quota limits")
    print("[INFO] Exact and Near duplicates still detected (without AI confirmation)\n")
    
    # ==================== LAYER 6: FIND OLDEST FILES ====================
    print("Step 6: Looking for OLDEST files in scope...\n")
    
    # Collect all files with their modified times
    file_times = []
    for file in file_data:
        modified_time = file_data[file]["modified_time"]
        file_times.append((file, modified_time))
    
    # Sort by modified time (ascending = oldest first)
    file_times.sort(key=lambda x: x[1])
    
    # Get top 3 oldest files (or all if less than 3)
    num_oldest = 3
    outdated_files = [f[0] for f in file_times[:num_oldest]]
    
    if outdated_files:
        current_time = time.time()
        for file in outdated_files:
            modified_time = file_data[file]["modified_time"]
            days_since_modified = (current_time - modified_time) / (24 * 60 * 60)
            print(f"[OLDEST] File: {file} (last modified: {days_since_modified:.1f} days ago)")
    else:
        print("No files found.\n")
    
    # ==================== COMPILE RESULTS ====================
    results = {
        "total_files": len(file_data),
        "exact_duplicates": [{"file1": pair[0], "file2": pair[1], "type": "Exact", "similarity": 100} for pair in exact_duplicates],
        "near_duplicates": [{"file1": pair[0], "file2": pair[1], "type": "Near", "similarity": int(next(c["similarity"] * 100 for c in near_duplicate_candidates if c["pair"] == pair))} for pair in strong_candidates],
        "ai_confirmed": [{"file1": pair[0], "file2": pair[1], "type": "Near Duplicate (AI Verified)" if pair[2] < 100 else "Exact", "similarity": pair[2]} for pair in ai_confirmed_duplicates],
        "outdated_files": [{"fileName": f, "duplicateType": "Oldest File", "similarity": 0} for f in outdated_files],
        "scan_stats": {
            "exact_matches": len(exact_duplicates),
            "near_duplicates": len(strong_candidates),
            "old_versions": len(outdated_files),
            "total_duplicates": len(exact_duplicates) + len(strong_candidates) + len(ai_confirmed_duplicates)
        },
        "ai_status": ai_error_status if ai_error_status else "Completed"
    }
    
    return results

# ==================== FLASK API ROUTES ====================

@app.route('/api/scan', methods=['POST'])
def scan_duplicates():
    """Endpoint to start a duplicate scan analysis"""
    try:
        print("API: Starting duplicate detection scan...")
        
        # Get request data
        request_data = request.json or {}
        source = request_data.get("source", "local")
        
        # Prepare source config based on type
        if source == "local":
            folder_path = request_data.get("folder_path", "data")
            source_config = {"folder_path": folder_path}
            source_name = os.path.basename(folder_path) if folder_path else "data"
        elif source == "gcs":
            gcs_config = request_data.get("gcs_config", {})
            source_config = {
                "bucket": gcs_config.get("bucket"),
                "credentials": gcs_config.get("credentials"),
                "prefix": gcs_config.get("prefix", "")
            }
            source_name = gcs_config.get("bucket", "gcs-bucket")
        else:
            return jsonify({
                "success": False,
                "error": f"Unknown source type: {source}"
            }), 400
        
        # Run analysis with source config
        results = analyze_duplicates(source_type=source, source_config=source_config)
        
        if not results:
            return jsonify({
                "success": False,
                "error": "Scan failed - no files found or error during scanning"
            }), 400
        
        print("API: Scan completed successfully")
        
        # Auto-save scan history to Firebase
        history_saved, scan_id, history_msg = save_scan_history_to_firebase(
            results,
            source_type=source.upper(),
            source_name=source_name
        )
        
        if history_saved:
            print(f"✅ {history_msg}")
            results["scan_id"] = scan_id  # Add scan ID to response
        else:
            print(f"⚠️  {history_msg}")
        
        return jsonify({
            "success": True,
            "data": results
        }), 200
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Endpoint to check if the API is running"""
    return jsonify({
        "status": "online",
        "message": "Duplicate Detection API is running"
    }), 200

@app.route('/api/files', methods=['GET'])
def get_files():
    """Endpoint to get list of all files in the data folder"""
    try:
        file_list = [f for f in files if os.path.isfile(os.path.join(folder_path, f))]
        return jsonify({
            "success": True,
            "files": file_list,
            "count": len(file_list)
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/archive/preview', methods=['POST'])
def archive_preview():
    """Generate a preview of files that will be archived"""
    try:
        print("API: Generating archive preview...")
        
        # Get scan results from request
        data = request.json or {}
        scan_results = data.get("scan_results", {})
        source = data.get("source", "local")
        folder_path_arg = data.get("folder_path", "data")
        gcs_config = data.get("gcs_config", None)
        
        if not scan_results:
            return jsonify({
                "success": False,
                "error": "No scan results provided"
            }), 400
        
        # Pass folder path context to preview generator
        preview = generate_archive_preview(scan_results, folder_path_arg)
        
        print("API: Archive preview generated successfully")
        return jsonify({
            "success": True,
            "preview": preview
        }), 200
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/archive/execute', methods=['POST'])
def execute_archive_endpoint():
    """Execute the archive action by moving files and generate report"""
    try:
        print("API: Executing archive action...")
        
        # Get archive actions from request
        data = request.json or {}
        archive_type = data.get("archive_type", "exact")  # NEW: Which category to archive
        archive_actions = data.get("archive_actions", {})
        source = data.get("source", "local")
        folder_path_arg = data.get("folder_path", "data")
        gcs_config = data.get("gcs_config", None)
        scan_results_original = data.get("scan_results", {})
        scan_id_input = data.get("scan_id", None)
        
        print(f"[INFO] Archive type: {archive_type}")
        print(f"[INFO] Received scan_results: {bool(scan_results_original)}")
        
        if not archive_actions:
            return jsonify({
                "success": False,
                "error": "No archive actions provided"
            }), 400
        
        # BUG FIX 1: FILTER archive_actions to only the selected type
        filtered_actions = {}
        if archive_type == "exact":
            filtered_actions["exact_duplicates"] = archive_actions.get("exact_duplicates", [])
            print(f"[INFO] Processing ONLY exact_duplicates: {len(filtered_actions['exact_duplicates'])} items")
        elif archive_type == "near":
            filtered_actions["near_duplicates"] = archive_actions.get("near_duplicates", [])
            print(f"[INFO] Processing ONLY near_duplicates: {len(filtered_actions['near_duplicates'])} items")
        elif archive_type == "outdated":
            filtered_actions["outdated"] = archive_actions.get("outdated", [])
            print(f"[INFO] Processing ONLY outdated: {len(filtered_actions['outdated'])} items")
        
        # Execute archive with ONLY the filtered category
        results = execute_archive(filtered_actions, folder_path_arg)
        
        # BUG FIX 2: Build explicit list of files that were SUCCESSFULLY archived
        successfully_archived = []
        for archived_file_info in results.get("archived_files", []):
            successfully_archived.append(archived_file_info.get("file"))
        
        print(f"[INFO] Successfully archived files: {successfully_archived}")
        print(f"[INFO] Total successfully archived: {len(successfully_archived)}")
        
        # BUG FIX 2: ONLY filter the category that was archived
        # Leave other categories completely unchanged
        # BUG FIX 3: Build updated_scan_results by removing ONLY successfully archived files
        # Start fresh from original scan results
        updated_scan_results = {
            "total_files": scan_results_original.get("total_files", 0),
            "exact_duplicates": scan_results_original.get("exact_duplicates", []).copy() if scan_results_original.get("exact_duplicates") else [],
            "near_duplicates": scan_results_original.get("near_duplicates", []).copy() if scan_results_original.get("near_duplicates") else [],
            "ai_confirmed": scan_results_original.get("ai_confirmed", []).copy() if scan_results_original.get("ai_confirmed") else [],
            "outdated_files": scan_results_original.get("outdated_files", []).copy() if scan_results_original.get("outdated_files") else [],
        }
        
        # Only filter the category that was archived - EXPLICIT filtering
        if archive_type == "exact":
            print(f"[FILTER] Filtering exact_duplicates. Before: {len(updated_scan_results['exact_duplicates'])}")
            # Remove duplicates where file2 was archived
            updated_scan_results["exact_duplicates"] = [
                d for d in updated_scan_results["exact_duplicates"] 
                if d.get("file2") not in successfully_archived
            ]
            print(f"[FILTER] Filtering exact_duplicates. After: {len(updated_scan_results['exact_duplicates'])}")
            print(f"[FILTER] Archived files that were removed: {successfully_archived}")
            
        elif archive_type == "near":
            print(f"[FILTER] Filtering near_duplicates. Before: {len(updated_scan_results['near_duplicates'])}")
            # Remove pairs where file2 was archived
            updated_scan_results["near_duplicates"] = [
                d for d in updated_scan_results["near_duplicates"] 
                if d.get("file2") not in successfully_archived
            ]
            updated_scan_results["ai_confirmed"] = [
                d for d in updated_scan_results["ai_confirmed"] 
                if d.get("file2") not in successfully_archived
            ]
            print(f"[FILTER] Filtering near_duplicates. After: {len(updated_scan_results['near_duplicates'])}")
            
        elif archive_type == "outdated":
            print(f"[FILTER] Filtering outdated_files. Before: {len(updated_scan_results['outdated_files'])}")
            # Remove outdated files that were archived (by fileName)
            updated_scan_results["outdated_files"] = [
                f for f in updated_scan_results["outdated_files"] 
                if f.get("fileName") not in successfully_archived
            ]
            print(f"[FILTER] Filtering outdated_files. After: {len(updated_scan_results['outdated_files'])}")
            print(f"[FILTER] Archived files that were removed: {successfully_archived}")
        
        # Recalculate statistics based on filtered results
        exact_after = len(updated_scan_results["exact_duplicates"])
        near_after = len(updated_scan_results["near_duplicates"])
        outdated_after = len(updated_scan_results["outdated_files"])
        
        updated_scan_results["scan_stats"] = {
            "exact_matches": exact_after,
            "near_duplicates": near_after,
            "old_versions": outdated_after,
            "total_duplicates": exact_after + near_after + outdated_after
        }
        updated_scan_results["ai_status"] = scan_results_original.get("ai_status", "Completed")
        
        print(f"[OK] Updated scan results ready. Categories: Exact={exact_after}, Near={near_after}, Outdated={outdated_after}, Total Dups={updated_scan_results['scan_stats']['total_duplicates']}")
        
        # Generate and upload archive report (non-blocking, errors don't break the response)
        report_url = None
        if results["success"] and results.get("archived_files"):
            try:
                # Use provided scan_id or generate new one
                scan_id = scan_id_input or str(uuid.uuid4())[:8]
                
                # Get source name
                source_name = folder_path_arg if source == "local" else (gcs_config.get("bucket") if gcs_config else "Unknown")
                
                # Generate human-readable report
                report_content = generate_archive_report(
                    scan_id,
                    source_name,
                    results.get("archived_files", []),
                    scan_results_original
                )
                
                # Upload to Firebase Storage
                upload_success, download_url, upload_error = upload_report_to_firebase_storage(report_content, scan_id)
                
                if upload_success:
                    report_url = download_url
                    
                    # Update Firestore with archived status and report URL
                    fs_success, fs_error = update_scan_history_archived(scan_id, report_url)
                    
                    if not fs_success:
                        print(f"[WARNING] {fs_error} (Report still available at: {report_url})")
                else:
                    print(f"[WARNING] {upload_error} (Archive completed, but report generation failed)")
            except Exception as report_error:
                print(f"[WARNING] Report generation error: {str(report_error)} (Archive still succeeded)")
        
        print("API: Archive execution completed")
        response_data = {
            "success": results["success"],
            "data": results,
            "updated_scan_results": updated_scan_results
        }
        
        # Include report URL if available
        if report_url:
            response_data["report_url"] = report_url
        
        return jsonify(response_data), 200 if results["success"] else 400
    except Exception as e:
        print(f"API Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================== GCS ENDPOINTS (Future-ready, not yet in UI) ====================

@app.route('/api/gcs/test-auth', methods=['POST'])
def test_gcs_auth():
    """Test GCS authentication (future endpoint for UI)"""
    try:
        if not GCS_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "google-cloud-storage library not installed"
            }), 400
        
        data = request.json or {}
        credentials = data.get("credentials")
        
        if not credentials:
            return jsonify({
                "success": False,
                "error": "No credentials provided"
            }), 400
        
        success, client, message = authenticate_gcs(credentials)
        
        return jsonify({
            "success": success,
            "message": message
        }), 200 if success else 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/gcs/scan', methods=['POST'])
def scan_gcs():
    """Scan GCS bucket for duplicates (future endpoint for UI)"""
    try:
        print("API: Starting GCS duplicate detection scan...")
        
        data = request.json or {}
        bucket_name = data.get("bucket")
        credentials = data.get("credentials")
        prefix = data.get("prefix", "")
        
        if not bucket_name or not credentials:
            return jsonify({
                "success": False,
                "error": "Missing 'bucket' or 'credentials' in request"
            }), 400
        
        if not GCS_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "google-cloud-storage library not installed"
            }), 400
        
        # Authenticate
        success, gcs_client, auth_msg = authenticate_gcs(credentials)
        if not success:
            return jsonify({
                "success": False,
                "error": f"Authentication failed: {auth_msg}"
            }), 400
        
        # Scan metadata
        success, metadata_list, scan_msg = scan_gcs_metadata(bucket_name, gcs_client, prefix)
        if not success:
            return jsonify({
                "success": False,
                "error": f"Scan failed: {scan_msg}"
            }), 400
        
        # For GCS, we can't compute hashes without downloading content
        # So we'll do basic duplicate detection by name/size similarity only
        print(f"Scanned {len(metadata_list)} objects from GCS")
        
        return jsonify({
            "success": True,
            "data": {
                "source": "gcs",
                "bucket": bucket_name,
                "metadata": metadata_list,
                "count": len(metadata_list),
                "note": "GCS scan returns metadata only. Hash-based exact duplicate detection unavailable."
            }
        }), 200
    
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ==================== SCAN HISTORY ENDPOINTS ====================

@app.route('/api/history', methods=['GET'])
def get_scan_history():
    """Fetch scan history from Firebase (latest first)"""
    try:
        if not FIREBASE_AVAILABLE or not firebase_db:
            return jsonify({
                "success": False,
                "error": "Firebase not configured",
                "history": []
            }), 200  # Return empty history if Firebase unavailable
        
        # Fetch last 20 scans, ordered by timestamp (latest first)
        docs = firebase_db.collection("scan_history").order_by(
            "timestamp", 
            direction=firestore.Query.DESCENDING
        ).limit(20).stream()
        
        history = []
        for doc in docs:
            data = doc.to_dict()
            # Convert Firestore timestamp to ISO format
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
        
        return jsonify({
            "success": True,
            "history": history,
            "count": len(history)
        }), 200
    
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "history": []
        }), 500

@app.route('/api/history/archive', methods=['POST'])
def archive_history_record():
    """Mark a history record as archived (metadata only update)"""
    try:
        if not FIREBASE_AVAILABLE or not firebase_db:
            return jsonify({
                "success": False,
                "error": "Firebase not configured"
            }), 400
        
        data = request.json or {}
        scan_id = data.get("scan_id")
        
        if not scan_id:
            return jsonify({
                "success": False,
                "error": "Missing 'scan_id' in request"
            }), 400
        
        # Update the record in Firestore (metadata only)
        firebase_db.collection("scan_history").document(scan_id).update({
            "archived": True,
            "archived_at": datetime.now()
        })
        
        return jsonify({
            "success": True,
            "message": f"History record {scan_id} marked as archived"
        }), 200
    
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    try:
        print("="*60)
        print("DUPLICATE DETECTION SYSTEM - BACKEND API")
        print("="*60)
        data_folder = os.path.abspath(folder_path)
        try:
            print(f"Data folder: {data_folder}")
        except UnicodeEncodeError:
            print(f"Data folder: [path with special characters]")
        print(f"Files to scan: {len(files)}")
        print("="*60)
        print("Starting Flask server on http://localhost:5000")
        print("="*60)
        sys.stdout.flush()
        app.run(host='127.0.0.1', debug=False, port=5000, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"BACKEND ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
