import json
import os
import random
import datetime
from typing import List, Dict, Optional

RECOMMENDATION_STORE = "recommendations.json"
INTERACTION_LOG = "recommendation_interactions.json"

def _load_store():
    if not os.path.exists(RECOMMENDATION_STORE):
        return {"dismissed": [], "completed": []}
    try:
        with open(RECOMMENDATION_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[recommendation_engine] Failed to load store: {e}")
        return {"dismissed": [], "completed": []}

def _save_store(data):
    with open(RECOMMENDATION_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _log_interaction(recommendation_id: str, action: str):
    log_data = []
    if os.path.exists(INTERACTION_LOG):
        try:
            with open(INTERACTION_LOG, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[recommendation_engine] Failed to load interaction log: {e}")
            log_data = []
    
    log_data.append({
        "id": recommendation_id,
        "action": action,
        "timestamp": datetime.datetime.now().isoformat()
    })
    
    with open(INTERACTION_LOG, "w", encoding="utf-8") as f:
        json.dump(log_data[-1000:], f, indent=2, ensure_ascii=False)

def generate_recommendations(guild_stats: Optional[Dict] = None, 
                            has_backups: bool = False,
                            playlist_count: int = 0,
                            active_servers: int = 0) -> List[Dict]:
    """Generate personalized recommendations based on dashboard data"""
    store = _load_store()
    recommendations = []
    now = datetime.datetime.now()
    hour = now.hour
    
    # 1. Time-based mood recommendations
    if "mood_recommendation" not in store["dismissed"]:
        mood = None
        mood_icon = None
        mood_desc = None
        
        if 6 <= hour < 12:
            mood = "Morning Vibes"
            mood_icon = "fa-sun"
            mood_desc = "Recommended calm songs to start your day"
        elif 12 <= hour < 17:
            mood = "Afternoon Energy"
            mood_icon = "fa-bolt"
            mood_desc = "Upbeat songs to boost your productivity"
        elif 17 <= hour < 22:
            mood = "Evening Chill"
            mood_icon = "fa-moon"
            mood_desc = "Relaxing music to wind down after a long day"
        else:
            mood = "Night Relax"
            mood_icon = "fa-star"
            mood_desc = "Soft songs for the night time"
        
        recommendations.append({
            "id": "mood_recommendation",
            "type": "mood",
            "title": mood,
            "description": mood_desc,
            "icon": mood_icon,
            "color": "from-purple-500 to-pink-500",
            "action_text": "Try Mood",
            "priority": 1
        })
    
    # 2. Backup recommendation
    if not has_backups and "backup_reminder" not in store["dismissed"]:
        recommendations.append({
            "id": "backup_reminder",
            "type": "warning",
            "title": "Create First Backup",
            "description": "Secure your data by creating a backup now",
            "icon": "fa-box-archive",
            "color": "from-amber-500 to-orange-500",
            "action_text": "Create Backup",
            "priority": 2
        })
    
    # 3. Playlist recommendation
    if playlist_count == 0 and "playlist_tip" not in store["dismissed"]:
        recommendations.append({
            "id": "playlist_tip",
            "type": "tip",
            "title": "Try Playlist Feature",
            "description": "Save your favorite songs into playlists for quick access",
            "icon": "fa-list-music",
            "color": "from-teal-500 to-emerald-500",
            "action_text": "Learn More",
            "priority": 3
        })
    
    # 4. Feature recommendations
    feature_tips = [
        {
            "id": "filter_tip",
            "type": "feature",
            "title": "Audio Filter Feature",
            "description": "Try bass boost, nightcore effects, and more!",
            "icon": "fa-sliders",
            "color": "from-blue-500 to-cyan-500",
            "action_text": "View Features",
            "priority": 4
        },
        {
            "id": "lyrics_tip",
            "type": "feature",
            "title": "Find Lyrics",
            "description": "Get lyrics for currently playing song easily",
            "icon": "fa-book-open",
            "color": "from-rose-500 to-red-500",
            "action_text": "Try Now",
            "priority": 4
        },
        {
            "id": "control_panel_tip",
            "type": "feature",
            "title": "Control Panel",
            "description": "Use the control panel for easier music control",
            "icon": "fa-gamepad",
            "color": "from-indigo-500 to-purple-500",
            "action_text": "Activate",
            "priority": 4
        }
    ]
    
    for tip in feature_tips:
        if tip["id"] not in store["dismissed"]:
            recommendations.append(tip)
    
    # 5. Random inspiration tip
    inspiration_tips = [
        {
            "id": "inspire_collab",
            "type": "inspiration",
            "title": "Play Music Together",
            "description": "Invite friends to vote on skips and create playlists together!",
            "icon": "fa-users",
            "color": "from-green-500 to-teal-500",
            "priority": 5
        },
        {
            "id": "inspire_genre",
            "type": "inspiration",
            "title": "Explore New Genres",
            "description": "Try music from different genres for a new experience",
            "icon": "fa-compass",
            "color": "from-yellow-500 to-amber-500",
            "priority": 5
        }
    ]
    
    for tip in inspiration_tips:
        if tip["id"] not in store["dismissed"]:
            recommendations.append(tip)
    
    # Sort by priority
    recommendations.sort(key=lambda x: x["priority"])
    return recommendations[:6]  # Show max 6 recommendations

def dismiss_recommendation(recommendation_id: str):
    """Mark a recommendation as dismissed"""
    store = _load_store()
    if recommendation_id not in store["dismissed"]:
        store["dismissed"].append(recommendation_id)
        _save_store(store)
        _log_interaction(recommendation_id, "dismissed")
    return True

def complete_recommendation(recommendation_id: str):
    """Mark a recommendation as completed"""
    store = _load_store()
    if recommendation_id not in store["completed"]:
        store["completed"].append(recommendation_id)
        if recommendation_id not in store["dismissed"]:
            store["dismissed"].append(recommendation_id)
        _save_store(store)
        _log_interaction(recommendation_id, "completed")
    return True

def get_interaction_stats() -> Dict:
    """Get statistics about recommendation interactions"""
    if not os.path.exists(INTERACTION_LOG):
        return {"total": 0, "completed": 0, "dismissed": 0}
    
    try:
        with open(INTERACTION_LOG, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[recommendation_engine] Failed to load stats: {e}")
        return {"total": 0, "completed": 0, "dismissed": 0}
    
    completed = sum(1 for entry in log_data if entry["action"] == "completed")
    dismissed = sum(1 for entry in log_data if entry["action"] == "dismissed")
    
    return {
        "total": len(log_data),
        "completed": completed,
        "dismissed": dismissed
    }

def reset_recommendations():
    """Reset all recommendations (for testing)"""
    _save_store({"dismissed": [], "completed": []})
    return True
