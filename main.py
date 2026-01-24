"""
Data Analysis Tool - Duplicate Detection System
================================================
Main Flask API Server

This is the core backend that handles:
- File scanning & duplicate detection
- Archive operations
- Flask API endpoints

All Google Cloud integrations are in integration.py
"""

import os
import sys
import hashlib
from difflib import SequenceMatcher
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
import shutil
import json
from datetime import datetime
import uuid

# Import all Google integrations
from integration import (
    GEMINI_AVAILABLE, gemini_client,
    ask_gemini_about_files, ask_gemini_gcs_duplicates,
    FIREBASE_AVAILABLE, firebase_db, firebase_storage_bucket,
    save_scan_history_to_firebase, generate_archive_report,
    upload_report_to_firebase_storage, update_scan_history_archived,
    get_scan_history_from_firebase, archive_history_record,
    GCS_AVAILABLE,
    authenticate_gcs, scan_gcs_metadata, normalize_gcs_metadata,
    prepare_gcs_archive_move, execute_gcs_archive_move
)

# Handle Unicode/encoding issues on Windows
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception as e:
        pass

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Data folder path
folder_path = "data"

# Get a list of all files in the data folder
if os.path.exists(folder_path):
    files = os.listdir(folder_path)
else:
    files = []

# ==================== ARCHIVE HELPER FUNCTIONS ====================

def create_archive_structure(folder_path_arg="data"):
    """Create archive folder structure if it doesn't exist"""
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
        if not os.path.exists(source_path):
            return False, f"Source file does not exist: {source_path}"
        
        dest_dir = os.path.dirname(dest_path)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        shutil.move(source_path, dest_path)
        return True, f"Moved: {source_path} → {dest_path}"
    except Exception as e:
        return False, f"Failed to move {source_path}: {str(e)}"


def generate_archive_preview(scan_results, folder_path_arg="data"):
    """Generate a preview of files that will be archived without actually moving them"""
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
            
            if not os.path.exists(file1_path) or not os.path.exists(file2_path):
                print(f"[WARNING] Skipping exact duplicate pair - file not found: {file1} or {file2}")
                continue
            
            try:
                file1_mtime = os.path.getmtime(file1_path)
                file2_mtime = os.path.getmtime(file2_path)
            except Exception as e:
                print(f"[WARNING] Failed to get modification times: {e}")
                continue
            
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
            
            if not os.path.exists(file1_path) or not os.path.exists(file2_path):
                print(f"[WARNING] Skipping near duplicate pair - file not found: {file1} or {file2}")
                continue
            
            try:
                file1_mtime = os.path.getmtime(file1_path)
                file2_mtime = os.path.getmtime(file2_path)
            except Exception as e:
                print(f"[WARNING] Failed to get modification times: {e}")
                continue
            
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
    
    preview["storage_savings_mb"] = round(preview["storage_savings_mb"], 2)
    
    return preview


def execute_archive(archive_actions, folder_path_arg="data"):
    """Execute the archive action by moving files to their destinations"""
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
            print(f"[WARNING] Near duplicate archive failed: {message}")
            results["failed_files"].append({
                "file": action["to_archive"],
                "error": message
            })
    
    # Archive outdated files
    for action in archive_actions.get("outdated", []):
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


# ==================== DUPLICATE DETECTION CORE LOGIC ====================

