import json
import os
import time
from typing import Dict, Optional
import zipfile
import datetime

BACKUP_DIR = "backups"

def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

def create_backup() -> str:
    """Create a full backup of the bot data"""
    ensure_backup_dir()
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    files_to_backup = [
        "playlists.json",
        "stats.json",
        "panel_store.json", 
        "request_channel_store.json",
        "quality_store.json",
        "audit_log.json",
    ]
    
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files_to_backup:
            if os.path.exists(file):
                zipf.write(file, file)
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_path):
            # Include a README warning instead of the .env itself to avoid leaking secrets
            zipf.writestr(
                'RESTORE_README.txt',
                'Environment configuration (.env) is intentionally excluded from this backup.\n'
                'Restore your .env manually from a secure location.\n'
            )
    
    return backup_path

def list_backups() -> list:
    """List all available backups"""
    ensure_backup_dir()
    
    backups = []
    for filename in os.listdir(BACKUP_DIR):
        if filename.startswith("backup_") and filename.endswith(".zip"):
            filepath = os.path.join(BACKUP_DIR, filename)
            backups.append({
                "name": filename,
                "path": filepath,
                "size": os.path.getsize(filepath),
                "created": os.path.getctime(filepath)
            })
    
    backups.sort(key=lambda x: x["created"], reverse=True)
    return backups

def restore_backup(backup_name: str) -> bool:
    """Restore from a backup"""
    ensure_backup_dir()
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return False
    
    try:
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.extractall(".")
        return True
    except Exception as e:
        print(f"Error restoring backup: {e}")
        return False

def delete_backup(backup_name: str) -> bool:
    """Delete a backup file"""
    ensure_backup_dir()
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return False
    
    os.remove(backup_path)
    return True

def get_backup_info(backup_name: str) -> Optional[Dict]:
    """Get detailed info about a backup"""
    ensure_backup_dir()
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return None
    
    with zipfile.ZipFile(backup_path, 'r') as zipf:
        file_list = zipf.namelist()
    
    return {
        "name": backup_name,
        "path": backup_path,
        "size": os.path.getsize(backup_path),
        "created": os.path.getctime(backup_path),
        "files": file_list
    }