def analyze_duplicates(source_type="local", source_config=None):
    """
    Run the complete duplicate analysis and return results
    
    Args:
        source_type (str): "local" or "gcs"
        source_config (dict): Configuration for the source
    """
    print(f"Step 1: Reading all files from {source_type} source and creating hashes...\n")
    
    file_data = {}
    
    if source_type == "local":
        folder_to_scan = source_config.get("folder_path", "data") if source_config else "data"
        
        if not os.path.exists(folder_to_scan):
            error_msg = f"Folder not found: '{folder_to_scan}'"
            print(f"ERROR: {error_msg}")
            return {}
        
        if not os.path.isdir(folder_to_scan):
            error_msg = f"'{folder_to_scan}' is not a directory!"
            print(f"ERROR: {error_msg}")
            return {}
        
        print(f"Scanning local folder: {os.path.abspath(folder_to_scan)}\n")
        
        try:
            items = os.listdir(folder_to_scan)
        except PermissionError:
            error_msg = f"Permission denied accessing '{folder_to_scan}'"
            print(f"ERROR: {error_msg}")
            return {}
        
        if not items:
            print(f"⚠️  Folder is empty: {os.path.abspath(folder_to_scan)}\n")
            return {}
        
        for file in items:
            file_full_path = os.path.join(folder_to_scan, file)
            
            if os.path.isfile(file_full_path):
                try:
                    file_size = os.path.getsize(file_full_path)
                    modified_time = os.path.getmtime(file_full_path)
                    
                    try:
                        with open(file_full_path, "r", encoding='utf-8') as f:
                            content = f.read()
                        file_hash = hashlib.md5(content.encode()).hexdigest()
                        is_binary = False
                    except (UnicodeDecodeError, PermissionError):
                        with open(file_full_path, "rb") as f:
                            content = f.read()
                        file_hash = hashlib.md5(content).hexdigest()
                        is_binary = True
                    
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
        if not source_config:
            print("ERROR: GCS source requires configuration")
            return {}
        
        bucket_name = source_config.get("bucket")
        credentials = source_config.get("credentials")
        prefix = source_config.get("prefix", "")
        
        if not bucket_name or not credentials:
            print("Error: GCS source requires 'bucket' and 'credentials'")
            return {}
        
        success, gcs_client, auth_msg = authenticate_gcs(credentials)
        if not success:
            print(f"GCS Auth Error: {auth_msg}")
            return {}
        
        print(f"Scanning GCS bucket: {bucket_name}\n")
        
        success, metadata_list, scan_msg = scan_gcs_metadata(bucket_name, gcs_client, prefix)
        if not success:
            print(f"GCS Scan Error: {scan_msg}")
            return {}
        
        file_data = normalize_gcs_metadata(metadata_list)
    
    else:
        print(f"ERROR: Unknown source type '{source_type}'")
        return {}
    
    # ==================== FIND EXACT DUPLICATES ====================
    print("Step 2: Looking for EXACT duplicates (same content)...\n")
    
    exact_duplicates = []
    
    for file1 in file_data:
        for file2 in file_data:
            if file1 != file2:
                if file_data[file1]["hash"] == file_data[file2]["hash"]:
                    pair = tuple(sorted([file1, file2]))
                    if pair not in exact_duplicates:
                        print(f"[EXACT] Exact Duplicate: {file1} <-----------------> {file2}")
                        exact_duplicates.append(pair)
    
    if not exact_duplicates:
        print("No exact duplicates found.\n")
    
    # ==================== FIND NEAR DUPLICATES ====================
    print("Step 3: Looking for NEAR duplicate candidates (name similarity)...\n")
    
    near_duplicate_candidates = []
    
    def get_name_similarity(name1, name2):
        similarity = SequenceMatcher(None, name1, name2).ratio()
        return similarity
    
    for file1 in file_data:
        for file2 in file_data:
            if file1 < file2:
                similarity_score = get_name_similarity(file1, file2)
                is_exact = tuple(sorted([file1, file2])) in exact_duplicates
                
                if similarity_score >= 0.95 and not is_exact:
                    pair = tuple(sorted([file1, file2]))
                    near_duplicate_candidates.append({
                        "pair": pair,
                        "similarity": similarity_score
                    })
    
    if not near_duplicate_candidates:
        print("No near duplicate candidates found.\n")
    
    # ==================== CHECK FILE SIZE FOR NEAR DUPLICATES ====================
    print("Step 4: Checking file sizes for near duplicate candidates...\n")
    
    strong_candidates = []
    weak_candidates = []
    
    for candidate in near_duplicate_candidates:
        file1, file2 = candidate["pair"]
        similarity_score = candidate["similarity"]
        
        size1 = file_data[file1]["size"]
        size2 = file_data[file2]["size"]
        
        max_size = max(size1, size2)
        size_difference = abs(size1 - size2) / max_size * 100 if max_size > 0 else 0
        
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
    
    # ==================== GEMINI AI ANALYSIS ====================
    print("Step 5: Skipping Gemini AI verification (quota limits reached)...\n")
    
    ai_confirmed_duplicates = []
    ai_error_status = "Gemini API quota exhausted"
    
    print("[SKIP] Gemini AI verification disabled due to quota limits")
    print("[INFO] Exact and Near duplicates still detected (without AI confirmation)\n")
    
    # ==================== FIND OLDEST FILES ====================
    print("Step 6: Looking for OLDEST files in scope...\n")
    
    file_times = []
    for file in file_data:
        modified_time = file_data[file]["modified_time"]
        file_times.append((file, modified_time))
    
    file_times.sort(key=lambda x: x[1])
    
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
        
        request_data = request.json or {}
        source = request_data.get("source", "local")
        
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
        
        results = analyze_duplicates(source_type=source, source_config=source_config)
        
        if not results:
            return jsonify({
                "success": False,
                "error": "Scan failed - no files found or error during scanning"
            }), 400
        
        print("API: Scan completed successfully")
        
        history_saved, scan_id, history_msg = save_scan_history_to_firebase(
            results,
            source_type=source.upper(),
            source_name=source_name
        )
        
        if history_saved:
            print(f"✅ {history_msg}")
            results["scan_id"] = scan_id
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
        
        data = request.json or {}
        scan_results = data.get("scan_results", {})
        folder_path_arg = data.get("folder_path", "data")
        
        if not scan_results:
            return jsonify({
                "success": False,
                "error": "No scan results provided"
            }), 400
        
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
        
        data = request.json or {}
        archive_type = data.get("archive_type", "exact")
        archive_actions = data.get("archive_actions", {})
        folder_path_arg = data.get("folder_path", "data")
        scan_results_original = data.get("scan_results", {})
        scan_id_input = data.get("scan_id", None)
        
        print(f"[INFO] Archive type: {archive_type}")
        
        if not archive_actions:
            return jsonify({
                "success": False,
                "error": "No archive actions provided"
            }), 400
        
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
        
        results = execute_archive(filtered_actions, folder_path_arg)
        
        successfully_archived = []
        for archived_file_info in results.get("archived_files", []):
            successfully_archived.append(archived_file_info.get("file"))
        
        print(f"[INFO] Successfully archived files: {successfully_archived}")
        
        updated_scan_results = {
            "total_files": scan_results_original.get("total_files", 0),
            "exact_duplicates": scan_results_original.get("exact_duplicates", []).copy() if scan_results_original.get("exact_duplicates") else [],
            "near_duplicates": scan_results_original.get("near_duplicates", []).copy() if scan_results_original.get("near_duplicates") else [],
            "ai_confirmed": scan_results_original.get("ai_confirmed", []).copy() if scan_results_original.get("ai_confirmed") else [],
            "outdated_files": scan_results_original.get("outdated_files", []).copy() if scan_results_original.get("outdated_files") else [],
        }
        
        if archive_type == "exact":
            print(f"[FILTER] Filtering exact_duplicates. Before: {len(updated_scan_results['exact_duplicates'])}")
            updated_scan_results["exact_duplicates"] = [
                d for d in updated_scan_results["exact_duplicates"] 
                if d.get("file2") not in successfully_archived
            ]
            print(f"[FILTER] Filtering exact_duplicates. After: {len(updated_scan_results['exact_duplicates'])}")
            
        elif archive_type == "near":
            print(f"[FILTER] Filtering near_duplicates. Before: {len(updated_scan_results['near_duplicates'])}")
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
            updated_scan_results["outdated_files"] = [
                f for f in updated_scan_results["outdated_files"] 
                if f.get("fileName") not in successfully_archived
            ]
            print(f"[FILTER] Filtering outdated_files. After: {len(updated_scan_results['outdated_files'])}")
        
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
        
        report_url = None
        if results["success"] and results.get("archived_files"):
            try:
                scan_id = scan_id_input or str(uuid.uuid4())[:8]
                source_name = folder_path_arg
                
                report_content = generate_archive_report(
                    scan_id,
                    source_name,
                    results.get("archived_files", []),
                    scan_results_original
                )
                
                upload_success, download_url, upload_error = upload_report_to_firebase_storage(report_content, scan_id)
                
                if upload_success:
                    report_url = download_url
                    fs_success, fs_error = update_scan_history_archived(scan_id, report_url)
                    if not fs_success:
                        print(f"[WARNING] {fs_error}")
                else:
                    print(f"[WARNING] {upload_error}")
            except Exception as report_error:
                print(f"[WARNING] Report generation error: {str(report_error)}")
        
        print("API: Archive execution completed")
        response_data = {
            "success": results["success"],
            "data": results,
            "updated_scan_results": updated_scan_results
        }
        
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


@app.route('/api/history', methods=['GET'])
def get_scan_history():
    """Fetch scan history from Firebase"""
    try:
        history = get_scan_history_from_firebase(limit=20)
        
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
def archive_history_endpoint():
    """Mark a history record as archived"""
    try:
        data = request.json or {}
        scan_id = data.get("scan_id")
        
        if not scan_id:
            return jsonify({
                "success": False,
                "error": "Missing 'scan_id' in request"
            }), 400
        
        success, message = archive_history_record(scan_id)
        
        return jsonify({
            "success": success,
            "message": message
        }), 200 if success else 400
    
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
